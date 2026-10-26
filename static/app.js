const taskInput = document.getElementById('taskInput');
const runTaskBtn = document.getElementById('runTaskBtn');
const injectFailureToggle = document.getElementById('injectFailureToggle');
const taskStatus = document.getElementById('taskStatus');
const taskSummary = document.getElementById('taskSummary');
const executionTimeline = document.getElementById('executionTimeline');
const toolObservations = document.getElementById('toolObservations');
const evidencePanel = document.getElementById('evidencePanel');
const approvalList = document.getElementById('approvalList');
const runHistory = document.getElementById('runHistory');
const ledgerTable = document.getElementById('ledgerTable');
const kpiCards = document.getElementById('kpiCards');
const overdueTable = document.getElementById('overdueTable');
const planList = document.getElementById('planList');
const ledgerSearch = document.getElementById('ledgerSearch');

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || 'Request failed');
  }
  return response.headers.get('content-type')?.includes('application/json') ? response.json() : null;
}

function setStatus(key, text) {
  taskStatus.className = `status-pill ${key}`;
  taskStatus.textContent = text;
}

function setPlan(items) {
  planList.innerHTML = '';
  (items || []).forEach((item) => {
    const li = document.createElement('li');
    li.textContent = item;
    planList.appendChild(li);
  });
}

function renderTimeline(events) {
  executionTimeline.innerHTML = '';
  if (!events || !events.length) {
    executionTimeline.innerHTML = '<div class="timeline-item"><strong>No events</strong><span>Task has not emitted execution history yet.</span></div>';
    return;
  }
  events.forEach((event) => {
    const item = document.createElement('div');
    item.className = 'timeline-item';
    item.innerHTML = `<strong>${event.event_type}</strong><span>${event.outcome} ${event.tool_name ? `via ${event.tool_name}` : ''}</span>`;
    executionTimeline.appendChild(item);
  });
}

function renderMetrics(metrics = {}) {
  const cards = [
    { label: 'Invoices', value: metrics.total_records ?? 0 },
    { label: 'Ledger Value', value: `$${Number(metrics.total_amount_usd ?? 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` },
    { label: 'Pending Approvals', value: metrics.pending_approvals ?? 0 },
    { label: 'Overdue', value: `${metrics.overdue_count ?? 0} / $${Number(metrics.overdue_total ?? 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` },
  ];
  kpiCards.innerHTML = cards.map((card) => `
    <div class="kpi-card">
      <span class="label">${card.label}</span>
      <span class="value">${card.value}</span>
    </div>
  `).join('');
}

function renderOverdue(summary = { count: 0, total_amount: 0, records: [] }) {
  overdueTable.innerHTML = '';
  if (!summary.records || !summary.records.length) {
    overdueTable.innerHTML = '<div class="overdue-item"><strong>No overdue invoices</strong><span>All tracked invoices are current.</span></div>';
    return;
  }
  summary.records.forEach((record) => {
    const item = document.createElement('div');
    item.className = 'overdue-item';
    item.innerHTML = `<strong>${record.vendor}</strong><span>${record.invoice_number} — ${record.currency} ${Number(record.amount).toFixed(2)} due ${record.due_date}</span>`;
    overdueTable.appendChild(item);
  });
}

async function refreshLedger() {
  const search = ledgerSearch.value.trim();
  const [records, summary, overdueSummary] = await Promise.all([
    api('/api/finance/invoices'),
    api('/api/finance/summary'),
    api('/api/finance/overdue')
  ]);
  renderMetrics(summary);
  renderOverdue(overdueSummary);
  const filtered = records.filter((record) => {
    if (!search) return true;
    const searchText = `${record.vendor} ${record.invoice_number}`.toLowerCase();
    return searchText.includes(search.toLowerCase());
  });
  ledgerTable.innerHTML = '<table><thead><tr><th>Vendor</th><th>Invoice</th><th>Amount</th><th>Due</th><th>Status</th></tr></thead><tbody>' + filtered.map((record) => `
    <tr><td>${record.vendor}</td><td>${record.invoice_number}</td><td>${record.currency} ${Number(record.amount).toFixed(2)}</td><td>${record.due_date || '—'}</td><td>${record.payment_status || 'outstanding'}</td></tr>
  `).join('') + '</tbody></table>';
}

async function refreshPendingApprovals() {
  try {
    const approvals = await api('/api/approvals/pending');
    approvalList.innerHTML = '';
    if (!approvals.length) {
      approvalList.innerHTML = '<div class="approval-item">No pending approvals.</div>';
      return;
    }
    approvals.forEach((approval) => {
      const item = document.createElement('div');
      item.className = 'approval-item';
      item.innerHTML = '<div><strong>Task:</strong> ' + approval.request + '</div>' +
        '<div><strong>Reason:</strong> ' + (approval.approval_reason || approval.reason || 'Approval required') + '</div>' +
        '<div class="approval-actions"><button class="approve-btn" data-id="' + approval.id + '">Approve</button><button class="reject-btn" data-id="' + approval.id + '">Reject</button></div>';
      approvalList.appendChild(item);
    });
    approvalList.querySelectorAll('.approve-btn').forEach((btn) => {
      btn.addEventListener('click', async () => {
        await api(`/api/runs/${btn.dataset.id}/approve`, { method: 'POST', body: JSON.stringify({ decision: 'approve' }) });
        await refreshPendingApprovals();
        await refreshRuns();
      });
    });
    approvalList.querySelectorAll('.reject-btn').forEach((btn) => {
      btn.addEventListener('click', async () => {
        await api(`/api/runs/${btn.dataset.id}/reject`, { method: 'POST', body: JSON.stringify({ decision: 'reject' }) });
        await refreshPendingApprovals();
        await refreshRuns();
      });
    });
  } catch (error) {
    console.error(error);
  }
}

async function refreshRuns() {
  const runs = await api('/api/runs');
  runHistory.innerHTML = '';
  runs.forEach((run) => {
    const item = document.createElement('button');
    item.className = 'run-item';
    item.textContent = `${run.created_at} — ${run.status}: ${run.summary || run.request}`;
    item.addEventListener('click', async () => {
      const detail = await api(`/api/runs/${run.task_id}`);
      setStatus(detail.run.status, detail.run.status);
      taskSummary.textContent = detail.run.summary || detail.run.reason || 'Run selected.';
      renderTimeline(detail.events);
      toolObservations.textContent = JSON.stringify(detail.events, null, 2);
      evidencePanel.textContent = JSON.stringify(detail.run.parsed || {}, null, 2);
      setPlan(['Locate invoice', 'Validate extracted fields', 'Check ledger', 'Submit record when approved']);
      runHistory.querySelectorAll('.run-item').forEach((entry) => entry.classList.remove('active'));
      item.classList.add('active');
    });
    runHistory.appendChild(item);
  });
}

async function runTask() {
  runTaskBtn.disabled = true;
  setStatus('running', 'Running');
  taskSummary.textContent = 'The agent is selecting the right invoice, reading and validating it, then checking the finance ledger.';
  try {
    const payload = {
      task: taskInput.value,
      inject_failure: injectFailureToggle.checked,
    };
    const result = await api('/api/tasks', { method: 'POST', body: JSON.stringify(payload) });
    const state = result.status || 'completed';
    setStatus(state, state.replace(/_/g, ' '));
    taskSummary.textContent = result.summary || result.reason || 'Task finished.';
    setPlan(['Locate matching invoice', 'Read and extract fields', 'Validate source data', 'Check for duplicates', 'Request approval if needed', 'Persist and verify output']);
    toolObservations.textContent = JSON.stringify(result.evidence || result, null, 2);
    evidencePanel.textContent = JSON.stringify(result.evidence || result, null, 2);
    const detail = await api(`/api/runs/${result.task_id}`);
    renderTimeline(detail.events);
    await refreshRuns();
    await refreshLedger();
    await refreshPendingApprovals();
  } catch (error) {
    setStatus('failed', 'Failed');
    taskSummary.textContent = error.message;
    toolObservations.textContent = error.message;
    evidencePanel.textContent = error.message;
  } finally {
    runTaskBtn.disabled = false;
  }
}

document.getElementById('runTaskBtn').addEventListener('click', runTask);
document.getElementById('refreshLedgerBtn').addEventListener('click', refreshLedger);
document.getElementById('ledgerSearch').addEventListener('input', refreshLedger);
document.querySelectorAll('.example-btn').forEach((btn) => {
  btn.addEventListener('click', () => {
    taskInput.value = btn.dataset.task;
    runTask();
  });
});

setPlan(['Locate matching invoice', 'Read and extract fields', 'Validate source data', 'Check for duplicates', 'Request approval if needed', 'Persist and verify output']);
refreshLedger();
refreshRuns();
refreshPendingApprovals();

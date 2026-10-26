# Technical Interview Guide

## Product summary

Relay is a local, sandboxed invoice-processing workflow built for a controlled enterprise-style demo. It accepts a natural-language task, selects the relevant invoice, extracts invoice metadata from a real PDF, checks the SQLite ledger for duplicates, pauses for approval when policy thresholds are exceeded, and then persists and verifies the finance record.

The app is intentionally narrow and safe: it runs locally, reads only sandboxed invoice files, stores data in SQLite, and exposes the results through a lightweight FastAPI dashboard.

## Core execution loop

The runtime flow is implemented in the agent controller and follows this path:

1. Parse the user task in app/agent/task_parser.py.
2. Decide whether the request is for a vendor lookup, invoice number lookup, extraction-only task, duplicate check, or overdue report.
3. In app/agent/controller.py, route the request to the right execution branch.
4. Read the invoice PDF from the local data/invoices directory.
5. Extract vendor, invoice number, date, due date, amount, and currency.
6. Check the finance ledger for duplicates before writing.
7. If the amount exceeds the configured approval threshold, move the task to awaiting_approval.
8. Attempt the finance write, then immediately verify the saved record against the extracted values.
9. Persist execution events and return the evidence payload to the UI and API consumers.

## Key files

- app/main.py — API layer and static hosting
- app/agent/task_parser.py — intent detection and action mapping
- app/agent/controller.py — orchestration, approval gating, retries, verification, persistence
- app/services/invoice_reader.py — PDF discovery and extraction
- app/services/finance.py — ledger operations, metrics, overdue summaries, verification logic
- app/db/database.py — schema setup and execution-event persistence
- static/index.html — enterprise dashboard layout
- static/app.js — frontend data binding and API calls
- tests/test_invoice_agent.py — regression coverage for the task lifecycle

## Why the design is interview-friendly

This project demonstrates several important engineering patterns without becoming over-engineered:

- Deterministic rule-based planning for a constrained business problem.
- State persistence through SQLite so tasks and events survive app restarts.
- Clear separation of concerns between parsing, orchestration, finance, and presentation.
- Real verification after mutation, which makes the workflow safer than a naive write-then-respond flow.
- Local-only safety: no external API credentials, no production payment system, no cloud dependency.

## Failure handling and resilience

The agent is intentionally designed to handle realistic edge cases:

- A duplicate invoice is blocked before a second ledger entry is created.
- A high-value invoice pauses for human approval rather than writing automatically.
- A one-time transient write failure triggers a single retry and then fails cleanly if the issue persists.
- Verification checks the stored values against the extracted values before final completion.

## Overdue report behavior

The overdue report is not a separate disconnected backend feature. It is routed through the same task parser and controller architecture as other tasks. A user request such as “Show overdue invoices.” is interpreted as a supported action, executed through the finance summary, and returned as structured evidence with an execution event for traceability.

## Interview talking points

### 1. What makes this resilient?
It keeps task state, ledger data, and execution history in persistent SQLite tables. That means operators can inspect exactly what happened, and the app can survive a restart without losing progress.

### 2. Why is approval required for some invoices?
The approval threshold is a policy guardrail. It prevents accidental or risky writes above a configured financial threshold while preserving a manual human checkpoint.

### 3. What is the verification step for?
It protects against data drift and silent corruption. After a finance record is created, the app re-loads the saved row and compares it with the source invoice values before calling it successful.

### 4. What would you extend next?
A realistic next step would be to add richer task types, policy-aware workflow routing, or a more advanced intent model behind the same controller and ledger layer.

## Example demonstration flow

1. Open the dashboard at http://127.0.0.1:8000.
2. Run a task such as “Process the latest invoice from Acme Labs and confirm when it has been entered.”
3. Watch the task status transition from queued to running to completed.
4. Inspect the execution timeline and evidence panel.
5. Review the finance ledger and overdue panel for the persisted records.
6. Try a high-value invoice to confirm approval gating.

## Summary

Relay is a compact but realistic workflow automation prototype. It proves that a local AI-style worker can safely parse intent, execute a controlled task lifecycle, persist decision history, and enforce business policy with transparent verification.

# Demo script

## Demo preparation

Before a live demo, reset the local demo database to a clean baseline:

```powershell
cd F:\centralign
.\.venv\Scripts\python.exe scripts\reset_demo.py --force
```

This creates a backup of the previous local demo database, reinitializes `data/relay.db`, and reseeds the fictional ledger without changing the invoice PDFs in `data/invoices`.

## Reproducible demo scenarios

Use these exact natural-language requests in order when running the demo.

### 1. Successful invoice processing

Request:

> Process the latest invoice from Acme Labs.

Expected result:
- The worker locates the latest Acme Labs invoice PDF.
- It extracts the vendor, invoice number, due date, amount, and currency.
- It checks the ledger for duplicates.
- It creates a finance record and verifies the saved row.
- The task finishes as completed.

### 2. Duplicate prevention

Request:

> Process invoice INV-2026-081.

Expected result:
- The system identifies that the invoice already exists in the ledger.
- It refuses to create a second record.
- The status remains safe and informative, with a duplicate detection outcome.

### 3. Approval gate

Request:

> Process the latest invoice from Northstar Cloud.

Expected result:
- The invoice exceeds the configured approval threshold.
- The task enters `awaiting_approval`.
- The approval panel shows the invoice details and the reasoning behind the approval requirement.
- After approving from the dashboard, the task resumes and completes.

### 4. Failure recovery and retry

Request:

> Process the latest invoice from Northstar Cloud.

Expected result while the failure toggle is enabled:
- The first write attempt is intentionally made to fail.
- The agent records the transient failure.
- It retries once and succeeds.
- The final record is persisted and verified before completion.

### 5. Overdue report

Request:

> Show overdue invoices.

Expected result:
- The task is interpreted as a supported overdue-report action.
- The dashboard shows only invoices whose effective status is overdue.
- The summary reflects the same logic as the finance ledger and KPI cards.

## Live walkthrough

1. Start the application with:
   ```powershell
   cd F:\centralign
   .\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
   ```
2. Open the app at http://127.0.0.1:8000/.
3. Point out the task bar, approval panel, run history, ledger, and overdue panel.
4. Run the successful scenario with the Acme Labs request.
5. Verify the execution timeline and evidence panel show real parsing, read, and verification events.
6. Run the duplicate scenario with `INV-2026-081`.
7. Run the Northstar Cloud approval scenario and approve it from the pending approval panel.
8. Toggle the transient failure option and rerun the Northstar Cloud request to demonstrate the retry and recovery flow.
9. Run `Show overdue invoices.` and confirm the overdue panel and summary are consistent with the ledger.

## Technical walkthrough

- The agent parses the request with `app/agent/task_parser.py`.
- The controller in `app/agent/controller.py` selects the invoice by vendor or invoice number.
- `app/services/invoice_reader.py` reads the real PDF and extracts fields using `pypdf`.
- The finance layer in `app/services/finance.py` computes a single effective invoice-status rule and performs duplicate-safe writes into SQLite.
- Verification is done by retrieving the saved record and comparing values to the original extracted invoice.
- Every tool call and state transition is inserted into `execution_events` for evidence and debugging.
- The browser UI updates from backend data rather than fake progress bars.

## What to point out during a technical review

- The source documents are real invoice PDFs in `data/invoices`.
- The ledger is a real SQLite database and survives restart.
- Status is derived consistently from the unpaid/paid and due-date logic rather than hardcoded mixed states.
- Approval checks are enforced by the backend, not just by a front-end flag.
- Failure injection is a single-task, scoped transient fault.
- The run history and evidence panels show persisted and queryable state.

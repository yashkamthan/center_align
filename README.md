# Relay — Autonomous Operations Worker

Relay is a local, sandboxed invoice-processing agent designed for the CentrAlign AI Engineering Intern assignment. It accepts a natural-language business request, interprets the requested action, locates the right invoice document, extracts invoice metadata, checks the finance ledger for duplicates, and either creates a record or pauses for approval when a risky transaction exceeds policy.

## Problem interpretation

This prototype focuses on one narrow but realistic workflow:

- understand the user’s intent from a natural-language task,
- plan the necessary actions,
- read real PDF invoices from a local sandbox directory,
- extract business-critical fields,
- check the SQLite finance ledger for duplicates,
- request human approval when the amount exceeds a configured threshold,
- persist and verify the final finance record,
- report evidence and execution status back to the user.

This keeps the system useful and testable while staying within a local-only, safe sandbox.

## Features

- Natural-language task parsing for:
  - latest invoice by vendor,
  - specific invoice number,
  - extraction-only requests,
  - duplicate detection,
  - unsupported requests with clear rejection.
- Real PDF processing using `pypdf`.
- Automatic invoice field extraction for vendor, invoice number, invoice date, due date, amount, and currency.
- SQLite-backed finance ledger with duplicate-safe inserts.
- Human approval gate with policy thresholding.
- Transient-failure injection for a one-time write error and bounded retry.
- End-to-end task persistence and execution timeline.
- Browser-based operations dashboard with finance ledger and run history.
- Independent post-write verification before marking a task complete.

## Supported task types

The default local planner supports:

1. "Process the latest invoice from Acme Labs"
2. "Process invoice INV-2026-081"
3. "Extract invoice details from the latest invoice from Vendor X"
4. Duplicate and already-recorded invoice checks
5. Safe rejection for unsupported or ambiguous requests

## Architecture

The project follows a straightforward layered design:

- `app/main.py` — FastAPI API and static file hosting.
- `app/agent/task_parser.py` — lightweight intent parsing and task interpretation.
- `app/agent/controller.py` — stateful agent loop for plan execution, retries, approvals, and verification.
- `app/services/invoice_reader.py` — PDF discovery and invoice extraction.
- `app/services/finance.py` — SQLite-backed finance operations and verification.
- `app/db/database.py` — database initialization and execution-event persistence.
- `app/models/schemas.py` — validated request and record models.
- `data/invoices/` — sandbox invoice PDFs.
- `static/` — HTML, CSS, and JavaScript dashboard.
- `tests/` — end-to-end unit/integration coverage.

## Agent loop

The execution logic follows this sequence:

1. Parse the user task.
2. Choose the matching invoice or vendor.
3. Read the PDF and extract fields.
4. Validate required values.
5. Search the SQLite ledger for duplicates.
6. Check approval policy.
7. Attempt finance write with transient-failure handling.
8. Independently verify the saved record against source values.
9. Persist execution events and report evidence.

## Tool registry and contracts

The worker exposes logical tools through a modular controller layer:

- `list_invoice_files` — returns matching invoice files and metadata.
- `read_invoice` — extracts text from a real PDF file.
- `extract_invoice_fields` — parses invoice fields.
- `search_finance_ledger` — checks for existing invoice records.
- `create_finance_record` — writes a finance record.
- `get_finance_record` — fetches a saved record.
- `verify_finance_record` — compares stored values with source values.
- `request_human_approval` — pauses and waits for human decision.

Each operation writes real events with timestamps and result metadata into SQLite.

## SQLite data model

The local SQLite database stores:

- `tasks` — user tasks, status, summary, parsed input, context, approval metadata.
- `execution_events` — tool calls, outcomes, timestamps, and errors.
- `finance_records` — persisted invoice records.
- `approvals` — approval actions from the user.

The design makes task state, execution history, and finance records persistent across restarts.

## Failure recovery and approval policy

- Approval threshold defaults to `5000.00 USD`.
- Invoices above the threshold are paused and require an explicit approval or rejection.
- Approval state is persisted and survives a browser refresh.
- Transient failure injection is scoped to a single task and triggers a deliberate write failure on the first attempt.
- The system permits one bounded retry and then stops rather than retrying forever.
- Verification is required before a task is marked complete.

## Setup and run

### Prerequisites

- Python 3.11+
- Windows 10/11 (the project was developed on Windows)

### Install dependencies

```powershell
cd F:\centralign
python -m pip install fastapi uvicorn pydantic pydantic-settings pytest pypdf python-multipart reportlab
```

### Prepare a clean demo database

This resets the local demo database only and creates a backup first. It does not touch the source PDF fixtures.

```powershell
cd F:\centralign
python scripts\reset_demo.py --force
```

The reset script targets the local demo database in `data/relay.db`, reseeds the fictional ledger, and clears stale pending approval tasks so the demo scenarios start in a predictable state.

### Start the application

```powershell
cd F:\centralign
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Then open:

- http://127.0.0.1:8000/

## Run tests

```powershell
cd F:\centralign
python -m pytest -q
```

## Demo scenarios

### Scenario A — Successful execution

Use the example task:

> Process the latest invoice from Acme Labs and confirm when it has been entered.

Expected result:

- The agent identifies the latest Acme Labs invoice.
- It reads and extracts the relevant invoice metadata.
- It checks for duplicate records.
- It creates the finance record.
- It verifies the stored values.
- It reports a completion summary with evidence.

### Scenario B — Duplicate detection

Use:

> Process invoice INV-2026-081.

Expected result:

- The agent finds the invoice in the ledger.
- It refuses to create a second record.
- It reports the duplicate and stops safely.

### Scenario C — Human approval

Use:

> Process the latest invoice from Northstar Cloud.

Expected result:

- The invoice exceeds the approval threshold.
- The run pauses in `awaiting_approval` state.
- The approval panel displays invoice details and reason.
- Approving the task resumes and writes the record.

### Scenario D — Recovery from failure

Use the toggle labeled: "Inject one temporary finance API failure" with a normal invoice task.

Expected result:

- The first write attempt fails intentionally.
- The task records the failure.
- The worker retries once and succeeds.
- Verification passes and the lifecycle is reported.

## Known limitations

- The prototype is intentionally narrow and local-only.
- It uses real invoice PDFs from a sandbox directory rather than arbitrary external sites.
- The natural-language parser is rule-based and intentionally constrained.
- It does not attempt broad enterprise workflow coverage beyond invoice processing.
- The approval UX is a browser-first local workflow, not a production identity system.

## Assumptions

- The user is operating within a trusted local environment.
- Invoice PDFs are well-formed and in the expected sandboxed folder.
- Duplicate detection is based on vendor + invoice number.
- The approval threshold is a policy control rather than a legal compliance system.

## Future work

If additional time were available, the next steps would be:

- connect to an optional LLM-based intent classifier behind a strict validation layer,
- add richer task planning and tool abstractions,
- add PDF template normalization for more diverse invoice layouts,
- expand the approval workflow with roles, audit logs, and email notifications,
- support deeper finance workflow automation with reconciliation and status tracking.

## Exact frameworks and libraries used

- Python 3.12
- FastAPI
- Uvicorn
- Pydantic
- SQLite
- PyPDF
- ReportLab
- pytest
- Vanilla JavaScript + HTML + CSS

## Notes

This is a prototype built for demonstration and testing in a controlled environment. It does not use real financial accounts, production credentials, or external systems.

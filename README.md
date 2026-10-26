# Relay — Autonomous Operations Worker

Relay is a local, sandboxed invoice-processing agent designed for the CentrAlign AI Engineering Intern assignment. It accepts a natural-language business request, interprets the requested action, locates the right invoice document, extracts invoice metadata, checks the finance ledger for duplicates, and either creates a record or pauses for approval when a risky transaction exceeds policy.

This project is a local rule-based automation worker for invoice operations. It reads real PDF invoices, extracts vendor and payment metadata, validates the result against a SQLite finance ledger, enforces approval gating for high-value records, verifies the persisted write, and reports the execution trail for demo and review.

## Features

- Natural-language task parsing for latest invoice selection, invoice lookup, overdue reporting, and duplicate detection
- Real PDF extraction using `pypdf`
- SQLite-backed finance ledger and task persistence
- Duplicate-safe invoice writes
- Approval and rejection workflow for high-value invoices
- Bounded transient failure recovery with retry logic
- Independent post-write verification before completion
- Browser dashboard for task runs, ledger data, and overdue summary

## Project structure

- `app/main.py` — FastAPI application and static hosting
- `app/agent/task_parser.py` — request interpretation and intent mapping
- `app/agent/controller.py` — orchestration, retries, approvals, verification, and task execution
- `app/services/invoice_reader.py` — invoice discovery and PDF parsing
- `app/services/finance.py` — ledger operations, metrics, and overdue logic
- `app/db/database.py` — SQLite schema and execution event records
- `static/` — dashboard UI assets
- `data/invoices/` — sandbox invoice PDFs
- `scripts/` — demo reset and fixture generation helpers
- `tests/` — regression test suite

## Local setup

### Install dependencies

```powershell
cd F:\centralign
python -m pip install fastapi uvicorn pydantic pydantic-settings pytest pypdf python-multipart reportlab
```

### Prepare a clean demo database

```powershell
cd F:\centralign
python scripts\reset_demo.py --force
```

### Start the app

```powershell
cd F:\centralign
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Then open:

- http://127.0.0.1:8000/

## Example requests

- Process the latest invoice from Acme Labs.
- Process invoice INV-2026-081.
- Process the latest invoice from Northstar Cloud.
- Show overdue invoices.

## Running tests

```powershell
cd F:\centralign
python -m pytest -q
```

## Notes

This project is intentionally local-only and sandboxed. It is designed for demonstration, validation, and safe workflow testing rather than production financial operations.

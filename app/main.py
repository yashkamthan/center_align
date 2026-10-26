from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.agent.controller import AgentController
from app.db.database import ensure_schema, get_db_connection
from app.models.schemas import ApprovalRequest, TaskRequest
from app.services.finance import DEMO_RECORDS, FinanceService

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "relay.db"
INVOICE_ROOT = BASE_DIR / "data" / "invoices"
app = FastAPI(title="Relay — Autonomous Operations Worker")


def ensure_demo_data() -> None:
    ensure_schema(DB_PATH)
    INVOICE_ROOT.mkdir(parents=True, exist_ok=True)
    service = FinanceService(DB_PATH)
    if len(service.list_records()) < len(DEMO_RECORDS):
        service.seed_demo_records()


ensure_demo_data()


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "Relay"}


@app.post("/api/tasks")
def create_task(payload: TaskRequest) -> dict:
    controller = AgentController(db_path=DB_PATH)
    result = controller.create_task(payload.task, inject_failure=payload.inject_failure)
    return result


@app.get("/api/runs")
def list_runs() -> list[dict]:
    controller = AgentController(db_path=DB_PATH)
    return controller.list_runs()


@app.get("/api/runs/{run_id}")
def get_run(run_id: str) -> dict:
    controller = AgentController(db_path=DB_PATH)
    task = controller.get_task(run_id)
    if not task:
        raise HTTPException(status_code=404, detail="Run not found")
    return {"run": task, "events": controller.list_events(run_id)}


@app.post("/api/runs/{run_id}/approve")
def approve_run(run_id: str, payload: ApprovalRequest) -> dict:
    if payload.decision != "approve":
        raise HTTPException(status_code=400, detail="Only approve is supported here")
    controller = AgentController(db_path=DB_PATH)
    return controller.approve_task(run_id)


@app.post("/api/runs/{run_id}/reject")
def reject_run(run_id: str, payload: ApprovalRequest) -> dict:
    if payload.decision != "reject":
        raise HTTPException(status_code=400, detail="Only reject is supported here")
    controller = AgentController(db_path=DB_PATH)
    return controller.reject_task(run_id)


@app.get("/api/finance/invoices")
def list_finance_records() -> list[dict]:
    service = FinanceService(DB_PATH)
    return service.list_records()


@app.get("/api/finance/summary")
def finance_summary() -> dict:
    service = FinanceService(DB_PATH)
    return service.get_metrics()


@app.get("/api/finance/overdue")
def overdue_invoices() -> dict:
    service = FinanceService(DB_PATH)
    return service.get_overdue_summary()


@app.get("/api/finance/invoices/{record_id}")
def get_finance_record(record_id: int) -> dict:
    service = FinanceService(DB_PATH)
    record = service.get_record_by_id(record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")
    return record


@app.get("/api/approvals/pending")
def pending_approvals() -> list[dict]:
    conn = get_db_connection(DB_PATH)
    rows = conn.execute(
        "SELECT id, request, status, summary, reason, approval_reason, created_at FROM tasks WHERE status = 'awaiting_approval' ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


@app.get("/api/invoices")
def list_invoice_entries() -> list[dict]:
    from app.services.invoice_reader import list_invoice_files

    return list_invoice_files(INVOICE_ROOT)


@app.get("/")
def root() -> FileResponse:
    return FileResponse(BASE_DIR / "static" / "index.html")


app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

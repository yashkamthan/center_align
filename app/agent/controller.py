from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from app.db.database import ensure_schema, fetch_task, fetch_task_events, get_db_connection, record_task_event
from app.services.finance import FinanceService
from app.services.invoice_reader import INVOICE_ROOT, extract_invoice_fields, list_invoice_files, safe_invoice_path
from app.agent.task_parser import interpret_task


class AgentController:
    def __init__(self, db_path: str | Path = "relay.db", approval_threshold: float = 5000.0):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.approval_threshold = approval_threshold
        ensure_schema(self.db_path)
        self.finance = FinanceService(db_path=self.db_path, approval_threshold=approval_threshold)

    def create_task(self, request_text: str, inject_failure: bool = False) -> dict[str, Any]:
        task_id = f"task-{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
        parsed = interpret_task(request_text)
        task = {
            "task_id": task_id,
            "request": request_text,
            "status": "queued",
            "summary": "Task queued",
            "reason": None,
            "parsed": parsed,
            "approval_required": False,
            "approval_reason": None,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        }
        conn = get_db_connection(self.db_path)
        conn.execute(
            """
            INSERT INTO tasks (id, request, status, summary, reason, parsed_json, context_json, approval_required, approval_reason, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                task_id,
                request_text,
                task["status"],
                task["summary"],
                task["reason"],
                json.dumps(parsed),
                json.dumps({"inject_failure": inject_failure}),
                int(task["approval_required"]),
                task["approval_reason"],
                task["created_at"],
                task["updated_at"],
            ),
        )
        conn.commit()
        conn.close()
        record_task_event(self.db_path, task_id, "task_created", None, "created", {"request": request_text})
        return self.execute_task(task_id, inject_failure=inject_failure)

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        row = fetch_task(self.db_path, task_id)
        if not row:
            return None
        row["task_id"] = row["id"]
        row["parsed"] = json.loads(row["parsed_json"] or "{}")
        row["context"] = json.loads(row["context_json"] or "{}")
        return row

    def list_runs(self) -> list[dict[str, Any]]:
        conn = get_db_connection(self.db_path)
        rows = conn.execute(
            "SELECT * FROM tasks ORDER BY created_at DESC, updated_at DESC"
        ).fetchall()
        conn.close()
        return [
            {
                "task_id": row["id"],
                "request": row["request"],
                "status": row["status"],
                "summary": row["summary"],
                "reason": row["reason"],
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def execute_task(self, task_id: str, inject_failure: bool = False) -> dict[str, Any]:
        task = self.get_task(task_id)
        if not task:
            raise ValueError(f"Unknown task {task_id}")

        parsed = task["parsed"]
        request = task["request"]
        action = parsed["action"]
        vendor = parsed["vendor"]
        invoice_number = parsed.get("invoice_number")

        try:
            if action == "process_latest_invoice":
                match_files = list_invoice_files(INVOICE_ROOT)
                vendor_matches = [entry for entry in match_files if entry["vendor"].lower() == vendor.lower()]
                if not vendor_matches:
                    raise ValueError(f"No invoice files found for vendor: {vendor}")
                latest = max(vendor_matches, key=lambda item: item["invoice_date"] or "1970-01-01")
                record = extract_invoice_fields(latest["path"])
                self._update_task(task_id, "running", f"Processing latest invoice from {vendor}", None, parsed, inject_failure)
                record_task_event(self.db_path, task_id, "invoice_selected", "list_invoice_files", "success", {"vendor": vendor, "invoice": latest})
                record_task_event(self.db_path, task_id, "invoice_extracted", "read_invoice", "success", {"source_file": record["source_file"], "fields": record})
                return self._process_invoice(task_id, record, inject_failure)

            if action == "process_invoice_number":
                files = list_invoice_files(INVOICE_ROOT)
                matches = [entry for entry in files if entry["invoice_number"].upper() == invoice_number.upper()]
                if not matches:
                    raise ValueError(f"No invoice file found matching invoice number {invoice_number}")
                selected = matches[0]
                record = extract_invoice_fields(selected["path"])
                self._update_task(task_id, "running", f"Processing invoice {invoice_number}", None, parsed, inject_failure)
                record_task_event(self.db_path, task_id, "invoice_selected", "list_invoice_files", "success", {"invoice_number": invoice_number, "invoice": selected})
                record_task_event(self.db_path, task_id, "invoice_extracted", "read_invoice", "success", {"source_file": record["source_file"], "fields": record})
                return self._process_invoice(task_id, record, inject_failure)

            if action == "extract_invoice_fields":
                files = list_invoice_files(INVOICE_ROOT)
                if not files:
                    raise ValueError("No invoice files available")
                selected = files[0]
                record = extract_invoice_fields(selected["path"])
                self._update_task(task_id, "running", "Extracting invoice fields", None, parsed, inject_failure)
                record_task_event(self.db_path, task_id, "invoice_extracted", "read_invoice", "success", {"source_file": record["source_file"], "fields": record})
                return {"task_id": task_id, "status": "completed", "summary": "Invoice fields extracted", "evidence": {"source_file": record["source_file"], "fields": record}}

            if action == "show_overdue_invoices":
                self._update_task(task_id, "running", "Reviewing overdue invoices", None, parsed, inject_failure)
                overdue_report = self.finance.get_overdue_summary()
                record_task_event(self.db_path, task_id, "overdue_report_requested", "get_overdue_summary", "success", {"report": overdue_report})
                self._update_task(task_id, "completed", "Overdue invoices reported", None, parsed, inject_failure, context={"overdue_report": overdue_report})
                return {
                    "task_id": task_id,
                    "status": "completed",
                    "summary": "Overdue invoices reported",
                    "reason": None,
                    "requires_approval": False,
                    "overdue_report": overdue_report,
                    "evidence": {"report": overdue_report},
                }

            raise ValueError(f"Unsupported action: {action}")
        except Exception as exc:  # pragma: no cover - handled by API layer
            self._update_task(task_id, "failed", "Task failed", str(exc), parsed, inject_failure)
            record_task_event(self.db_path, task_id, "task_failed", None, "error", {"error": str(exc)})
            return {"task_id": task_id, "status": "failed", "summary": "Task failed", "reason": str(exc)}

    def _process_invoice(self, task_id: str, invoice: dict[str, Any], inject_failure: bool) -> dict[str, Any]:
        self._update_task(task_id, "running", "Validating invoice fields", None, None, inject_failure, context={"invoice": invoice})
        record_task_event(self.db_path, task_id, "invoice_validated", "extract_invoice_fields", "success", {"invoice": invoice})

        existing = self.finance.get_record_by_invoice(invoice["vendor"], invoice["invoice_number"])
        if existing:
            self._update_task(task_id, "blocked", "Duplicate invoice record found", "Invoice already exists in the finance ledger.", None, inject_failure, context={"invoice": invoice, "existing_record": existing})
            record_task_event(self.db_path, task_id, "duplicate_detected", "search_finance_ledger", "blocked", {"existing_record": existing})
            return {"task_id": task_id, "status": "blocked", "reason": "Duplicate invoice found", "summary": "Invoice already recorded", "evidence": {"existing_record": existing, "source_file": invoice["source_file"], "fields": invoice}, "requires_approval": False}

        if float(invoice["amount"]) > self.approval_threshold:
            self._update_task(task_id, "awaiting_approval", "Approval required", "Amount exceeds approval threshold.", None, inject_failure, context={"invoice": invoice})
            record_task_event(self.db_path, task_id, "approval_required", "request_human_approval", "pending", {"invoice": invoice, "threshold": self.approval_threshold})
            return {"task_id": task_id, "status": "awaiting_approval", "reason": "Approval required", "requires_approval": True, "approval_required": True, "approval_reason": "Amount exceeds approval threshold.", "evidence": {"source_file": invoice["source_file"], "fields": invoice}}

        record_task_event(self.db_path, task_id, "finance_write_attempt", "create_finance_record", "pending", {"invoice": invoice, "inject_failure": inject_failure})
        created = None
        retry_count = 0
        transient_failure = False
        while retry_count <= 1 and created is None:
            self.finance.fail_on_next_write = bool(inject_failure and retry_count == 0)
            created = self.finance.create_record(
                vendor=invoice["vendor"],
                invoice_number=invoice["invoice_number"],
                invoice_date=invoice["invoice_date"],
                due_date=invoice["due_date"],
                amount=float(invoice["amount"]),
                currency=invoice["currency"],
                source_file=invoice["source_file"],
            )
            if created is None and inject_failure and retry_count == 0:
                transient_failure = True
                record_task_event(self.db_path, task_id, "transient_failure", "create_finance_record", "error", {"invoice": invoice, "error": "Transient finance API failure"})
                retry_count += 1
                continue
            if created is None:
                break
            retry_count += 1

        if created is None:
            if transient_failure:
                self._update_task(task_id, "failed", "Transient finance failure", "A temporary API failure interrupted the first write attempt.", None, inject_failure, context={"invoice": invoice})
                return {"task_id": task_id, "status": "failed", "reason": "Transient finance failure", "summary": "Retry is required after a temporary finance API failure.", "evidence": {"source_file": invoice["source_file"], "fields": invoice}, "requires_approval": False}
            self._update_task(task_id, "failed", "Finance write failed", "The finance write returned no record.", None, inject_failure, context={"invoice": invoice})
            record_task_event(self.db_path, task_id, "finance_write_failed", "create_finance_record", "error", {"invoice": invoice})
            return {"task_id": task_id, "status": "failed", "reason": "Finance write failed"}

        verification = self.finance.verify_record(
            record_id=created["id"],
            expected_vendor=invoice["vendor"],
            expected_invoice_number=invoice["invoice_number"],
            expected_amount=float(invoice["amount"]),
            expected_currency=invoice["currency"],
            expected_invoice_date=invoice["invoice_date"],
            expected_due_date=invoice["due_date"],
        )
        if not verification["verification_passed"]:
            self._update_task(task_id, "failed", "Verification failed", "The saved record did not match the extracted invoice.", None, inject_failure, context={"invoice": invoice, "record": created})
            record_task_event(self.db_path, task_id, "verification_failed", "verify_finance_record", "error", {"verification": verification})
            return {"task_id": task_id, "status": "failed", "reason": "Verification failed", "evidence": verification}

        self._update_task(task_id, "completed", "Invoice processed successfully", "Finance record created and verified.", None, inject_failure, context={"invoice": invoice, "record": created})
        record_task_event(self.db_path, task_id, "finance_write_succeeded", "create_finance_record", "success", {"record": created, "recovered_from_failure": transient_failure})
        record_task_event(self.db_path, task_id, "verification_succeeded", "verify_finance_record", "success", {"verification": verification})
        return {
            "task_id": task_id,
            "status": "completed",
            "summary": "Invoice processed successfully",
            "reason": None,
            "record": created,
            "requires_approval": False,
            "evidence": {
                "source_file": invoice["source_file"],
                "fields": invoice,
                "verification": verification,
                "recovered_from_failure": transient_failure,
            },
        }

    def _update_task(self, task_id: str, status: str, summary: str, reason: str | None, parsed: dict[str, Any] | None, inject_failure: bool, context: dict[str, Any] | None = None) -> None:
        now = datetime.now().isoformat()
        conn = get_db_connection(self.db_path)
        task = self.get_task(task_id) or {}
        current_context = task.get("context") or {}
        merged = {**current_context, **(context or {}), "inject_failure": inject_failure}
        conn.execute(
            """
            UPDATE tasks
            SET status = ?, summary = ?, reason = ?, parsed_json = ?, context_json = ?, approval_required = ?, approval_reason = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                status,
                summary,
                reason,
                json.dumps(parsed or task.get("parsed") or {}),
                json.dumps(merged),
                int(status == "awaiting_approval"),
                reason if status == "awaiting_approval" else None,
                now,
                task_id,
            ),
        )
        conn.commit()
        conn.close()

    def approve_task(self, task_id: str) -> dict[str, Any]:
        task = self.get_task(task_id)
        if not task:
            raise ValueError("Unknown task")
        if task["status"] != "awaiting_approval":
            raise ValueError("Task is not awaiting approval.")

        parsed = task["parsed"]
        invoice = task["context"].get("invoice")
        if not invoice:
            raise ValueError("Missing invoice evidence for this approval.")
        self._update_task(task_id, "running", "Resuming after approval", None, parsed, False)
        record_task_event(self.db_path, task_id, "approval_decision", "request_human_approval", "approved", {"decision": "approve"})
        return self._process_invoice(task_id, invoice, False)

    def reject_task(self, task_id: str) -> dict[str, Any]:
        task = self.get_task(task_id)
        if not task:
            raise ValueError("Unknown task")
        if task["status"] != "awaiting_approval":
            raise ValueError("Task is not awaiting approval.")
        self._update_task(task_id, "rejected", "Approval rejected by user", "Human approval was rejected.", task["parsed"], False)
        record_task_event(self.db_path, task_id, "approval_decision", "request_human_approval", "rejected", {"decision": "reject"})
        return {"task_id": task_id, "status": "rejected", "summary": "Approval rejected", "reason": "Human approval was rejected."}

    def list_events(self, task_id: str) -> list[dict[str, Any]]:
        return fetch_task_events(self.db_path, task_id)

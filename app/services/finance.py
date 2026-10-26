from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

from app.db.database import ensure_schema, get_db_connection


DEMO_RECORDS = [
    {"vendor": "Vertex Systems", "invoice_number": "INV-2026-081", "invoice_date": "2026-01-20", "due_date": "2026-02-20", "amount": 1825.0, "currency": "USD", "source_file": "vertex_2026_01_20.pdf", "payment_status": "outstanding"},
    {"vendor": "Harbor Data", "invoice_number": "INV-2026-091", "invoice_date": "2026-01-15", "due_date": "2026-02-15", "amount": 4980.0, "currency": "USD", "source_file": "harbor_2026_01_15.pdf", "payment_status": "outstanding"},
    {"vendor": "Crestwood Labs", "invoice_number": "INV-2026-102", "invoice_date": "2026-02-05", "due_date": "2026-02-28", "amount": 8375.0, "currency": "USD", "source_file": "crestwood_2026_02_05.pdf", "payment_status": "outstanding"},
    {"vendor": "BluePeak Health", "invoice_number": "INV-2026-118", "invoice_date": "2026-02-12", "due_date": "2026-03-05", "amount": 2195.0, "currency": "USD", "source_file": "bluepeak_2026_04_12.pdf", "payment_status": "outstanding"},
    {"vendor": "Summit Works", "invoice_number": "INV-2026-134", "invoice_date": "2026-02-18", "due_date": "2026-03-10", "amount": 6400.0, "currency": "USD", "source_file": "summit_2026_02_18.pdf", "payment_status": "outstanding"},
    {"vendor": "Oakridge Retail", "invoice_number": "INV-2026-145", "invoice_date": "2026-02-23", "due_date": "2026-03-23", "amount": 1450.0, "currency": "USD", "source_file": "oakridge_2026_02_23.pdf", "payment_status": "outstanding"},
    {"vendor": "Northwind Logistics", "invoice_number": "INV-2026-156", "invoice_date": "2026-03-01", "due_date": "2026-03-14", "amount": 22100.0, "currency": "USD", "source_file": "northwind_2026_03_01.pdf", "payment_status": "outstanding"},
    {"vendor": "Helio Energy", "invoice_number": "INV-2026-167", "invoice_date": "2026-03-08", "due_date": "2026-03-28", "amount": 7430.0, "currency": "USD", "source_file": "helio_2026_03_08.pdf", "payment_status": "outstanding"},
    {"vendor": "Luma Studio", "invoice_number": "INV-2026-173", "invoice_date": "2026-03-09", "due_date": "2026-03-19", "amount": 3200.0, "currency": "USD", "source_file": "luma_2026_03_09.pdf", "payment_status": "paid"},
    {"vendor": "Westline Services", "invoice_number": "INV-2026-189", "invoice_date": "2026-03-18", "due_date": "2026-04-08", "amount": 6400.0, "currency": "USD", "source_file": "westline_2026_03_18.pdf", "payment_status": "outstanding"},
    {"vendor": "Quarry Peak", "invoice_number": "INV-2026-195", "invoice_date": "2026-03-27", "due_date": "2026-04-10", "amount": 9075.0, "currency": "USD", "source_file": "quarry_2026_03_27.pdf", "payment_status": "outstanding"},
    {"vendor": "Meridian Ops", "invoice_number": "INV-2026-205", "invoice_date": "2026-04-01", "due_date": "2026-04-30", "amount": 5675.0, "currency": "USD", "source_file": "meridian_2026_04_01.pdf", "payment_status": "outstanding"},
    {"vendor": "Cedar Lane", "invoice_number": "INV-2026-214", "invoice_date": "2026-04-12", "due_date": "2026-11-10", "amount": 4125.0, "currency": "USD", "source_file": "cedar_2026_04_12.pdf", "payment_status": "outstanding"},
    {"vendor": "Granite Works", "invoice_number": "INV-2026-221", "invoice_date": "2026-04-20", "due_date": "2026-11-18", "amount": 3450.0, "currency": "USD", "source_file": "granite_2026_04_20.pdf", "payment_status": "outstanding"},
    {"vendor": "Aster Labs", "invoice_number": "INV-2026-233", "invoice_date": "2026-05-03", "due_date": "2026-11-15", "amount": 7320.0, "currency": "USD", "source_file": "aster_2026_05_03.pdf", "payment_status": "outstanding"},
]


def _parse_due_date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None
        for candidate in (value, value[:10]):
            try:
                return datetime.strptime(candidate, "%Y-%m-%d").date()
            except ValueError:
                pass
        try:
            return datetime.fromisoformat(value).date()
        except ValueError:
            return None
    return None


def get_effective_invoice_status(record: dict[str, Any], reference_date: date | None = None) -> str:
    ref = reference_date or date.today()
    payment_status = str(record.get("payment_status") or "").lower()
    if payment_status == "paid":
        return "paid"
    due_date = _parse_due_date(record.get("due_date"))
    if due_date is None:
        return "outstanding"
    return "overdue" if due_date < ref else "outstanding"


class FinanceService:
    def __init__(self, db_path: str | Path = "relay.db", approval_threshold: float = 5000.0):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.approval_threshold = approval_threshold
        self.fail_on_next_write = False
        ensure_schema(self.db_path)

    def _normalize_record(self, record: dict[str, Any], reference_date: date | None = None) -> dict[str, Any]:
        normalized = dict(record)
        normalized["payment_status"] = get_effective_invoice_status(normalized, reference_date)
        normalized["effective_status"] = normalized["payment_status"]
        normalized["is_overdue"] = normalized["payment_status"] == "overdue"
        return normalized

    def create_record(
        self,
        vendor: str,
        invoice_number: str,
        invoice_date: str,
        due_date: str | None,
        amount: float,
        currency: str,
        source_file: str,
        payment_status: str = "outstanding",
    ) -> dict[str, Any] | None:
        existing = self.get_record_by_invoice(vendor, invoice_number)
        if existing:
            return None

        if self.fail_on_next_write:
            self.fail_on_next_write = False
            return None

        normalized_status = str(payment_status or "").lower()
        if normalized_status not in {"paid", "outstanding"}:
            normalized_status = "outstanding"

        conn = get_db_connection(self.db_path)
        cursor = conn.execute(
            """
            INSERT INTO finance_records (vendor, invoice_number, invoice_date, due_date, amount, currency, source_file, payment_status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            """,
            (vendor, invoice_number, invoice_date, due_date, float(amount), currency.upper(), source_file, normalized_status),
        )
        conn.commit()
        record_id = cursor.lastrowid
        record = conn.execute("SELECT * FROM finance_records WHERE id = ?", (record_id,)).fetchone()
        conn.close()
        return dict(record)

    def get_record_by_invoice(self, vendor: str, invoice_number: str) -> dict[str, Any] | None:
        conn = get_db_connection(self.db_path)
        row = conn.execute(
            "SELECT * FROM finance_records WHERE vendor = ? AND invoice_number = ?",
            (vendor, invoice_number),
        ).fetchone()
        conn.close()
        return dict(row) if row else None

    def get_record_by_id(self, record_id: int, reference_date: date | None = None) -> dict[str, Any] | None:
        conn = get_db_connection(self.db_path)
        row = conn.execute("SELECT * FROM finance_records WHERE id = ?", (record_id,)).fetchone()
        conn.close()
        if not row:
            return None
        return self._normalize_record(dict(row), reference_date)

    def list_records(self, reference_date: date | None = None) -> list[dict[str, Any]]:
        conn = get_db_connection(self.db_path)
        rows = conn.execute(
            "SELECT * FROM finance_records ORDER BY invoice_date DESC, id DESC"
        ).fetchall()
        conn.close()
        return [self._normalize_record(dict(row), reference_date) for row in rows]

    def get_metrics(self, reference_date: date | None = None) -> dict[str, Any]:
        ref = reference_date or date.today()
        records = self.list_records(reference_date=ref)
        overdue_records = [record for record in records if record["payment_status"] == "overdue"]
        total_amount_usd = sum(float(record["amount"] or 0) for record in records if (record.get("currency") or "USD").upper() == "USD")
        metrics = {
            "total_records": len(records),
            "total_amount_usd": total_amount_usd,
            "pending_approvals": 0,
            "overdue_count": len(overdue_records),
            "overdue_total": sum(float(record["amount"] or 0) for record in overdue_records),
        }
        conn = get_db_connection(self.db_path)
        metrics["pending_approvals"] = conn.execute("SELECT COUNT(*) FROM tasks WHERE status = 'awaiting_approval'").fetchone()[0]
        conn.close()
        return metrics

    def get_overdue_invoices(self, reference_date: date | None = None) -> list[dict[str, Any]]:
        ref = reference_date or date.today()
        overdue = [record for record in self.list_records(reference_date=ref) if record["payment_status"] == "overdue"]
        return sorted(overdue, key=lambda item: (_parse_due_date(item.get("due_date")) or ref, -float(item.get("amount") or 0)))

    def get_overdue_summary(self, reference_date: date | None = None) -> dict[str, Any]:
        records = self.get_overdue_invoices(reference_date=reference_date)
        totals_by_currency: dict[str, float] = {}
        for record in records:
            currency = (record.get("currency") or "USD").upper()
            totals_by_currency[currency] = totals_by_currency.get(currency, 0.0) + float(record["amount"] or 0)
        return {
            "count": len(records),
            "total_amount": sum(totals_by_currency.values()),
            "currency_totals": {currency: round(total, 2) for currency, total in totals_by_currency.items()},
            "records": records,
        }

    def seed_demo_records(self) -> list[dict[str, Any]]:
        added: list[dict[str, Any]] = []
        for record in DEMO_RECORDS:
            if not self.get_record_by_invoice(record["vendor"], record["invoice_number"]):
                inserted = self.create_record(
                    vendor=record["vendor"],
                    invoice_number=record["invoice_number"],
                    invoice_date=record["invoice_date"],
                    due_date=record["due_date"],
                    amount=float(record["amount"]),
                    currency=record["currency"],
                    source_file=record["source_file"],
                    payment_status=record["payment_status"],
                )
                if inserted:
                    added.append(inserted)
        return self.list_records()

    def verify_record(
        self,
        record_id: int,
        expected_vendor: str,
        expected_invoice_number: str | None = None,
        expected_amount: float | None = None,
        expected_currency: str | None = None,
        expected_invoice_date: str | None = None,
        expected_due_date: str | None = None,
    ) -> dict[str, Any]:
        record = self.get_record_by_id(record_id)
        if not record:
            return {"verification_passed": False, "issues": ["Record not found"], "record_id": record_id}
        issues: list[str] = []
        if record["vendor"] != expected_vendor:
            issues.append("vendor mismatch")
        if expected_invoice_number and record["invoice_number"] != expected_invoice_number:
            issues.append("invoice number mismatch")
        if expected_amount is not None and float(record["amount"]) != float(expected_amount):
            issues.append("amount mismatch")
        if expected_currency and record["currency"] != expected_currency.upper():
            issues.append("currency mismatch")
        if expected_invoice_date and record["invoice_date"] != expected_invoice_date:
            issues.append("invoice date mismatch")
        if expected_due_date and record["due_date"] != expected_due_date:
            issues.append("due date mismatch")
        return {
            "verification_passed": not issues,
            "issues": issues,
            "record_id": record_id,
            "record": record,
        }

    def search_records(self, vendor: str | None = None, invoice_number: str | None = None, reference_date: date | None = None) -> list[dict[str, Any]]:
        conn = get_db_connection(self.db_path)
        query = "SELECT * FROM finance_records WHERE 1=1"
        params: list[Any] = []
        if vendor:
            query += " AND vendor LIKE ?"
            params.append(f"%{vendor}%")
        if invoice_number:
            query += " AND invoice_number LIKE ?"
            params.append(f"%{invoice_number}%")
        query += " ORDER BY created_at DESC"
        rows = conn.execute(query, params).fetchall()
        conn.close()
        return [self._normalize_record(dict(row), reference_date) for row in rows]

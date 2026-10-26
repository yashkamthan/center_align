from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from reportlab.pdfgen import canvas

from app.agent.task_parser import interpret_task
from app.agent.controller import AgentController
from app.services.finance import FinanceService, get_effective_invoice_status
from app.services.invoice_reader import read_invoice_pdf, extract_invoice_fields, list_invoice_files


def _write_pdf(path: Path, vendor: str, invoice_number: str, invoice_date: str, due_date: str, amount: float, currency: str = "USD") -> None:
    pdf = canvas.Canvas(str(path), pagesize=(800, 900))
    pdf.setFont("Helvetica-Bold", 22)
    pdf.drawString(60, 820, vendor)
    pdf.setFont("Helvetica", 14)
    pdf.drawString(60, 780, f"Invoice Number: {invoice_number}")
    pdf.drawString(60, 750, f"Invoice Date: {invoice_date}")
    pdf.drawString(60, 720, f"Due Date: {due_date}")
    pdf.drawString(60, 690, f"Amount: {amount:.2f} {currency}")
    pdf.save()


@pytest.fixture
def sample_invoice_dir(tmp_path: Path) -> Path:
    invoice_dir = tmp_path / "invoices"
    invoice_dir.mkdir()
    _write_pdf(
        invoice_dir / "acme_2026_01_15.pdf",
        "Acme Labs",
        "INV-2026-010",
        "2026-01-15",
        "2026-02-15",
        1250.0,
    )
    (invoice_dir / "README.txt").write_text("""ACME LABS\nInvoice Number: INV-2026-010\nInvoice Date: 2026-01-15\nDue Date: 2026-02-15\nAmount: 1250.00 USD\n""")
    return invoice_dir


def test_extract_fields_from_real_pdf(tmp_path):
    invoice_dir = tmp_path / "invoices"
    invoice_dir.mkdir()
    pdf_path = invoice_dir / "acme_2026_01_15.pdf"
    _write_pdf(
        pdf_path,
        "Acme Labs",
        "INV-2026-010",
        "2026-01-15",
        "2026-02-15",
        1250.0,
    )

    fields = extract_invoice_fields(pdf_path)
    assert fields["vendor"] == "Acme Labs"
    assert fields["invoice_number"] == "INV-2026-010"
    assert fields["amount"] == 1250.0
    assert fields["currency"] == "USD"


def test_select_latest_invoice_for_vendor(sample_invoice_dir):
    files = list_invoice_files(sample_invoice_dir)
    assert files
    latest = next(iter(files))
    assert latest["filename"].endswith(".pdf")


def test_interpret_supported_task():
    request = "Process the latest invoice from Acme Labs and confirm when entered."
    parsed = interpret_task(request)
    assert parsed["action"] == "process_latest_invoice"
    assert parsed["vendor"] == "Acme Labs"


def test_process_invoice_and_persist_record(tmp_path):
    db_path = tmp_path / "relay.db"
    service = FinanceService(db_path)
    service.create_record(
        vendor="Acme Labs",
        invoice_number="INV-2026-010",
        invoice_date="2026-01-15",
        due_date="2026-02-15",
        amount=1250.0,
        currency="USD",
        source_file="acme_2026_01_15.pdf",
    )
    row = service.get_record_by_invoice("Acme Labs", "INV-2026-010")
    assert row is not None
    assert row["amount"] == 1250.0


def test_duplicate_prevention(tmp_path):
    db_path = tmp_path / "relay.db"
    service = FinanceService(db_path)
    service.create_record(
        vendor="Acme Labs",
        invoice_number="INV-2026-010",
        invoice_date="2026-01-15",
        due_date="2026-02-15",
        amount=1250.0,
        currency="USD",
        source_file="acme_2026_01_15.pdf",
    )
    duplicate = service.create_record(
        vendor="Acme Labs",
        invoice_number="INV-2026-010",
        invoice_date="2026-01-15",
        due_date="2026-02-15",
        amount=1250.0,
        currency="USD",
        source_file="acme_2026_01_15.pdf",
    )
    assert duplicate is None


def test_approval_required_for_high_value_invoice(tmp_path):
    db_path = tmp_path / "relay.db"
    controller = AgentController(db_path=db_path, approval_threshold=5000)
    task = controller.create_task("Process the latest invoice from Northstar Cloud.")
    assert task["requires_approval"] is True


def test_retry_after_transient_failure(tmp_path):
    db_path = tmp_path / "relay.db"
    service = FinanceService(db_path)
    service.fail_on_next_write = True
    first = service.create_record(
        vendor="FluxWorks",
        invoice_number="INV-2026-200",
        invoice_date="2026-02-01",
        due_date="2026-03-01",
        amount=900.0,
        currency="USD",
        source_file="flux_2026_02_01.pdf",
    )
    assert first is None
    second = service.create_record(
        vendor="FluxWorks",
        invoice_number="INV-2026-200",
        invoice_date="2026-02-01",
        due_date="2026-03-01",
        amount=900.0,
        currency="USD",
        source_file="flux_2026_02_01.pdf",
    )
    assert second is not None


def test_verification_fails_when_data_mismatched(tmp_path):
    db_path = tmp_path / "relay.db"
    service = FinanceService(db_path)
    service.create_record(
        vendor="Acme Labs",
        invoice_number="INV-2026-010",
        invoice_date="2026-01-15",
        due_date="2026-02-15",
        amount=100.0,
        currency="USD",
        source_file="acme_2026_01_15.pdf",
    )
    verification = service.verify_record(
        record_id=1,
        expected_vendor="Acme Labs",
        expected_amount=1250.0,
        expected_currency="USD",
    )
    assert verification["verification_passed"] is False


def test_missing_or_invalid_invoice_file(tmp_path):
    bad_path = tmp_path / "missing.pdf"
    with pytest.raises(FileNotFoundError):
        read_invoice_pdf(bad_path)


def test_overdue_report_task_uses_finance_summary(tmp_path):
    db_path = tmp_path / "relay.db"
    service = FinanceService(db_path)
    service.seed_demo_records()

    controller = AgentController(db_path=db_path)
    task = controller.create_task("Show overdue invoices.")

    assert task["status"] == "completed"
    assert "overdue_report" in task
    assert task["overdue_report"]["count"] > 0
    assert task["overdue_report"]["records"]


def test_effective_invoice_status_rules():
    assert get_effective_invoice_status({"payment_status": "paid", "due_date": "2026-02-01"}, date(2026, 10, 26)) == "paid"
    assert get_effective_invoice_status({"payment_status": "outstanding", "due_date": "2026-02-01"}, date(2026, 10, 26)) == "overdue"
    assert get_effective_invoice_status({"payment_status": "outstanding", "due_date": "2026-10-27"}, date(2026, 10, 26)) == "outstanding"
    assert get_effective_invoice_status({"payment_status": "outstanding", "due_date": "2026-10-26"}, date(2026, 10, 26)) == "outstanding"
    assert get_effective_invoice_status({"payment_status": "outstanding", "due_date": None}, date(2026, 10, 26)) == "outstanding"
    assert get_effective_invoice_status({"payment_status": "outstanding", "due_date": "not-a-date"}, date(2026, 10, 26)) == "outstanding"


def test_overdue_metrics_match_ledger_statuses(tmp_path):
    db_path = tmp_path / "relay.db"
    service = FinanceService(db_path)
    service.create_record(
        vendor="Paid Vendor",
        invoice_number="INV-PAID-1",
        invoice_date="2026-01-01",
        due_date="2026-01-15",
        amount=250.0,
        currency="USD",
        source_file="paid.pdf",
        payment_status="paid",
    )
    service.create_record(
        vendor="Late Vendor",
        invoice_number="INV-LATE-1",
        invoice_date="2026-01-01",
        due_date="2026-02-01",
        amount=500.0,
        currency="USD",
        source_file="late.pdf",
        payment_status="outstanding",
    )
    service.create_record(
        vendor="Future Vendor",
        invoice_number="INV-FUTURE-1",
        invoice_date="2026-01-01",
        due_date="2026-12-01",
        amount=300.0,
        currency="USD",
        source_file="future.pdf",
        payment_status="outstanding",
    )

    records = service.list_records(reference_date=date(2026, 10, 26))
    statuses = {record["invoice_number"]: record["payment_status"] for record in records}
    assert statuses["INV-PAID-1"] == "paid"
    assert statuses["INV-LATE-1"] == "overdue"
    assert statuses["INV-FUTURE-1"] == "outstanding"

    summary = service.get_overdue_summary(reference_date=date(2026, 10, 26))
    assert summary["count"] == 1
    assert summary["records"][0]["invoice_number"] == "INV-LATE-1"


def test_persist_task_events_across_reconnect(tmp_path):
    db_path = tmp_path / "relay.db"
    controller = AgentController(db_path=db_path)
    task = controller.create_task("Process invoice INV-2026-081.")
    assert task["task_id"]
    reconnect = AgentController(db_path=db_path)
    persisted = reconnect.get_task(task["task_id"])
    assert persisted["task_id"] == task["task_id"]

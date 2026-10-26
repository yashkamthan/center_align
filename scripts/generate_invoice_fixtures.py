from __future__ import annotations

from pathlib import Path

from reportlab.pdfgen import canvas

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "invoices"
OUT.mkdir(parents=True, exist_ok=True)


def add_invoice(path: Path, vendor: str, invoice_number: str, invoice_date: str, due_date: str, amount: float, currency: str = "USD") -> None:
    c = canvas.Canvas(str(path), pagesize=(800, 900))
    c.setTitle(invoice_number)
    c.setFont("Helvetica-Bold", 22)
    c.drawString(60, 820, vendor)
    c.setFont("Helvetica", 14)
    c.drawString(60, 780, f"Invoice Number: {invoice_number}")
    c.drawString(60, 750, f"Invoice Date: {invoice_date}")
    c.drawString(60, 720, f"Due Date: {due_date}")
    c.drawString(60, 690, f"Amount: {amount:.2f} {currency}")
    c.drawString(60, 660, "Terms: Net 30")
    c.save()


samples = [
    ("acme_2026_01_15.pdf", "Acme Labs", "INV-2026-010", "2026-01-15", "2026-02-15", 1250.00),
    ("acme_2026_02_10.pdf", "Acme Labs", "INV-2026-025", "2026-02-10", "2026-03-10", 1700.00),
    ("northstar_2026_03_01.pdf", "Northstar Cloud", "INV-2026-110", "2026-03-01", "2026-04-01", 6800.00),
    ("northstar_2026_02_14.pdf", "Northstar Cloud", "INV-2026-095", "2026-02-14", "2026-03-14", 4200.00),
    ("vertex_2026_01_20.pdf", "Vertex Systems", "INV-2026-081", "2026-01-20", "2026-02-20", 1825.00),
    ("fluxworks_2026_02_01.pdf", "FluxWorks", "INV-2026-200", "2026-02-01", "2026-03-01", 900.00),
    ("bluepeak_2026_04_12.pdf", "BluePeak Health", "INV-2026-330", "2026-04-12", "2026-05-12", 930.00),
]

for filename, vendor, invoice_number, invoice_date, due_date, amount in samples:
    add_invoice(OUT / filename, vendor, invoice_number, invoice_date, due_date, amount)

print(f"Created {len(samples)} invoice PDFs in {OUT}")

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any

from pypdf import PdfReader


INVOICE_ROOT = Path(__file__).resolve().parents[2] / "data" / "invoices"


def list_invoice_files(invoice_root: str | Path | None = None) -> list[dict[str, Any]]:
    root = Path(invoice_root) if invoice_root else INVOICE_ROOT
    files: list[dict[str, Any]] = []
    if not root.exists():
        return files
    for path in sorted(root.glob("*.pdf")):
        try:
            extracted = extract_invoice_fields(path)
            files.append(
                {
                    "path": str(path),
                    "filename": path.name,
                    "vendor": extracted.get("vendor", "Unknown Vendor"),
                    "invoice_number": extracted.get("invoice_number", ""),
                    "invoice_date": extracted.get("invoice_date", ""),
                    "amount": extracted.get("amount"),
                    "currency": extracted.get("currency", "USD"),
                }
            )
        except Exception:
            files.append(
                {
                    "path": str(path),
                    "filename": path.name,
                    "vendor": "Unknown Vendor",
                    "invoice_number": "",
                    "invoice_date": "",
                    "amount": None,
                    "currency": "USD",
                }
            )
    return files


def safe_invoice_path(invoice_root: str | Path, filename: str) -> Path:
    root = Path(invoice_root).resolve()
    candidate = (root / filename).resolve()
    if root not in candidate.parents and candidate != root:
        raise ValueError(f"Unsafe invoice path: {filename}")
    return candidate


def read_invoice_pdf(path: str | Path) -> str:
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"Invoice file not found: {file_path}")
    if file_path.suffix.lower() != ".pdf":
        raise ValueError(f"Unsupported file type: {file_path}")
    reader = PdfReader(str(file_path))
    pages: list[str] = []
    for page in reader.pages:
        pages.append(page.extract_text() or "")
    text = "\n".join(pages).strip()
    if not text:
        raise ValueError(f"Could not extract text from PDF: {file_path}")
    return text


def _normalize_date(value: str) -> str:
    if not value:
        return ""
    for fmt in ["%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%Y/%m/%d"]:
        try:
            return datetime.strptime(value.strip(), fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return value.strip()


def _parse_amount(value: str) -> float:
    cleaned = re.sub(r"[^0-9.\-]", "", value)
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def extract_invoice_fields(path: str | Path) -> dict[str, Any]:
    text = read_invoice_pdf(path)
    vendor = ""
    invoice_number = ""
    invoice_date = ""
    due_date = ""
    amount = 0.0
    currency = "USD"

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for line in lines:
        if not vendor and re.search(r"(Acme Labs|Northstar Cloud|FluxWorks|Vertex Systems|Crestwood Labs|BluePeak Health)", line):
            vendor = re.search(r"(Acme Labs|Northstar Cloud|FluxWorks|Vertex Systems|Crestwood Labs|BluePeak Health)", line).group(1)
        if not invoice_number:
            match = re.search(r"(?:Invoice Number|Invoice #|Invoice No|Inv No)\s*[:#-]?\s*([A-Z0-9-]+)", line, flags=re.I)
            if match:
                invoice_number = match.group(1).upper()
        if not invoice_date:
            match = re.search(r"(?:Invoice Date|Date)\s*[:#-]?\s*(\d{4}-\d{2}-\d{2}|\d{2}/\d{2}/\d{4}|\d{4}/\d{2}/\d{2})", line, flags=re.I)
            if match:
                invoice_date = _normalize_date(match.group(1))
        if not due_date:
            match = re.search(r"(?:Due Date|Due)\s*[:#-]?\s*(\d{4}-\d{2}-\d{2}|\d{2}/\d{2}/\d{4}|\d{4}/\d{2}/\d{2})", line, flags=re.I)
            if match:
                due_date = _normalize_date(match.group(1))
        if amount == 0.0:
            match = re.search(r"(?:Amount|Total)\s*[:$]?\s*\(?([0-9,]+\.[0-9]{2})\)?\s*([A-Z]{3})?", line, flags=re.I)
            if match:
                amount = _parse_amount(match.group(1))
                currency = (match.group(2) or "USD").upper()

    if not vendor:
        vendor = lines[0] if lines else "Unknown Vendor"
    if not invoice_number:
        raise ValueError(f"Could not extract invoice number from: {path}")
    if not invoice_date:
        raise ValueError(f"Could not extract invoice date from: {path}")
    if amount == 0.0:
        raise ValueError(f"Could not extract invoice amount from: {path}")

    return {
        "vendor": vendor,
        "invoice_number": invoice_number,
        "invoice_date": invoice_date,
        "due_date": due_date,
        "amount": amount,
        "currency": currency,
        "source_file": str(Path(path).name),
    }

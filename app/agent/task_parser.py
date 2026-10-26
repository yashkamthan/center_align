from __future__ import annotations

import re


def interpret_task(task_text: str) -> dict[str, str | bool | None]:
    text = task_text.strip()
    if not text:
        raise ValueError("Task text cannot be empty.")

    lowered = text.lower()
    if "latest invoice" in lowered or "most recent invoice" in lowered:
        vendor = None
        if " from " in lowered:
            vendor_match = re.search(r"from\s+([A-Za-z][A-Za-z0-9&.\- ]+?)(?:\s+and\s+|\s+for\s+|\.|$)", text, flags=re.I)
            if vendor_match:
                vendor = vendor_match.group(1).strip().rstrip(".")
        if not vendor:
            raise ValueError("I need the vendor name to process the latest invoice.")
        return {"action": "process_latest_invoice", "vendor": vendor, "invoice_number": None, "requires_approval": False}

    invoice_match = re.search(r"invoice\s+(?:no\.?\s*|number\s+)?([A-Z0-9-]+)", text, flags=re.I)
    if invoice_match:
        return {"action": "process_invoice_number", "vendor": None, "invoice_number": invoice_match.group(1).upper(), "requires_approval": False}

    if "extract" in lowered and "invoice" in lowered:
        vendor = None
        if " from " in lowered:
            vendor_match = re.search(r"from\s+([A-Za-z][A-Za-z0-9&.\- ]+?)(?:\s+and\s+|\s+for\s+|$)", text, flags=re.I)
            if vendor_match:
                vendor = vendor_match.group(1).strip()
        return {"action": "extract_invoice_fields", "vendor": vendor, "invoice_number": None, "requires_approval": False}

    if ("overdue" in lowered and ("invoice" in lowered or "invoices" in lowered or "report" in lowered or "show" in lowered or "list" in lowered)) or ("show" in lowered and "overdue" in lowered):
        return {"action": "show_overdue_invoices", "vendor": None, "invoice_number": None, "requires_approval": False}

    if "already recorded" in lowered or "duplicate" in lowered:
        return {"action": "check_duplicate", "vendor": None, "invoice_number": None, "requires_approval": False}

    raise ValueError("This task is not supported. Please specify a vendor or invoice number to process.")

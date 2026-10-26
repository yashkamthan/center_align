from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class TaskRequest(BaseModel):
    task: str = Field(..., min_length=3)
    inject_failure: bool = False


class ApprovalRequest(BaseModel):
    decision: Literal["approve", "reject"]


class FinanceRecord(BaseModel):
    vendor: str
    invoice_number: str
    invoice_date: str
    due_date: str | None = None
    amount: float
    currency: str = "USD"
    source_file: str

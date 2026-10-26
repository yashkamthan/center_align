from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


def get_db_connection(db_path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def ensure_schema(db_path: str | Path) -> None:
    conn = get_db_connection(db_path)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS tasks (
            id TEXT PRIMARY KEY,
            request TEXT NOT NULL,
            status TEXT NOT NULL,
            summary TEXT,
            reason TEXT,
            parsed_json TEXT,
            context_json TEXT,
            approval_required INTEGER DEFAULT 0,
            approval_reason TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS execution_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            tool_name TEXT,
            outcome TEXT NOT NULL,
            details_json TEXT,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS finance_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            vendor TEXT NOT NULL,
            invoice_number TEXT NOT NULL,
            invoice_date TEXT NOT NULL,
            due_date TEXT,
            amount REAL NOT NULL,
            currency TEXT NOT NULL,
            source_file TEXT,
            payment_status TEXT NOT NULL DEFAULT 'outstanding',
            created_at TEXT NOT NULL,
            UNIQUE(vendor, invoice_number)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS approvals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT NOT NULL,
            decision TEXT,
            reason TEXT,
            created_at TEXT NOT NULL
        )
        """
    )

    columns = [row[1] for row in conn.execute("PRAGMA table_info(finance_records)").fetchall()]
    if "payment_status" not in columns:
        conn.execute("ALTER TABLE finance_records ADD COLUMN payment_status TEXT NOT NULL DEFAULT 'outstanding'")

    conn.commit()
    conn.close()


def record_task_event(db_path: str | Path, task_id: str, event_type: str, tool_name: str | None, outcome: str, details: dict[str, Any]) -> None:
    conn = get_db_connection(db_path)
    conn.execute(
        """
        INSERT INTO execution_events (task_id, event_type, tool_name, outcome, details_json, created_at)
        VALUES (?, ?, ?, ?, ?, datetime('now'))
        """,
        (task_id, event_type, tool_name, outcome, json.dumps(details, default=str)),
    )
    conn.commit()
    conn.close()


def fetch_task(db_path: str | Path, task_id: str) -> dict[str, Any] | None:
    conn = get_db_connection(db_path)
    row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    conn.close()
    if not row:
        return None
    return dict(row)


def fetch_task_events(db_path: str | Path, task_id: str) -> list[dict[str, Any]]:
    conn = get_db_connection(db_path)
    rows = conn.execute(
        "SELECT * FROM execution_events WHERE task_id = ? ORDER BY created_at ASC, id ASC",
        (task_id,),
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]

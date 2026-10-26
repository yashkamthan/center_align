#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db.database import ensure_schema, get_db_connection
from app.services.finance import FinanceService

DEFAULT_DB = ROOT / "data" / "relay.db"


def backup_database(db_path: Path) -> Path | None:
    if not db_path.exists():
        return None
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = db_path.with_name(f"{db_path.stem}_{ts}.bak")
    shutil.copy2(db_path, backup_path)
    return backup_path


def reset_demo_database(db_path: Path, force: bool = False) -> tuple[int, int, Path | None]:
    if db_path.exists() and not force:
        response = input(
            f"This will permanently reset the local demo database at {db_path}. "
            "A backup will be created first. Type RESET to continue: "
        )
        if response.strip() != "RESET":
            raise SystemExit("Reset cancelled.")

    backup_path = backup_database(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        try:
            db_path.unlink()
        except PermissionError as exc:
            raise SystemExit(
                f"Could not reset {db_path} because it is currently in use by the running Relay app. "
                "Stop the app server and run this script again."
            ) from exc

    ensure_schema(db_path)
    service = FinanceService(db_path=db_path)
    records = service.seed_demo_records()

    conn = get_db_connection(db_path)
    conn.close()

    return len(records), service.get_metrics()["total_records"], backup_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Reset the local Relay demo database and reseed the fictional ledger.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="Path to the local SQLite demo database to reset.")
    parser.add_argument("--force", action="store_true", help="Skip the confirmation prompt and reset immediately.")
    args = parser.parse_args()

    db_path = args.db.resolve() if args.db.is_absolute() else (ROOT / args.db).resolve()
    print(f"Target database: {db_path}")
    print("Warning: this reset changes local demo data only; it does not modify the source PDF fixtures.")

    try:
        seeded_count, total_records, backup_path = reset_demo_database(db_path, force=args.force)
    except SystemExit as exc:
        print(str(exc))
        return

    if backup_path:
        print(f"Backup created: {backup_path}")
    else:
        print("No existing demo database was found; creating a new one.")

    print(f"Seeded records: {seeded_count}")
    print(f"Finance records after reset: {total_records}")
    print(f"Reset complete. Demo database is now ready for scenario testing.")


if __name__ == "__main__":
    main()

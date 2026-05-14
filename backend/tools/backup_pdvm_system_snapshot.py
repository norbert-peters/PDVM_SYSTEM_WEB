"""Erstellt einen vollständigen JSONL-Snapshot der pdvm_system Datenbank.

Usage:
  python tools/backup_pdvm_system_snapshot.py
  python tools/backup_pdvm_system_snapshot.py --output-dir ../database/backups
"""
from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
from pathlib import Path
import sys

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import asyncpg

from app.core.connection_manager import ConnectionManager


async def _get_db_url() -> str:
    cfg = await ConnectionManager.get_system_config("pdvm_system")
    return cfg.to_url()


async def main_async(output_dir: Path) -> int:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_file = output_dir / f"pdvm_system_snapshot_{stamp}.jsonl"

    db_url = await _get_db_url()
    conn = await asyncpg.connect(db_url)

    table_rows = 0
    table_count = 0
    try:
        tables = await conn.fetch(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            ORDER BY table_name
            """
        )
        table_names = [str(r["table_name"]).strip() for r in tables if str(r["table_name"]).strip()]

        with out_file.open("w", encoding="utf-8") as fh:
            for table_name in table_names:
                rows = await conn.fetch(f"SELECT row_to_json(t)::text AS j FROM (SELECT * FROM {table_name}) t")
                row_count = 0
                for row in rows:
                    payload = {
                        "table": table_name,
                        "row": json.loads(row["j"]),
                    }
                    fh.write(json.dumps(payload, ensure_ascii=False) + "\n")
                    row_count += 1
                table_rows += row_count
                table_count += 1

        print(f"✅ Snapshot erstellt: {out_file}")
        print(f"📊 Tabellen: {table_count} | Zeilen: {table_rows}")
        return 0
    finally:
        await conn.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create full pdvm_system JSONL snapshot")
    parser.add_argument(
        "--output-dir",
        default=str((BACKEND_DIR.parent / "database" / "backups").resolve()),
        help="Ausgabeordner für Snapshot-Datei",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    raise SystemExit(asyncio.run(main_async(Path(args.output_dir))))

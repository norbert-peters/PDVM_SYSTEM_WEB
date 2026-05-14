"""Bootstrap fuer Workflow Draft-Container Tabellen in pdvm_system.

Usage:
  python tools/bootstrap_workflow_draft_tables.py
  python tools/bootstrap_workflow_draft_tables.py --apply
  python tools/bootstrap_workflow_draft_tables.py --json
"""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any, Dict, List

import sys

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import asyncpg

from app.core.connection_manager import ConnectionManager
from app.core.pdvm_table_schema import PDVM_TABLE_COLUMNS, PDVM_TABLE_INDEXES


TARGET_TABLES = [
    "dev_workflow_draft",
    "dev_workflow_draft_item",
]


async def _get_db_url(cli_db_url: str | None) -> str:
    if cli_db_url:
        return cli_db_url
    cfg = await ConnectionManager.get_system_config("pdvm_system")
    return cfg.to_url()


async def _table_exists(conn: asyncpg.Connection, table_name: str) -> bool:
    return bool(
        await conn.fetchval(
            """
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = $1
            )
            """,
            table_name,
        )
    )


async def main_async(args: argparse.Namespace) -> int:
    db_url = await _get_db_url(args.db_url)
    conn = await asyncpg.connect(db_url)
    try:
        summary: Dict[str, Any] = {
            "total": len(TARGET_TABLES),
            "created": [],
            "existing": [],
            "errors": [],
        }

        if args.apply:
            await conn.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')

        for table_name in TARGET_TABLES:
            try:
                exists = await _table_exists(conn, table_name)
                if exists:
                    summary["existing"].append(table_name)
                    continue

                if args.apply:
                    columns = ", ".join([f"{col} {definition}" for col, definition in PDVM_TABLE_COLUMNS.items()])
                    await conn.execute(
                        f"""
                        CREATE TABLE public.{table_name} (
                            {columns}
                        )
                        """
                    )
                    for idx_col in PDVM_TABLE_INDEXES:
                        if idx_col == "daten":
                            await conn.execute(
                                f"""
                                CREATE INDEX IF NOT EXISTS idx_{table_name}_{idx_col}
                                ON public.{table_name} USING GIN({idx_col})
                                """
                            )
                        else:
                            await conn.execute(
                                f"""
                                CREATE INDEX IF NOT EXISTS idx_{table_name}_{idx_col}
                                ON public.{table_name}({idx_col})
                                """
                            )

                summary["created"].append(table_name)
            except Exception as exc:
                summary["errors"].append(f"{table_name}: {exc}")

        summary["ok"] = len(summary["errors"]) == 0

        if args.json:
            print(json.dumps(summary, indent=2, ensure_ascii=False))
        else:
            mode = "APPLY" if args.apply else "DRY-RUN"
            print(f"=== Workflow Draft Table Bootstrap ({mode}) ===")
            print(f"Total:    {summary['total']}")
            print(f"Created:  {len(summary['created'])}")
            print(f"Existing: {len(summary['existing'])}")
            print(f"Errors:   {len(summary['errors'])}")
            if summary["created"]:
                print("\nCreated:")
                for t in summary["created"]:
                    print(f"- {t}")
            if summary["existing"]:
                print("\nExisting:")
                for t in summary["existing"]:
                    print(f"- {t}")
            if summary["errors"]:
                print("\nError details:")
                for e in summary["errors"]:
                    print(f"- {e}")

        return 0 if summary["ok"] else 2
    finally:
        await conn.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Bootstrap workflow draft tables")
    parser.add_argument("--db-url", default=None, help="Optional PostgreSQL URL")
    parser.add_argument("--apply", action="store_true", help="Write changes (default dry-run)")
    parser.add_argument("--json", action="store_true", help="Print JSON output")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main_async(parse_args())))

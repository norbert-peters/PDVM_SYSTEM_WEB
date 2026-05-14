"""Seed fuer Workflow Draft Blueprint Artefakte (Dialog/View/Frame).

Usage:
  python tools/seed_workflow_draft_blueprint.py
  python tools/seed_workflow_draft_blueprint.py --apply
  python tools/seed_workflow_draft_blueprint.py --apply --force-update
"""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any, Dict

import sys

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import asyncpg

from app.core.connection_manager import ConnectionManager
from tools.workflow_draft_blueprint_registry import (
    BlueprintSpec,
    get_workflow_draft_blueprint_specs,
    with_resolved_self_fields,
)


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


async def _load_by_uid(conn: asyncpg.Connection, spec: BlueprintSpec) -> Dict[str, Any] | None:
    row = await conn.fetchrow(
        f"SELECT uid, name, daten FROM {spec.table_name} WHERE uid = $1",
        spec.uid,
    )
    return dict(row) if row else None


async def _load_by_name(conn: asyncpg.Connection, spec: BlueprintSpec) -> Dict[str, Any] | None:
    row = await conn.fetchrow(
        f"SELECT uid, name, daten FROM {spec.table_name} WHERE name = $1 ORDER BY modified_at DESC LIMIT 1",
        spec.name,
    )
    return dict(row) if row else None


async def _insert_record(conn: asyncpg.Connection, spec: BlueprintSpec, data: Dict[str, Any]) -> None:
    payload = json.dumps(data, ensure_ascii=False)
    await conn.execute(
        f"""
        INSERT INTO {spec.table_name} (uid, daten, name, historisch, created_at, modified_at)
        VALUES ($1::uuid, $2::jsonb, $3, 0, NOW(), NOW())
        """,
        spec.uid,
        payload,
        spec.name,
    )


async def _update_record(conn: asyncpg.Connection, spec: BlueprintSpec, data: Dict[str, Any]) -> None:
    payload = json.dumps(data, ensure_ascii=False)
    await conn.execute(
        f"""
        UPDATE {spec.table_name}
        SET daten = $2::jsonb,
            name = $3,
            modified_at = NOW()
        WHERE uid = $1::uuid
        """,
        spec.uid,
        payload,
        spec.name,
    )


async def main_async(args: argparse.Namespace) -> int:
    db_url = await _get_db_url(args.db_url)
    specs = get_workflow_draft_blueprint_specs()

    conn = await asyncpg.connect(db_url)
    try:
        summary = {
            "total": len(specs),
            "inserted": 0,
            "updated": 0,
            "skipped_existing": 0,
            "skipped_name_conflict": 0,
            "errors": [],
        }

        for spec in specs:
            try:
                if not await _table_exists(conn, spec.table_name):
                    summary["errors"].append(f"Tabelle fehlt: {spec.table_name}")
                    continue

                data = with_resolved_self_fields(spec)
                existing_uid = await _load_by_uid(conn, spec)

                if existing_uid:
                    if args.force_update:
                        if args.apply:
                            await _update_record(conn, spec, data)
                        summary["updated"] += 1
                    else:
                        summary["skipped_existing"] += 1
                    continue

                existing_name = await _load_by_name(conn, spec)
                if existing_name:
                    summary["skipped_name_conflict"] += 1
                    continue

                if args.apply:
                    await _insert_record(conn, spec, data)
                summary["inserted"] += 1
            except Exception as exc:
                summary["errors"].append(f"{spec.table_name}/{spec.name}: {exc}")

        mode = "APPLY" if args.apply else "DRY-RUN"
        print(f"=== Seed Workflow Draft Blueprint ({mode}) ===")
        print(f"Total:                 {summary['total']}")
        print(f"Inserted:              {summary['inserted']}")
        print(f"Updated:               {summary['updated']}")
        print(f"Skipped (existing):    {summary['skipped_existing']}")
        print(f"Skipped (name conflict): {summary['skipped_name_conflict']}")
        print(f"Errors:                {len(summary['errors'])}")
        if summary["skipped_existing"] > 0 and not args.force_update:
            print("Hinweis: Bestehende UIDs wurden nicht aktualisiert. Fuer Ueberschreiben bitte --force-update verwenden.")
        if summary["errors"]:
            print("\nError details:")
            for item in summary["errors"]:
                print(f"- {item}")

        return 0 if not summary["errors"] else 2
    finally:
        await conn.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed workflow draft blueprint")
    parser.add_argument("--db-url", default=None, help="Optional PostgreSQL URL")
    parser.add_argument("--apply", action="store_true", help="Write changes to DB (default is dry-run)")
    parser.add_argument("--force-update", action="store_true", help="Update existing UID records")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main_async(parse_args())))

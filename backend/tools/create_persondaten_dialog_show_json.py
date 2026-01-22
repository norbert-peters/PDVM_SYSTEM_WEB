"""Create a PDVM dialog + frame for persondaten (show_json) in pdvm_system.

- Inserts into sys_dialogdaten and sys_framedaten (schema auto-detected).
- Dialog ROOT references:
  - TABLE = persondaten
  - VIEW_GUID = provided view guid
  - FRAME_GUID = created frame guid
  - EDIT_TYPE = show_json

Usage:
  python backend/tools/create_persondaten_dialog_show_json.py \
    --view-guid a7cc4cd1-7d34-46ca-a371-011c9bf608ea

Optional:
  --dialog-uid <uuid>  (so you can wire menu deterministically)
  --frame-uid <uuid>
  --db-url <postgres-url>  (defaults to ConnectionManager.get_system_config('pdvm_system'))

This script is safe to re-run with the same --dialog-uid/--frame-uid: it upserts by PK.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import uuid
from pathlib import Path
from typing import Iterable, Set, Tuple

import sys

# Allow running this script from repo root (adds `backend/` to sys.path)
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import asyncpg

from app.core.connection_manager import ConnectionManager


async def _first_existing_relation(conn: asyncpg.Connection, candidates: Iterable[str]) -> str:
    for rel in candidates:
        found = await conn.fetchval("SELECT to_regclass($1)", rel)
        if found:
            return rel
    raise RuntimeError(f"Could not find table. Tried: {', '.join(candidates)}")


async def _get_columns(conn: asyncpg.Connection, schema: str, table: str) -> Set[str]:
    rows = await conn.fetch(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = $1 AND table_name = $2
        """,
        schema,
        table,
    )
    return {r["column_name"] for r in rows}


def _split_schema_table(relation: str) -> Tuple[str, str]:
    if "." in relation:
        s, t = relation.split(".", 1)
        return s, t
    return "public", relation


def _pick_pk(cols: Set[str]) -> str:
    if "uid" in cols:
        return "uid"
    if "uuid" in cols:
        return "uuid"
    raise RuntimeError("No uid/uuid PK column found")


async def _upsert_jsonb_record(
    conn: asyncpg.Connection,
    *,
    relation: str,
    cols: Set[str],
    pk_col: str,
    record_id: uuid.UUID,
    name: str,
    daten: dict,
) -> None:
    # Columns we will write
    insert_cols = [pk_col, "daten", "name"]
    if "historisch" in cols:
        insert_cols.append("historisch")

    # Optional timestamp columns
    if "created_at" in cols:
        insert_cols.append("created_at")
    if "modified_at" in cols:
        insert_cols.append("modified_at")

    values = [record_id, json.dumps(daten), name]
    placeholders = ["$1", "$2::jsonb", "$3"]

    if "historisch" in cols:
        # fixed literal is fine
        pass

    # For created_at/modified_at, use NOW() literals
    if "created_at" in cols:
        pass
    if "modified_at" in cols:
        pass

    # Build INSERT ... ON CONFLICT
    set_parts = [
        "daten = EXCLUDED.daten",
        "name = EXCLUDED.name",
    ]
    if "historisch" in cols:
        set_parts.append("historisch = EXCLUDED.historisch")
    if "modified_at" in cols:
        set_parts.append("modified_at = NOW()")

    # Insert expression list matches insert_cols
    exprs = []
    exprs.append("$1")
    exprs.append("$2::jsonb")
    exprs.append("$3")

    if "historisch" in cols:
        exprs.append("0")
    if "created_at" in cols:
        exprs.append("NOW()")
    if "modified_at" in cols:
        exprs.append("NOW()")

    query = f"""
        INSERT INTO {relation} ({', '.join(insert_cols)})
        VALUES ({', '.join(exprs)})
        ON CONFLICT ({pk_col}) DO UPDATE
        SET {', '.join(set_parts)}
    """

    await conn.execute(query, *values)


async def main() -> int:
    parser = argparse.ArgumentParser(description="Create sys_dialogdaten + sys_framedaten for persondaten (show_json)")
    parser.add_argument("--view-guid", required=True, help="Existing sys_viewdaten UID to use for Tab 1")
    parser.add_argument("--dialog-uid", help="Optional dialog UID to use")
    parser.add_argument("--frame-uid", help="Optional frame UID to use")
    parser.add_argument("--dialog-name", default="Personendaten Dialog", help="Display name for sys_dialogdaten")
    parser.add_argument("--frame-name", default="Personendaten Edit (JSON)", help="Display name for sys_framedaten")
    parser.add_argument("--db-url", default=None, help="Optional Postgres URL for pdvm_system")
    args = parser.parse_args()

    # Validate GUIDs
    view_guid = str(uuid.UUID(args.view_guid))
    dialog_id = uuid.UUID(args.dialog_uid) if args.dialog_uid else uuid.uuid4()
    frame_id = uuid.UUID(args.frame_uid) if args.frame_uid else uuid.uuid4()

    if args.db_url:
        db_url = args.db_url
    else:
        cfg = await ConnectionManager.get_system_config("pdvm_system")
        db_url = cfg.to_url()

    dialog_daten = {
        "ROOT": {
            "TABLE": "persondaten",
            "TABS": 2,
            "VIEW_GUID": view_guid,
            "FRAME_GUID": str(frame_id),
            "EDIT_TYPE": "show_json",
            "SELECTION_MODE": "single",
            "OPEN_EDIT": "button",
        }
    }

    frame_daten = {
        "ROOT": {
            "DIALOG_GUID": str(dialog_id),
            "EDIT_TYPE": "show_json",
        },
        "FIELDS": {},
    }

    conn = await asyncpg.connect(db_url)
    try:
        dialog_rel = await _first_existing_relation(
            conn,
            ["pdvm_system.sys_dialogdaten", "public.sys_dialogdaten", "sys_dialogdaten"],
        )
        frame_rel = await _first_existing_relation(
            conn,
            ["pdvm_system.sys_framedaten", "public.sys_framedaten", "sys_framedaten"],
        )

        dialog_schema, dialog_table = _split_schema_table(dialog_rel)
        frame_schema, frame_table = _split_schema_table(frame_rel)

        dialog_cols = await _get_columns(conn, dialog_schema, dialog_table)
        frame_cols = await _get_columns(conn, frame_schema, frame_table)

        dialog_pk = _pick_pk(dialog_cols)
        frame_pk = _pick_pk(frame_cols)

        # Upsert both
        await _upsert_jsonb_record(
            conn,
            relation=dialog_rel,
            cols=dialog_cols,
            pk_col=dialog_pk,
            record_id=dialog_id,
            name=args.dialog_name,
            daten=dialog_daten,
        )

        await _upsert_jsonb_record(
            conn,
            relation=frame_rel,
            cols=frame_cols,
            pk_col=frame_pk,
            record_id=frame_id,
            name=args.frame_name,
            daten=frame_daten,
        )

        print("✅ Dialog + Frame created/updated")
        print(f"   sys_dialogdaten: {dialog_rel}  {dialog_pk}={dialog_id}")
        print(f"   sys_framedaten:  {frame_rel}  {frame_pk}={frame_id}")
        print(f"   ROOT.TABLE: persondaten")
        print(f"   ROOT.VIEW_GUID: {view_guid}")
        print(f"   ROOT.EDIT_TYPE: show_json")

    finally:
        await conn.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

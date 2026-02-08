"""Create sys_viewdaten + sys_dialogdaten + sys_framedaten for import_data.

Usage:
  python backend/tools/create_import_data_dialog.py
  python backend/tools/create_import_data_dialog.py --dialog-uid <uuid> --view-uid <uuid> --frame-uid <uuid>
"""
from __future__ import annotations

import argparse
import asyncio
import json
import uuid
from pathlib import Path
from typing import Iterable, Set, Tuple

import sys

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import asyncpg

from app.core.connection_manager import ConnectionManager


def _build_view_daten(view_guid: str) -> dict:
    return {
        "ROOT": {
            "NO_DATA": True,
            "VIEW_NAME": "Import Data",
            "VIEW_GUID": view_guid,
            "HEADER_TEXT": "Import Data",
            "PROJECTION_MODE": "standard",
            "ALLOW_FILTER": True,
            "ALLOW_SORT": True,
            "DEFAULT_SORT_COLUMN": "",
            "DEFAULT_SORT_REVERSE": False,
            "TABLE": "sys_ext_table",
        },
        "SYSTEM": {
            "11111111-1111-1111-1111-111111111111": {
                "gruppe": "SYSTEM",
                "feld": "uid",
                "label": "UID",
                "type": "string",
                "control_type": "base",
                "show": True,
                "display_order": 1,
                "searchable": True,
                "sortable": True,
                "filterType": "contains",
                "table": "sys_ext_table",
            },
            "22222222-2222-2222-2222-222222222222": {
                "gruppe": "SYSTEM",
                "feld": "name",
                "label": "Name",
                "type": "string",
                "control_type": "base",
                "show": True,
                "display_order": 2,
                "searchable": True,
                "sortable": True,
                "filterType": "contains",
                "table": "sys_ext_table",
            },
        },
    }


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
    insert_cols = [pk_col, "daten", "name"]
    if "historisch" in cols:
        insert_cols.append("historisch")
    if "created_at" in cols:
        insert_cols.append("created_at")
    if "modified_at" in cols:
        insert_cols.append("modified_at")

    values = [record_id, json.dumps(daten), name]

    set_parts = ["daten = EXCLUDED.daten", "name = EXCLUDED.name"]
    if "historisch" in cols:
        set_parts.append("historisch = EXCLUDED.historisch")
    if "modified_at" in cols:
        set_parts.append("modified_at = NOW()")

    exprs = ["$1", "$2::jsonb", "$3"]
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
    parser = argparse.ArgumentParser(description="Create import_data dialog + view + frame")
    parser.add_argument("--view-uid", help="Optional view UID")
    parser.add_argument("--dialog-uid", help="Optional dialog UID")
    parser.add_argument("--frame-uid", help="Optional frame UID")
    parser.add_argument("--dialog-name", default="Import Data Dialog", help="Dialog name")
    parser.add_argument("--frame-name", default="Import Data Frame", help="Frame name")
    parser.add_argument("--view-name", default="Import Data View", help="View name")
    parser.add_argument("--db-url", default=None, help="Optional Postgres URL for pdvm_system")
    args = parser.parse_args()

    view_id = uuid.UUID(args.view_uid) if args.view_uid else uuid.uuid4()
    dialog_id = uuid.UUID(args.dialog_uid) if args.dialog_uid else uuid.uuid4()
    frame_id = uuid.UUID(args.frame_uid) if args.frame_uid else uuid.uuid4()

    if args.db_url:
        db_url = args.db_url
    else:
        cfg = await ConnectionManager.get_system_config("pdvm_system")
        db_url = cfg.to_url()

    view_daten = _build_view_daten(str(view_id))
    view_name = args.view_name

    dialog_daten = {
        "ROOT": {
            "TABLE": "sys_ext_table",
            "TABS": 2,
            "VIEW_GUID": str(view_id),
            "FRAME_GUID": str(frame_id),
            "EDIT_TYPE": "import_data",
            "SELECTION_MODE": "single",
            "OPEN_EDIT": "button",
        }
    }

    frame_daten = {
        "ROOT": {
            "DIALOG_GUID": str(dialog_id),
            "EDIT_TYPE": "import_data",
        },
        "FIELDS": {},
    }

    conn = await asyncpg.connect(db_url)
    try:
        view_rel = await _first_existing_relation(
            conn,
            ["pdvm_system.sys_viewdaten", "public.sys_viewdaten", "sys_viewdaten"],
        )
        dialog_rel = await _first_existing_relation(
            conn,
            ["pdvm_system.sys_dialogdaten", "public.sys_dialogdaten", "sys_dialogdaten"],
        )
        frame_rel = await _first_existing_relation(
            conn,
            ["pdvm_system.sys_framedaten", "public.sys_framedaten", "sys_framedaten"],
        )

        view_schema, view_table = _split_schema_table(view_rel)
        dialog_schema, dialog_table = _split_schema_table(dialog_rel)
        frame_schema, frame_table = _split_schema_table(frame_rel)

        view_cols = await _get_columns(conn, view_schema, view_table)
        dialog_cols = await _get_columns(conn, dialog_schema, dialog_table)
        frame_cols = await _get_columns(conn, frame_schema, frame_table)

        view_pk = _pick_pk(view_cols)
        dialog_pk = _pick_pk(dialog_cols)
        frame_pk = _pick_pk(frame_cols)

        await _upsert_jsonb_record(
            conn,
            relation=view_rel,
            cols=view_cols,
            pk_col=view_pk,
            record_id=view_id,
            name=view_name,
            daten=view_daten,
        )

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

        print("✅ import_data View + Dialog + Frame erstellt")
        print(f"   sys_viewdaten: {view_rel}  {view_pk}={view_id}")
        print(f"   sys_dialogdaten: {dialog_rel}  {dialog_pk}={dialog_id}")
        print(f"   sys_framedaten: {frame_rel}  {frame_pk}={frame_id}")
        print("   ROOT.EDIT_TYPE: import_data")

    finally:
        await conn.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

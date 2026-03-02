"""Create the first concrete sys_control_dict dialog (View + Frame + Dialog) for pdvm_edit.

Usage:
  python backend/tools/create_sys_control_dict_dialog.py
  python backend/tools/create_sys_control_dict_dialog.py --dialog-uid <uuid> --view-uid <uuid> --frame-uid <uuid>

The script is idempotent (upsert by PK) and follows current Dialog V2 conventions:
- Dialog tab 1: MODULE=view
- Dialog tab 2: MODULE=edit, EDIT_TYPE=pdvm_edit
- New-record flow uses generic Draft API (defined in backend API), no special create path.
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
from tools.setup_linear_frames import _build_sys_control_dict_frame

DEFAULT_DIALOG_UID = "9f06711e-4ad8-4ea4-9837-2f40f3a6f101"
DEFAULT_VIEW_UID = "9f06711e-4ad8-4ea4-9837-2f40f3a6f102"
DEFAULT_FRAME_UID = "9f06711e-4ad8-4ea4-9837-2f40f3a6f103"


def _control_template_555_payload() -> dict:
    return {
        "TEMPLATES": {
            "CONTROL": {
                "NAME": "",
                "TYPE": "",
                "FIELD": "",
                "LABEL": "",
                "TABLE": "",
                "GRUPPE": "",
                "ABDATUM": False,
                "DEFAULT": "",
                "SORTABLE": True,
                "READ_ONLY": False,
                "HISTORICAL": False,
                "SEARCHABLE": True,
                "EXPERT_MODE": True,
                "FILTER_TYPE": "contains",
                "PARENT_GUID": None,
                "SOURCE_PATH": "root",
                "DISPLAY_SHOW": True,
                "EXPERT_ORDER": 0,
                "DISPLAY_ORDER": 0,
                "SORT_DIRECTION": "asc",
                "SORT_BY_ORIGINAL": False,
                "FIELDS_ELEMENTS": {},
                "CONFIGS_ELEMENTS": {},
            },
            "CONFIGS_ELEMENTS": {
                "KEY": "",
                "FIELD": "",
                "TABLE": "",
                "GRUPPE": "",
                "ELM_TYPE": "",
            },
            "FIELDS_ELEMENTS": {
                "BY_FRAME_GUID": True,
            },
        }
    }


def _build_view_daten(view_guid: str) -> dict:
    return {
        "ROOT": {
            "NO_DATA": False,
            "VIEW_NAME": "Control Dictionary",
            "VIEW_GUID": view_guid,
            "HEADER_TEXT": "Control Dictionary",
            "PROJECTION_MODE": "standard",
            "ALLOW_FILTER": True,
            "ALLOW_SORT": True,
            "DEFAULT_SORT_COLUMN": "name",
            "DEFAULT_SORT_REVERSE": False,
            "TABLE": "sys_control_dict",
        },
        "SYSTEM": {
            "11111111-1111-1111-1111-111111111111": {
                "gruppe": "SYSTEM",
                "feld": "uid",
                "label": "UID",
                "type": "string",
                "control_type": "base",
                "show": False,
                "display_order": 1,
                "searchable": True,
                "sortable": True,
                "filterType": "contains",
                "table": "sys_control_dict",
            },
            "22222222-2222-2222-2222-222222222222": {
                "gruppe": "SYSTEM",
                "feld": "name",
                "label": "Name",
                "type": "string",
                "control_type": "base",
                "show": True,
                            "NO_DATA": False,
                "searchable": True,
                "sortable": True,
                "filterType": "contains",
                "table": "sys_control_dict",
            },
            "33333333-3333-3333-3333-333333333333": {
                "gruppe": "ROOT",
                "feld": "table",
                "label": "Tabelle",
                "type": "string",
                "control_type": "base",
                "show": True,
                "display_order": 3,
                "searchable": True,
                "sortable": True,
                "filterType": "contains",
                "table": "sys_control_dict",
            },
            "44444444-4444-4444-4444-444444444444": {
                "gruppe": "ROOT",
                "feld": "gruppe",
                "label": "Gruppe",
                "type": "string",
                "control_type": "base",
                "show": True,
                "display_order": 4,
                "searchable": True,
                "sortable": True,
                "filterType": "contains",
                "table": "sys_control_dict",
            },
            "55555555-6666-7777-8888-999999999999": {
                "gruppe": "ROOT",
                "feld": "type",
                "label": "Typ",
                "type": "string",
                "control_type": "base",
                "show": True,
                "display_order": 5,
                "searchable": True,
                "sortable": True,
                "filterType": "contains",
                "table": "sys_control_dict",
            },
        },
    }


def _build_frame_daten(dialog_guid: str) -> dict:
    return _build_sys_control_dict_frame(_control_template_555_payload())


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
    parser = argparse.ArgumentParser(description="Create first sys_control_dict dialog + view + frame")
    parser.add_argument("--view-uid", default=DEFAULT_VIEW_UID, help="Optional view UID")
    parser.add_argument("--dialog-uid", default=DEFAULT_DIALOG_UID, help="Optional dialog UID")
    parser.add_argument("--frame-uid", default=DEFAULT_FRAME_UID, help="Optional frame UID")
    parser.add_argument("--dialog-name", default="sys_control_dict Dialog", help="Dialog name")
    parser.add_argument("--frame-name", default="sys_control_dict Frame", help="Frame name")
    parser.add_argument("--view-name", default="sys_control_dict View", help="View name")
    parser.add_argument("--db-url", default=None, help="Optional Postgres URL for pdvm_system")
    args = parser.parse_args()

    view_id = uuid.UUID(args.view_uid)
    dialog_id = uuid.UUID(args.dialog_uid)
    frame_id = uuid.UUID(args.frame_uid)

    if args.db_url:
        db_url = args.db_url
    else:
        cfg = await ConnectionManager.get_system_config("pdvm_system")
        db_url = cfg.to_url()

    view_daten = _build_view_daten(str(view_id))
    dialog_daten = {
        "ROOT": {
            "SELF_GUID": str(dialog_id),
            "SELF_NAME": args.dialog_name,
            "TABLE": "sys_control_dict",
            "DIALOG_TYPE": "norm",
            "TABS": 2,
            "EDIT_TYPE": "pdvm_edit",
            "TAB_ELEMENTS": {
                "TAB_01": {
                    "GUID": str(view_id),
                    "HEAD": "Liste",
                    "TABLE": "sys_control_dict",
                    "MODULE": "view",
                    "EDIT_TYPE": "pdvm_edit",
                    "OPEN_EDIT": "double_click",
                    "SELECTION_MODE": "single",
                },
                "TAB_02": {
                    "GUID": str(frame_id),
                    "HEAD": "Bearbeiten",
                    "TABLE": "sys_control_dict",
                    "MODULE": "edit",
                    "EDIT_TYPE": "pdvm_edit",
                    "OPEN_EDIT": "double_click",
                    "SELECTION_MODE": "single",
                },
            },
        }
    }
    frame_daten = _build_frame_daten(str(dialog_id))

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
            name=args.view_name,
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

        print("✅ sys_control_dict View + Dialog + Frame upserted")
        print(f"   sys_viewdaten:  {view_id}")
        print(f"   sys_dialogdaten: {dialog_id}")
        print(f"   sys_framedaten: {frame_id}")
        print("   ROOT.EDIT_TYPE: pdvm_edit")
        print("   ROOT.TABLE: sys_control_dict")
        print("\nNächster API-Test:")
        print(f"   GET  /api/dialogs/{dialog_id}")
        print(f"   POST /api/dialogs/{dialog_id}/draft/start")

    finally:
        await conn.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

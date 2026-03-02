"""Create sys_viewdaten + sys_dialogdaten + sys_framedaten for edit_frame.

Usage:
  python backend/tools/create_edit_frame_dialog.py
  python backend/tools/create_edit_frame_dialog.py --dialog-uid <uuid> --view-uid <uuid> --frame-uid <uuid>
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
            "VIEW_NAME": "Edit Frame",
            "VIEW_GUID": view_guid,
            "HEADER_TEXT": "Edit Frame",
            "PROJECTION_MODE": "standard",
            "ALLOW_FILTER": True,
            "ALLOW_SORT": True,
            "DEFAULT_SORT_COLUMN": "",
            "DEFAULT_SORT_REVERSE": False,
            "TABLE": "sys_framedaten",
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
                "table": "sys_framedaten",
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
                "table": "sys_framedaten",
            },
        },
    }


def _build_frame_daten(dialog_guid: str) -> dict:
    tabs_def = {
        "11111111-bbbb-bbbb-bbbb-111111111111": {"index": 1, "HEAD": "Root", "GRUPPE": "ROOT", "display_order": 10},
        "22222222-bbbb-bbbb-bbbb-222222222222": {"index": 2, "HEAD": "Tabs", "GRUPPE": "ROOT", "display_order": 20},
    }

    field_template = {
        "tab": 1,
        "feld": "FELD",
        "name": "feld_name",
        "type": "string",
        "label": "Neues Feld",
        "table": "sys_framedaten",
        "gruppe": "ROOT",
        "abdatum": False,
        "configs": {
            "help": {"key": "", "feld": "", "table": "", "gruppe": ""},
            "dropdown": {"key": "", "feld": "", "table": "", "gruppe": ""},
        },
        "tooltip": "",
        "read_only": False,
        "historical": False,
        "source_path": "root",
        "display_order": 10,
    }

    tab_template = {"index": 1, "HEAD": "Tab 1", "GRUPPE": "ROOT", "display_order": 10}
    tab_fields = [
        {"name": "index", "label": "Index", "type": "number"},
        {"name": "HEAD", "label": "Head", "type": "text"},
        {"name": "GRUPPE", "label": "Gruppe", "type": "text"},
        {"name": "display_order", "label": "Sortierung", "type": "number"},
    ]

    field_fields = [
        {"name": "tab", "label": "Tab", "type": "number"},
        {"name": "feld", "label": "Feld", "type": "text"},
        {"name": "name", "label": "Name", "type": "text"},
        {"name": "type", "label": "Type", "type": "text"},
        {"name": "label", "label": "Label", "type": "text"},
        {"name": "gruppe", "label": "Gruppe", "type": "text"},
        {"name": "display_order", "label": "Sortierung", "type": "number"},
        {"name": "read_only", "label": "Read Only", "type": "dropdown", "options": [{"value": "true", "label": "true"}, {"value": "false", "label": "false"}]},
    ]

    return {
        "ROOT": {
            "DIALOG_GUID": dialog_guid,
            "EDIT_TYPE": "edit_frame",
            "SELF_NAME": "Edit Frame",
            "TABS": 2,
            "TAB_01": {"HEAD": "Root", "GRUPPE": "ROOT"},
            "TAB_02": {"HEAD": "Tabs", "GRUPPE": "ROOT"},
            "TABS_DEF": tabs_def,
        },
        "FIELDS": {
            "11111111-aaaa-aaaa-aaaa-111111111111": {
                "tab": 1,
                "feld": "SELF_NAME",
                "name": "self_name",
                "type": "string",
                "label": "Dialog-Name",
                "table": "sys_framedaten",
                "gruppe": "ROOT",
                "abdatum": False,
                "configs": {"help": {"key": "", "feld": "", "table": "", "gruppe": ""}, "dropdown": {"key": "", "feld": "", "table": "", "gruppe": ""}},
                "tooltip": "",
                "read_only": False,
                "historical": False,
                "source_path": "root",
                "display_order": 10,
            },
            "22222222-aaaa-aaaa-aaaa-222222222222": {
                "tab": 1,
                "feld": "EDIT_TYPE",
                "name": "edit_type",
                "type": "string",
                "label": "Edit-Type",
                "table": "sys_framedaten",
                "gruppe": "ROOT",
                "abdatum": False,
                "configs": {"help": {"key": "", "feld": "", "table": "", "gruppe": ""}, "dropdown": {"key": "", "feld": "", "table": "", "gruppe": ""}},
                "tooltip": "",
                "read_only": False,
                "historical": False,
                "source_path": "root",
                "display_order": 20,
            },
            "33333333-aaaa-aaaa-aaaa-333333333333": {
                "tab": 1,
                "feld": "TABS",
                "name": "tabs",
                "type": "string",
                "label": "Tabs",
                "table": "sys_framedaten",
                "gruppe": "ROOT",
                "abdatum": False,
                "configs": {"help": {"key": "", "feld": "", "table": "", "gruppe": ""}, "dropdown": {"key": "", "feld": "", "table": "", "gruppe": ""}},
                "tooltip": "Anzahl der Tabs",
                "read_only": False,
                "historical": False,
                "source_path": "root",
                "display_order": 30,
            },
            "88888888-aaaa-aaaa-aaaa-888888888888": {
                "tab": 2,
                "feld": "TABS_DEF",
                "name": "tabs_def",
                "type": "element_list",
                "label": "Tabs (Liste)",
                "table": "sys_framedaten",
                "gruppe": "ROOT",
                "abdatum": False,
                "configs": {"element_template": tab_template, "element_fields": tab_fields},
                "tooltip": "",
                "read_only": False,
                "historical": False,
                "source_path": "root",
                "display_order": 5,
            },
            "99999999-aaaa-aaaa-aaaa-999999999999": {
                "tab": 2,
                "feld": "FIELDS",
                "name": "fields",
                "type": "element_list",
                "label": "Controls (FIELDS)",
                "table": "sys_framedaten",
                "gruppe": "__ROOT__",
                "abdatum": False,
                "configs": {"element_template": field_template, "element_fields": field_fields},
                "tooltip": "",
                "read_only": False,
                "historical": False,
                "source_path": "root",
                "display_order": 10,
            },
            "44444444-aaaa-aaaa-aaaa-444444444444": {
                "tab": 2,
                "feld": "TAB_01.HEAD",
                "name": "tab01_head",
                "type": "string",
                "label": "Tab 1 - Head",
                "table": "sys_framedaten",
                "gruppe": "ROOT",
                "abdatum": False,
                "configs": {"help": {"key": "", "feld": "", "table": "", "gruppe": ""}, "dropdown": {"key": "", "feld": "", "table": "", "gruppe": ""}},
                "tooltip": "",
                "read_only": False,
                "historical": False,
                "source_path": "root",
                "display_order": 10,
            },
            "55555555-aaaa-aaaa-aaaa-555555555555": {
                "tab": 2,
                "feld": "TAB_01.GRUPPE",
                "name": "tab01_gruppe",
                "type": "string",
                "label": "Tab 1 - Gruppe",
                "table": "sys_framedaten",
                "gruppe": "ROOT",
                "abdatum": False,
                "configs": {"help": {"key": "", "feld": "", "table": "", "gruppe": ""}, "dropdown": {"key": "", "feld": "", "table": "", "gruppe": ""}},
                "tooltip": "",
                "read_only": False,
                "historical": False,
                "source_path": "root",
                "display_order": 20,
            },
            "66666666-aaaa-aaaa-aaaa-666666666666": {
                "tab": 2,
                "feld": "TAB_02.HEAD",
                "name": "tab02_head",
                "type": "string",
                "label": "Tab 2 - Head",
                "table": "sys_framedaten",
                "gruppe": "ROOT",
                "abdatum": False,
                "configs": {"help": {"key": "", "feld": "", "table": "", "gruppe": ""}, "dropdown": {"key": "", "feld": "", "table": "", "gruppe": ""}},
                "tooltip": "",
                "read_only": False,
                "historical": False,
                "source_path": "root",
                "display_order": 30,
            },
            "77777777-aaaa-aaaa-aaaa-777777777777": {
                "tab": 2,
                "feld": "TAB_02.GRUPPE",
                "name": "tab02_gruppe",
                "type": "string",
                "label": "Tab 2 - Gruppe",
                "table": "sys_framedaten",
                "gruppe": "ROOT",
                "abdatum": False,
                "configs": {"help": {"key": "", "feld": "", "table": "", "gruppe": ""}, "dropdown": {"key": "", "feld": "", "table": "", "gruppe": ""}},
                "tooltip": "",
                "read_only": False,
                "historical": False,
                "source_path": "root",
                "display_order": 40,
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
    parser = argparse.ArgumentParser(description="Create edit_frame dialog + view + frame")
    parser.add_argument("--view-uid", help="Optional view UID")
    parser.add_argument("--dialog-uid", help="Optional dialog UID")
    parser.add_argument("--frame-uid", help="Optional frame UID")
    parser.add_argument("--dialog-name", default="Edit Frame Dialog", help="Dialog name")
    parser.add_argument("--frame-name", default="Edit Frame", help="Frame name")
    parser.add_argument("--view-name", default="Edit Frame View", help="View name")
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
            "TABLE": "sys_framedaten",
            "TABS": 2,
            "VIEW_GUID": str(view_id),
            "FRAME_GUID": str(frame_id),
            "EDIT_TYPE": "edit_frame",
            "SELECTION_MODE": "single",
            "OPEN_EDIT": "double_click",
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

        print("✅ edit_frame records upserted:")
        print(f"  sys_viewdaten:  {view_id}")
        print(f"  sys_dialogdaten: {dialog_id}")
        print(f"  sys_framedaten: {frame_id}")
    finally:
        await conn.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

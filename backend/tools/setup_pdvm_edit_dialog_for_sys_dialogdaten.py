"""Setup eines generischen pdvm_edit Dialogs fuer sys_dialogdaten.

Enthaelt:
1) sys_control_dict Controls (modul_type=edit, auf Basis 666/555 Templates)
2) sys_viewdaten Datensatz fuer sys_dialogdaten
3) sys_framedaten Datensatz fuer lineare Dialogdaten-Pflege
4) sys_dialogdaten Datensatz mit TAB_ELEMENTS Struktur

Usage:
  python backend/tools/setup_pdvm_edit_dialog_for_sys_dialogdaten.py
"""
from __future__ import annotations

import argparse
import asyncio
import json
import uuid
from pathlib import Path
from typing import Any, Dict, Iterable, Set, Tuple

import sys

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import asyncpg

from app.core.connection_manager import ConnectionManager

DEFAULT_DIALOG_UID = "1f3a0e00-48bb-4a08-9cb8-7a7d52f23001"
DEFAULT_VIEW_UID = "1f3a0e00-48bb-4a08-9cb8-7a7d52f23002"
DEFAULT_FRAME_UID = "1f3a0e00-48bb-4a08-9cb8-7a7d52f23003"

CONTROL_NAMESPACE = uuid.UUID("6f8de3d4-1e39-4d56-9f35-0fdbd8f2a111")


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


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


def _build_view_daten(view_guid: str) -> dict:
    return {
        "ROOT": {
            "NO_DATA": True,
            "VIEW_NAME": "Dialogdaten",
            "VIEW_GUID": view_guid,
            "HEADER_TEXT": "Dialogdaten",
            "PROJECTION_MODE": "standard",
            "ALLOW_FILTER": True,
            "ALLOW_SORT": True,
            "DEFAULT_SORT_COLUMN": "name",
            "DEFAULT_SORT_REVERSE": False,
            "TABLE": "sys_dialogdaten",
        },
        "SYSTEM": {
            "11111111-1000-4000-8000-111111111111": {
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
                "table": "sys_dialogdaten",
            },
            "22222222-2000-4000-8000-222222222222": {
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
                "table": "sys_dialogdaten",
            },
            "33333333-3000-4000-8000-333333333333": {
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
                "table": "sys_dialogdaten",
            },
            "44444444-4000-4000-8000-444444444444": {
                "gruppe": "ROOT",
                "feld": "edit_type",
                "label": "Edit Type",
                "type": "string",
                "control_type": "base",
                "show": True,
                "display_order": 4,
                "searchable": True,
                "sortable": True,
                "filterType": "contains",
                "table": "sys_dialogdaten",
            },
        },
    }


def _build_frame_daten(dialog_guid: str) -> dict:
    tab_elements_template = {
        "GUID": "",
        "HEAD": "",
        "TABLE": "",
        "MODULE": "view",
        "EDIT_TYPE": "pdvm_edit",
        "OPEN_EDIT": "double_click",
        "SELECTION_MODE": "single",
    }
    tab_elements_fields = [
        {"name": "GUID", "label": "GUID", "type": "text"},
        {"name": "HEAD", "label": "Head", "type": "text"},
        {"name": "TABLE", "label": "Table", "type": "text"},
        {
            "name": "MODULE",
            "label": "Module",
            "type": "dropdown",
            "options": [
                {"value": "view", "label": "view"},
                {"value": "edit", "label": "edit"},
                {"value": "acti", "label": "acti"},
            ],
        },
        {"name": "EDIT_TYPE", "label": "Edit Type", "type": "text"},
        {"name": "OPEN_EDIT", "label": "Open Edit", "type": "text"},
        {"name": "SELECTION_MODE", "label": "Selection", "type": "text"},
    ]

    return {
        "ROOT": {
            "DIALOG_GUID": dialog_guid,
            "EDIT_TYPE": "pdvm_edit",
            "SELF_NAME": "Edit Dialogdaten",
            "TABS": 2,
            "TAB_01": {"HEAD": "Basis", "GRUPPE": "ROOT"},
            "TAB_02": {"HEAD": "Tabs", "GRUPPE": "ROOT"},
            "TABS_DEF": {
                "11111111-aaaa-bbbb-cccc-111111111111": {"index": 1, "HEAD": "Basis", "GRUPPE": "ROOT", "display_order": 10},
                "22222222-aaaa-bbbb-cccc-222222222222": {"index": 2, "HEAD": "Tabs", "GRUPPE": "ROOT", "display_order": 20},
            },
        },
        "FIELDS": {
            "11111111-aaaa-aaaa-aaaa-111111111111": {
                "tab": 1,
                "feld": "SELF_GUID",
                "name": "self_guid",
                "type": "string",
                "label": "Self GUID",
                "table": "sys_dialogdaten",
                "gruppe": "ROOT",
                "display_order": 10,
                "read_only": True,
            },
            "22222222-aaaa-aaaa-aaaa-222222222222": {
                "tab": 1,
                "feld": "SELF_NAME",
                "name": "self_name",
                "type": "string",
                "label": "Self Name",
                "table": "sys_dialogdaten",
                "gruppe": "ROOT",
                "display_order": 20,
                "read_only": False,
            },
            "33333333-aaaa-aaaa-aaaa-333333333333": {
                "tab": 1,
                "feld": "TABLE",
                "name": "table",
                "type": "string",
                "label": "Tabelle",
                "table": "sys_dialogdaten",
                "gruppe": "ROOT",
                "display_order": 30,
                "read_only": False,
            },
            "44444444-aaaa-aaaa-aaaa-444444444444": {
                "tab": 1,
                "feld": "DIALOG_TYPE",
                "name": "dialog_type",
                "type": "string",
                "label": "Dialog Type",
                "table": "sys_dialogdaten",
                "gruppe": "ROOT",
                "display_order": 40,
                "read_only": False,
            },
            "55555555-aaaa-aaaa-aaaa-555555555555": {
                "tab": 1,
                "feld": "TABS",
                "name": "tabs",
                "type": "string",
                "label": "Anzahl Tabs",
                "table": "sys_dialogdaten",
                "gruppe": "ROOT",
                "display_order": 50,
                "read_only": False,
            },
            "66666666-aaaa-aaaa-aaaa-666666666666": {
                "tab": 1,
                "feld": "EDIT_TYPE",
                "name": "edit_type",
                "type": "string",
                "label": "Edit Type (Root)",
                "table": "sys_dialogdaten",
                "gruppe": "ROOT",
                "display_order": 60,
                "read_only": False,
            },
            "77777777-aaaa-aaaa-aaaa-777777777777": {
                "tab": 2,
                "feld": "TAB_ELEMENTS",
                "name": "tab_elements",
                "type": "element_list",
                "label": "Tab Elements",
                "table": "sys_dialogdaten",
                "gruppe": "ROOT",
                "display_order": 10,
                "read_only": False,
                "configs": {
                    "element_template": tab_elements_template,
                    "element_fields": tab_elements_fields,
                },
            },
        },
    }


def _build_dialog_daten(dialog_guid: str, view_guid: str, frame_guid: str, dialog_name: str) -> dict:
    return {
        "ROOT": {
            "SELF_GUID": dialog_guid,
            "SELF_NAME": dialog_name,
            "TABLE": "sys_dialogdaten",
            "DIALOG_TYPE": "norm",
            "TABS": 2,
            "EDIT_TYPE": "pdvm_edit",
            "TAB_ELEMENTS": {
                "TAB_01": {
                    "GUID": view_guid,
                    "HEAD": "Liste",
                    "TABLE": "sys_dialogdaten",
                    "MODULE": "view",
                    "EDIT_TYPE": "pdvm_edit",
                    "OPEN_EDIT": "double_click",
                    "SELECTION_MODE": "single",
                },
                "TAB_02": {
                    "GUID": frame_guid,
                    "HEAD": "Bearbeiten",
                    "TABLE": "sys_dialogdaten",
                    "MODULE": "edit",
                    "EDIT_TYPE": "pdvm_edit",
                    "OPEN_EDIT": "double_click",
                    "SELECTION_MODE": "single",
                },
            },
        }
    }


async def _seed_dialog_controls(conn: asyncpg.Connection) -> int:
    base_row = await conn.fetchrow("SELECT daten FROM sys_control_dict WHERE uid = $1", uuid.UUID("66666666-6666-6666-6666-666666666666"))
    modul_row = await conn.fetchrow("SELECT daten FROM sys_control_dict WHERE uid = $1", uuid.UUID("55555555-5555-5555-5555-555555555555"))

    base = _as_dict(base_row["daten"]) if base_row else {}
    base_control = _as_dict(base.get("CONTROL")) if isinstance(base.get("CONTROL"), dict) else base

    modul = _as_dict(modul_row["daten"]) if modul_row else {}
    modul_map = _as_dict(modul.get("MODUL"))
    modul_edit = _as_dict(modul_map.get("edit"))

    template_defaults = {**base_control, **modul_edit, "modul_type": "edit"}

    control_specs = [
        ("SELF_GUID", "SELF GUID", "ROOT", "SELF_GUID", "string", 10),
        ("SELF_NAME", "SELF NAME", "ROOT", "SELF_NAME", "string", 20),
        ("TABLE", "TABLE", "ROOT", "TABLE", "string", 30),
        ("DIALOG_TYPE", "DIALOG TYPE", "ROOT", "DIALOG_TYPE", "string", 40),
        ("TABS", "TABS", "ROOT", "TABS", "string", 50),
        ("EDIT_TYPE", "EDIT TYPE", "ROOT", "EDIT_TYPE", "string", 60),
        ("TAB_ELEMENTS", "TAB ELEMENTS", "ROOT", "TAB_ELEMENTS", "element_list", 70),
        ("OPEN_EDIT", "OPEN EDIT", "ROOT", "OPEN_EDIT", "string", 80),
        ("SELECTION_MODE", "SELECTION MODE", "ROOT", "SELECTION_MODE", "string", 90),
    ]

    tab_elements_cfg = {
        "element_template": {
            "GUID": "",
            "HEAD": "",
            "TABLE": "",
            "MODULE": "view",
            "EDIT_TYPE": "pdvm_edit",
            "OPEN_EDIT": "double_click",
            "SELECTION_MODE": "single",
        },
        "element_fields": [
            {"name": "GUID", "label": "GUID", "type": "text"},
            {"name": "HEAD", "label": "Head", "type": "text"},
            {"name": "TABLE", "label": "Table", "type": "text"},
            {"name": "MODULE", "label": "Module", "type": "text"},
            {"name": "EDIT_TYPE", "label": "Edit Type", "type": "text"},
            {"name": "OPEN_EDIT", "label": "Open Edit", "type": "text"},
            {"name": "SELECTION_MODE", "label": "Selection", "type": "text"},
        ],
    }

    inserted = 0
    for control_name, label, gruppe, feld, field_type, order in control_specs:
        uid = uuid.uuid5(CONTROL_NAMESPACE, f"sys_dialogdaten:{control_name}")
        name = f"SYS_{control_name}"
        daten = {
            **template_defaults,
            "name": control_name.lower(),
            "SELF_NAME": name,
            "label": label,
            "type": field_type,
            "table": "sys_dialogdaten",
            "gruppe": gruppe,
            "feld": feld,
            "display_order": order,
            "modul_type": "edit",
            "read_only": True if control_name == "SELF_GUID" else False,
        }
        if control_name == "TAB_ELEMENTS":
            daten["configs"] = tab_elements_cfg

        await conn.execute(
            """
            INSERT INTO sys_control_dict (uid, name, daten, historisch, created_at, modified_at)
            VALUES ($1, $2, $3::jsonb, 0, NOW(), NOW())
            ON CONFLICT (uid) DO UPDATE
            SET name = EXCLUDED.name,
                daten = EXCLUDED.daten,
                modified_at = NOW()
            """,
            uid,
            name,
            json.dumps(daten),
        )
        inserted += 1

    return inserted


async def main() -> int:
    parser = argparse.ArgumentParser(description="Setup pdvm_edit dialog for sys_dialogdaten")
    parser.add_argument("--dialog-uid", default=DEFAULT_DIALOG_UID, help="Dialog UID")
    parser.add_argument("--view-uid", default=DEFAULT_VIEW_UID, help="View UID")
    parser.add_argument("--frame-uid", default=DEFAULT_FRAME_UID, help="Frame UID")
    parser.add_argument("--dialog-name", default="Dialogdaten Editor", help="Dialog Name")
    parser.add_argument("--view-name", default="Dialogdaten View", help="View Name")
    parser.add_argument("--frame-name", default="Dialogdaten Frame", help="Frame Name")
    parser.add_argument("--db-url", default=None, help="Optional Postgres URL")
    args = parser.parse_args()

    dialog_id = uuid.UUID(args.dialog_uid)
    view_id = uuid.UUID(args.view_uid)
    frame_id = uuid.UUID(args.frame_uid)

    if args.db_url:
        db_url = args.db_url
    else:
        cfg = await ConnectionManager.get_system_config("pdvm_system")
        db_url = cfg.to_url()

    conn = await asyncpg.connect(db_url)
    try:
        controls_created = await _seed_dialog_controls(conn)

        view_rel = await _first_existing_relation(conn, ["pdvm_system.sys_viewdaten", "public.sys_viewdaten", "sys_viewdaten"])
        dialog_rel = await _first_existing_relation(conn, ["pdvm_system.sys_dialogdaten", "public.sys_dialogdaten", "sys_dialogdaten"])
        frame_rel = await _first_existing_relation(conn, ["pdvm_system.sys_framedaten", "public.sys_framedaten", "sys_framedaten"])

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
            daten=_build_view_daten(str(view_id)),
        )

        await _upsert_jsonb_record(
            conn,
            relation=frame_rel,
            cols=frame_cols,
            pk_col=frame_pk,
            record_id=frame_id,
            name=args.frame_name,
            daten=_build_frame_daten(str(dialog_id)),
        )

        await _upsert_jsonb_record(
            conn,
            relation=dialog_rel,
            cols=dialog_cols,
            pk_col=dialog_pk,
            record_id=dialog_id,
            name=args.dialog_name,
            daten=_build_dialog_daten(str(dialog_id), str(view_id), str(frame_id), args.dialog_name),
        )

        print("✅ Setup abgeschlossen: pdvm_edit fuer sys_dialogdaten")
        print(f"   Controls upserted: {controls_created}")
        print(f"   Dialog: {dialog_id}")
        print(f"   View:   {view_id}")
        print(f"   Frame:  {frame_id}")

    finally:
        await conn.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

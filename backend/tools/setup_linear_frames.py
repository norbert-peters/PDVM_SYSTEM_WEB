"""Setup linear frames for sys_control_dict and sys_dialogdaten.

Ziel:
- Frame fuer sys_control_dict auf lineare Pflege umstellen
- Frame fuer sys_dialogdaten auf TAB_ELEMENTS-basierte lineare Pflege umstellen

Hinweis:
- Frames werden per UID upserted (idempotent)
- Nutzt vorhandene 555-Templates als Quelle fuer element_list-Strukturen
"""
from __future__ import annotations

import argparse
import asyncio
import json
import uuid
from pathlib import Path
from typing import Any, Dict, Iterable, List, Set, Tuple

import sys

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import asyncpg

from app.core.connection_manager import ConnectionManager

TEMPLATE_UID_555 = uuid.UUID("55555555-5555-5555-5555-555555555555")

SYS_CONTROL_DICT_DIALOG_UID = uuid.UUID("9f06711e-4ad8-4ea4-9837-2f40f3a6f101")
SYS_CONTROL_DICT_FRAME_UID = uuid.UUID("9f06711e-4ad8-4ea4-9837-2f40f3a6f103")

SYS_DIALOGDATEN_DIALOG_UID = uuid.UUID("1f3a0e00-48bb-4a08-9cb8-7a7d52f23001")
SYS_DIALOGDATEN_FRAME_UID = uuid.UUID("1f3a0e00-48bb-4a08-9cb8-7a7d52f23003")


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


def _element_fields_from_template(template_obj: Dict[str, Any]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for key, value in template_obj.items():
        key_u = str(key).upper()
        if isinstance(value, bool):
            out.append(
                {
                    "name": key_u,
                    "label": key_u.title().replace("_", " "),
                    "type": "dropdown",
                    "options": [{"value": "true", "label": "true"}, {"value": "false", "label": "false"}],
                }
            )
        elif isinstance(value, (int, float)):
            out.append({"name": key_u, "label": key_u.title().replace("_", " "), "type": "number"})
        else:
            out.append({"name": key_u, "label": key_u.title().replace("_", " "), "type": "text"})
    return out


def _build_sys_control_dict_frame(template_555: Dict[str, Any]) -> Dict[str, Any]:
    templates = _as_dict(template_555.get("TEMPLATES"))
    tpl_control = _as_dict(templates.get("CONTROL"))
    tpl_configs = _as_dict(templates.get("CONFIGS_ELEMENTS"))
    tpl_fields = _as_dict(templates.get("FIELDS_ELEMENTS"))

    control_element_template = {str(k).upper(): v for k, v in tpl_control.items()}
    control_element_fields = _element_fields_from_template(control_element_template)

    tabs_def = {
        "11111111-f001-4001-8001-000000000001": {"index": 1, "HEAD": "Basis", "GRUPPE": "ROOT", "display_order": 10},
        "22222222-f001-4001-8001-000000000002": {"index": 2, "HEAD": "Eigenschaften", "GRUPPE": "ROOT", "display_order": 20},
        "33333333-f001-4001-8001-000000000003": {"index": 3, "HEAD": "Control-Liste", "GRUPPE": "CONTROL", "display_order": 30},
        "44444444-f001-4001-8001-000000000004": {"index": 4, "HEAD": "Templates", "GRUPPE": "TEMPLATES", "display_order": 40},
    }

    fields: Dict[str, Dict[str, Any]] = {
        # Basis
        "11111111-e001-4001-8001-000000000001": {
            "tab": 1, "feld": "name", "name": "name", "type": "string", "label": "Name", "table": "sys_control_dict", "gruppe": "ROOT", "display_order": 10, "read_only": False
        },
        "11111111-e001-4001-8001-000000000002": {
            "tab": 1, "feld": "label", "name": "label", "type": "string", "label": "Label", "table": "sys_control_dict", "gruppe": "ROOT", "display_order": 20, "read_only": False
        },
        "11111111-e001-4001-8001-000000000003": {
            "tab": 1, "feld": "table", "name": "table", "type": "string", "label": "Table", "table": "sys_control_dict", "gruppe": "ROOT", "display_order": 30, "read_only": False
        },
        "11111111-e001-4001-8001-000000000004": {
            "tab": 1, "feld": "gruppe", "name": "gruppe", "type": "string", "label": "Gruppe", "table": "sys_control_dict", "gruppe": "ROOT", "display_order": 40, "read_only": False
        },
        "11111111-e001-4001-8001-000000000005": {
            "tab": 1, "feld": "feld", "name": "feld", "type": "string", "label": "Feld", "table": "sys_control_dict", "gruppe": "ROOT", "display_order": 50, "read_only": False
        },
        "11111111-e001-4001-8001-000000000006": {
            "tab": 1, "feld": "type", "name": "type", "type": "string", "label": "Type", "table": "sys_control_dict", "gruppe": "ROOT", "display_order": 60, "read_only": False
        },
        # Eigenschaften
        "22222222-e001-4001-8001-000000000001": {
            "tab": 2, "feld": "read_only", "name": "read_only", "type": "true_false", "label": "Read Only", "table": "sys_control_dict", "gruppe": "ROOT", "display_order": 10, "read_only": False
        },
        "22222222-e001-4001-8001-000000000002": {
            "tab": 2, "feld": "historical", "name": "historical", "type": "true_false", "label": "Historical", "table": "sys_control_dict", "gruppe": "ROOT", "display_order": 20, "read_only": False
        },
        "22222222-e001-4001-8001-000000000003": {
            "tab": 2, "feld": "searchable", "name": "searchable", "type": "true_false", "label": "Searchable", "table": "sys_control_dict", "gruppe": "ROOT", "display_order": 30, "read_only": False
        },
        "22222222-e001-4001-8001-000000000004": {
            "tab": 2, "feld": "sortable", "name": "sortable", "type": "true_false", "label": "Sortable", "table": "sys_control_dict", "gruppe": "ROOT", "display_order": 40, "read_only": False
        },
        "22222222-e001-4001-8001-000000000005": {
            "tab": 2, "feld": "filter_type", "name": "filter_type", "type": "string", "label": "Filter Type", "table": "sys_control_dict", "gruppe": "ROOT", "display_order": 50, "read_only": False
        },
        "22222222-e001-4001-8001-000000000006": {
            "tab": 2, "feld": "default", "name": "default", "type": "string", "label": "Default", "table": "sys_control_dict", "gruppe": "ROOT", "display_order": 60, "read_only": False
        },
        # Control-Liste
        "33333333-e001-4001-8001-000000000001": {
            "tab": 3,
            "feld": "CONTROL",
            "name": "control",
            "type": "element_list",
            "label": "CONTROL (Elemente)",
            "table": "sys_control_dict",
            "gruppe": "__ROOT__",
            "display_order": 10,
            "read_only": False,
            "configs": {
                "element_template": control_element_template,
                "element_fields": control_element_fields,
            },
        },
        # Templates (666)
        "44444444-e001-4001-8001-000000000001": {
            "tab": 4, "feld": "ROOT.SELF_GUID", "name": "root_self_guid", "type": "string", "label": "ROOT.SELF_GUID", "table": "sys_control_dict", "gruppe": "__ROOT__", "display_order": 10, "read_only": False
        },
        "44444444-e001-4001-8001-000000000002": {
            "tab": 4, "feld": "ROOT.SELF_NAME", "name": "root_self_name", "type": "string", "label": "ROOT.SELF_NAME", "table": "sys_control_dict", "gruppe": "__ROOT__", "display_order": 20, "read_only": False
        },
    }

    order = 100
    for key, value in tpl_control.items():
        key_u = str(key).upper()
        field_type = "true_false" if isinstance(value, bool) else "string"
        fields[str(uuid.uuid5(uuid.UUID("91f305a8-62f1-4e58-a992-30a18a5b2b10"), f"tpl-control:{key_u}"))] = {
            "tab": 4,
            "feld": f"TEMPLATES.CONTROL.{key_u}",
            "name": f"tpl_control_{key_u.lower()}",
            "type": field_type,
            "label": f"TPL CONTROL {key_u}",
            "table": "sys_control_dict",
            "gruppe": "__ROOT__",
            "display_order": order,
            "read_only": False,
        }
        order += 10

    for key, value in tpl_configs.items():
        key_u = str(key).upper()
        fields[str(uuid.uuid5(uuid.UUID("91f305a8-62f1-4e58-a992-30a18a5b2b10"), f"tpl-configs:{key_u}"))] = {
            "tab": 4,
            "feld": f"TEMPLATES.CONFIGS_ELEMENTS.{key_u}",
            "name": f"tpl_configs_{key_u.lower()}",
            "type": "string",
            "label": f"TPL CONFIGS {key_u}",
            "table": "sys_control_dict",
            "gruppe": "__ROOT__",
            "display_order": order,
            "read_only": False,
        }
        order += 10

    for key, value in tpl_fields.items():
        key_u = str(key).upper()
        field_type = "true_false" if isinstance(value, bool) else "string"
        fields[str(uuid.uuid5(uuid.UUID("91f305a8-62f1-4e58-a992-30a18a5b2b10"), f"tpl-fields:{key_u}"))] = {
            "tab": 4,
            "feld": f"TEMPLATES.FIELDS_ELEMENTS.{key_u}",
            "name": f"tpl_fields_{key_u.lower()}",
            "type": field_type,
            "label": f"TPL FIELDS {key_u}",
            "table": "sys_control_dict",
            "gruppe": "__ROOT__",
            "display_order": order,
            "read_only": False,
        }
        order += 10

    return {
        "ROOT": {
            "DIALOG_GUID": str(SYS_CONTROL_DICT_DIALOG_UID),
            "EDIT_TYPE": "pdvm_edit",
            "SELF_NAME": "Edit sys_control_dict (Linear)",
            "TABS": 4,
            "TAB_01": {"HEAD": "Basis", "GRUPPE": "ROOT"},
            "TAB_02": {"HEAD": "Eigenschaften", "GRUPPE": "ROOT"},
            "TAB_03": {"HEAD": "Control-Liste", "GRUPPE": "CONTROL"},
            "TAB_04": {"HEAD": "Templates", "GRUPPE": "TEMPLATES"},
            "TABS_DEF": tabs_def,
        },
        "FIELDS": fields,
    }


def _build_sys_dialogdaten_frame(template_555_dialog: Dict[str, Any]) -> Dict[str, Any]:
    templates = _as_dict(template_555_dialog.get("TEMPLATES"))
    tab_elements = _as_dict(templates.get("TAB_ELEMENTS"))
    tab_guid_template = _as_dict(tab_elements.get("TAB_GUID"))

    element_template = dict(tab_guid_template)
    element_fields = _element_fields_from_template(element_template)

    tabs_def = {
        "11111111-f002-4001-8001-000000000001": {"index": 1, "HEAD": "Basis", "GRUPPE": "ROOT", "display_order": 10},
        "22222222-f002-4001-8001-000000000002": {"index": 2, "HEAD": "Tab Elements", "GRUPPE": "ROOT", "display_order": 20},
        "33333333-f002-4001-8001-000000000003": {"index": 3, "HEAD": "Template", "GRUPPE": "TEMPLATES", "display_order": 30},
    }

    fields: Dict[str, Dict[str, Any]] = {
        "11111111-e002-4001-8001-000000000001": {"tab": 1, "feld": "SELF_GUID", "name": "self_guid", "type": "string", "label": "Self GUID", "table": "sys_dialogdaten", "gruppe": "ROOT", "display_order": 10, "read_only": True},
        "11111111-e002-4001-8001-000000000002": {"tab": 1, "feld": "SELF_NAME", "name": "self_name", "type": "string", "label": "Self Name", "table": "sys_dialogdaten", "gruppe": "ROOT", "display_order": 20, "read_only": False},
        "11111111-e002-4001-8001-000000000003": {"tab": 1, "feld": "TABLE", "name": "table", "type": "string", "label": "Table", "table": "sys_dialogdaten", "gruppe": "ROOT", "display_order": 30, "read_only": False},
        "11111111-e002-4001-8001-000000000004": {"tab": 1, "feld": "DIALOG_TYPE", "name": "dialog_type", "type": "string", "label": "Dialog Type", "table": "sys_dialogdaten", "gruppe": "ROOT", "display_order": 40, "read_only": False},
        "11111111-e002-4001-8001-000000000005": {"tab": 1, "feld": "TABS", "name": "tabs", "type": "string", "label": "Tabs", "table": "sys_dialogdaten", "gruppe": "ROOT", "display_order": 50, "read_only": False},
        "22222222-e002-4001-8001-000000000001": {
            "tab": 2,
            "feld": "TAB_ELEMENTS",
            "name": "tab_elements",
            "type": "element_list",
            "label": "TAB_ELEMENTS",
            "table": "sys_dialogdaten",
            "gruppe": "ROOT",
            "display_order": 10,
            "read_only": False,
            "configs": {
                "element_template": element_template,
                "element_fields": element_fields,
            },
        },
    }

    order = 100
    for key, value in tab_guid_template.items():
        key_u = str(key).upper()
        field_type = "true_false" if isinstance(value, bool) else "string"
        fields[str(uuid.uuid5(uuid.UUID("ef89641d-08fa-4ff5-af22-d86f4a7f5efd"), f"tab-guid-template:{key_u}"))] = {
            "tab": 3,
            "feld": f"TEMPLATES.TAB_ELEMENTS.TAB_GUID.{key_u}",
            "name": f"tpl_tab_guid_{key_u.lower()}",
            "type": field_type,
            "label": f"TPL TAB {key_u}",
            "table": "sys_dialogdaten",
            "gruppe": "__ROOT__",
            "display_order": order,
            "read_only": False,
        }
        order += 10

    return {
        "ROOT": {
            "DIALOG_GUID": str(SYS_DIALOGDATEN_DIALOG_UID),
            "EDIT_TYPE": "pdvm_edit",
            "SELF_NAME": "Edit sys_dialogdaten (Linear)",
            "TABS": 3,
            "TAB_01": {"HEAD": "Basis", "GRUPPE": "ROOT"},
            "TAB_02": {"HEAD": "Tab Elements", "GRUPPE": "ROOT"},
            "TAB_03": {"HEAD": "Template", "GRUPPE": "TEMPLATES"},
            "TABS_DEF": tabs_def,
        },
        "FIELDS": fields,
    }


async def _load_template_555(conn: asyncpg.Connection, table_name: str) -> Dict[str, Any]:
    row = await conn.fetchrow(f"SELECT daten FROM {table_name} WHERE uid = $1", TEMPLATE_UID_555)
    if not row:
        return {}
    data = row.get("daten") or {}
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except Exception:
            data = {}
    return _as_dict(data)


async def main() -> int:
    parser = argparse.ArgumentParser(description="Setup linear frames")
    parser.add_argument("--db-url", default=None, help="Optional Postgres URL for pdvm_system")
    args = parser.parse_args()

    if args.db_url:
        db_url = args.db_url
    else:
        cfg = await ConnectionManager.get_system_config("pdvm_system")
        db_url = cfg.to_url()

    conn = await asyncpg.connect(db_url)
    try:
        frame_rel = await _first_existing_relation(conn, ["pdvm_system.sys_framedaten", "public.sys_framedaten", "sys_framedaten"])
        frame_schema, frame_table = _split_schema_table(frame_rel)
        frame_cols = await _get_columns(conn, frame_schema, frame_table)
        frame_pk = _pick_pk(frame_cols)

        tpl_control_555 = await _load_template_555(conn, "sys_control_dict")
        tpl_dialog_555 = await _load_template_555(conn, "sys_dialogdaten")

        sys_control_frame = _build_sys_control_dict_frame(tpl_control_555)
        sys_dialog_frame = _build_sys_dialogdaten_frame(tpl_dialog_555)

        await _upsert_jsonb_record(
            conn,
            relation=frame_rel,
            cols=frame_cols,
            pk_col=frame_pk,
            record_id=SYS_CONTROL_DICT_FRAME_UID,
            name="sys_control_dict Frame (Linear)",
            daten=sys_control_frame,
        )

        await _upsert_jsonb_record(
            conn,
            relation=frame_rel,
            cols=frame_cols,
            pk_col=frame_pk,
            record_id=SYS_DIALOGDATEN_FRAME_UID,
            name="sys_dialogdaten Frame (Linear)",
            daten=sys_dialog_frame,
        )

        print("✅ Linear Frames gesetzt")
        print(f"   sys_control_dict frame: {SYS_CONTROL_DICT_FRAME_UID}")
        print(f"   sys_dialogdaten frame:  {SYS_DIALOGDATEN_FRAME_UID}")
        print("   Enthalten: element_list fuer CONTROL und TAB_ELEMENTS + Template-Pfade")

    finally:
        await conn.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

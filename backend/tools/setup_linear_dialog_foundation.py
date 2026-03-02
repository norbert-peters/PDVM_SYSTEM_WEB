"""Setup Linear Dialog Foundation

Erzeugt/aktualisiert:
1) Templates 6666/5555 in sys_control_dict
2) Templates 6666/5555 in sys_dialogdaten
3) Controls in sys_control_dict nach Konvention SYS_<CONTROLNAME>
4) Ersten Dialogsatz in sys_dialogdaten mit ROOT.TAB_ELEMENTS

Hinweis:
- Fokus liegt bewusst auf Controls + Dialogdaten.
- Framedaten werden laut Vorgabe im naechsten Schritt separat angepasst.
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

TEMPLATE_UID_666 = uuid.UUID("66666666-6666-6666-6666-666666666666")
TEMPLATE_UID_555 = uuid.UUID("55555555-5555-5555-5555-555555555555")

CONTROL_NAMESPACE = uuid.UUID("8ec2de25-f2df-4db4-9fff-7bc16f5f9e41")

DIALOG_EDITOR_UID = uuid.UUID("1f3a0e00-48bb-4a08-9cb8-7a7d52f23001")
DIALOG_EDITOR_VIEW_UID = uuid.UUID("1f3a0e00-48bb-4a08-9cb8-7a7d52f23002")
DIALOG_EDITOR_FRAME_UID = uuid.UUID("1f3a0e00-48bb-4a08-9cb8-7a7d52f23003")


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _to_label(key: str) -> str:
    return str(key).replace("_", " ").strip().title()


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


def _control_template_666() -> Dict[str, Any]:
    return {
        "ROOT": {
            "SELF_GUID": "",
            "SELF_NAME": "",
        },
        "CONTROL": {},
    }


def _control_template_555() -> Dict[str, Any]:
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


def _dialog_template_666() -> Dict[str, Any]:
    return {
        "ROOT": {
            "TABS": 0,
            "TABLE": "",
            "SELF_GUID": "",
            "SELF_NAME": "",
            "DIALOG_TYPE": "norm",
            "TAB_ELEMENTS": {},
        }
    }


def _dialog_template_555() -> Dict[str, Any]:
    return {
        "TEMPLATES": {
            "TAB_ELEMENTS": {
                "TAB_GUID": {
                    "TAB": 0,
                    "GUID": "",
                    "HEAD": "",
                    "TABLE": "",
                    "MODULE": "",
                    "EDIT_TYPE": "",
                    "OPEN_EDIT": "",
                    "SELECTION_MODE": "",
                }
            }
        }
    }


def _infer_type_from_value(value: Any, key: str) -> str:
    key_upper = str(key).upper()
    if key_upper in {"FIELDS_ELEMENTS", "CONFIGS_ELEMENTS", "ROOT", "CONTROL", "TAB_ELEMENTS"}:
        return "element_list"
    if isinstance(value, bool):
        return "true_false"
    if isinstance(value, (int, float)):
        return "string"
    return "string"


def _build_control_record(
    *,
    table: str,
    gruppe: str,
    field: str,
    default_value: Any,
    template_control_defaults: Dict[str, Any],
    element_reference: Dict[str, Any] | None = None,
) -> Tuple[uuid.UUID, str, Dict[str, Any]]:
    field_upper = str(field).upper()
    name = f"SYS_{field_upper}"
    control_uid = uuid.uuid5(CONTROL_NAMESPACE, f"{table}:{gruppe}:{field_upper}")

    control_type = _infer_type_from_value(default_value, field_upper)
    label = _to_label(field_upper)

    daten = dict(template_control_defaults)
    daten.update(
        {
            "SELF_GUID": str(control_uid),
            "SELF_NAME": name,
            "NAME": name,
            "name": name,
            "TYPE": control_type,
            "type": control_type,
            "FIELD": field_upper,
            "feld": field_upper,
            "LABEL": label,
            "label": label,
            "TABLE": table,
            "table": table,
            "GRUPPE": gruppe,
            "gruppe": gruppe,
        }
    )

    if element_reference:
        daten["CONFIGS_ELEMENTS"] = element_reference
        daten["CONFIGS_ELEMENTS"] = element_reference

    return control_uid, name, daten


async def _seed_controls(conn: asyncpg.Connection, template_555: Dict[str, Any]) -> int:
    templates = _as_dict(template_555.get("TEMPLATES"))
    control_defaults = _as_dict(templates.get("CONTROL"))

    fields_for_controls: List[Tuple[str, str, Any, Dict[str, Any] | None]] = [
        ("ROOT", "ROOT", {}, {"KEY": "TEMPLATES", "FIELD": "CONTROL", "TABLE": "sys_control_dict", "GRUPPE": "TEMPLATES", "ELM_TYPE": "template"}),
        ("ROOT", "CONTROL", {}, {"KEY": "TEMPLATES", "FIELD": "CONTROL", "TABLE": "sys_control_dict", "GRUPPE": "TEMPLATES", "ELM_TYPE": "template"}),
    ]

    for key, value in control_defaults.items():
        ref = None
        if str(key).upper() in {"FIELDS_ELEMENTS", "CONFIGS_ELEMENTS"}:
            ref = {
                "KEY": "TEMPLATES",
                "FIELD": str(key).upper(),
                "TABLE": "sys_control_dict",
                "GRUPPE": "TEMPLATES",
                "ELM_TYPE": "template",
            }
        fields_for_controls.append(("CONTROL", str(key).upper(), value, ref))

    inserted = 0
    for gruppe, field, default_value, ref in fields_for_controls:
        uid, name, daten = _build_control_record(
            table="sys_control_dict",
            gruppe=gruppe,
            field=field,
            default_value=default_value,
            template_control_defaults=control_defaults,
            element_reference=ref,
        )

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


async def _analyze_template_coverage(conn: asyncpg.Connection, template_555: Dict[str, Any]) -> Dict[str, Any]:
    known_keys = set(_as_dict(_as_dict(template_555.get("TEMPLATES")).get("CONTROL")).keys())

    rows = await conn.fetch(
        """
        SELECT daten
        FROM sys_control_dict
        WHERE historisch = 0
          AND uid NOT IN ($1, $2)
        """,
        TEMPLATE_UID_666,
        TEMPLATE_UID_555,
    )

    observed_upper: Set[str] = set()
    for row in rows:
        daten = row.get("daten") or {}
        if isinstance(daten, str):
            try:
                daten = json.loads(daten)
            except Exception:
                daten = {}
        if not isinstance(daten, dict):
            continue
        for key in daten.keys():
            key_str = str(key).strip()
            if key_str and key_str.upper() == key_str:
                observed_upper.add(key_str)

    ignore = {
        "SELF_GUID",
        "SELF_NAME",
        "NAME",
        "TYPE",
        "FIELD",
        "LABEL",
        "TABLE",
        "GRUPPE",
        "MODUL_TYPE",
    }

    missing = sorted(k for k in observed_upper if k not in known_keys and k not in ignore)
    return {
        "observed_upper_count": len(observed_upper),
        "known_template_count": len(known_keys),
        "missing_keys": missing,
    }


def _build_dialog_record() -> Dict[str, Any]:
    return {
        "ROOT": {
            "SELF_GUID": str(DIALOG_EDITOR_UID),
            "SELF_NAME": "Dialogdaten Editor",
            "TABLE": "sys_dialogdaten",
            "DIALOG_TYPE": "norm",
            "TABS": 2,
            "TAB_ELEMENTS": {
                "TAB_01": {
                    "TAB": 1,
                    "GUID": str(DIALOG_EDITOR_VIEW_UID),
                    "HEAD": "Liste",
                    "TABLE": "sys_dialogdaten",
                    "MODULE": "view",
                    "EDIT_TYPE": "pdvm_edit",
                    "OPEN_EDIT": "double_click",
                    "SELECTION_MODE": "single",
                },
                "TAB_02": {
                    "TAB": 2,
                    "GUID": str(DIALOG_EDITOR_FRAME_UID),
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


async def main() -> int:
    parser = argparse.ArgumentParser(description="Setup linear dialog foundation")
    parser.add_argument("--db-url", default=None, help="Optional Postgres URL for pdvm_system")
    args = parser.parse_args()

    if args.db_url:
        db_url = args.db_url
    else:
        cfg = await ConnectionManager.get_system_config("pdvm_system")
        db_url = cfg.to_url()

    conn = await asyncpg.connect(db_url)
    try:
        control_dict_rel = await _first_existing_relation(conn, ["pdvm_system.sys_control_dict", "public.sys_control_dict", "sys_control_dict"])
        dialog_rel = await _first_existing_relation(conn, ["pdvm_system.sys_dialogdaten", "public.sys_dialogdaten", "sys_dialogdaten"])

        cd_schema, cd_table = _split_schema_table(control_dict_rel)
        dg_schema, dg_table = _split_schema_table(dialog_rel)

        cd_cols = await _get_columns(conn, cd_schema, cd_table)
        dg_cols = await _get_columns(conn, dg_schema, dg_table)

        cd_pk = _pick_pk(cd_cols)
        dg_pk = _pick_pk(dg_cols)

        control_666 = _control_template_666()
        control_555 = _control_template_555()
        dialog_666 = _dialog_template_666()
        dialog_555 = _dialog_template_555()

        await _upsert_jsonb_record(
            conn,
            relation=control_dict_rel,
            cols=cd_cols,
            pk_col=cd_pk,
            record_id=TEMPLATE_UID_666,
            name="SYS_CONTROL_TEMPLATE_666",
            daten=control_666,
        )
        await _upsert_jsonb_record(
            conn,
            relation=control_dict_rel,
            cols=cd_cols,
            pk_col=cd_pk,
            record_id=TEMPLATE_UID_555,
            name="SYS_CONTROL_TEMPLATE_555",
            daten=control_555,
        )

        await _upsert_jsonb_record(
            conn,
            relation=dialog_rel,
            cols=dg_cols,
            pk_col=dg_pk,
            record_id=TEMPLATE_UID_666,
            name="SYS_DIALOG_TEMPLATE_666",
            daten=dialog_666,
        )
        await _upsert_jsonb_record(
            conn,
            relation=dialog_rel,
            cols=dg_cols,
            pk_col=dg_pk,
            record_id=TEMPLATE_UID_555,
            name="SYS_DIALOG_TEMPLATE_555",
            daten=dialog_555,
        )

        controls_seeded = await _seed_controls(conn, control_555)
        coverage = await _analyze_template_coverage(conn, control_555)

        await _upsert_jsonb_record(
            conn,
            relation=dialog_rel,
            cols=dg_cols,
            pk_col=dg_pk,
            record_id=DIALOG_EDITOR_UID,
            name="Dialogdaten Editor",
            daten=_build_dialog_record(),
        )

        print("✅ Linear Foundation Setup abgeschlossen")
        print(f"   Templates gesetzt: sys_control_dict(666/555), sys_dialogdaten(666/555)")
        print(f"   Controls upserted: {controls_seeded}")
        print(f"   Coverage observed keys: {coverage['observed_upper_count']}")
        print(f"   Coverage template keys: {coverage['known_template_count']}")
        print(f"   Coverage missing keys: {len(coverage['missing_keys'])}")
        if coverage["missing_keys"]:
            print("   Missing keys detail:")
            for key in coverage["missing_keys"]:
                print(f"   - {key}")

        print(f"   Dialog Editor UID: {DIALOG_EDITOR_UID}")
        print(f"   Hinweis: Frame/View fuer diesen Dialog wurden bereits vorher angelegt (GUIDs bleiben gleich).")

    finally:
        await conn.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

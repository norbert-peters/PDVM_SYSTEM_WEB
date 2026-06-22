from __future__ import annotations

import argparse
import asyncio
import copy
import json
import uuid
import datetime as dt
from typing import Any, Dict, List, Optional, Tuple

import asyncpg

from app.core.connection_manager import ConnectionManager
from app.core.dialog_service import extract_dialog_runtime_config

DEFAULT_DIALOG_UID = "14b932e7-451c-5509-b4b4-aac3199e2936"

DROPDOWN_DEFS: Dict[str, Dict[str, Any]] = {
    "DIALOG_TYPE": {
        "dataset_uid": "3cd9df82-2ca4-4507-9dba-b8ef904fd880",
        "dataset_name": "WORKFLOW_DIALOG_TYPE_OPTIONS",
        "field_key": "dialog_type",
        "options": [
            ("norm", "Normal", "Normal"),
            ("work", "Workflow", "Workflow"),
            ("acti", "Aktion", "Action"),
        ],
    },
    "SELECTION_MODE": {
        "dataset_uid": "b73633dd-4734-48ab-a9f9-63bf2f4c1db7",
        "dataset_name": "WORKFLOW_SELECTION_MODE_OPTIONS",
        "field_key": "selection_mode",
        "options": [
            ("single", "Einzelauswahl", "Single"),
            ("multi", "Mehrfachauswahl", "Multi"),
        ],
    },
}


def as_obj(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def _is_true(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    text = str(value or "").strip().lower()
    return text in {"1", "true", "t", "yes", "y", "ja", "j", "active", "aktiv"}


def _extract_control_blob(daten: Dict[str, Any]) -> Dict[str, Any]:
    control = daten.get("CONTROL") if isinstance(daten.get("CONTROL"), dict) else {}
    return dict(control)


def _extract_dropdown_config(control_blob: Dict[str, Any]) -> Dict[str, Any]:
    configs = control_blob.get("CONFIGS_ELEMENTS") if isinstance(control_blob.get("CONFIGS_ELEMENTS"), dict) else {}
    dropdown = configs.get("dropdown") if isinstance(configs.get("dropdown"), dict) else {}
    return dict(dropdown)


def _build_dataset(dataset_uid: str, dataset_name: str, field_key: str, options: List[Tuple[str, str, str]]) -> Dict[str, Any]:
    options_obj: Dict[str, Dict[str, Any]] = {}
    for key, value_de, value_en in options:
        options_obj[str(key)] = {
            "DE-DE": str(value_de),
            "EN-US": str(value_en),
        }

    return {
        "ROOT": {
            "SELF_GUID": str(dataset_uid),
            "SELF_NAME": str(dataset_name),
            "FIELD_KEY": str(field_key),
            "DEFAULT_LANGUAGE": "DE-DE",
        },
        "OPTIONS": options_obj,
    }


async def _table_exists(conn: asyncpg.Connection, table_name: str) -> bool:
    row = await conn.fetchrow(
        """
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = $1
        """,
        table_name,
    )
    return bool(row)


async def _table_columns(conn: asyncpg.Connection, table_name: str) -> Dict[str, Dict[str, Any]]:
    rows = await conn.fetch(
        """
        SELECT column_name, is_nullable, column_default, data_type, udt_name
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = $1
        """,
        table_name,
    )
    result: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        result[str(row["column_name"])]= {
            "nullable": str(row["is_nullable"]) == "YES",
            "default": row["column_default"],
            "data_type": str(row["data_type"] or "").lower(),
            "udt_name": str(row["udt_name"] or "").lower(),
        }
    return result


async def _resolve_dropdown_table(conn: asyncpg.Connection) -> str:
    if await _table_exists(conn, "ss_dropdowndaten"):
        return "ss_dropdowndaten"
    if await _table_exists(conn, "sys_dropdowndaten"):
        return "sys_dropdowndaten"
    raise RuntimeError("Weder ss_dropdowndaten noch sys_dropdowndaten vorhanden")


async def _ensure_dropdown_dataset(
    conn: asyncpg.Connection,
    *,
    dropdown_table: str,
    dataset_uid: str,
    dataset_name: str,
    field_key: str,
    options: List[Tuple[str, str, str]],
) -> str:
    columns = await _table_columns(conn, dropdown_table)
    payload = _build_dataset(dataset_uid, dataset_name, field_key, options)

    uid_value = uuid.UUID(str(dataset_uid))
    existing = await conn.fetchrow(
        f"SELECT uid FROM {dropdown_table} WHERE uid = $1::uuid",
        uid_value,
    )

    if existing:
        set_parts = []
        values: List[Any] = []
        idx = 2
        if "name" in columns:
            set_parts.append(f"name = ${idx}")
            values.append(dataset_name)
            idx += 1
        if "daten" in columns:
            set_parts.append(f"daten = ${idx}::jsonb")
            values.append(json.dumps(payload, ensure_ascii=False))
            idx += 1
        if "historisch" in columns:
            set_parts.append(f"historisch = ${idx}")
            values.append(False)
            idx += 1
        if "modified_at" in columns:
            set_parts.append("modified_at = NOW()")

        if set_parts:
            await conn.execute(
                f"UPDATE {dropdown_table} SET {', '.join(set_parts)} WHERE uid = $1::uuid",
                uid_value,
                *values,
            )
        return dropdown_table

    template = await conn.fetchrow(
        f"SELECT * FROM {dropdown_table} WHERE uid = $1::uuid",
        uuid.UUID("66666666-6666-6666-6666-666666666666"),
    )
    if not template:
        template = await conn.fetchrow(f"SELECT * FROM {dropdown_table} LIMIT 1")

    row_data: Dict[str, Any] = {}
    if template:
        for key in template.keys():
            row_data[str(key)] = template[key]

    row_data["uid"] = uid_value
    if "name" in columns:
        row_data["name"] = dataset_name
    if "daten" in columns:
        row_data["daten"] = json.dumps(payload, ensure_ascii=False)
    if "historisch" in columns:
        row_data["historisch"] = False
    if "gilt_bis" in columns and row_data.get("gilt_bis") is None:
        gilt_meta = columns.get("gilt_bis") or {}
        gilt_type = str(gilt_meta.get("data_type") or "")
        gilt_udt = str(gilt_meta.get("udt_name") or "")
        if "timestamp" in gilt_type or gilt_udt in {"timestamp", "timestamptz", "date"}:
            row_data["gilt_bis"] = dt.datetime(9999, 12, 31, 23, 59, 59)
        else:
            row_data["gilt_bis"] = 9999365.0
    if "created_at" in columns and row_data.get("created_at") is None:
        row_data["created_at"] = None
    if "modified_at" in columns:
        row_data["modified_at"] = None

    if "sec_id" in columns and row_data.get("sec_id") is None:
        sec_meta = columns.get("sec_id") or {}
        sec_type = str(sec_meta.get("data_type") or "")
        sec_udt = str(sec_meta.get("udt_name") or "")
        if "uuid" in sec_type or sec_udt == "uuid":
            row_data["sec_id"] = uuid.uuid4()
        else:
            max_row = await conn.fetchrow(f"SELECT MAX(sec_id) AS max_sec_id FROM {dropdown_table}")
            max_sec = int(max_row["max_sec_id"] or 0) if max_row else 0
            row_data["sec_id"] = max_sec + 1

    required_missing: List[str] = []
    for col_name, meta in columns.items():
        if col_name not in row_data and (not meta["nullable"]) and meta["default"] is None:
            required_missing.append(col_name)
    if required_missing:
        raise RuntimeError(f"Pflichtspalten ohne Wert in {dropdown_table}: {required_missing}")

    insert_cols = [col for col in columns.keys() if col in row_data]
    placeholders = [f"${idx}" for idx in range(1, len(insert_cols) + 1)]
    values = [row_data[col] for col in insert_cols]

    await conn.execute(
        f"INSERT INTO {dropdown_table} ({', '.join(insert_cols)}) VALUES ({', '.join(placeholders)})",
        *values,
    )
    return dropdown_table


async def _load_dialog(conn: asyncpg.Connection, dialog_uid: str) -> Dict[str, Any]:
    row = await conn.fetchrow(
        """
        SELECT uid, name, daten
        FROM sys_dialogdaten
        WHERE uid = $1::uuid AND COALESCE(historisch, 0) = 0
        """,
        uuid.UUID(str(dialog_uid)),
    )
    if not row:
        raise RuntimeError(f"Dialog nicht gefunden: {dialog_uid}")

    data = as_obj(row["daten"])
    root = as_obj(data.get("ROOT"))
    runtime = extract_dialog_runtime_config(
        {
            "uid": str(row["uid"]),
            "name": str(row["name"]),
            "daten": data,
            "root": root,
        }
    )

    return {
        "uid": str(row["uid"]),
        "name": str(row["name"]),
        "daten": data,
        "runtime": runtime if isinstance(runtime, dict) else {},
    }


def _resolve_setup_frame_guid(dialog_obj: Dict[str, Any]) -> str:
    runtime = dialog_obj.get("runtime") if isinstance(dialog_obj.get("runtime"), dict) else {}
    tabs = runtime.get("tab_modules") if isinstance(runtime.get("tab_modules"), list) else []

    sorted_tabs = sorted(tabs, key=lambda x: int((x or {}).get("index") or 0))
    for tab in sorted_tabs:
        head = str((tab or {}).get("head") or "").strip().lower()
        module = str((tab or {}).get("module") or "").strip().lower()
        index = int((tab or {}).get("index") or 0)
        if module == "edit" and (head == "setup" or index == 2):
            guid = str((tab or {}).get("guid") or "").strip()
            if guid:
                return guid

    raise RuntimeError("Setup-Tab Frame-GUID konnte nicht aus tab_modules ermittelt werden")


async def _load_active_control_rows(conn: asyncpg.Connection, field_name: str) -> List[Dict[str, Any]]:
    rows = await conn.fetch(
        """
        SELECT uid, name, daten, historisch
        FROM sys_control_dict
        WHERE COALESCE(historisch, 0) = 0
        """
    )

    result: List[Dict[str, Any]] = []
    target = str(field_name or "").strip().upper()
    for row in rows:
        data = as_obj(row["daten"])
        control = _extract_control_blob(data)
        feld = str(control.get("FELD") or control.get("FIELD") or "").strip().upper()
        if feld != target:
            continue
        result.append(
            {
                "uid": str(row["uid"]),
                "name": str(row["name"]),
                "daten": data,
                "control": control,
            }
        )
    return result


async def _update_control_dropdown_link(
    conn: asyncpg.Connection,
    *,
    field_name: str,
    dropdown_table: str,
    dropdown_key: str,
    dropdown_field: str,
) -> int:
    rows = await _load_active_control_rows(conn, field_name)
    updated = 0

    dropdown_cfg = {
        "source": "static",
        "table": dropdown_table,
        "key": str(dropdown_key),
        "feld": str(dropdown_field),
        "group": "",
    }

    for row in rows:
        data = copy.deepcopy(row["daten"])
        control = data.get("CONTROL") if isinstance(data.get("CONTROL"), dict) else {}
        control = dict(control)
        control["TYPE"] = "dropdown"
        control["type"] = "dropdown"

        configs = control.get("CONFIGS_ELEMENTS") if isinstance(control.get("CONFIGS_ELEMENTS"), dict) else {}
        configs = dict(configs)
        current_dropdown = configs.get("dropdown") if isinstance(configs.get("dropdown"), dict) else {}
        merged_dropdown = dict(current_dropdown)
        merged_dropdown.update(dropdown_cfg)
        configs["dropdown"] = merged_dropdown
        control["CONFIGS_ELEMENTS"] = configs
        data["CONTROL"] = control

        await conn.execute(
            """
            UPDATE sys_control_dict
            SET daten = $2::jsonb,
                modified_at = NOW()
            WHERE uid = $1::uuid
            """,
            uuid.UUID(row["uid"]),
            json.dumps(data, ensure_ascii=False),
        )
        updated += 1

    return updated


async def _update_setup_frame_dropdowns(
    conn: asyncpg.Connection,
    *,
    frame_guid: str,
    field_to_dropdown_cfg: Dict[str, Dict[str, Any]],
) -> Dict[str, int]:
    row = await conn.fetchrow(
        """
        SELECT uid, daten
        FROM sys_framedaten
        WHERE uid = $1::uuid AND COALESCE(historisch, 0) = 0
        """,
        uuid.UUID(str(frame_guid)),
    )
    if not row:
        raise RuntimeError(f"Setup-Frame nicht gefunden: {frame_guid}")

    data = as_obj(row["daten"])
    fields_map = data.get("FIELDS") if isinstance(data.get("FIELDS"), dict) else {}
    fields_map = dict(fields_map)

    changed = 0
    touched: Dict[str, int] = {"DIALOG_TYPE": 0, "SELECTION_MODE": 0}
    for field_uid, item in fields_map.items():
        entry = item if isinstance(item, dict) else {}
        feld = str(entry.get("feld") or entry.get("field") or "").strip().upper()
        if feld not in field_to_dropdown_cfg:
            continue

        cfg = field_to_dropdown_cfg[feld]
        old_type = str(entry.get("type") or "").strip().lower()
        if old_type != "dropdown":
            entry["type"] = "dropdown"
            changed += 1

        configs = entry.get("configs") if isinstance(entry.get("configs"), dict) else {}
        configs = dict(configs)
        dropdown = configs.get("dropdown") if isinstance(configs.get("dropdown"), dict) else {}
        merged = dict(dropdown)
        merged.update(cfg)
        if merged != dropdown:
            configs["dropdown"] = merged
            entry["configs"] = configs
            changed += 1

        fields_map[field_uid] = entry
        touched[feld] = touched.get(feld, 0) + 1

    # Add required workflow fields when they are missing in setup frame.
    for required_feld in ("DIALOG_TYPE", "SELECTION_MODE"):
        if touched.get(required_feld, 0) > 0:
            continue
        cfg = field_to_dropdown_cfg[required_feld]
        new_field_uid = str(uuid.uuid4())
        display_order = 40 if required_feld == "DIALOG_TYPE" else 50
        label = "Dialog Type" if required_feld == "DIALOG_TYPE" else "Selection Mode"
        name = "wf_dialog_dialog_type" if required_feld == "DIALOG_TYPE" else "wf_dialog_selection_mode"
        fields_map[new_field_uid] = {
            "tab": 1,
            "feld": required_feld,
            "name": name,
            "type": "dropdown",
            "label": label,
            "table": "SYS_CONTROL_DICT",
            "gruppe": "FIELDS",
            "abdatum": False,
            "configs": {
                "help": {"key": "", "feld": "", "table": "", "gruppe": ""},
                "dropdown": cfg,
            },
            "tooltip": "",
            "read_only": False,
            "historical": False,
            "source_path": "fields",
            "display_order": display_order,
        }
        touched[required_feld] = 1
        changed += 1

    if changed > 0:
        data["FIELDS"] = fields_map
        await conn.execute(
            """
            UPDATE sys_framedaten
            SET daten = $2::jsonb,
                modified_at = NOW()
            WHERE uid = $1::uuid
            """,
            uuid.UUID(str(frame_guid)),
            json.dumps(data, ensure_ascii=False),
        )

    return {
        "changed_fragments": changed,
        "touched_dialog_type": touched.get("DIALOG_TYPE", 0),
        "touched_selection_mode": touched.get("SELECTION_MODE", 0),
    }


async def run(dialog_uid: str) -> Dict[str, Any]:
    cfg = await ConnectionManager.get_system_config("pdvm_system")
    conn = await asyncpg.connect(cfg.to_url())

    try:
        dialog = await _load_dialog(conn, dialog_uid)
        setup_frame_guid = _resolve_setup_frame_guid(dialog)
        dropdown_table = await _resolve_dropdown_table(conn)

        field_dropdown_configs: Dict[str, Dict[str, Any]] = {}
        dataset_results: Dict[str, Any] = {}
        control_updates: Dict[str, int] = {}

        for field_name, spec in DROPDOWN_DEFS.items():
            used_table = await _ensure_dropdown_dataset(
                conn,
                dropdown_table=dropdown_table,
                dataset_uid=spec["dataset_uid"],
                dataset_name=spec["dataset_name"],
                field_key=spec["field_key"],
                options=spec["options"],
            )
            field_dropdown_configs[field_name] = {
                "source": "static",
                "table": used_table,
                "key": spec["dataset_uid"],
                "feld": spec["field_key"],
                "group": "",
            }
            dataset_results[field_name] = {
                "table": used_table,
                "key": spec["dataset_uid"],
                "feld": spec["field_key"],
            }

            control_updates[field_name] = await _update_control_dropdown_link(
                conn,
                field_name=field_name,
                dropdown_table=used_table,
                dropdown_key=spec["dataset_uid"],
                dropdown_field=spec["field_key"],
            )

        frame_result = await _update_setup_frame_dropdowns(
            conn,
            frame_guid=setup_frame_guid,
            field_to_dropdown_cfg=field_dropdown_configs,
        )

        return {
            "dialog_uid": dialog["uid"],
            "dialog_name": dialog["name"],
            "setup_frame_guid": setup_frame_guid,
            "dropdown_table": dropdown_table,
            "datasets": dataset_results,
            "control_updates": control_updates,
            "frame_update": frame_result,
        }
    finally:
        await conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Fix workflow setup tab dropdown links")
    parser.add_argument("--dialog-uid", default=DEFAULT_DIALOG_UID, help="Workflow dialog UID")
    args = parser.parse_args()

    result = asyncio.run(run(args.dialog_uid))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

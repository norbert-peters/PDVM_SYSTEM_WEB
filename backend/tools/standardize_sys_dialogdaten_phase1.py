from __future__ import annotations

import argparse
import asyncio
import copy
import datetime as dt
import json
import uuid
from pathlib import Path
import sys
from typing import Any, Dict, List, Tuple

import asyncpg

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.connection_manager import ConnectionManager


UID_555 = "55555555-5555-5555-5555-555555555555"
UID_666 = "66666666-6666-6666-6666-666666666666"
UID_000 = "00000000-0000-0000-0000-000000000000"
RESERVED = {UID_000, UID_555, UID_666}
CONTROL_NS = uuid.UUID("13cfa2a8-87bf-4c2a-9e3d-f2f620f4e9d1")


def _as_obj(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def _is_meaningful(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str) and not value.strip():
        return False
    return True


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _upper_field(name: str) -> str:
    return str(name or "").strip().upper()


def _canonical_control_name(table_name: str, field_name: str) -> str:
    prefix = str(table_name or "sys").strip().split("_", 1)[0].upper() or "SYS"
    return f"{prefix}_{_upper_field(field_name)}"


def _extract_tab_elements(root: Dict[str, Any]) -> Dict[int, Dict[str, Any]]:
    out: Dict[int, Dict[str, Any]] = {}

    tab_elements = _as_obj(root.get("TAB_ELEMENTS"))
    for key, value in tab_elements.items():
        row = _as_obj(value)
        if not row:
            continue
        idx = 0
        if isinstance(row.get("index"), int):
            idx = int(row.get("index") or 0)
        if idx <= 0:
            txt = str(key or "").strip().upper()
            if txt.startswith("TAB_"):
                idx = _to_int(txt.split("_", 1)[1], 0)
        if idx > 0:
            out[idx] = row

    for i in range(1, 21):
        legacy_key = f"TAB_{i:02d}"
        row = _as_obj(root.get(legacy_key))
        if row and i not in out:
            out[i] = row

    return out


def _template_tab_shape(template_666: Dict[str, Any]) -> Dict[str, Any]:
    templates = _as_obj(template_666.get("TEMPLATES"))
    tab_elements = _as_obj(templates.get("TAB_ELEMENTS"))
    if tab_elements:
        first_key = sorted(tab_elements.keys())[0]
        return _as_obj(tab_elements.get(first_key))
    return {
        "HEAD": "",
        "MODULE": "",
        "GUID": "",
        "TABLE": "",
        "EDIT_TYPE": "",
    }


def _normalize_tab_elements(
    *,
    root_current: Dict[str, Any],
    root_555: Dict[str, Any],
    tab_shape: Dict[str, Any],
) -> Tuple[Dict[str, Dict[str, Any]], int]:
    tabs_raw = _to_int(root_current.get("TABS"), _to_int(root_555.get("TABS"), 0))
    extracted = _extract_tab_elements(root_current)
    if tabs_raw <= 0:
        tabs_raw = len(extracted)

    tabs = max(tabs_raw, len(extracted))
    tabs = max(0, min(20, tabs))

    normalized: Dict[str, Dict[str, Any]] = {}
    shape_keys = list(_as_obj(tab_shape).keys())
    if not shape_keys:
        shape_keys = ["HEAD", "MODULE", "GUID", "TABLE", "EDIT_TYPE"]

    for i in range(1, tabs + 1):
        src = _as_obj(extracted.get(i))
        base = copy.deepcopy(tab_shape)

        for key in shape_keys:
            if _is_meaningful(src.get(key)):
                base[key] = src.get(key)

        if not _is_meaningful(base.get("MODULE")):
            if i == 1:
                base["MODULE"] = "view"
            elif i == 2:
                base["MODULE"] = "edit"

        normalized[f"TAB_{i:02d}"] = base

    return normalized, tabs


def _normalize_table_info(*, daten_current: Dict[str, Any], template_666: Dict[str, Any]) -> Dict[str, Any]:
    templates = _as_obj(template_666.get("TEMPLATES"))
    table_info_tpl = _as_obj(templates.get("TABLE_INFO"))
    current_ti = _as_obj(daten_current.get("TABLE_INFO"))

    out = copy.deepcopy(table_info_tpl)
    for key in table_info_tpl.keys():
        if _is_meaningful(current_ti.get(key)):
            out[key] = current_ti.get(key)
    return out


def _build_normalized_dialog_daten(
    *,
    uid: str,
    row_name: str,
    daten_current: Dict[str, Any],
    root_555: Dict[str, Any],
    template_666: Dict[str, Any],
) -> Dict[str, Any]:
    root_current = _as_obj(daten_current.get("ROOT"))
    new_root: Dict[str, Any] = {}

    for key in root_555.keys():
        if _is_meaningful(root_current.get(key)):
            new_root[key] = root_current.get(key)
        else:
            new_root[key] = root_555.get(key)

    tab_shape = _template_tab_shape(template_666)
    tab_elements, tabs = _normalize_tab_elements(root_current=root_current, root_555=root_555, tab_shape=tab_shape)

    if "TAB_ELEMENTS" in root_555:
        new_root["TAB_ELEMENTS"] = tab_elements
    if "TABS" in root_555:
        new_root["TABS"] = tabs

    new_root["SELF_GUID"] = uid
    if _is_meaningful(root_current.get("SELF_NAME")):
        new_root["SELF_NAME"] = root_current.get("SELF_NAME")
    else:
        new_root["SELF_NAME"] = row_name

    table_info = _normalize_table_info(daten_current=daten_current, template_666=template_666)

    return {
        "ROOT": new_root,
        "TABLE_INFO": table_info,
    }


def _infer_control_type(group: str, field: str) -> str:
    field_up = _upper_field(field)
    if field_up.endswith("_AT") or field_up.endswith("_BIS"):
        return "datetime"
    if field_up in {"TABS"}:
        return "number"
    if field_up in {"TAB_ELEMENTS", "TABLE_INFO"}:
        return "json"
    if field_up in {"OPEN_EDIT", "DIALOG_TYPE", "SELECTION_MODE"}:
        return "text"
    return "text"


def _collect_required_controls(root_555: Dict[str, Any], table_info_template: Dict[str, Any]) -> List[Tuple[str, str]]:
    required: List[Tuple[str, str]] = []

    for key in root_555.keys():
        required.append(("ROOT", _upper_field(key)))

    for key in table_info_template.keys():
        required.append(("TABLE_INFO", _upper_field(key)))

    # Stable order and dedupe.
    seen = set()
    out: List[Tuple[str, str]] = []
    for group, field in required:
        marker = f"{group}::{field}"
        if marker in seen:
            continue
        seen.add(marker)
        out.append((group, field))
    return out


async def _table_columns(conn: asyncpg.Connection, table_name: str) -> Dict[str, Dict[str, Any]]:
    rows = await conn.fetch(
        """
        SELECT column_name, is_nullable, column_default, data_type, udt_name
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = $1
        """,
        table_name,
    )
    out: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        out[str(row["column_name"])] = {
            "nullable": str(row["is_nullable"]) == "YES",
            "default": row["column_default"],
            "data_type": str(row["data_type"] or "").lower(),
            "udt_name": str(row["udt_name"] or "").lower(),
        }
    return out


async def _insert_control_from_template(
    conn: asyncpg.Connection,
    *,
    template_row: asyncpg.Record,
    columns: Dict[str, Dict[str, Any]],
    uid_value: str,
    name_value: str,
    daten_value: Dict[str, Any],
) -> None:
    row_data: Dict[str, Any] = {str(k): template_row[k] for k in template_row.keys()}

    row_data["uid"] = uuid.UUID(uid_value)
    if "name" in columns:
        row_data["name"] = name_value
    if "daten" in columns:
        row_data["daten"] = json.dumps(daten_value, ensure_ascii=False)
    if "historisch" in columns:
        row_data["historisch"] = False
    if "modified_at" in columns:
        row_data["modified_at"] = None
    if "created_at" in columns and row_data.get("created_at") is None:
        row_data["created_at"] = None
    if "link_uid" in columns:
        row_data["link_uid"] = uuid.UUID(uid_value)
    if "sec_id" in columns and row_data.get("sec_id") is None:
        sec_meta = columns.get("sec_id") or {}
        if "uuid" in str(sec_meta.get("data_type") or "") or str(sec_meta.get("udt_name") or "") == "uuid":
            row_data["sec_id"] = uuid.uuid4()
    if "gilt_bis" in columns and row_data.get("gilt_bis") is None:
        gb_meta = columns.get("gilt_bis") or {}
        gb_type = str(gb_meta.get("data_type") or "")
        gb_udt = str(gb_meta.get("udt_name") or "")
        if "timestamp" in gb_type or gb_udt in {"timestamp", "timestamptz", "date"}:
            row_data["gilt_bis"] = dt.datetime(9999, 12, 31, 23, 59, 59)

    insert_cols = [col for col in columns.keys() if col in row_data]
    placeholders = [f"${i}" for i in range(1, len(insert_cols) + 1)]
    values = [row_data[c] for c in insert_cols]

    await conn.execute(
        f"INSERT INTO sys_control_dict ({', '.join(insert_cols)}) VALUES ({', '.join(placeholders)})",
        *values,
    )


async def main_async(*, apply_changes: bool, dialog_uid_focus: str | None) -> int:
    cfg = await ConnectionManager.get_system_config("pdvm_system")
    conn = await asyncpg.connect(cfg.to_url())

    try:
        row_555 = await conn.fetchrow(
            "SELECT daten FROM sys_dialogdaten WHERE uid = $1::uuid AND COALESCE(historisch,0)=0",
            UID_555,
        )
        row_666 = await conn.fetchrow(
            "SELECT daten FROM sys_dialogdaten WHERE uid = $1::uuid AND COALESCE(historisch,0)=0",
            UID_666,
        )
        if not row_555 or not row_666:
            raise RuntimeError("sys_dialogdaten 555/666 fehlen")

        daten_555 = _as_obj(row_555.get("daten"))
        daten_666 = _as_obj(row_666.get("daten"))
        root_555 = _as_obj(daten_555.get("ROOT"))
        templates_666 = _as_obj(daten_666.get("TEMPLATES"))
        table_info_template = _as_obj(templates_666.get("TABLE_INFO"))

        rows = await conn.fetch(
            "SELECT uid, name, daten FROM sys_dialogdaten WHERE COALESCE(historisch,0)=0 ORDER BY name"
        )

        changed_dialogs: List[str] = []
        removed_root_props_total = 0

        for row in rows:
            uid_txt = str(row["uid"])
            if uid_txt in RESERVED:
                continue
            if dialog_uid_focus and uid_txt != dialog_uid_focus:
                continue

            current_daten = _as_obj(row.get("daten"))
            current_root = _as_obj(current_daten.get("ROOT"))
            before_root_keys = set(current_root.keys())

            normalized = _build_normalized_dialog_daten(
                uid=uid_txt,
                row_name=str(row.get("name") or ""),
                daten_current=current_daten,
                root_555=root_555,
                template_666=daten_666,
            )

            after_root_keys = set(_as_obj(normalized.get("ROOT")).keys())
            removed = [k for k in before_root_keys if k not in after_root_keys]
            removed_root_props_total += len(removed)

            if json.dumps(current_daten, ensure_ascii=False, sort_keys=True) == json.dumps(normalized, ensure_ascii=False, sort_keys=True):
                continue

            changed_dialogs.append(f"{row.get('name')} [{uid_txt}]")
            if apply_changes:
                await conn.execute(
                    """
                    UPDATE sys_dialogdaten
                    SET daten = $2::jsonb,
                        modified_at = NOW()
                    WHERE uid = $1::uuid
                    """,
                    uuid.UUID(uid_txt),
                    json.dumps(normalized, ensure_ascii=False),
                )

        # Control existence check/create for remaining properties.
        required_controls = _collect_required_controls(root_555, table_info_template)

        control_rows = await conn.fetch(
            "SELECT uid, daten FROM sys_control_dict WHERE COALESCE(historisch,0)=0"
        )
        existing: Dict[str, str] = {}
        for crow in control_rows:
            data = _as_obj(crow.get("daten"))
            control = _as_obj(data.get("CONTROL"))
            group = _upper_field(control.get("GRUPPE") or control.get("gruppe"))
            field = _upper_field(control.get("FIELD") or control.get("FELD") or control.get("feld"))
            table = str(control.get("TABLE") or "").strip().lower()
            if table != "sys_dialogdaten":
                continue
            if not group or not field:
                continue
            existing[f"{group}::{field}"] = str(crow.get("uid"))

        control_template_row = await conn.fetchrow(
            "SELECT * FROM sys_control_dict WHERE uid = $1::uuid AND COALESCE(historisch,0)=0",
            UID_666,
        )
        if not control_template_row:
            raise RuntimeError("sys_control_dict 666 fehlt")
        control_template_data = _as_obj(control_template_row.get("daten"))
        base_root = _as_obj(control_template_data.get("ROOT"))
        base_control = _as_obj(control_template_data.get("CONTROL"))
        control_columns = await _table_columns(conn, "sys_control_dict")

        created_controls: List[str] = []

        for group, field in required_controls:
            marker = f"{group}::{field}"
            if marker in existing:
                continue

            ctrl_uid = str(uuid.uuid5(CONTROL_NS, f"sys_dialogdaten::{group}::{field}"))
            ctrl_name = _canonical_control_name("sys_dialogdaten", field)

            root = copy.deepcopy(base_root)
            root.update(
                {
                    "SELF_GUID": ctrl_uid,
                    "SELF_NAME": ctrl_name,
                    "NAME": ctrl_name,
                    "TABLE": "sys_dialogdaten",
                    "FIELD": field,
                }
            )

            control = copy.deepcopy(base_control)
            control.update(
                {
                    "NAME": ctrl_name,
                    "TABLE": "sys_dialogdaten",
                    "GRUPPE": group,
                    "FIELD": field,
                    "FELD": field,
                    "TYPE": _infer_control_type(group, field),
                    "type": _infer_control_type(group, field),
                }
            )

            daten_new = {"ROOT": root, "CONTROL": control}

            created_controls.append(f"{group}.{field} [{ctrl_uid}]")
            if apply_changes:
                await _insert_control_from_template(
                    conn,
                    template_row=control_template_row,
                    columns=control_columns,
                    uid_value=ctrl_uid,
                    name_value=ctrl_name,
                    daten_value=daten_new,
                )

        mode = "APPLY" if apply_changes else "DRY-RUN"
        print(f"=== sys_dialogdaten Standardisierung ({mode}) ===")
        print(f"dialog_uid_focus: {dialog_uid_focus or 'ALL'}")
        print(f"dialogs_changed: {len(changed_dialogs)}")
        print(f"root_properties_removed_total: {removed_root_props_total}")
        for item in changed_dialogs[:20]:
            print(f"- {item}")

        print(f"\n=== sys_control_dict Abgleich ({mode}) ===")
        print(f"required_controls: {len(required_controls)}")
        print(f"controls_created: {len(created_controls)}")
        for item in created_controls[:40]:
            print(f"- {item}")

        return 0
    finally:
        await conn.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Standardisiert sys_dialogdaten und ergänzt fehlende sys_control_dict Controls")
    parser.add_argument("--apply", action="store_true", help="Schreibt Änderungen in die DB")
    parser.add_argument("--dialog-uid", default=None, help="Optional: nur ein Dialogdatensatz")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    raise SystemExit(asyncio.run(main_async(apply_changes=bool(args.apply), dialog_uid_focus=args.dialog_uid)))

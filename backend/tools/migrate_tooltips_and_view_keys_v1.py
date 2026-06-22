"""
Migration V1:
1) sys_tooltipdaten anlegen und Basissaetze 000/555/666 sicherstellen.
2) sys_framedaten: tooltip-Strings nach sys_tooltipdaten migrieren und als Referenz speichern.
3) sys_viewdaten: Legacy-Keys hart auf kanonische Keys umstellen (ohne Alias/Fallback).

Ausfuehrung:
    python tools/migrate_tooltips_and_view_keys_v1.py
"""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Optional, Tuple

import asyncpg


DEFAULT_DB_URL = os.getenv("DATABASE_URL") or os.getenv("PDVM_SYSTEM_DATABASE_URL") or "postgresql://postgres:Polari$55@localhost:5432/pdvm_system"

BASE_UIDS = {
    "000": uuid.UUID("00000000-0000-0000-0000-000000000000"),
    "555": uuid.UUID("55555555-5555-5555-5555-555555555555"),
    "666": uuid.UUID("66666666-6666-6666-6666-666666666666"),
}


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_json_object(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _deep_copy_json(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False))


def _boolish(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return float(value) != 0.0
    s = _as_text(value).lower()
    return s in {"1", "true", "yes", "y", "on"}


@dataclass
class FrameMigrationStats:
    rows_checked: int = 0
    rows_changed: int = 0
    tooltip_values_migrated: int = 0
    tooltip_datasets_upserted: int = 0


@dataclass
class ViewMigrationStats:
    rows_checked: int = 0
    rows_changed: int = 0
    controls_changed: int = 0


def _base_tooltip_row(uid: uuid.UUID, name: str) -> Dict[str, Any]:
    uid_text = str(uid)
    return {
        "ROOT": {
            "SELF_GUID": uid_text,
            "SELF_NAME": name,
            "TABLE": "sys_tooltipdaten",
            "DEFAULT_LANGUAGE": "DE-DE",
            "IS_TEMPLATE": uid_text in {str(BASE_UIDS["555"]), str(BASE_UIDS["666"])},
        },
        "DE-DE": {},
        "EN-EN": {},
    }


def _merge_tooltip_entry(language_map: Dict[str, Any], feld_key: str, text_value: str) -> bool:
    current = language_map.get(feld_key)
    if isinstance(current, dict):
        if _as_text(current.get("text")):
            return False
        current = dict(current)
        current["text"] = text_value
        current.setdefault("label", feld_key)
        language_map[feld_key] = current
        return True

    if isinstance(current, str):
        if _as_text(current):
            return False

    language_map[feld_key] = {
        "label": feld_key,
        "text": text_value,
    }
    return True


async def _ensure_tooltip_table_and_base_rows(conn: asyncpg.Connection) -> None:
    await conn.execute("SELECT create_pdvm_table('sys_tooltipdaten')")

    for suffix, uid in BASE_UIDS.items():
        row = await conn.fetchrow("SELECT uid FROM sys_tooltipdaten WHERE uid = $1", uid)
        if row:
            continue
        name = f"sys_tooltipdaten_template_{suffix}"
        await conn.execute(
            """
            INSERT INTO sys_tooltipdaten (uid, name, daten, historisch)
            VALUES ($1, $2, $3::jsonb, 0)
            """,
            uid,
            name,
            json.dumps(_base_tooltip_row(uid, name), ensure_ascii=False),
        )


async def _load_tooltip_dataset(conn: asyncpg.Connection, dataset_uid: uuid.UUID, frame_uid: uuid.UUID) -> Tuple[str, Dict[str, Any]]:
    row = await conn.fetchrow("SELECT name, daten FROM sys_tooltipdaten WHERE uid = $1", dataset_uid)
    if row:
        name = _as_text(row["name"]) or f"frame_tooltips_{str(frame_uid)[:8]}"
        daten = _as_json_object(row["daten"])
        daten.setdefault("ROOT", {})
        daten.setdefault("DE-DE", {})
        daten.setdefault("EN-EN", {})
        return name, daten

    name = f"frame_tooltips_{str(frame_uid)[:8]}"
    return name, _base_tooltip_row(dataset_uid, name)


def _normalize_tooltip_ref(*, dataset_uid: uuid.UUID, feld_key: str) -> Dict[str, Any]:
    return {
        "table": "sys_tooltipdaten",
        "key": str(dataset_uid),
        "feld": str(feld_key),
        "gruppe": "",
    }


async def _migrate_frame_tooltips(conn: asyncpg.Connection) -> FrameMigrationStats:
    stats = FrameMigrationStats()

    rows = await conn.fetch("SELECT uid, daten FROM sys_framedaten WHERE historisch = 0")
    stats.rows_checked = len(rows)

    for row in rows:
        frame_uid = row["uid"]
        daten = _as_json_object(row["daten"])
        fields = _as_dict(daten.get("FIELDS"))
        if not fields:
            continue

        dataset_uid = uuid.uuid5(uuid.NAMESPACE_URL, f"sys_tooltipdaten:{frame_uid}")
        dataset_name = ""
        dataset_data: Dict[str, Any] = {}
        dataset_dirty = False
        frame_dirty = False

        next_fields = _deep_copy_json(fields)

        for field_key, raw_item in next_fields.items():
            item = _as_dict(raw_item)
            if not item:
                continue

            tooltip_ref_raw = item.get("tooltip")
            if isinstance(tooltip_ref_raw, dict):
                # Bereits migriert: sicherheitshalber configs.tooltips spiegeln.
                cfg = _as_dict(item.get("configs"))
                if cfg.get("tooltips") != tooltip_ref_raw:
                    cfg = dict(cfg)
                    cfg["tooltips"] = tooltip_ref_raw
                    item["configs"] = cfg
                    next_fields[field_key] = item
                    frame_dirty = True
                continue

            tooltip_text = _as_text(item.get("tooltip") or item.get("TOOLTIP"))
            if not tooltip_text:
                continue

            if not dataset_data:
                dataset_name, dataset_data = await _load_tooltip_dataset(conn, dataset_uid, frame_uid)

            de_group = _as_dict(dataset_data.get("DE-DE"))
            en_group = _as_dict(dataset_data.get("EN-EN"))
            changed_de = _merge_tooltip_entry(de_group, str(field_key), tooltip_text)
            changed_en = _merge_tooltip_entry(en_group, str(field_key), tooltip_text)
            dataset_data["DE-DE"] = de_group
            dataset_data["EN-EN"] = en_group

            if changed_de or changed_en:
                dataset_dirty = True

            ref_obj = _normalize_tooltip_ref(dataset_uid=dataset_uid, feld_key=str(field_key))
            cfg = _as_dict(item.get("configs"))
            cfg = dict(cfg)
            cfg["tooltips"] = ref_obj

            updated_item = dict(item)
            updated_item["tooltip"] = ref_obj
            updated_item.pop("TOOLTIP", None)
            updated_item["configs"] = cfg

            next_fields[field_key] = updated_item
            frame_dirty = True
            stats.tooltip_values_migrated += 1

        if dataset_dirty and dataset_data:
            await conn.execute(
                """
                INSERT INTO sys_tooltipdaten (uid, name, daten, historisch)
                VALUES ($1, $2, $3::jsonb, 0)
                ON CONFLICT (uid)
                DO UPDATE SET
                    name = EXCLUDED.name,
                    daten = EXCLUDED.daten,
                    modified_at = NOW()
                """,
                dataset_uid,
                dataset_name,
                json.dumps(dataset_data, ensure_ascii=False),
            )
            stats.tooltip_datasets_upserted += 1

        if frame_dirty:
            next_data = _deep_copy_json(daten)
            next_data["FIELDS"] = next_fields
            await conn.execute(
                "UPDATE sys_framedaten SET daten = $1::jsonb, modified_at = NOW() WHERE uid = $2",
                json.dumps(next_data, ensure_ascii=False),
                frame_uid,
            )
            stats.rows_changed += 1

    return stats


def _pick_first(control: Dict[str, Any], keys: Iterable[str]) -> Any:
    for key in keys:
        if key in control and control.get(key) is not None:
            return control.get(key)
    return None


def _normalize_view_control_keys(control: Dict[str, Any]) -> Tuple[Dict[str, Any], bool]:
    out = dict(control)
    changed = False

    mappings = [
        ("TYPE", ["TYPE", "type", "CONTROL_TYPE", "control_type"]),
        ("FILTER_TYPE", ["FILTER_TYPE", "filter_type", "FILTERTYPE", "filterType"]),
        ("DISPLAY_SHOW", ["DISPLAY_SHOW", "display_show", "SHOW", "show"]),
        ("SORT_BY_ORIGINAL", ["SORT_BY_ORIGINAL", "sort_by_original", "SORTBYORIGINAL", "sortByOriginal"]),
        ("SORT_DIRECTION", ["SORT_DIRECTION", "sort_direction", "SORTDIRECTION", "sortDirection"]),
    ]

    for target, aliases in mappings:
        picked = _pick_first(out, aliases)
        if target == "DISPLAY_SHOW" and picked is not None:
            picked = _boolish(picked)
        if target in {"SORT_DIRECTION"} and picked is not None:
            picked = _as_text(picked).lower()

        if picked is not None and out.get(target) != picked:
            out[target] = picked
            changed = True

        for alias in aliases:
            if alias == target:
                continue
            if alias in out:
                out.pop(alias, None)
                changed = True

    return out, changed


async def _migrate_view_keys(conn: asyncpg.Connection) -> ViewMigrationStats:
    stats = ViewMigrationStats()
    rows = await conn.fetch("SELECT uid, daten FROM sys_viewdaten WHERE historisch = 0")
    stats.rows_checked = len(rows)

    for row in rows:
        view_uid = row["uid"]
        daten = _as_json_object(row["daten"])
        if not daten:
            continue

        changed_row = False
        next_data = _deep_copy_json(daten)

        for section_key, section_val in list(next_data.items()):
            if section_key == "ROOT":
                continue
            if not isinstance(section_val, dict):
                continue

            next_section = dict(section_val)
            section_changed = False
            for control_guid, raw_control in list(next_section.items()):
                if not isinstance(raw_control, dict):
                    continue
                normalized_control, control_changed = _normalize_view_control_keys(raw_control)
                if control_changed:
                    next_section[control_guid] = normalized_control
                    section_changed = True
                    stats.controls_changed += 1

            if section_changed:
                next_data[section_key] = next_section
                changed_row = True

        if changed_row:
            await conn.execute(
                "UPDATE sys_viewdaten SET daten = $1::jsonb, modified_at = NOW() WHERE uid = $2",
                json.dumps(next_data, ensure_ascii=False),
                view_uid,
            )
            stats.rows_changed += 1

    return stats


async def run() -> None:
    conn = await asyncpg.connect(DEFAULT_DB_URL)
    try:
        print("=" * 80)
        print("MIGRATION V1: TOOLTIPS + VIEW-KEYS")
        print("=" * 80)

        await _ensure_tooltip_table_and_base_rows(conn)
        print("[1/3] sys_tooltipdaten bereit und Basissaetze 000/555/666 vorhanden")

        frame_stats = await _migrate_frame_tooltips(conn)
        print(
            "[2/3] sys_framedaten migriert: "
            f"rows_checked={frame_stats.rows_checked}, "
            f"rows_changed={frame_stats.rows_changed}, "
            f"tooltip_values_migrated={frame_stats.tooltip_values_migrated}, "
            f"tooltip_datasets_upserted={frame_stats.tooltip_datasets_upserted}"
        )

        view_stats = await _migrate_view_keys(conn)
        print(
            "[3/3] sys_viewdaten migriert: "
            f"rows_checked={view_stats.rows_checked}, "
            f"rows_changed={view_stats.rows_changed}, "
            f"controls_changed={view_stats.controls_changed}"
        )

        print("=" * 80)
        print("FERTIG")
        print("=" * 80)
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(run())

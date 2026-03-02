"""Normalisiert Kern-Tabellen auf PDVM Linear Schema V1 (Schritt 3).

Scope:
- Case-Normalisierung (Gruppen + Property-Keys)
- Struktur-Normalisierung (ROOT-Pflichtfelder, TAB_ELEMENTS in Dialogen)
- Vereinheitlichung SELF_GUID/SELF_NAME

Usage:
  python backend/tools/migrate_linear_schema_v1.py --dry-run
  python backend/tools/migrate_linear_schema_v1.py --apply
  python backend/tools/migrate_linear_schema_v1.py --apply --tables sys_dialogdaten,sys_control_dict
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

import sys

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import asyncpg

from app.core.connection_manager import ConnectionManager

DEFAULT_TABLES = [
    "sys_control_dict",
    "sys_contr_dict_man",
    "sys_dialogdaten",
    "sys_viewdaten",
    "sys_framedaten",
]


@dataclass
class MigrationStats:
    table_name: str
    scanned: int = 0
    changed: int = 0
    unchanged: int = 0
    skipped: int = 0


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _upper_dict_keys(data: Dict[str, Any]) -> Tuple[Dict[str, Any], bool]:
    changed = False
    out: Dict[str, Any] = {}
    for key, value in data.items():
        new_key = key.upper() if isinstance(key, str) else key
        if new_key != key:
            changed = True
        out[new_key] = value
    return out, changed


def _extract_tab_elements(value: Any) -> Dict[int, Dict[str, Any]]:
    out: Dict[int, Dict[str, Any]] = {}

    if isinstance(value, dict):
        for key, row in value.items():
            if not isinstance(row, dict):
                continue
            idx = None
            match = re.match(r"^TAB[_\-]?0*(\d+)$", str(key), flags=re.IGNORECASE)
            if match:
                idx = int(match.group(1))
            elif isinstance(row.get("TAB"), int):
                idx = int(row.get("TAB"))
            if not idx or idx < 1 or idx > 20:
                continue
            out[idx] = row
        return out

    if isinstance(value, list):
        for pos, row in enumerate(value, start=1):
            if not isinstance(row, dict):
                continue
            raw_idx = row.get("TAB") or row.get("index") or pos
            try:
                idx = int(raw_idx)
            except Exception:
                continue
            if idx < 1 or idx > 20:
                continue
            out[idx] = row

    return out


def _normalize_dialog_tab_elements(root: Dict[str, Any]) -> Tuple[Dict[str, Any], bool]:
    changed = False
    new_root = dict(root)

    tabs_raw = new_root.get("TABS")
    try:
        tabs = int(tabs_raw) if tabs_raw is not None else 0
    except Exception:
        tabs = 0
    tabs = max(0, min(20, tabs))

    existing = _extract_tab_elements(new_root.get("TAB_ELEMENTS"))

    for idx in range(1, tabs + 1):
        if idx in existing:
            continue
        legacy = new_root.get(f"TAB_{idx:02d}")
        if isinstance(legacy, dict):
            existing[idx] = dict(legacy)
            changed = True

    normalized: Dict[str, Dict[str, Any]] = {}
    root_edit_type = str(new_root.get("EDIT_TYPE") or "").strip().lower() or "pdvm_edit"
    root_table = str(new_root.get("TABLE") or "").strip()

    for idx in sorted(existing.keys()):
        tab = dict(existing[idx])
        tab, tab_changed = _upper_dict_keys(tab)
        changed = changed or tab_changed

        if not str(tab.get("MODULE") or "").strip():
            tab["MODULE"] = "view" if idx == 1 else ("edit" if idx == 2 else "view")
            changed = True
        if not str(tab.get("EDIT_TYPE") or "").strip():
            tab["EDIT_TYPE"] = root_edit_type
            changed = True
        if not str(tab.get("TABLE") or "").strip() and root_table:
            tab["TABLE"] = root_table
            changed = True

        normalized[f"TAB_{idx:02d}"] = tab

    if normalized != new_root.get("TAB_ELEMENTS"):
        new_root["TAB_ELEMENTS"] = normalized
        changed = True

    for i in range(1, 21):
        key = f"TAB_{i:02d}"
        if key in new_root:
            del new_root[key]
            changed = True

    for dup in ("VIEW_GUID", "FRAME_GUID"):
        if dup in new_root:
            del new_root[dup]
            changed = True

    return new_root, changed


def _normalize_row(
    *,
    table_name: str,
    uid: uuid.UUID,
    name: str,
    daten: Dict[str, Any],
) -> Tuple[Dict[str, Any], bool]:
    if not isinstance(daten, dict):
        return daten, False

    changed = False

    out, top_changed = _upper_dict_keys(daten)
    changed = changed or top_changed

    root = _as_dict(out.get("ROOT"))
    if not root:
        root = {}
        changed = True

    root, root_key_changed = _upper_dict_keys(root)
    changed = changed or root_key_changed

    if str(root.get("SELF_GUID") or "").strip() != str(uid):
        root["SELF_GUID"] = str(uid)
        changed = True

    if not str(root.get("SELF_NAME") or "").strip() or (name and str(root.get("SELF_NAME") or "") != name):
        root["SELF_NAME"] = str(name or "")
        changed = True

    out["ROOT"] = root

    for group_name in ("CONTROL", "TEMPLATES"):
        group = _as_dict(out.get(group_name))
        if not group:
            continue
        normalized_group, grp_changed = _upper_dict_keys(group)
        if grp_changed:
            out[group_name] = normalized_group
            changed = True

    if table_name == "sys_dialogdaten":
        normalized_root, dialog_changed = _normalize_dialog_tab_elements(out["ROOT"])
        if dialog_changed:
            out["ROOT"] = normalized_root
            changed = True

    return out, changed


async def _find_relation(conn: asyncpg.Connection, table_name: str) -> str | None:
    for relation in (f"pdvm_system.{table_name}", f"public.{table_name}", table_name):
        exists = await conn.fetchval("SELECT to_regclass($1)", relation)
        if exists:
            return relation
    return None


async def _migrate_table(
    conn: asyncpg.Connection,
    table_name: str,
    *,
    apply_changes: bool,
    include_historisch: bool,
) -> MigrationStats:
    stats = MigrationStats(table_name=table_name)

    relation = await _find_relation(conn, table_name)
    if not relation:
        stats.skipped += 1
        return stats

    where_clause = "" if include_historisch else "WHERE historisch = 0"
    rows = await conn.fetch(
        f"""
        SELECT uid, name, daten
        FROM {relation}
        {where_clause}
        """
    )

    for row in rows:
        stats.scanned += 1
        data = row.get("daten")
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except Exception:
                stats.skipped += 1
                continue

        normalized, changed = _normalize_row(
            table_name=table_name,
            uid=row["uid"],
            name=str(row.get("name") or ""),
            daten=data,
        )

        if not changed:
            stats.unchanged += 1
            continue

        stats.changed += 1
        if apply_changes:
            await conn.execute(
                f"""
                UPDATE {relation}
                SET daten = $1::jsonb,
                    modified_at = NOW()
                WHERE uid = $2
                """,
                json.dumps(normalized),
                row["uid"],
            )

    return stats


async def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate to PDVM_LINEAR_SCHEMA_V1")
    parser.add_argument(
        "--tables",
        default=",".join(DEFAULT_TABLES),
        help="Comma-separated Tabellenliste",
    )
    parser.add_argument("--dry-run", action="store_true", help="Nur analysieren")
    parser.add_argument("--apply", action="store_true", help="Änderungen schreiben")
    parser.add_argument(
        "--include-historisch",
        action="store_true",
        help="Migriert auch historisch=1 Datensätze",
    )
    parser.add_argument("--db-url", default=None, help="Optionale DB-URL")
    args = parser.parse_args()

    if args.apply and args.dry_run:
        print("❌ --apply und --dry-run können nicht gleichzeitig gesetzt werden")
        return 2

    apply_changes = bool(args.apply)
    mode = "APPLY" if apply_changes else "DRY-RUN"

    table_names = [t.strip() for t in args.tables.split(",") if t.strip()]

    if args.db_url:
        db_url = args.db_url
    else:
        cfg = await ConnectionManager.get_system_config("pdvm_system")
        db_url = cfg.to_url()

    conn = await asyncpg.connect(db_url)
    try:
        stats_list = [
            await _migrate_table(
                conn,
                table_name,
                apply_changes=apply_changes,
                include_historisch=args.include_historisch,
            )
            for table_name in table_names
        ]
    finally:
        await conn.close()

    print(f"=== PDVM_LINEAR_SCHEMA_V1 Migration ({mode}) ===")
    total_scanned = 0
    total_changed = 0
    total_unchanged = 0
    total_skipped = 0

    for stats in stats_list:
        total_scanned += stats.scanned
        total_changed += stats.changed
        total_unchanged += stats.unchanged
        total_skipped += stats.skipped

        print(
            f"[{stats.table_name}] scanned={stats.scanned} changed={stats.changed} "
            f"unchanged={stats.unchanged} skipped={stats.skipped}"
        )

    print("=== SUMMARY ===")
    print(f"Scanned:   {total_scanned}")
    print(f"Changed:   {total_changed}")
    print(f"Unchanged: {total_unchanged}")
    print(f"Skipped:   {total_skipped}")

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

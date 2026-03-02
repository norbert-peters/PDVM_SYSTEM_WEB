"""Migration: sys_dialogdaten auf ROOT.TAB_ELEMENTS Struktur.

- Uebernimmt legacy TAB_01/TAB_02/... in TAB_ELEMENTS
- Setzt SELF_GUID/SELF_NAME falls leer
- Leitet VIEW_GUID/FRAME_GUID ueber MODULE in TAB_ELEMENTS ab (runtime), entfernt Duplikate aus ROOT

Usage:
  python backend/tools/migrate_dialogs_to_tab_elements.py
  python backend/tools/migrate_dialogs_to_tab_elements.py --dry-run
"""
from __future__ import annotations

import argparse
import asyncio
import json
import uuid
from pathlib import Path
from typing import Any, Dict, Tuple

import sys

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import asyncpg

from app.core.connection_manager import ConnectionManager


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _find_legacy_tab_block(container: Dict[str, Any], tab_index: int) -> Dict[str, Any] | None:
    if not isinstance(container, dict):
        return None
    rx = __import__("re").compile(rf"^tab[_\-]?0*{tab_index}$", flags=__import__("re").IGNORECASE)
    for key, value in container.items():
        if rx.match(str(key)) and isinstance(value, dict):
            return value
    return None


def _extract_tab_elements(value: Any) -> Dict[int, Dict[str, Any]]:
    out: Dict[int, Dict[str, Any]] = {}

    if isinstance(value, dict):
        for key, row in value.items():
            if not isinstance(row, dict):
                continue
            idx = None
            if isinstance(row.get("index"), int):
                idx = int(row.get("index"))
            if idx is None:
                m = __import__("re").match(r"^tab[_\-]?0*(\d+)$", str(key), flags=__import__("re").IGNORECASE)
                if m:
                    idx = int(m.group(1))
            if not idx or idx <= 0 or idx > 20:
                continue
            out[idx] = row
        return out

    if isinstance(value, list):
        for pos, row in enumerate(value, start=1):
            if not isinstance(row, dict):
                continue
            idx_raw = row.get("index") or row.get("tab") or pos
            try:
                idx = int(idx_raw)
            except Exception:
                continue
            if idx <= 0 or idx > 20:
                continue
            out[idx] = row

    return out


def _migrate_row(uid: uuid.UUID, name: str, daten: Dict[str, Any]) -> Tuple[Dict[str, Any], bool]:
    root = _as_dict(daten.get("ROOT"))
    if not root:
        return daten, False

    changed = False
    out = dict(daten)
    new_root = dict(root)

    if not str(new_root.get("SELF_GUID") or "").strip():
        new_root["SELF_GUID"] = str(uid)
        changed = True
    if not str(new_root.get("SELF_NAME") or "").strip():
        new_root["SELF_NAME"] = str(name or "")
        changed = True

    tabs_raw = new_root.get("TABS")
    try:
        tabs = int(tabs_raw) if tabs_raw is not None else 0
    except Exception:
        tabs = 0
    tabs = max(0, min(20, tabs))

    existing_elements = _extract_tab_elements(new_root.get("TAB_ELEMENTS"))
    tab_elements: Dict[int, Dict[str, Any]] = dict(existing_elements)

    for i in range(1, tabs + 1):
        if i in tab_elements:
            continue
        block = _find_legacy_tab_block(new_root, i)
        if block:
            tab_elements[i] = dict(block)
            changed = True

    root_edit_type = str(new_root.get("EDIT_TYPE") or "").strip().lower() or "pdvm_edit"
    root_open_edit = str(new_root.get("OPEN_EDIT") or "").strip().lower() or "double_click"
    root_selection_mode = str(new_root.get("SELECTION_MODE") or "").strip().lower() or "single"
    root_table = str(new_root.get("TABLE") or "").strip()

    normalized: Dict[str, Dict[str, Any]] = {}
    for idx in sorted(tab_elements.keys()):
        tab = dict(tab_elements[idx])
        if not str(tab.get("MODULE") or "").strip():
            if idx == 1:
                tab["MODULE"] = "view"
            elif idx == 2:
                tab["MODULE"] = "edit"
        if not str(tab.get("EDIT_TYPE") or "").strip():
            tab["EDIT_TYPE"] = root_edit_type
        if not str(tab.get("OPEN_EDIT") or "").strip():
            tab["OPEN_EDIT"] = root_open_edit
        if not str(tab.get("SELECTION_MODE") or "").strip():
            tab["SELECTION_MODE"] = root_selection_mode
        if not str(tab.get("TABLE") or "").strip() and root_table:
            tab["TABLE"] = root_table

        key = f"TAB_{idx:02d}"
        normalized[key] = tab

    if normalized:
        if new_root.get("TAB_ELEMENTS") != normalized:
            new_root["TAB_ELEMENTS"] = normalized
            changed = True

    for i in range(1, 21):
        legacy_key = f"TAB_{i:02d}"
        if legacy_key in new_root:
            del new_root[legacy_key]
            changed = True

    for legacy_guid_key in ("VIEW_GUID", "FRAME_GUID"):
        if legacy_guid_key in new_root:
            del new_root[legacy_guid_key]
            changed = True

    if changed:
        out["ROOT"] = new_root

    return out, changed


async def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate sys_dialogdaten to TAB_ELEMENTS")
    parser.add_argument("--dry-run", action="store_true", help="Only analyze changes")
    parser.add_argument("--db-url", default=None, help="Optional Postgres URL")
    args = parser.parse_args()

    if args.db_url:
        db_url = args.db_url
    else:
        cfg = await ConnectionManager.get_system_config("pdvm_system")
        db_url = cfg.to_url()

    conn = await asyncpg.connect(db_url)
    changed_count = 0
    total = 0
    try:
        rows = await conn.fetch("SELECT uid, name, daten FROM sys_dialogdaten WHERE historisch = 0")
        total = len(rows)

        for row in rows:
            uid = row["uid"]
            name = row.get("name") or ""
            daten = row.get("daten") or {}
            if isinstance(daten, str):
                try:
                    daten = json.loads(daten)
                except Exception:
                    continue
            if not isinstance(daten, dict):
                continue

            migrated, changed = _migrate_row(uid, name, daten)
            if not changed:
                continue

            changed_count += 1
            if args.dry_run:
                continue

            await conn.execute(
                """
                UPDATE sys_dialogdaten
                SET daten = $1::jsonb, modified_at = NOW()
                WHERE uid = $2
                """,
                json.dumps(migrated),
                uid,
            )

        mode = "DRY-RUN" if args.dry_run else "APPLY"
        print(f"✅ Migration {mode} fertig")
        print(f"   Datensaetze gesamt: {total}")
        print(f"   Datensaetze angepasst: {changed_count}")
    finally:
        await conn.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

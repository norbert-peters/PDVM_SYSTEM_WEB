"""Bereinigt sys_viewdaten/sys_framedaten nach Dialog-Referenzen.

Policy:
- Nicht-reservierte Datensaetze mit Referenz aus sys_dialogdaten -> normalisieren (666-Basis)
- Nicht-reservierte Datensaetze ohne Referenz -> loeschen

Usage:
  python tools/cleanup_table_by_dialog_refs.py --table sys_viewdaten
  python tools/cleanup_table_by_dialog_refs.py --table sys_framedaten
"""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import sys
import uuid
from typing import Any, Dict, List, Set

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import asyncpg

from app.core.connection_manager import ConnectionManager
from tools.normalize_table_record import main_async as normalize_one

UID_000 = "00000000-0000-0000-0000-000000000000"
UID_555 = "55555555-5555-5555-5555-555555555555"
UID_666 = "66666666-6666-6666-6666-666666666666"
RESERVED = {UID_000, UID_555, UID_666}


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


def _is_uuid(value: Any) -> bool:
    token = str(value or "").strip()
    if not token:
        return False
    try:
        uuid.UUID(token)
        return True
    except Exception:
        return False


def _extract_dialog_refs(dialog_daten: Dict[str, Any], *, target_table: str) -> Set[str]:
    refs: Set[str] = set()
    root = _as_obj(dialog_daten.get("ROOT"))

    if target_table == "sys_viewdaten":
        value = root.get("VIEW_GUID")
        if _is_uuid(value):
            refs.add(str(value).strip())
    elif target_table == "sys_framedaten":
        for key in ("FRAME_GUID", "CREATE_FRAME_GUID"):
            value = root.get(key)
            if _is_uuid(value):
                refs.add(str(value).strip())

    tab_elements = _as_obj(root.get("TAB_ELEMENTS"))
    for _tab_key, tab_value in tab_elements.items():
        tab = _as_obj(tab_value)
        guid = tab.get("GUID")
        if not _is_uuid(guid):
            continue
        module = str(tab.get("MODULE") or "").strip().lower()
        if target_table == "sys_viewdaten" and module == "view":
            refs.add(str(guid).strip())
        if target_table == "sys_framedaten" and module in {"edit", "acti"}:
            refs.add(str(guid).strip())

    return refs


async def main_async(table: str) -> int:
    if table not in {"sys_viewdaten", "sys_framedaten"}:
        raise RuntimeError("--table muss sys_viewdaten oder sys_framedaten sein")

    cfg = await ConnectionManager.get_system_config("pdvm_system")
    conn = await asyncpg.connect(cfg.to_url())
    try:
        target_rows = await conn.fetch(
            f"SELECT uid, name FROM {table} WHERE COALESCE(historisch,0)=0 ORDER BY name"
        )
        dialog_rows = await conn.fetch(
            "SELECT daten FROM sys_dialogdaten WHERE COALESCE(historisch,0)=0"
        )

        refs: Set[str] = set()
        for drow in dialog_rows:
            refs.update(_extract_dialog_refs(_as_obj(drow["daten"]), target_table=table))

        normalized: List[str] = []
        deleted: List[str] = []

        for row in target_rows:
            uid = str(row["uid"])
            name = str(row["name"] or "")
            if uid in RESERVED:
                continue
            if uid in refs:
                await normalize_one(table, uid)
                normalized.append(f"{name} [{uid}]")
            else:
                await conn.execute(f"DELETE FROM {table} WHERE uid = $1::uuid", uid)
                deleted.append(f"{name} [{uid}]")

        print(f"Cleanup done for {table}")
        print(f"normalized: {len(normalized)}")
        for item in normalized:
            print(f"- {item}")
        print(f"deleted: {len(deleted)}")
        for item in deleted:
            print(f"- {item}")
        return 0
    finally:
        await conn.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Cleanup target table by sys_dialogdaten references")
    parser.add_argument("--table", required=True)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    raise SystemExit(asyncio.run(main_async(args.table)))

"""Audit fuer sys_viewdaten/sys_framedaten inkl. Referenzen aus sys_dialogdaten.

Prueft:
- Reservierte UIDs 000/555/666 vorhanden.
- 555-Struktur (ROOT + TEMPLATES), 666-Struktur (ROOT).
- Nicht-reservierte Datensaetze gegen 666-ROOT-Basisschluessel.
- Referenzen aus sys_dialogdaten (ROOT.VIEW_GUID/FRAME_GUID/CREATE_FRAME_GUID + TAB_ELEMENTS.*.GUID).

Usage:
  python tools/audit_table_with_dialog_refs.py --table sys_viewdaten
  python tools/audit_table_with_dialog_refs.py --table sys_framedaten
"""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import sys
import uuid
from typing import Any, Dict, List, Set, Tuple

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import asyncpg

from app.core.connection_manager import ConnectionManager


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


async def _get_db_url() -> str:
    cfg = await ConnectionManager.get_system_config("pdvm_system")
    return cfg.to_url()


def _extract_dialog_refs(dialog_daten: Dict[str, Any], *, target_table: str) -> Set[str]:
    refs: Set[str] = set()
    root = _as_obj(dialog_daten.get("ROOT"))

    # Root-level references
    if target_table == "sys_viewdaten":
        for key in ("VIEW_GUID",):
            value = root.get(key)
            if _is_uuid(value):
                refs.add(str(value).strip())
    elif target_table == "sys_framedaten":
        for key in ("FRAME_GUID", "CREATE_FRAME_GUID"):
            value = root.get(key)
            if _is_uuid(value):
                refs.add(str(value).strip())

    # Tab-level references via GUID + MODULE hint
    tab_elements = _as_obj(root.get("TAB_ELEMENTS"))
    for _tab_key, tab_value in tab_elements.items():
        tab = _as_obj(tab_value)
        guid = tab.get("GUID")
        if not _is_uuid(guid):
            continue
        module = str(tab.get("MODULE") or "").strip().lower()
        if target_table == "sys_viewdaten":
            if module == "view":
                refs.add(str(guid).strip())
            continue
        if target_table == "sys_framedaten":
            if module in {"edit", "acti"}:
                refs.add(str(guid).strip())
            continue

    return refs


def _validate_non_reserved(*, uid: str, daten: Dict[str, Any], required_root_keys: List[str]) -> List[str]:
    issues: List[str] = []
    if not daten:
        return ["daten leer/ungueltig"]
    root = _as_obj(daten.get("ROOT"))
    if not root:
        return ["ROOT fehlt oder ist kein Objekt"]

    self_guid = str(root.get("SELF_GUID") or "").strip()
    if self_guid.lower() != uid.lower():
        issues.append("ROOT.SELF_GUID passt nicht zur UID")

    self_name = str(root.get("SELF_NAME") or "").strip()
    if not self_name:
        issues.append("ROOT.SELF_NAME fehlt")

    for key in required_root_keys:
        if key in {"SELF_GUID", "SELF_NAME"}:
            continue
        if key not in root:
            issues.append(f"ROOT.{key} fehlt (laut 666-Basis)")

    return issues


async def main_async(table_name: str) -> int:
    if table_name not in {"sys_viewdaten", "sys_framedaten"}:
        raise ValueError("--table muss sys_viewdaten oder sys_framedaten sein")

    db_url = await _get_db_url()
    conn = await asyncpg.connect(db_url)
    try:
        target_rows = await conn.fetch(
            f"SELECT uid, name, daten FROM {table_name} WHERE COALESCE(historisch,0)=0 ORDER BY name"
        )
        target_by_uid = {str(r["uid"]): r for r in target_rows}

        print(f"=== Audit {table_name} mit Dialog-Referenzen ===")
        print(f"Gesamt aktive Saetze: {len(target_rows)}")

        missing_reserved = [u for u in [UID_000, UID_555, UID_666] if u not in target_by_uid]
        if missing_reserved:
            print("Fehlende reservierte UID(s):")
            for uid in missing_reserved:
                print(f"- {uid}")
        else:
            print("Reserviert vorhanden: 000/555/666 OK")

        row_555 = target_by_uid.get(UID_555)
        if row_555:
            d555 = _as_obj(row_555["daten"])
            if not _as_obj(d555.get("ROOT")):
                print("Finding: UID 555 ohne ROOT-Objekt")
            if not _as_obj(d555.get("TEMPLATES")):
                print("Finding: UID 555 ohne TEMPLATES-Objekt")

        row_666 = target_by_uid.get(UID_666)
        required_root_keys: List[str] = []
        if row_666:
            d666 = _as_obj(row_666["daten"])
            root666 = _as_obj(d666.get("ROOT"))
            if not root666:
                print("Finding: UID 666 ohne ROOT-Objekt")
            required_root_keys = sorted(list(root666.keys()))

        dialog_rows = await conn.fetch(
            "SELECT uid, name, daten FROM sys_dialogdaten WHERE COALESCE(historisch,0)=0 ORDER BY name"
        )

        ref_map: Dict[str, List[str]] = {}
        for drow in dialog_rows:
            dialog_uid = str(drow["uid"])
            dialog_name = str(drow["name"] or "")
            refs = _extract_dialog_refs(_as_obj(drow["daten"]), target_table=table_name)
            for rid in refs:
                ref_map.setdefault(rid, []).append(f"{dialog_name} [{dialog_uid}]")

        invalid: List[Tuple[str, str, List[str], List[str]]] = []
        for row in target_rows:
            uid = str(row["uid"])
            if uid in RESERVED:
                continue
            issues = _validate_non_reserved(uid=uid, daten=_as_obj(row["daten"]), required_root_keys=required_root_keys)
            if issues:
                invalid.append((uid, str(row["name"] or ""), issues, ref_map.get(uid, [])))

        print(f"Strukturkandidaten (nicht-reserviert): {len(invalid)}")
        for uid, name, issues, refs in invalid:
            print(f"- {name} [{uid}]")
            for issue in issues:
                print(f"    * {issue}")
            print(f"    * dialog_refs: {len(refs)}")
            for ref in refs:
                print(f"      - {ref}")

        # Also list orphan candidates (no dialog refs) regardless of validity.
        orphans: List[Tuple[str, str]] = []
        for row in target_rows:
            uid = str(row["uid"])
            if uid in RESERVED:
                continue
            if uid not in ref_map:
                orphans.append((uid, str(row["name"] or "")))

        print(f"\nUnreferenzierte Saetze (ohne Dialog-Bezug): {len(orphans)}")
        for uid, name in orphans:
            print(f"- {name} [{uid}]")

        return 0
    finally:
        await conn.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit target table with sys_dialogdaten references")
    parser.add_argument("--table", required=True, help="sys_viewdaten oder sys_framedaten")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    raise SystemExit(asyncio.run(main_async(args.table)))

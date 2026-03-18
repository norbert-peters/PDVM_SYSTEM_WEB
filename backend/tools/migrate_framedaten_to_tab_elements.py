"""Migration: sys_framedaten auf ROOT.TAB_ELEMENTS (STRICT).

ZIEL:
- ROOT.TABS bleibt als Anzahl
- ROOT.TAB_ELEMENTS.TAB_01..TAB_NN ist die einzige Tab-Definition
- Legacy-Felder werden entfernt:
  - ROOT.TAB_01..TAB_20
  - ROOT.EDIT_TABS
  - ROOT.EDIT_TAB_LABEL_XX

Usage:
  python backend/tools/migrate_framedaten_to_tab_elements.py --dry-run
  python backend/tools/migrate_framedaten_to_tab_elements.py --apply
  python backend/tools/migrate_framedaten_to_tab_elements.py --uid <frame_guid> --dry-run
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, Tuple, Optional

import asyncpg

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.connection_manager import ConnectionManager


_TAB_KEY_RX = re.compile(r"^TAB_(\d{2})$")


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _to_int(value: Any) -> int:
    try:
        return int(value)
    except Exception:
        return 0


def _normalize_tab_entry(tab_value: Any, fallback_label: str) -> Dict[str, Any]:
    if isinstance(tab_value, dict):
        tab_dict = dict(tab_value)
    elif isinstance(tab_value, str):
        tab_dict = {"HEAD": tab_value}
    else:
        tab_dict = {"HEAD": fallback_label}

    head = tab_dict.get("HEAD")
    if not head:
        alt = tab_dict.get("LABEL")
        tab_dict["HEAD"] = str(alt) if alt else fallback_label

    return tab_dict


def migrate_row(daten: Dict[str, Any]) -> Tuple[Dict[str, Any], bool, str]:
    if not isinstance(daten, dict):
        return daten, False, "daten not dict"

    root = _as_dict(daten.get("ROOT"))
    if not root:
        return daten, False, "no ROOT"

    original = json.dumps(root, ensure_ascii=False, sort_keys=True)

    tab_elements_existing = root.get("TAB_ELEMENTS") if isinstance(root.get("TAB_ELEMENTS"), dict) else {}

    tab_count = _to_int(root.get("TABS"))
    if tab_count <= 0:
        tab_count = _to_int(root.get("EDIT_TABS"))
    if tab_count <= 0 and tab_elements_existing:
        tab_count = len(tab_elements_existing)

    if tab_count <= 0:
        return daten, False, "no tabs"

    root["TABS"] = tab_count

    normalized_tab_elements: Dict[str, Dict[str, Any]] = {}

    for i in range(1, tab_count + 1):
        tab_key = f"TAB_{i:02d}"

        fallback_label: Optional[str] = None

        old_label_key = f"EDIT_TAB_LABEL_{i:02d}"
        old_label = root.get(old_label_key)
        if old_label:
            fallback_label = str(old_label)

        if not fallback_label:
            tab_el = tab_elements_existing.get(tab_key)
            if isinstance(tab_el, dict):
                tab_el_head = tab_el.get("HEAD") or tab_el.get("LABEL")
                if tab_el_head:
                    fallback_label = str(tab_el_head)

        if not fallback_label:
            legacy_direct = root.get(tab_key)
            if isinstance(legacy_direct, dict):
                legacy_head = legacy_direct.get("HEAD") or legacy_direct.get("LABEL")
                if legacy_head:
                    fallback_label = str(legacy_head)

        if not fallback_label:
            fallback_label = f"Tab {i}"

        source_value = tab_elements_existing.get(tab_key)
        if not isinstance(source_value, dict):
            source_value = root.get(tab_key)

        normalized_tab_elements[tab_key] = _normalize_tab_entry(source_value, fallback_label)

    root["TAB_ELEMENTS"] = normalized_tab_elements

    # STRICT CLEANUP: alte Tab-Felder entfernen
    remove_keys = []
    for key in list(root.keys()):
        if key == "EDIT_TABS" or key.startswith("EDIT_TAB_LABEL_"):
            remove_keys.append(key)
            continue
        m = _TAB_KEY_RX.match(str(key))
        if m:
            remove_keys.append(key)

    for key in remove_keys:
        root.pop(key, None)

    new_daten = dict(daten)
    new_daten["ROOT"] = root

    changed = json.dumps(root, ensure_ascii=False, sort_keys=True) != original
    return new_daten, changed, f"tabs={tab_count}"


async def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate sys_framedaten to ROOT.TAB_ELEMENTS (strict)")
    parser.add_argument("--dry-run", action="store_true", help="Only analyze, no DB update")
    parser.add_argument("--apply", action="store_true", help="Persist updates")
    parser.add_argument("--uid", default=None, help="Optional: only one frame UID")
    parser.add_argument("--db-url", default=None, help="Optional Postgres URL")
    args = parser.parse_args()

    if args.apply and args.dry_run:
        print("❌ --apply und --dry-run gleichzeitig nicht erlaubt")
        return 2

    apply_mode = bool(args.apply) and not bool(args.dry_run)

    if args.db_url:
        db_url = args.db_url
    else:
        cfg = await ConnectionManager.get_system_config("pdvm_system")
        db_url = cfg.to_url()

    conn = await asyncpg.connect(db_url)

    total = 0
    changed_count = 0
    changed_uids = []

    try:
        if args.uid:
            rows = await conn.fetch(
                "SELECT uid, daten FROM public.sys_framedaten WHERE historisch = 0 AND uid = $1::uuid",
                args.uid,
            )
        else:
            rows = await conn.fetch("SELECT uid, daten FROM public.sys_framedaten WHERE historisch = 0")

        total = len(rows)

        for row in rows:
            uid = str(row["uid"])
            daten = row.get("daten") or {}
            if isinstance(daten, str):
                try:
                    daten = json.loads(daten)
                except Exception:
                    continue
            if not isinstance(daten, dict):
                continue

            migrated, changed, _ = migrate_row(daten)
            if not changed:
                continue

            changed_count += 1
            changed_uids.append(uid)

            if apply_mode:
                await conn.execute(
                    """
                    UPDATE public.sys_framedaten
                    SET daten = $1::jsonb,
                        modified_at = NOW()
                    WHERE uid = $2::uuid
                    """,
                    json.dumps(migrated, ensure_ascii=False),
                    uid,
                )

        mode = "APPLY" if apply_mode else "DRY-RUN"
        print(f"✅ sys_framedaten Migration {mode} abgeschlossen")
        print(f"   Datensaetze gesamt: {total}")
        print(f"   Datensaetze angepasst: {changed_count}")
        if changed_uids:
            preview = changed_uids[:10]
            print(f"   Beispiel-UIDs: {preview}")

    finally:
        await conn.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

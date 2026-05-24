"""
Dialog/View/Frame Normalizer V1 (safe structural normalization).

Default: dry-run (no DB updates)
Apply mode: --apply

Normalizations:
1. TAB_ELEMENTS dict keys -> canonical TAB_XX format.
2. ROOT.TABS -> synchronize with number of TAB_ELEMENTS entries.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import asyncpg

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.connection_manager import ConnectionManager
from tools.phaseB_persist_template_modes import SYSTEM_MANDANT_UIDS


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _as_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            return {}
    return {}


def _parse_tab_index(key: str, tab_obj: Dict[str, Any], fallback: int) -> int:
    key_u = str(key).upper()
    suffix = key_u[3:] if key_u.startswith("TAB") else ""
    suffix = suffix.lstrip("_")
    digits = "".join(ch for ch in suffix if ch.isdigit())
    if digits:
        try:
            return int(digits)
        except Exception:
            pass
    tab_field = tab_obj.get("TAB")
    try:
        return int(tab_field)
    except Exception:
        return fallback


def _canonicalize_tab_elements(tab_elements: Dict[str, Any]) -> Tuple[Dict[str, Any], bool, List[Dict[str, Any]]]:
    if not isinstance(tab_elements, dict):
        return tab_elements, False, []

    indexed: List[Tuple[int, Dict[str, Any], str]] = []
    fallback = 1
    for key, value in tab_elements.items():
        entry = _as_dict(value)
        if not entry:
            continue
        idx = _parse_tab_index(str(key), entry, fallback)
        fallback += 1
        indexed.append((idx, entry, str(key)))

    if not indexed:
        return tab_elements, False, []

    indexed.sort(key=lambda x: x[0])
    normalized: Dict[str, Any] = {}
    changes: List[Dict[str, Any]] = []
    changed = False

    for idx, entry, old_key in indexed:
        new_key = f"TAB_{idx:02d}"
        normalized[new_key] = entry
        if old_key != new_key:
            changed = True
            changes.append({"old_key": old_key, "new_key": new_key})

    if set(normalized.keys()) != set(tab_elements.keys()):
        changed = True

    return normalized, changed, changes


async def _resolve_table(conn: asyncpg.Connection) -> Optional[str]:
    for name in ["sys_dialogdaten", "asy_dialogdaten", "msy_dialogdaten"]:
        exists = await conn.fetchval("SELECT to_regclass($1) IS NOT NULL", f"public.{name}")
        if exists:
            return name
    return None


async def _load_dialog_rows(conn: asyncpg.Connection, table: str) -> List[asyncpg.Record]:
    return await conn.fetch(
        f'''
        SELECT uid::text AS uid, name, daten
        FROM "{table}"
        WHERE COALESCE(historisch, 0) = 0
        ORDER BY created_at
        '''
    )


async def run_normalizer(apply_changes: bool, output_path: Path) -> int:
    cfg = await ConnectionManager.get_system_config("pdvm_system")
    conn = await asyncpg.connect(**cfg.to_dict())

    report: Dict[str, Any] = {
        "phase": "dialog_view_frame_normalize_v1",
        "generated_at_utc": _utc_now(),
        "apply_mode": bool(apply_changes),
        "database": cfg.database,
        "dialog_table": None,
        "scanned_dialogs": 0,
        "planned_changes": 0,
        "applied_changes": 0,
        "items": [],
        "summary": {},
    }

    try:
        table = await _resolve_table(conn)
        report["dialog_table"] = table
        if not table:
            report["summary"] = {"overall_status": "failed", "reason": "dialog table missing"}
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            return 1

        rows = await _load_dialog_rows(conn, table)

        for row in rows:
            uid = str(row.get("uid") or "")
            if uid in SYSTEM_MANDANT_UIDS:
                continue

            data = _as_dict(row.get("daten"))
            root = _as_dict(data.get("ROOT"))
            tab_elements = _as_dict(root.get("TAB_ELEMENTS"))

            report["scanned_dialogs"] += 1

            item_changes: List[Dict[str, Any]] = []
            changed = False

            normalized_tabs, tabs_changed, key_changes = _canonicalize_tab_elements(tab_elements)
            if tabs_changed:
                root["TAB_ELEMENTS"] = normalized_tabs
                item_changes.append({"type": "tab_key_normalization", "changes": key_changes})
                changed = True

            tab_count = len(_as_dict(root.get("TAB_ELEMENTS")))
            current_tabs_value = root.get("TABS")
            try:
                current_tabs_int = int(current_tabs_value)
            except Exception:
                current_tabs_int = None

            if current_tabs_int != tab_count:
                root["TABS"] = tab_count
                item_changes.append(
                    {
                        "type": "tabs_count_sync",
                        "old": current_tabs_value,
                        "new": tab_count,
                    }
                )
                changed = True

            if not changed:
                continue

            report["planned_changes"] += 1
            item = {
                "uid": uid,
                "name": str(row.get("name") or ""),
                "changes": item_changes,
            }
            report["items"].append(item)

            if apply_changes:
                data["ROOT"] = root
                await conn.execute(
                    f'UPDATE "{table}" SET daten = $1::jsonb WHERE uid::text = $2',
                    json.dumps(data, ensure_ascii=False),
                    uid,
                )
                report["applied_changes"] += 1

    finally:
        await conn.close()

    report["summary"] = {
        "overall_status": "applied" if apply_changes else "dry_run",
        "scanned_dialogs": report["scanned_dialogs"],
        "planned_changes": report["planned_changes"],
        "applied_changes": report["applied_changes"],
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n=== Dialog/View/Frame Normalizer V1 ===")
    print(f"Mode: {'apply' if apply_changes else 'dry-run'}")
    print(f"Scanned dialogs: {report['scanned_dialogs']}")
    print(f"Planned changes: {report['planned_changes']}")
    print(f"Applied changes: {report['applied_changes']}")
    print(f"Report: {output_path}")

    return 0


def _default_output_path() -> Path:
    return BACKEND_DIR / "reports" / "dialog_view_frame_normalize_report_v1.json"


def main() -> int:
    parser = argparse.ArgumentParser(description="Dialog/View/Frame normalizer v1")
    parser.add_argument("--apply", action="store_true", help="Persist safe normalization changes to DB")
    parser.add_argument("--output", default=str(_default_output_path()), help="Output report path")
    args = parser.parse_args()
    return asyncio.run(run_normalizer(apply_changes=bool(args.apply), output_path=Path(args.output)))


if __name__ == "__main__":
    raise SystemExit(main())

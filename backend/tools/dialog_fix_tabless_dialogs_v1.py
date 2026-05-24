"""
Fixes remaining tabless dialog exceptions by applying explicit TAB_ELEMENTS structures.

Targets:
- 72eada00-508e-405c-bae4-261c90e4dd71 (Dialogdaten Editor) -> 2-tab structure
- 4392bf9a-064d-4080-a0a2-26e70a33642c (Import Data Dialog 1) -> 1-tab import structure

Usage:
  python backend/tools/dialog_fix_tabless_dialogs_v1.py
  python backend/tools/dialog_fix_tabless_dialogs_v1.py --apply
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import asyncpg

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.connection_manager import ConnectionManager

TARGET_DIALOG_EDITOR_UID = "72eada00-508e-405c-bae4-261c90e4dd71"
TARGET_IMPORT_DIALOG_UID = "4392bf9a-064d-4080-a0a2-26e70a33642c"

DIALOG_VIEW_GUID = "1f3a0e00-48bb-4a08-9cb8-7a7d52f23002"
DIALOG_EDIT_FRAME_GUID = "1f3a0e00-48bb-4a08-9cb8-7a7d52f23003"
GENERIC_EDIT_FRAME_GUID = "4413571e-6bf6-4f42-b81a-bc898db4880c"


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


async def _table_exists(conn: asyncpg.Connection, table_name: str) -> bool:
    return bool(await conn.fetchval("SELECT to_regclass($1) IS NOT NULL", f"public.{table_name}"))


async def _resolve_dialog_table(conn: asyncpg.Connection) -> Optional[str]:
    for t in ["sys_dialogdaten", "asy_dialogdaten", "msy_dialogdaten"]:
        if await _table_exists(conn, t):
            return t
    return None


def _editor_tab_structure() -> Dict[str, Any]:
    return {
        "TAB_01": {
            "TAB": 1,
            "GUID": DIALOG_VIEW_GUID,
            "HEAD": "Liste",
            "TABLE": "sys_dialogdaten",
            "MODULE": "view",
            "EDIT_TYPE": "pdvm_edit",
            "OPEN_EDIT": "double_click",
            "SELECTION_MODE": "single",
        },
        "TAB_02": {
            "TAB": 2,
            "GUID": DIALOG_EDIT_FRAME_GUID,
            "HEAD": "Bearbeiten",
            "TABLE": "sys_dialogdaten",
            "MODULE": "edit",
            "EDIT_TYPE": "pdvm_edit",
            "OPEN_EDIT": "double_click",
            "SELECTION_MODE": "single",
        },
    }


def _import_tab_structure() -> Dict[str, Any]:
    return {
        "TAB_01": {
            "TAB": 1,
            "GUID": GENERIC_EDIT_FRAME_GUID,
            "HEAD": "Import",
            "TABLE": "sys_ext_table",
            "MODULE": "edit",
            "EDIT_TYPE": "import_data",
            "OPEN_EDIT": "double_click",
            "SELECTION_MODE": "single",
        }
    }


def _apply_target_structure(uid: str, root: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(root)

    if uid == TARGET_DIALOG_EDITOR_UID:
        out["TABLE"] = "sys_dialogdaten"
        out["ON_NEW_SET"] = True
        out["TAB_ELEMENTS"] = _editor_tab_structure()
        out["TABS"] = 2
    elif uid == TARGET_IMPORT_DIALOG_UID:
        out["TABLE"] = "sys_ext_table"
        out["EDIT_TYPE"] = "import_data"
        out["TAB_ELEMENTS"] = _import_tab_structure()
        out["TABS"] = 1
    return out


def _default_output_path() -> Path:
    return BACKEND_DIR / "reports" / "dialog_fix_tabless_dialogs_report_v1.json"


async def run_fix(apply_changes: bool, output_path: Path) -> int:
    cfg = await ConnectionManager.get_system_config("pdvm_system")
    conn = await asyncpg.connect(**cfg.to_dict())

    report: Dict[str, Any] = {
        "phase": "dialog_fix_tabless_dialogs_v1",
        "generated_at_utc": _utc_now(),
        "database": cfg.database,
        "apply_mode": bool(apply_changes),
        "dialog_table": None,
        "targets": [TARGET_DIALOG_EDITOR_UID, TARGET_IMPORT_DIALOG_UID],
        "planned": [],
        "applied_count": 0,
        "summary": {},
    }

    try:
        dialog_table = await _resolve_dialog_table(conn)
        report["dialog_table"] = dialog_table
        if not dialog_table:
            report["summary"] = {"overall_status": "failed", "reason": "dialog table missing"}
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            return 1

        rows = await conn.fetch(
            f'''
            SELECT uid::text AS uid, name, daten
            FROM "{dialog_table}"
            WHERE COALESCE(historisch,0)=0
              AND uid::text = ANY($1::text[])
            ORDER BY name
            ''',
            [TARGET_DIALOG_EDITOR_UID, TARGET_IMPORT_DIALOG_UID],
        )

        for r in rows:
            uid = str(r["uid"])
            name = str(r["name"] or "")
            daten = _as_dict(r["daten"])
            root = _as_dict(daten.get("ROOT"))
            before_tabs = _as_dict(root.get("TAB_ELEMENTS"))

            target_root = _apply_target_structure(uid, root)
            after_tabs = _as_dict(target_root.get("TAB_ELEMENTS"))

            changed = json.dumps(root, ensure_ascii=False, sort_keys=True) != json.dumps(target_root, ensure_ascii=False, sort_keys=True)
            report["planned"].append(
                {
                    "uid": uid,
                    "name": name,
                    "changed": changed,
                    "before_tabs_count": len(before_tabs),
                    "after_tabs_count": len(after_tabs),
                    "before_tabs_keys": sorted(before_tabs.keys()),
                    "after_tabs_keys": sorted(after_tabs.keys()),
                    "after_table": target_root.get("TABLE"),
                    "after_tabs": after_tabs,
                }
            )

            if changed and apply_changes:
                daten["ROOT"] = target_root
                await conn.execute(
                    f'UPDATE "{dialog_table}" SET daten = $1::jsonb WHERE uid::text = $2',
                    json.dumps(daten, ensure_ascii=False),
                    uid,
                )
                report["applied_count"] += 1

        report["summary"] = {
            "overall_status": "applied" if apply_changes else "dry_run",
            "targets_found": len(rows),
            "planned_changes": sum(1 for x in report["planned"] if x.get("changed")),
            "applied_count": report["applied_count"],
        }

    finally:
        await conn.close()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n=== dialog_fix_tabless_dialogs_v1 ===")
    print(f"Mode: {'apply' if apply_changes else 'dry-run'}")
    print(f"Targets found: {report['summary'].get('targets_found')}")
    print(f"Planned changes: {report['summary'].get('planned_changes')}")
    print(f"Applied changes: {report['summary'].get('applied_count')}")
    print(f"Report: {output_path}")

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Fix tabless dialog exceptions with explicit tab structures")
    parser.add_argument("--apply", action="store_true", help="Persist changes")
    parser.add_argument("--output", default=str(_default_output_path()), help="Output report path")
    args = parser.parse_args()
    return asyncio.run(run_fix(apply_changes=bool(args.apply), output_path=Path(args.output)))


if __name__ == "__main__":
    raise SystemExit(main())

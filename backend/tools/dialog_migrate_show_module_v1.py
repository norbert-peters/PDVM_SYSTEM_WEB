"""
Migrates JSON display tabs to MODULE=show.

Rules:
1) Any tab with EDIT_TYPE=show_json and MODULE=edit/acti -> MODULE=show.
2) Restore known unintended conversion in "Anzeigen JSON":
   MODULE=edit + EDIT_TYPE=edit_json (TAB_02) -> MODULE=show + EDIT_TYPE=show_json.

Usage:
  python backend/tools/dialog_migrate_show_module_v1.py
  python backend/tools/dialog_migrate_show_module_v1.py --apply
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
from tools.phaseB_persist_template_modes import SYSTEM_MANDANT_UIDS

ANZEIGEN_JSON_UID = "68d11a99-a0cd-4b10-a0f7-040fc71da546"


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


async def _resolve_table(conn: asyncpg.Connection, candidates: List[str]) -> Optional[str]:
    for t in candidates:
        if await _table_exists(conn, t):
            return t
    return None


def _default_output_path() -> Path:
    return BACKEND_DIR / "reports" / "dialog_migrate_show_module_report_v1.json"


async def run_migration(apply_changes: bool, output_path: Path) -> int:
    cfg = await ConnectionManager.get_system_config("pdvm_system")
    conn = await asyncpg.connect(**cfg.to_dict())

    report: Dict[str, Any] = {
        "phase": "dialog_migrate_show_module_v1",
        "generated_at_utc": _utc_now(),
        "database": cfg.database,
        "apply_mode": bool(apply_changes),
        "dialog_table": None,
        "scanned_dialogs": 0,
        "planned": [],
        "applied_count": 0,
        "summary": {},
    }

    try:
        dialog_table = await _resolve_table(conn, ["sys_dialogdaten", "asy_dialogdaten", "msy_dialogdaten"])
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
            ORDER BY created_at
            '''
        )

        for r in rows:
            uid = str(r["uid"] or "")
            if uid in SYSTEM_MANDANT_UIDS:
                continue
            report["scanned_dialogs"] += 1
            name = str(r["name"] or "")
            data = _as_dict(r.get("daten"))
            root = _as_dict(data.get("ROOT"))
            tabs = _as_dict(root.get("TAB_ELEMENTS"))
            if not tabs:
                continue

            changed_items: List[Dict[str, Any]] = []
            changed = False

            for tab_key, tab in list(tabs.items()):
                tab_obj = _as_dict(tab)
                if not tab_obj:
                    continue

                module = str(tab_obj.get("MODULE") or "").strip().lower()
                edit_type = str(tab_obj.get("EDIT_TYPE") or "").strip().lower()

                # Generic migration: show_json belongs to show module.
                if edit_type == "show_json" and module in {"edit", "acti"}:
                    tab_obj["MODULE"] = "show"
                    tabs[tab_key] = tab_obj
                    changed = True
                    changed_items.append(
                        {
                            "tab_key": tab_key,
                            "change": "show_json_module_to_show",
                            "from_module": module,
                            "to_module": "show",
                            "edit_type": edit_type,
                        }
                    )

                # Targeted rollback of previous unintended conversion.
                if uid == ANZEIGEN_JSON_UID and module == "edit" and edit_type == "edit_json":
                    tab_obj["MODULE"] = "show"
                    tab_obj["EDIT_TYPE"] = "show_json"
                    tabs[tab_key] = tab_obj
                    changed = True
                    changed_items.append(
                        {
                            "tab_key": tab_key,
                            "change": "rollback_edit_json_to_show_json",
                            "from_module": "edit",
                            "to_module": "show",
                            "from_edit_type": "edit_json",
                            "to_edit_type": "show_json",
                        }
                    )

            if not changed:
                continue

            report["planned"].append({"dialog_uid": uid, "dialog_name": name, "items": changed_items})

            if apply_changes:
                root["TAB_ELEMENTS"] = tabs
                data["ROOT"] = root
                await conn.execute(
                    f'UPDATE "{dialog_table}" SET daten = $1::jsonb WHERE uid::text = $2',
                    json.dumps(data, ensure_ascii=False),
                    uid,
                )
                report["applied_count"] += 1

    finally:
        await conn.close()

    report["summary"] = {
        "overall_status": "applied" if apply_changes else "dry_run",
        "scanned_dialogs": report["scanned_dialogs"],
        "planned_dialogs": len(report["planned"]),
        "applied_count": report["applied_count"],
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n=== dialog_migrate_show_module_v1 ===")
    print(f"Mode: {'apply' if apply_changes else 'dry_run'}")
    print(f"Scanned dialogs: {report['scanned_dialogs']}")
    print(f"Planned dialogs: {len(report['planned'])}")
    print(f"Applied count: {report['applied_count']}")
    print(f"Report: {output_path}")

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate show_json tabs to MODULE=show")
    parser.add_argument("--apply", action="store_true", help="Persist changes")
    parser.add_argument("--output", default=str(_default_output_path()), help="Output report path")
    args = parser.parse_args()
    return asyncio.run(run_migration(apply_changes=bool(args.apply), output_path=Path(args.output)))


if __name__ == "__main__":
    raise SystemExit(main())

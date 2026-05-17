"""
Phase 7: Duplikat-Bereinigung fuer sys_control_dict

Verarbeitet duplicate_resolution aus
backend/reports/phase7_control_dict_migration_suggestions.json.

Sicherheitsregeln:
- Template-UIDs 555/666 werden nie stillgelegt.
- UIDs, die in sys_framedaten/sys_viewdaten/sys_dialogdaten explizit referenziert werden,
  werden nicht stillgelegt.
- Default ist dry-run. --apply fuehrt Updates aus.

Usage:
  python backend/tools/phase7_apply_duplicate_cleanup.py
  python backend/tools/phase7_apply_duplicate_cleanup.py --apply
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Set

import asyncpg

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.connection_manager import ConnectionManager

TEMPLATE_UIDS = {
    "55555555-5555-5555-5555-555555555555",
    "66666666-6666-6666-6666-666666666666",
}

UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


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


def _collect_uuid_strings(node: Any, out: Set[str]) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            _collect_uuid_strings(key, out)
            _collect_uuid_strings(value, out)
    elif isinstance(node, list):
        for item in node:
            _collect_uuid_strings(item, out)
    elif isinstance(node, str):
        s = node.strip().lower()
        if UUID_RE.match(s):
            out.add(s)


async def _load_explicitly_referenced_control_uids(conn: asyncpg.Connection) -> Set[str]:
    source_tables = ["sys_framedaten", "sys_viewdaten", "sys_dialogdaten"]
    refs: Set[str] = set()

    for table in source_tables:
        exists = await conn.fetchval("SELECT to_regclass($1)", f"public.{table}")
        if not exists:
            continue

        rows = await conn.fetch(
            f'''
            SELECT daten
            FROM "{table}"
            WHERE historisch = 0
            '''
        )
        for row in rows:
            daten = _as_dict(row.get("daten"))
            _collect_uuid_strings(daten, refs)

    return refs


def _load_suggestions(path: Path) -> Dict[str, Any]:
    raw = path.read_text(encoding="utf-8")
    data = json.loads(raw)
    return data if isinstance(data, dict) else {}


async def _run(apply_changes: bool, suggestions_path: Path, output_path: Path) -> Dict[str, Any]:
    suggestions = _load_suggestions(suggestions_path)
    duplicate_resolution = suggestions.get("duplicate_resolution") if isinstance(suggestions.get("duplicate_resolution"), list) else []

    cfg = await ConnectionManager.get_system_config()
    conn = await asyncpg.connect(**cfg.to_dict())
    try:
        explicit_refs = await _load_explicitly_referenced_control_uids(conn)

        actions: List[Dict[str, Any]] = []
        will_retire: List[str] = []
        skipped: List[Dict[str, Any]] = []

        for item in duplicate_resolution:
            ref_name = str(item.get("ref_name") or "")
            keep_uid = str(item.get("keep_uid") or "").strip().lower()
            retire_uids = [str(u).strip().lower() for u in item.get("retire_uids", []) if str(u).strip()]

            safe_retire: List[str] = []
            for uid in retire_uids:
                if uid in TEMPLATE_UIDS:
                    skipped.append({"uid": uid, "ref_name": ref_name, "reason": "template_uid_protected"})
                    continue
                if uid == keep_uid:
                    skipped.append({"uid": uid, "ref_name": ref_name, "reason": "same_as_keep_uid"})
                    continue
                if uid in explicit_refs:
                    skipped.append({"uid": uid, "ref_name": ref_name, "reason": "explicitly_referenced_in_source_tables"})
                    continue
                safe_retire.append(uid)

            actions.append(
                {
                    "ref_name": ref_name,
                    "keep_uid": keep_uid,
                    "retire_uids_requested": retire_uids,
                    "retire_uids_safe": safe_retire,
                }
            )
            will_retire.extend(safe_retire)

        if apply_changes and will_retire:
            await conn.execute(
                '''
                UPDATE sys_control_dict
                SET historisch = 1,
                    modified_at = NOW()
                WHERE uid = ANY($1::uuid[])
                  AND historisch = 0
                ''',
                will_retire,
            )

        result = {
            "phase": "phase7",
            "title": "Apply Duplicate Cleanup",
            "database": cfg.database,
            "mode": "apply" if apply_changes else "dry-run",
            "summary": {
                "duplicate_groups": len(duplicate_resolution),
                "uids_requested_for_retire": sum(len(a.get("retire_uids_requested", [])) for a in actions),
                "uids_safe_to_retire": len(will_retire),
                "uids_skipped": len(skipped),
            },
            "actions": actions,
            "skipped": skipped,
        }

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        return result
    finally:
        await conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 7 Duplicate Cleanup fuer sys_control_dict")
    parser.add_argument(
        "--suggestions",
        default=str(BACKEND_DIR / "reports" / "phase7_control_dict_migration_suggestions.json"),
        help="Pfad zu suggestions JSON",
    )
    parser.add_argument(
        "--output",
        default=str(BACKEND_DIR / "reports" / "phase7_control_dict_duplicate_cleanup_result.json"),
        help="Pfad fuer Ergebnis JSON",
    )
    parser.add_argument("--apply", action="store_true", help="Aenderungen wirklich in DB schreiben")
    args = parser.parse_args()

    suggestions_path = Path(args.suggestions)
    if not suggestions_path.exists():
        print(f"ERROR: suggestions file not found: {suggestions_path}")
        return 2

    result = asyncio.run(_run(args.apply, suggestions_path, Path(args.output)))
    summary = result.get("summary", {})

    print("PHASE7_DUPLICATE_CLEANUP")
    print(f"mode={result.get('mode')}")
    print(f"output={args.output}")
    for key in [
        "duplicate_groups",
        "uids_requested_for_retire",
        "uids_safe_to_retire",
        "uids_skipped",
    ]:
        print(f"{key}={summary.get(key)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

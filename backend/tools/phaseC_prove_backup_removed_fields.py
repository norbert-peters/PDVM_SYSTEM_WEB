"""
Phase C Punkt 2: Nachweislauf fuer backup_daten bei Feldentfall.

Ziel:
1. Legacy-Felder in infos-Tabellen erkennen, die nicht mehr zum Zielmodell gehoeren.
2. Entfallene Werte additiv in backup_daten.MIGRATION_BACKUP protokollieren.
3. Dry-Run und Apply als reproduzierbare Reports liefern.

Zielmodell (V1):
1. sys_dropdowndaten: ROOT + OPTIONS
2. sys_beschreibungen: ROOT + TEXTS

Usage:
  python backend/tools/phaseC_prove_backup_removed_fields.py
  python backend/tools/phaseC_prove_backup_removed_fields.py --apply
  python backend/tools/phaseC_prove_backup_removed_fields.py --output backend/reports/phaseC_prove_backup_removed_fields_report.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

import asyncpg

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.connection_manager import ConnectionManager

SYSTEM_UIDS = {
    "55555555-5555-5555-5555-555555555555",
    "66666666-6666-6666-6666-666666666666",
    "00000000-0000-0000-0000-000000000000",
}

TARGET_TOP_LEVEL_KEYS: Dict[str, set[str]] = {
    "sys_dropdowndaten": {"ROOT", "OPTIONS"},
    "sys_beschreibungen": {"ROOT", "TEXTS"},
}


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


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _backup_payload(
    existing_backup: Dict[str, Any],
    *,
    removed_entries: List[Dict[str, Any]],
    table_name: str,
    row_uid: str,
    row_name: str,
) -> Dict[str, Any]:
    out = dict(existing_backup)
    migration_backup = _as_dict(out.get("MIGRATION_BACKUP"))
    ts = _utc_now()
    migration_backup[ts] = {
        "table": table_name,
        "uid": row_uid,
        "name": row_name,
        "reason": "template_removed",
        "removed": removed_entries,
    }
    out["MIGRATION_BACKUP"] = migration_backup
    return out


async def _table_has_backup_column(conn: asyncpg.Connection, table_name: str) -> bool:
    count = await conn.fetchval(
        """
        SELECT COUNT(*)
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = $1
          AND column_name = 'backup_daten'
        """,
        table_name,
    )
    return int(count or 0) > 0


async def _process_table(conn: asyncpg.Connection, table_name: str, apply: bool) -> Dict[str, Any]:
    allowed = TARGET_TOP_LEVEL_KEYS[table_name]
    has_backup = await _table_has_backup_column(conn, table_name)

    entry: Dict[str, Any] = {
        "table": table_name,
        "allowed_top_level_keys": sorted(list(allowed)),
        "has_backup_column": has_backup,
        "rows_scanned": 0,
        "rows_with_removed_fields": 0,
        "removed_field_count": 0,
        "rows_updated": 0,
        "samples": [],
        "error": None,
    }

    if not has_backup:
        entry["error"] = "backup_daten_column_missing"
        return entry

    rows = await conn.fetch(
        f'''
        SELECT uid::text AS uid, name, daten, backup_daten
        FROM "{table_name}"
        WHERE COALESCE(historisch, 0) = 0
        ORDER BY created_at
        '''
    )

    for row in rows:
        uid = str(row.get("uid") or "")
        if uid in SYSTEM_UIDS:
            continue

        entry["rows_scanned"] += 1

        daten = _as_dict(row.get("daten"))
        if not daten:
            continue

        remove_keys = [k for k in daten.keys() if k not in allowed]
        if not remove_keys:
            continue

        removed_entries: List[Dict[str, Any]] = []
        for key in remove_keys:
            removed_entries.append(
                {
                    "path": key,
                    "value": daten.get(key),
                    "reason": "template_removed",
                }
            )

        entry["rows_with_removed_fields"] += 1
        entry["removed_field_count"] += len(removed_entries)
        if len(entry["samples"]) < 20:
            entry["samples"].append(
                {
                    "uid": uid,
                    "name": str(row.get("name") or ""),
                    "removed_paths": [e["path"] for e in removed_entries],
                }
            )

        if not apply:
            continue

        new_daten = dict(daten)
        for k in remove_keys:
            new_daten.pop(k, None)

        backup_old = _as_dict(row.get("backup_daten"))
        backup_new = _backup_payload(
            backup_old,
            removed_entries=removed_entries,
            table_name=table_name,
            row_uid=uid,
            row_name=str(row.get("name") or ""),
        )

        await conn.execute(
            f'''
            UPDATE "{table_name}"
            SET daten = $1::jsonb,
                backup_daten = $2::jsonb,
                modified_at = NOW()
            WHERE uid::text = $3
            ''',
            json.dumps(new_daten, ensure_ascii=False),
            json.dumps(backup_new, ensure_ascii=False),
            uid,
        )
        entry["rows_updated"] += 1

    return entry


async def build_report(apply: bool) -> Dict[str, Any]:
    cfg = await ConnectionManager.get_system_config("pdvm_system")
    conn = await asyncpg.connect(**cfg.to_dict())

    report: Dict[str, Any] = {
        "phase": "phaseC_prove_backup_removed_fields",
        "apply": bool(apply),
        "database": cfg.database,
        "generated_at_utc": _utc_now(),
        "tables": [],
        "summary": {
            "tables_total": 0,
            "tables_with_errors": 0,
            "rows_scanned": 0,
            "rows_with_removed_fields": 0,
            "removed_field_count": 0,
            "rows_updated": 0,
        },
    }

    try:
        for table_name in ("sys_beschreibungen", "sys_dropdowndaten"):
            entry = await _process_table(conn, table_name, apply=apply)
            report["tables"].append(entry)

        report["summary"]["tables_total"] = len(report["tables"])
        for t in report["tables"]:
            if t.get("error"):
                report["summary"]["tables_with_errors"] += 1
            report["summary"]["rows_scanned"] += int(t.get("rows_scanned", 0))
            report["summary"]["rows_with_removed_fields"] += int(t.get("rows_with_removed_fields", 0))
            report["summary"]["removed_field_count"] += int(t.get("removed_field_count", 0))
            report["summary"]["rows_updated"] += int(t.get("rows_updated", 0))
    finally:
        await conn.close()

    return report


def _default_output_path() -> Path:
    return BACKEND_DIR / "reports" / "phaseC_prove_backup_removed_fields_report.json"


def _print_summary(report: Dict[str, Any]) -> None:
    s = report.get("summary", {})
    print("\n=== Phase C Punkt 2: backup_daten Nachweislauf ===")
    print(f"Tables total: {s.get('tables_total', 0)}")
    print(f"Tables with errors: {s.get('tables_with_errors', 0)}")
    print(f"Rows scanned: {s.get('rows_scanned', 0)}")
    print(f"Rows with removed fields: {s.get('rows_with_removed_fields', 0)}")
    print(f"Removed field count: {s.get('removed_field_count', 0)}")
    print(f"Rows updated: {s.get('rows_updated', 0)}")


async def _run(apply: bool, output_path: Path) -> int:
    report = await build_report(apply=apply)
    _print_summary(report)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nReport geschrieben: {output_path}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase C Punkt 2: prove backup_daten on removed fields")
    parser.add_argument("--apply", action="store_true", help="Schreibt Bereinigung + backup_daten")
    parser.add_argument("--output", default=str(_default_output_path()), help="Pfad fuer JSON-Report")
    args = parser.parse_args()
    return asyncio.run(_run(apply=bool(args.apply), output_path=Path(args.output)))


if __name__ == "__main__":
    raise SystemExit(main())

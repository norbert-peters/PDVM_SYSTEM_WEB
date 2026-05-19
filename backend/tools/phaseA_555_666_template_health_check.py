"""
Phase A: 555/666 Template Health Check

Prueft tabellenweit in der System-DB:
- Existiert 555 und 666 je Tabelle?
- Sind ROOT-Strukturen vorhanden und identisch?
- Ist 666.TEMPLATES vorhanden?
- Welche Gruppen aus 555 sind in 666.TEMPLATES nicht abgebildet?

Usage:
  python backend/tools/phaseA_555_666_template_health_check.py
  python backend/tools/phaseA_555_666_template_health_check.py --output backend/reports/phaseA_555_666_template_health_check.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import asyncpg

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.connection_manager import ConnectionManager

UID_555 = "55555555-5555-5555-5555-555555555555"
UID_666 = "66666666-6666-6666-6666-666666666666"


@dataclass
class TableCheckResult:
    table: str
    has_historisch: bool
    has_555: bool = False
    has_666: bool = False
    errors: List[str] = None
    warnings: List[str] = None
    missing_template_groups: List[str] = None

    def __post_init__(self) -> None:
        self.errors = self.errors or []
        self.warnings = self.warnings or []
        self.missing_template_groups = self.missing_template_groups or []


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


def _safe_keys(value: Any) -> Set[str]:
    if isinstance(value, dict):
        return {str(k) for k in value.keys()}
    return set()


async def _find_candidate_tables(conn: asyncpg.Connection) -> List[Dict[str, Any]]:
    rows = await conn.fetch(
        """
        WITH cols AS (
          SELECT table_name,
                 MAX(CASE WHEN column_name = 'uid' THEN 1 ELSE 0 END) AS has_uid,
                 MAX(CASE WHEN column_name = 'daten' THEN 1 ELSE 0 END) AS has_daten,
                 MAX(CASE WHEN column_name = 'historisch' THEN 1 ELSE 0 END) AS has_historisch
          FROM information_schema.columns
          WHERE table_schema = 'public'
          GROUP BY table_name
        )
        SELECT table_name, has_historisch
        FROM cols
        WHERE has_uid = 1 AND has_daten = 1
        ORDER BY table_name
        """
    )
    return [dict(r) for r in rows]


async def _fetch_template_row(
    conn: asyncpg.Connection,
    table_name: str,
    uid_value: str,
    has_historisch: bool,
) -> Optional[Dict[str, Any]]:
    where_hist = "AND COALESCE(historisch, 0) = 0" if has_historisch else ""
    row = await conn.fetchrow(
        f'''
        SELECT uid::text AS uid, name, daten
        FROM "{table_name}"
        WHERE uid::text = $1
        {where_hist}
        LIMIT 1
        ''',
        uid_value,
    )
    return dict(row) if row else None


def _validate_table_templates(
    table_name: str,
    has_historisch: bool,
    row_555: Optional[Dict[str, Any]],
    row_666: Optional[Dict[str, Any]],
) -> TableCheckResult:
    result = TableCheckResult(table=table_name, has_historisch=has_historisch)

    result.has_555 = row_555 is not None
    result.has_666 = row_666 is not None

    if not result.has_555:
        result.errors.append("Template 555 fehlt")
    if not result.has_666:
        result.errors.append("Template 666 fehlt")

    if not (result.has_555 and result.has_666):
        return result

    data_555 = _as_dict(row_555.get("daten"))
    data_666 = _as_dict(row_666.get("daten"))

    root_555 = _as_dict(data_555.get("ROOT"))
    root_666 = _as_dict(data_666.get("ROOT"))
    templates_666 = _as_dict(data_666.get("TEMPLATES"))

    if not root_555:
        result.errors.append("555.ROOT fehlt oder ist kein Objekt")
    if not root_666:
        result.errors.append("666.ROOT fehlt oder ist kein Objekt")
    if not templates_666:
        result.errors.append("666.TEMPLATES fehlt oder ist kein Objekt")

    extra_top_666 = sorted(str(k) for k in data_666.keys() if str(k) not in {"ROOT", "TEMPLATES"})
    if extra_top_666:
        result.errors.append(f"666 darf nur ROOT+TEMPLATES enthalten (zusätzliche Keys: {extra_top_666})")

    if "TEMPLATES" in data_555:
        result.errors.append("555 darf kein Top-Level TEMPLATES enthalten")

    if root_555 and root_666:
        keys_555 = _safe_keys(root_555)
        keys_666 = _safe_keys(root_666)
        if keys_555 != keys_666:
            only_555 = sorted(keys_555 - keys_666)
            only_666 = sorted(keys_666 - keys_555)
            result.errors.append(
                f"ROOT-Struktur ungleich (nur in 555: {only_555}, nur in 666: {only_666})"
            )

    # Gruppen in 555: alle Top-Level ausser ROOT/TEMPLATES/BACKUP_DUMMY
    groups_555 = {
        str(k)
        for k in data_555.keys()
        if str(k) not in {"ROOT", "TEMPLATES", "BACKUP_DUMMY"}
    }

    wrong_type_555_groups = sorted(g for g in groups_555 if not isinstance(data_555.get(g), dict))
    non_empty_555_groups = sorted(g for g in groups_555 if isinstance(data_555.get(g), dict) and data_555.get(g))
    if wrong_type_555_groups:
        result.errors.append(f"555-Gruppen müssen Objekte sein (ungültig: {wrong_type_555_groups})")
    if non_empty_555_groups:
        result.errors.append(f"555-Gruppen müssen leer sein (nicht leer: {non_empty_555_groups})")

    if groups_555 and templates_666:
        missing = sorted(g for g in groups_555 if g not in templates_666)
        if missing:
            result.errors.append("Gruppen aus 555 fehlen in 666.TEMPLATES")
            result.missing_template_groups.extend(missing)

        extra_templates = sorted(str(g) for g in templates_666.keys() if str(g) not in groups_555)
        if extra_templates:
            result.errors.append(f"666.TEMPLATES enthält Fremd-Gruppen: {extra_templates}")

        wrong_template_types = sorted(str(k) for k, v in templates_666.items() if not isinstance(v, dict))
        if wrong_template_types:
            result.errors.append(f"666.TEMPLATES-Felder müssen Objekte sein: {wrong_template_types}")

    return result


async def build_report() -> Dict[str, Any]:
    cfg = await ConnectionManager.get_system_config()
    conn = await asyncpg.connect(**cfg.to_dict())

    try:
        candidates = await _find_candidate_tables(conn)
        checks: List[TableCheckResult] = []

        for candidate in candidates:
            table_name = str(candidate.get("table_name"))
            has_historisch = bool(candidate.get("has_historisch"))

            row_555 = await _fetch_template_row(conn, table_name, UID_555, has_historisch)
            row_666 = await _fetch_template_row(conn, table_name, UID_666, has_historisch)

            check = _validate_table_templates(table_name, has_historisch, row_555, row_666)
            checks.append(check)

        tables_with_templates = [c for c in checks if c.has_555 or c.has_666]
        tables_failing = [c for c in tables_with_templates if c.errors or c.warnings]

        report = {
            "phase": "phaseA",
            "title": "555/666 Template Health Check",
            "database": cfg.database,
            "summary": {
                "tables_scanned": len(checks),
                "tables_with_555_or_666": len(tables_with_templates),
                "tables_with_findings": len(tables_failing),
                "tables_ok": len([c for c in tables_with_templates if not c.errors and not c.warnings]),
                "error_count": sum(len(c.errors) for c in tables_with_templates),
                "warning_count": sum(len(c.warnings) for c in tables_with_templates),
            },
            "tables": [
                {
                    "table": c.table,
                    "has_historisch": c.has_historisch,
                    "has_555": c.has_555,
                    "has_666": c.has_666,
                    "errors": c.errors,
                    "warnings": c.warnings,
                    "missing_template_groups": c.missing_template_groups,
                }
                for c in checks
            ],
        }
        return report
    finally:
        await conn.close()


def _print_summary(report: Dict[str, Any]) -> None:
    summary = report.get("summary", {})
    print("\n=== Phase A: 555/666 Template Health Check ===")
    print(f"DB: {report.get('database')}")
    print(f"Tabellen gescannt: {summary.get('tables_scanned', 0)}")
    print(f"Mit 555/666 gefunden: {summary.get('tables_with_555_or_666', 0)}")
    print(f"Mit Findings: {summary.get('tables_with_findings', 0)}")
    print(f"Ohne Findings: {summary.get('tables_ok', 0)}")
    print(f"Errors: {summary.get('error_count', 0)}")
    print(f"Warnings: {summary.get('warning_count', 0)}")


def _default_output_path() -> Path:
    return BACKEND_DIR / "reports" / "phaseA_555_666_template_health_check.json"


async def _run(output_path: Path) -> int:
    report = await build_report()
    _print_summary(report)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nReport geschrieben: {output_path}")

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase A 555/666 Template Health Check")
    parser.add_argument(
        "--output",
        default=str(_default_output_path()),
        help="Pfad fuer den JSON-Report",
    )
    args = parser.parse_args()

    return asyncio.run(_run(Path(args.output)))


if __name__ == "__main__":
    raise SystemExit(main())

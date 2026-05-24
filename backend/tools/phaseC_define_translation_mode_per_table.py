"""
Phase C Punkt 8: Uebersetzungsmodus je Tabelle finalisieren und nachweisen.

Usage:
  python backend/tools/phaseC_define_translation_mode_per_table.py
  python backend/tools/phaseC_define_translation_mode_per_table.py --output backend/reports/phaseC_define_translation_mode_per_table_v1.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import asyncpg

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.connection_manager import ConnectionManager

_IDENTIFIER_RE = re.compile(r"^[a-z_][a-z0-9_]*$")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _as_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _as_list(value: Any) -> List[Any]:
    if isinstance(value, list):
        return value
    return []


def _load_config(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _is_safe_identifier(name: str) -> bool:
    return bool(_IDENTIFIER_RE.match(name or ""))


async def _table_exists(conn: asyncpg.Connection, table_name: str) -> bool:
    regclass = await conn.fetchval("SELECT to_regclass($1)", f"public.{table_name}")
    return regclass is not None


async def _active_count(conn: asyncpg.Connection, table_name: str) -> int:
    query = f'SELECT COUNT(*)::bigint FROM "{table_name}" WHERE COALESCE(historisch, 0) = 0'
    return int(await conn.fetchval(query) or 0)


async def build_report(config_path: Path) -> Dict[str, Any]:
    config = _load_config(config_path)
    allowed_modes = {str(x).upper() for x in _as_list(config.get("allowed_modes"))}
    in_scope_tables = [str(x) for x in _as_list(config.get("in_scope_tables")) if str(x).strip()]
    assignments = _as_dict(config.get("assignments"))

    cfg = await ConnectionManager.get_system_config("pdvm_system")
    conn = await asyncpg.connect(**cfg.to_dict())

    assignment_results: List[Dict[str, Any]] = []
    invalid_mode_count = 0
    missing_review_rule_count = 0

    try:
        for table_name in in_scope_tables:
            data = _as_dict(assignments.get(table_name))
            mode = str(data.get("mode") or "").upper()
            decision_locked = bool(data.get("decision_locked"))
            review_required = bool(data.get("review_required", True))
            review_rule = str(data.get("review_rule") or "").strip()

            safe_identifier = _is_safe_identifier(table_name)
            table_exists = False
            active_rows = None
            error = None

            if not safe_identifier:
                error = "invalid_table_identifier"
            else:
                table_exists = await _table_exists(conn, table_name)
                if table_exists:
                    active_rows = await _active_count(conn, table_name)

            mode_valid = mode in allowed_modes
            if not mode_valid:
                invalid_mode_count += 1
            if not review_rule:
                missing_review_rule_count += 1

            assignment_results.append(
                {
                    "table": table_name,
                    "mode": mode,
                    "mode_valid": mode_valid,
                    "decision_locked": decision_locked,
                    "review_required": review_required,
                    "review_rule": review_rule,
                    "table_identifier_valid": safe_identifier,
                    "table_exists": table_exists,
                    "active_rows_non_historic": active_rows,
                    "error": error,
                }
            )
    finally:
        await conn.close()

    assigned_table_set = {str(k) for k in assignments.keys()}
    in_scope_set = set(in_scope_tables)
    missing_assignments = sorted(in_scope_set - assigned_table_set)
    extra_assignments = sorted(assigned_table_set - in_scope_set)

    tables_missing_count = sum(1 for x in assignment_results if not bool(x.get("table_exists")))
    open_decisions_count = sum(1 for x in assignment_results if not bool(x.get("decision_locked")))

    return {
        "phase": "phaseC_define_translation_mode_per_table",
        "generated_at_utc": _utc_now(),
        "database": cfg.database,
        "config_path": str(config_path),
        "config": config,
        "assignments": assignment_results,
        "diff": {
            "missing_assignments": missing_assignments,
            "extra_assignments": extra_assignments,
        },
        "summary": {
            "in_scope_tables_count": len(in_scope_tables),
            "assignments_count": len(assignment_results),
            "invalid_mode_count": invalid_mode_count,
            "missing_review_rule_count": missing_review_rule_count,
            "tables_missing_count": tables_missing_count,
            "open_decisions_count": open_decisions_count,
            "decision_set_complete": (
                len(missing_assignments) == 0
                and invalid_mode_count == 0
                and missing_review_rule_count == 0
                and tables_missing_count == 0
                and open_decisions_count == 0
            ),
        },
    }


def _default_config_path() -> Path:
    return BACKEND_DIR / "config" / "i18n_translation_mode_per_table_v1.json"


def _default_output_path() -> Path:
    return BACKEND_DIR / "reports" / "phaseC_define_translation_mode_per_table_v1.json"


def _print_summary(report: Dict[str, Any]) -> None:
    s = _as_dict(report.get("summary"))
    print("\n=== Phase C Punkt 8: Translation Mode Per Table ===")
    print(f"In scope tables: {s.get('in_scope_tables_count')}")
    print(f"Assignments: {s.get('assignments_count')}")
    print(f"Invalid modes: {s.get('invalid_mode_count')}")
    print(f"Missing review rules: {s.get('missing_review_rule_count')}")
    print(f"Missing tables: {s.get('tables_missing_count')}")
    print(f"Open decisions: {s.get('open_decisions_count')}")
    print(f"Decision set complete: {s.get('decision_set_complete')}")


async def _run(config_path: Path, output_path: Path) -> int:
    report = await build_report(config_path)
    _print_summary(report)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nReport geschrieben: {output_path}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase C Punkt 8: define translation mode per table")
    parser.add_argument("--config", default=str(_default_config_path()), help="Pfad zur Mode-Config")
    parser.add_argument("--output", default=str(_default_output_path()), help="Pfad fuer JSON-Report")
    args = parser.parse_args()
    return asyncio.run(_run(Path(args.config), Path(args.output)))


if __name__ == "__main__":
    raise SystemExit(main())

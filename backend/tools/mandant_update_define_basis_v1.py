"""
Definiert die Mandant-Update-Basis (State + History Tabellen) in der main_mandant DB.

Usage:
  python backend/tools/mandant_update_define_basis_v1.py
  python backend/tools/mandant_update_define_basis_v1.py --apply
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import asyncpg

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from tools.phaseB_persist_template_modes import _resolve_main_mandant_config

STATE_TABLE = "msy_update_state"
HISTORY_TABLE = "msy_update_history"
SQL_ARTIFACT_PATH = BACKEND_DIR / "reports" / "mandant_update_basis_v1.sql"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _table_exists(conn: asyncpg.Connection, table_name: str) -> bool:
    exists = await conn.fetchval("SELECT to_regclass($1) IS NOT NULL", f"public.{table_name}")
    return bool(exists)


def _ddl_statements() -> List[str]:
    raw_sql = SQL_ARTIFACT_PATH.read_text(encoding="utf-8")
    filtered_lines: List[str] = []
    for line in raw_sql.splitlines():
        stripped = line.strip()
        if stripped.startswith("--"):
            continue
        filtered_lines.append(line)

    sql_text = "\n".join(filtered_lines)
    parts: List[str] = []
    for statement in sql_text.split(";"):
        cleaned = statement.strip()
        if not cleaned:
            continue
        parts.append(cleaned + ";")
    return parts


async def build_report(apply: bool) -> Dict[str, Any]:
    mandant_cfg, mandant_info = await _resolve_main_mandant_config()
    report: Dict[str, Any] = {
        "phase": "mandant_update_define_basis_v1",
        "apply": bool(apply),
        "generated_at_utc": _utc_now(),
        "sql_artifact": str(SQL_ARTIFACT_PATH),
        "main_mandant": mandant_info,
        "database": None,
        "actions": [],
        "summary": {
            "db_available": False,
            "state_table_exists_before": False,
            "history_table_exists_before": False,
            "state_table_exists_after": False,
            "history_table_exists_after": False,
            "ddl_statement_count": 0,
            "ddl_executed_count": 0,
            "errors": 0,
        },
    }

    if not SQL_ARTIFACT_PATH.exists():
        report["actions"].append({"status": "error", "message": "sql_artifact_missing"})
        report["summary"]["errors"] += 1
        return report

    if not mandant_cfg:
        report["actions"].append({"status": "error", "message": "main_mandant_not_resolved"})
        report["summary"]["errors"] += 1
        return report

    report["database"] = mandant_cfg.database
    ddl = _ddl_statements()
    report["summary"]["ddl_statement_count"] = len(ddl)

    conn = await asyncpg.connect(**mandant_cfg.to_dict())
    try:
        report["summary"]["db_available"] = True
        report["summary"]["state_table_exists_before"] = await _table_exists(conn, STATE_TABLE)
        report["summary"]["history_table_exists_before"] = await _table_exists(conn, HISTORY_TABLE)

        if apply:
            for statement in ddl:
                await conn.execute(statement)
                report["summary"]["ddl_executed_count"] += 1
            report["actions"].append({"status": "applied", "message": "ddl_executed"})
        else:
            report["actions"].append({"status": "dry_run", "message": "ddl_not_executed"})

        report["summary"]["state_table_exists_after"] = await _table_exists(conn, STATE_TABLE)
        report["summary"]["history_table_exists_after"] = await _table_exists(conn, HISTORY_TABLE)
    except Exception as exc:
        report["actions"].append({"status": "error", "message": str(exc)})
        report["summary"]["errors"] += 1
    finally:
        await conn.close()

    return report


def _default_output_path() -> Path:
    return BACKEND_DIR / "reports" / "mandant_update_define_basis_v1.json"


def _print_summary(report: Dict[str, Any]) -> None:
    s = report.get("summary", {})
    print("\n=== Mandant Update Basis V1 ===")
    print(f"DB available: {s.get('db_available')}")
    print(f"State table before/after: {s.get('state_table_exists_before')} -> {s.get('state_table_exists_after')}")
    print(f"History table before/after: {s.get('history_table_exists_before')} -> {s.get('history_table_exists_after')}")
    print(f"DDL executed count: {s.get('ddl_executed_count')}")
    print(f"Errors: {s.get('errors')}")


async def _run(apply: bool, output_path: Path) -> int:
    report = await build_report(apply=apply)
    _print_summary(report)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nReport geschrieben: {output_path}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Define mandant update basis tables")
    parser.add_argument("--apply", action="store_true", help="Führt DDL in main_mandant DB aus")
    parser.add_argument("--output", default=str(_default_output_path()), help="Pfad für JSON-Report")
    args = parser.parse_args()
    return asyncio.run(_run(apply=bool(args.apply), output_path=Path(args.output)))


if __name__ == "__main__":
    raise SystemExit(main())

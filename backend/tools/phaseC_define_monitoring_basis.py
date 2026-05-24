"""
Phase C Punkt 4: Monitoring-Basis entscheiden und technisch absichern.

Ziel:
1. Mandantenweite Monitoring-Tabelle fuer Batch/Job-Ablaufe definieren.
2. DDL reproduzierbar als Dry-Run/Apply ausfuehren.
3. JSON-Report fuer Abnahme erzeugen.

Usage:
  python backend/tools/phaseC_define_monitoring_basis.py
  python backend/tools/phaseC_define_monitoring_basis.py --apply
  python backend/tools/phaseC_define_monitoring_basis.py --output backend/reports/phaseC_define_monitoring_basis_v1.json
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

from app.core.connection_manager import ConnectionManager
from tools.phaseB_persist_template_modes import _resolve_main_mandant_config

TABLE_NAME = "msy_batch_job_monitoring"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _table_exists(conn: asyncpg.Connection, table_name: str) -> bool:
    exists = await conn.fetchval("SELECT to_regclass($1) IS NOT NULL", f"public.{table_name}")
    return bool(exists)


def _ddl_statements() -> List[str]:
    return [
        f'''
CREATE TABLE IF NOT EXISTS "{TABLE_NAME}" (
    uid UUID PRIMARY KEY,
    link_uid UUID NULL,
    name TEXT NOT NULL DEFAULT '',
    daten JSONB NOT NULL DEFAULT '{{}}'::jsonb,
    backup_daten JSONB NOT NULL DEFAULT '{{}}'::jsonb,
    daten_backup JSONB NOT NULL DEFAULT '{{}}'::jsonb,
    historisch INTEGER NOT NULL DEFAULT 0,
    source_hash TEXT NOT NULL DEFAULT '',
    sec_id TEXT NOT NULL DEFAULT '',
    gilt_bis DOUBLE PRECISION NOT NULL DEFAULT 1001,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    modified_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
'''.strip(),
        f'''CREATE INDEX IF NOT EXISTS idx_{TABLE_NAME}_historisch ON "{TABLE_NAME}" (historisch);''',
        f'''CREATE INDEX IF NOT EXISTS idx_{TABLE_NAME}_created_at ON "{TABLE_NAME}" (created_at);''',
        f'''CREATE INDEX IF NOT EXISTS idx_{TABLE_NAME}_modified_at ON "{TABLE_NAME}" (modified_at);''',
        f'''CREATE INDEX IF NOT EXISTS idx_{TABLE_NAME}_job_name ON "{TABLE_NAME}" ((daten->'ROOT'->>'JOB_NAME'));''',
        f'''CREATE INDEX IF NOT EXISTS idx_{TABLE_NAME}_run_status ON "{TABLE_NAME}" ((daten->'ROOT'->>'RUN_STATUS'));''',
    ]


async def build_report(apply: bool) -> Dict[str, Any]:
    mandant_cfg, mandant_info = await _resolve_main_mandant_config()
    report: Dict[str, Any] = {
        "phase": "phaseC_define_monitoring_basis",
        "apply": bool(apply),
        "generated_at_utc": _utc_now(),
        "table_name": TABLE_NAME,
        "main_mandant": mandant_info,
        "database": None,
        "ddl": _ddl_statements(),
        "actions": [],
        "summary": {
            "db_available": False,
            "table_exists_before": False,
            "table_exists_after": False,
            "ddl_statement_count": len(_ddl_statements()),
            "ddl_executed_count": 0,
            "errors": 0,
        },
    }

    if not mandant_cfg:
        report["actions"].append({"status": "error", "message": "main_mandant_not_resolved"})
        report["summary"]["errors"] += 1
        return report

    report["database"] = mandant_cfg.database

    conn = await asyncpg.connect(**mandant_cfg.to_dict())
    try:
        report["summary"]["db_available"] = True
        before = await _table_exists(conn, TABLE_NAME)
        report["summary"]["table_exists_before"] = before

        if apply:
            for ddl in _ddl_statements():
                await conn.execute(ddl)
                report["summary"]["ddl_executed_count"] += 1
            report["actions"].append({"status": "applied", "message": "ddl_executed"})
        else:
            report["actions"].append({"status": "dry_run", "message": "ddl_not_executed"})

        after = await _table_exists(conn, TABLE_NAME)
        report["summary"]["table_exists_after"] = after
    except Exception as exc:
        report["actions"].append({"status": "error", "message": f"{exc}"})
        report["summary"]["errors"] += 1
    finally:
        await conn.close()

    return report


def _default_output_path() -> Path:
    return BACKEND_DIR / "reports" / "phaseC_define_monitoring_basis_v1.json"


def _print_summary(report: Dict[str, Any]) -> None:
    s = report.get("summary", {})
    print("\n=== Phase C Punkt 4: Monitoring-Basis ===")
    print(f"DB available: {s.get('db_available', False)}")
    print(f"Table exists before: {s.get('table_exists_before', False)}")
    print(f"Table exists after: {s.get('table_exists_after', False)}")
    print(f"DDL executed count: {s.get('ddl_executed_count', 0)}")
    print(f"Errors: {s.get('errors', 0)}")


async def _run(apply: bool, output_path: Path) -> int:
    report = await build_report(apply=apply)
    _print_summary(report)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nReport geschrieben: {output_path}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase C Punkt 4: define monitoring basis")
    parser.add_argument("--apply", action="store_true", help="Fuehrt DDL in main_mandant DB aus")
    parser.add_argument("--output", default=str(_default_output_path()), help="Pfad fuer JSON-Report")
    args = parser.parse_args()
    return asyncio.run(_run(apply=bool(args.apply), output_path=Path(args.output)))


if __name__ == "__main__":
    raise SystemExit(main())

"""
Validiert den Mandanten-Update-Zustand (State + History + Zielversionskonsistenz).

Usage:
  python backend/tools/mandant_update_validate_v1.py
  python backend/tools/mandant_update_validate_v1.py --output backend/reports/mandant_update_validate_v1.json
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

from tools.phaseB_persist_template_modes import _resolve_main_mandant_config

STATE_TABLE = "msy_update_state"
HISTORY_TABLE = "msy_update_history"
DEFAULTS_PATH = BACKEND_DIR / "config" / "mandant_update_runtime_defaults_v1.json"


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


def _load_defaults(path: Path) -> Dict[str, Any]:
    defaults = {
        "version": 1,
        "source_version_target": "v2.1.0",
        "db_schema_version_target": "db.2026.05.21.01",
        "data_model_version_target": "data.2026.05.21.01",
        "run_interval_minutes": 15,
        "max_db_errors": 0,
        "max_batches": 500,
    }
    if not path.exists():
        return defaults
    try:
        raw = _as_dict(json.loads(path.read_text(encoding="utf-8")))
    except Exception:
        return defaults
    for key in defaults.keys():
        if key in raw:
            defaults[key] = raw[key]
    return defaults


async def _table_exists(conn: asyncpg.Connection, table_name: str) -> bool:
    exists = await conn.fetchval("SELECT to_regclass($1) IS NOT NULL", f"public.{table_name}")
    return bool(exists)


async def _load_state_row(conn: asyncpg.Connection, mandant_guid: str) -> Optional[Dict[str, Any]]:
    row = await conn.fetchrow(
        f'''
        SELECT
            uid::text AS uid,
            mandant_guid::text AS mandant_guid,
            source_version_current,
            db_schema_version_current,
            data_model_version_current,
            last_successful_run_id::text AS last_successful_run_id,
            modified_at
        FROM "{STATE_TABLE}"
        WHERE COALESCE(historisch, 0) = 0
          AND mandant_guid::text = $1
        ORDER BY modified_at DESC
        LIMIT 1
        ''',
        mandant_guid,
    )
    if not row:
        return None
    return {
        "uid": str(row.get("uid") or ""),
        "mandant_guid": str(row.get("mandant_guid") or ""),
        "source_version_current": str(row.get("source_version_current") or ""),
        "db_schema_version_current": str(row.get("db_schema_version_current") or ""),
        "data_model_version_current": str(row.get("data_model_version_current") or ""),
        "last_successful_run_id": str(row.get("last_successful_run_id") or ""),
        "modified_at": str(row.get("modified_at") or ""),
    }


async def _load_history_row(conn: asyncpg.Connection, run_id: str) -> Optional[Dict[str, Any]]:
    if not run_id:
        return None
    row = await conn.fetchrow(
        f'''
        SELECT
            uid::text AS uid,
            run_id::text AS run_id,
            mandant_guid::text AS mandant_guid,
            source_version_target,
            db_schema_version_target,
            data_model_version_target,
            run_status,
            step_name,
            started_at_utc,
            ended_at_utc,
            error_count,
            warning_count,
            report_json
        FROM "{HISTORY_TABLE}"
        WHERE run_id::text = $1
        ORDER BY started_at_utc DESC
        LIMIT 1
        ''',
        run_id,
    )
    if not row:
        return None
    return {
        "uid": str(row.get("uid") or ""),
        "run_id": str(row.get("run_id") or ""),
        "mandant_guid": str(row.get("mandant_guid") or ""),
        "source_version_target": str(row.get("source_version_target") or ""),
        "db_schema_version_target": str(row.get("db_schema_version_target") or ""),
        "data_model_version_target": str(row.get("data_model_version_target") or ""),
        "run_status": str(row.get("run_status") or ""),
        "step_name": str(row.get("step_name") or ""),
        "started_at_utc": str(row.get("started_at_utc") or ""),
        "ended_at_utc": str(row.get("ended_at_utc") or ""),
        "error_count": int(row.get("error_count") or 0),
        "warning_count": int(row.get("warning_count") or 0),
        "report_json": _as_dict(row.get("report_json")),
    }


def _add_check(report: Dict[str, Any], name: str, ok: bool, details: Dict[str, Any]) -> None:
    checks = report.setdefault("checks", [])
    checks.append({"name": name, "ok": bool(ok), "details": details})


async def build_report(
    source_version_target: str,
    db_schema_version_target: str,
    data_model_version_target: str,
    defaults_path: Path,
) -> Dict[str, Any]:
    defaults = _load_defaults(defaults_path)
    mandant_cfg, mandant_info = await _resolve_main_mandant_config()

    report: Dict[str, Any] = {
        "phase": "mandant_update_validate_v1",
        "generated_at_utc": _utc_now(),
        "main_mandant": mandant_info,
        "database": None,
        "defaults": defaults,
        "targets": {
            "source_version_target": source_version_target,
            "db_schema_version_target": db_schema_version_target,
            "data_model_version_target": data_model_version_target,
        },
        "state": None,
        "history": None,
        "checks": [],
        "summary": {
            "db_available": False,
            "checks_total": 0,
            "checks_passed": 0,
            "checks_failed": 0,
            "validation_status": "failed",
            "errors": 0,
        },
    }

    if not mandant_cfg:
        _add_check(report, "main_mandant_resolved", False, {"reason": "main_mandant_not_resolved"})
        report["summary"]["errors"] += 1
        return report

    mandant_guid = str((mandant_info or {}).get("uid") or "")
    report["database"] = mandant_cfg.database
    if not mandant_guid:
        _add_check(report, "mandant_guid_available", False, {"reason": "mandant_guid_missing"})
        report["summary"]["errors"] += 1
        return report

    conn = await asyncpg.connect(**mandant_cfg.to_dict())
    try:
        report["summary"]["db_available"] = True

        state_exists = await _table_exists(conn, STATE_TABLE)
        history_exists = await _table_exists(conn, HISTORY_TABLE)
        _add_check(report, "state_table_exists", state_exists, {"table": STATE_TABLE})
        _add_check(report, "history_table_exists", history_exists, {"table": HISTORY_TABLE})

        if not state_exists or not history_exists:
            report["summary"]["errors"] += 1
            return report

        state = await _load_state_row(conn, mandant_guid)
        report["state"] = state
        has_state = state is not None
        _add_check(report, "state_row_exists", has_state, {"mandant_guid": mandant_guid})
        if not has_state:
            report["summary"]["errors"] += 1
            return report

        source_ok = str(state.get("source_version_current") or "") == source_version_target
        db_ok = str(state.get("db_schema_version_current") or "") == db_schema_version_target
        data_ok = str(state.get("data_model_version_current") or "") == data_model_version_target
        _add_check(
            report,
            "state_versions_match_targets",
            bool(source_ok and db_ok and data_ok),
            {
                "source_current": state.get("source_version_current"),
                "source_target": source_version_target,
                "db_current": state.get("db_schema_version_current"),
                "db_target": db_schema_version_target,
                "data_current": state.get("data_model_version_current"),
                "data_target": data_model_version_target,
            },
        )

        last_run_id = str(state.get("last_successful_run_id") or "")
        has_last_run = bool(last_run_id)
        _add_check(report, "state_has_last_successful_run_id", has_last_run, {"last_successful_run_id": last_run_id})

        history = await _load_history_row(conn, last_run_id)
        report["history"] = history
        history_found = history is not None
        _add_check(report, "history_row_for_last_run_exists", history_found, {"run_id": last_run_id})
        if history_found:
            history_status_ok = str(history.get("run_status") or "").lower() == "success"
            _add_check(
                report,
                "history_last_run_success",
                history_status_ok,
                {
                    "run_status": history.get("run_status"),
                    "error_count": history.get("error_count"),
                    "warning_count": history.get("warning_count"),
                },
            )
            history_target_ok = (
                str(history.get("source_version_target") or "") == source_version_target
                and str(history.get("db_schema_version_target") or "") == db_schema_version_target
                and str(history.get("data_model_version_target") or "") == data_model_version_target
            )
            _add_check(
                report,
                "history_targets_match",
                history_target_ok,
                {
                    "source_target": history.get("source_version_target"),
                    "db_target": history.get("db_schema_version_target"),
                    "data_target": history.get("data_model_version_target"),
                },
            )
            report_json_ok = isinstance(history.get("report_json"), dict) and bool(history.get("report_json"))
            _add_check(report, "history_report_json_present", report_json_ok, {"report_json_keys": list((history.get("report_json") or {}).keys())})
    except Exception as exc:
        report["summary"]["errors"] += 1
        _add_check(report, "runtime_exception", False, {"message": str(exc)})
    finally:
        await conn.close()

    checks = report.get("checks", [])
    passed = sum(1 for c in checks if bool(c.get("ok")))
    total = len(checks)
    failed = total - passed

    report["summary"]["checks_total"] = total
    report["summary"]["checks_passed"] = passed
    report["summary"]["checks_failed"] = failed
    report["summary"]["validation_status"] = "passed" if failed == 0 else "failed"

    return report


def _default_output_path() -> Path:
    return BACKEND_DIR / "reports" / "mandant_update_validate_v1.json"


async def _run(args: argparse.Namespace) -> int:
    defaults = _load_defaults(Path(args.defaults))

    source_target = args.source_version_target or str(defaults.get("source_version_target") or "")
    db_target = args.db_schema_version_target or str(defaults.get("db_schema_version_target") or "")
    data_target = args.data_model_version_target or str(defaults.get("data_model_version_target") or "")

    report = await build_report(
        source_version_target=source_target,
        db_schema_version_target=db_target,
        data_model_version_target=data_target,
        defaults_path=Path(args.defaults),
    )

    s = report.get("summary", {})
    print("\n=== Mandant Update Validate V1 ===")
    print(f"Validation status: {s.get('validation_status')}")
    print(f"Checks passed/total: {s.get('checks_passed')} / {s.get('checks_total')}")
    print(f"Errors: {s.get('errors')}")

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nReport geschrieben: {output_path}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate mandant update state and history consistency")
    parser.add_argument("--defaults", default=str(DEFAULTS_PATH), help="Pfad zu Runtime-Defaults")
    parser.add_argument("--source-version-target", default=None, help="Ziel fuer SOURCE_VERSION")
    parser.add_argument("--db-schema-version-target", default=None, help="Ziel fuer DB_SCHEMA_VERSION")
    parser.add_argument("--data-model-version-target", default=None, help="Ziel fuer DATA_MODEL_VERSION")
    parser.add_argument("--output", default=str(_default_output_path()), help="Pfad fuer JSON-Report")
    args = parser.parse_args()
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())

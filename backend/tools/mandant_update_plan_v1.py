"""
Erzeugt einen Delta-Plan für Mandanten-DB-Updates (Source, DB-Schema, Datenmodell).

Usage:
  python backend/tools/mandant_update_plan_v1.py
  python backend/tools/mandant_update_plan_v1.py --source-version-target v2.2.0
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import asyncpg

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from tools.phaseB_persist_template_modes import _resolve_main_mandant_config

STATE_TABLE = "msy_update_state"
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


def _delta_action(name: str, current: str, target: str, order: int) -> Dict[str, Any]:
    changed = (current or "") != (target or "")
    return {
        "order": order,
        "update_type": name,
        "current": current,
        "target": target,
        "changed": changed,
    }


async def build_report(
    source_version_target: str,
    db_schema_version_target: str,
    data_model_version_target: str,
    defaults_path: Path,
) -> Dict[str, Any]:
    defaults = _load_defaults(defaults_path)

    mandant_cfg, mandant_info = await _resolve_main_mandant_config()
    report: Dict[str, Any] = {
        "phase": "mandant_update_plan_v1",
        "generated_at_utc": _utc_now(),
        "plan_id": str(uuid.uuid4()),
        "main_mandant": mandant_info,
        "database": None,
        "defaults": defaults,
        "targets": {
            "source_version_target": source_version_target,
            "db_schema_version_target": db_schema_version_target,
            "data_model_version_target": data_model_version_target,
        },
        "state": None,
        "actions": [],
        "summary": {
            "db_available": False,
            "state_table_exists": False,
            "state_row_exists": False,
            "delta_count": 0,
            "plan_status": "blocked",
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
        exists = await _table_exists(conn, STATE_TABLE)
        report["summary"]["state_table_exists"] = exists
        if not exists:
            report["actions"].append({"status": "blocked", "message": "state_table_missing"})
            report["summary"]["plan_status"] = "blocked"
            return report

        mandant_guid = str((mandant_info or {}).get("uid") or "")
        if not mandant_guid:
            report["actions"].append({"status": "blocked", "message": "mandant_guid_missing"})
            report["summary"]["plan_status"] = "blocked"
            return report

        state = await _load_state_row(conn, mandant_guid)
        report["state"] = state
        report["summary"]["state_row_exists"] = state is not None

        current_source = str((state or {}).get("source_version_current") or "")
        current_db = str((state or {}).get("db_schema_version_current") or "")
        current_data = str((state or {}).get("data_model_version_current") or "")

        action_source = _delta_action("SOURCE_UPDATE", current_source, source_version_target, 1)
        action_db = _delta_action("DATABASE_UPDATE", current_db, db_schema_version_target, 2)
        action_data = _delta_action("DATA_UPDATE", current_data, data_model_version_target, 3)
        report["actions"].extend([action_source, action_db, action_data])

        delta_count = sum(1 for a in [action_source, action_db, action_data] if bool(a.get("changed")))
        report["summary"]["delta_count"] = delta_count

        if delta_count == 0:
            report["summary"]["plan_status"] = "no_change"
        else:
            report["summary"]["plan_status"] = "ready"
    except Exception as exc:
        report["actions"].append({"status": "error", "message": str(exc)})
        report["summary"]["errors"] += 1
        report["summary"]["plan_status"] = "failed"
    finally:
        await conn.close()

    return report


def _default_output_path() -> Path:
    return BACKEND_DIR / "reports" / "mandant_update_plan_v1.json"


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
    print("\n=== Mandant Update Plan V1 ===")
    print(f"Plan status: {s.get('plan_status')}")
    print(f"Delta count: {s.get('delta_count')}")
    print(f"State table exists: {s.get('state_table_exists')}")
    print(f"State row exists: {s.get('state_row_exists')}")

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nReport geschrieben: {output_path}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Build mandant update delta plan")
    parser.add_argument("--defaults", default=str(DEFAULTS_PATH), help="Pfad zu Runtime-Defaults")
    parser.add_argument("--source-version-target", default=None, help="Ziel fuer SOURCE_VERSION")
    parser.add_argument("--db-schema-version-target", default=None, help="Ziel fuer DB_SCHEMA_VERSION")
    parser.add_argument("--data-model-version-target", default=None, help="Ziel fuer DATA_MODEL_VERSION")
    parser.add_argument("--output", default=str(_default_output_path()), help="Pfad fuer JSON-Report")
    args = parser.parse_args()
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())

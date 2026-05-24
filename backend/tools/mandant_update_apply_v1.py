"""
Fuehrt Mandanten-Update-Apply fuer Versionsachsen SOURCE/DB_SCHEMA/DATA_MODEL aus.

Usage:
  python backend/tools/mandant_update_apply_v1.py
  python backend/tools/mandant_update_apply_v1.py --apply
  python backend/tools/mandant_update_apply_v1.py --apply --output backend/reports/mandant_update_apply_v1.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

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


def _delta_action(name: str, current: str, target: str, order: int) -> Dict[str, Any]:
    changed = (current or "") != (target or "")
    return {
        "order": order,
        "update_type": name,
        "current": current,
        "target": target,
        "changed": changed,
    }


async def _upsert_state(
    conn: asyncpg.Connection,
    *,
    mandant_guid: str,
    existing_uid: Optional[str],
    source_version_target: str,
    db_schema_version_target: str,
    data_model_version_target: str,
    run_id: str,
) -> str:
    if existing_uid:
        await conn.execute(
            f'''
            UPDATE "{STATE_TABLE}"
            SET source_version_current = $1,
                db_schema_version_current = $2,
                data_model_version_current = $3,
                last_successful_run_id = $4::uuid,
                modified_at = NOW()
            WHERE uid::text = $5
            ''',
            source_version_target,
            db_schema_version_target,
            data_model_version_target,
            run_id,
            existing_uid,
        )
        return existing_uid

    new_uid = str(uuid.uuid4())
    await conn.execute(
        f'''
        INSERT INTO "{STATE_TABLE}" (
            uid,
            mandant_guid,
            source_version_current,
            db_schema_version_current,
            data_model_version_current,
            last_successful_run_id,
            name,
            daten
        ) VALUES (
            $1::uuid,
            $2::uuid,
            $3,
            $4,
            $5,
            $6::uuid,
            $7,
            $8::jsonb
        )
        ''',
        new_uid,
        mandant_guid,
        source_version_target,
        db_schema_version_target,
        data_model_version_target,
        run_id,
        f"MANDANT_UPDATE_STATE::{mandant_guid}",
        json.dumps(
            {
                "ROOT": {
                    "MANDANT_GUID": mandant_guid,
                    "SOURCE_VERSION_CURRENT": source_version_target,
                    "DB_SCHEMA_VERSION_CURRENT": db_schema_version_target,
                    "DATA_MODEL_VERSION_CURRENT": data_model_version_target,
                    "LAST_SUCCESSFUL_RUN_ID": run_id,
                }
            },
            ensure_ascii=False,
        ),
    )
    return new_uid


async def _insert_history(
    conn: asyncpg.Connection,
    *,
    run_id: str,
    mandant_guid: str,
    source_version_target: str,
    db_schema_version_target: str,
    data_model_version_target: str,
    report_payload: Dict[str, Any],
) -> None:
    history_uid = str(uuid.uuid4())
    await conn.execute(
        f'''
        INSERT INTO "{HISTORY_TABLE}" (
            uid,
            run_id,
            mandant_guid,
            source_version_target,
            db_schema_version_target,
            data_model_version_target,
            run_status,
            step_name,
            started_at_utc,
            ended_at_utc,
            error_count,
            warning_count,
            report_json,
            name,
            daten
        ) VALUES (
            $1::uuid,
            $2::uuid,
            $3::uuid,
            $4,
            $5,
            $6,
            'success',
            'FINALIZE',
            NOW(),
            NOW(),
            0,
            0,
            $7::jsonb,
            $8,
            $9::jsonb
        )
        ''',
        history_uid,
        run_id,
        mandant_guid,
        source_version_target,
        db_schema_version_target,
        data_model_version_target,
        json.dumps(report_payload, ensure_ascii=False),
        f"MANDANT_UPDATE_RUN::{run_id}",
        json.dumps(
            {
                "ROOT": {
                    "RUN_ID": run_id,
                    "MANDANT_GUID": mandant_guid,
                    "RUN_STATUS": "success",
                    "STEP": "FINALIZE",
                }
            },
            ensure_ascii=False,
        ),
    )


async def build_report(
    *,
    apply: bool,
    source_version_target: str,
    db_schema_version_target: str,
    data_model_version_target: str,
    defaults_path: Path,
) -> Dict[str, Any]:
    defaults = _load_defaults(defaults_path)
    run_id = str(uuid.uuid4())

    mandant_cfg, mandant_info = await _resolve_main_mandant_config()
    report: Dict[str, Any] = {
        "phase": "mandant_update_apply_v1",
        "apply": bool(apply),
        "generated_at_utc": _utc_now(),
        "run_id": run_id,
        "main_mandant": mandant_info,
        "database": None,
        "defaults": defaults,
        "targets": {
            "source_version_target": source_version_target,
            "db_schema_version_target": db_schema_version_target,
            "data_model_version_target": data_model_version_target,
        },
        "state_before": None,
        "state_after": None,
        "actions": [],
        "summary": {
            "db_available": False,
            "state_table_exists": False,
            "history_table_exists": False,
            "state_row_exists_before": False,
            "state_row_exists_after": False,
            "delta_count": 0,
            "applied_writes": 0,
            "apply_status": "blocked",
            "errors": 0,
        },
    }

    if not mandant_cfg:
        report["actions"].append({"status": "error", "message": "main_mandant_not_resolved"})
        report["summary"]["errors"] += 1
        return report

    mandant_guid = str((mandant_info or {}).get("uid") or "")
    if not mandant_guid:
        report["actions"].append({"status": "error", "message": "mandant_guid_missing"})
        report["summary"]["errors"] += 1
        return report

    report["database"] = mandant_cfg.database

    conn = await asyncpg.connect(**mandant_cfg.to_dict())
    try:
        report["summary"]["db_available"] = True
        state_exists = await _table_exists(conn, STATE_TABLE)
        history_exists = await _table_exists(conn, HISTORY_TABLE)
        report["summary"]["state_table_exists"] = state_exists
        report["summary"]["history_table_exists"] = history_exists

        if not state_exists or not history_exists:
            report["actions"].append({"status": "blocked", "message": "basis_tables_missing"})
            report["summary"]["apply_status"] = "blocked"
            return report

        state_before = await _load_state_row(conn, mandant_guid)
        report["state_before"] = state_before
        report["summary"]["state_row_exists_before"] = state_before is not None

        current_source = str((state_before or {}).get("source_version_current") or "")
        current_db = str((state_before or {}).get("db_schema_version_current") or "")
        current_data = str((state_before or {}).get("data_model_version_current") or "")

        action_source = _delta_action("SOURCE_UPDATE", current_source, source_version_target, 1)
        action_db = _delta_action("DATABASE_UPDATE", current_db, db_schema_version_target, 2)
        action_data = _delta_action("DATA_UPDATE", current_data, data_model_version_target, 3)
        report["actions"].extend([action_source, action_db, action_data])

        delta_count = sum(1 for a in [action_source, action_db, action_data] if bool(a.get("changed")))
        report["summary"]["delta_count"] = delta_count

        if not apply:
            report["summary"]["apply_status"] = "dry_run_ready" if delta_count > 0 else "dry_run_no_change"
            report["state_after"] = state_before
            report["summary"]["state_row_exists_after"] = state_before is not None
            return report

        if delta_count == 0:
            report["summary"]["apply_status"] = "no_change"
            report["state_after"] = state_before
            report["summary"]["state_row_exists_after"] = state_before is not None
            return report

        async with conn.transaction():
            state_uid = await _upsert_state(
                conn,
                mandant_guid=mandant_guid,
                existing_uid=(state_before or {}).get("uid"),
                source_version_target=source_version_target,
                db_schema_version_target=db_schema_version_target,
                data_model_version_target=data_model_version_target,
                run_id=run_id,
            )
            report["summary"]["applied_writes"] += 1

            history_payload = {
                "run_id": run_id,
                "mandant_guid": mandant_guid,
                "targets": report.get("targets"),
                "actions": report.get("actions"),
                "state_uid": state_uid,
            }
            await _insert_history(
                conn,
                run_id=run_id,
                mandant_guid=mandant_guid,
                source_version_target=source_version_target,
                db_schema_version_target=db_schema_version_target,
                data_model_version_target=data_model_version_target,
                report_payload=history_payload,
            )
            report["summary"]["applied_writes"] += 1

        state_after = await _load_state_row(conn, mandant_guid)
        report["state_after"] = state_after
        report["summary"]["state_row_exists_after"] = state_after is not None
        report["summary"]["apply_status"] = "applied"
    except Exception as exc:
        report["actions"].append({"status": "error", "message": str(exc)})
        report["summary"]["errors"] += 1
        report["summary"]["apply_status"] = "failed"
    finally:
        await conn.close()

    return report


def _default_output_path() -> Path:
    return BACKEND_DIR / "reports" / "mandant_update_apply_v1.json"


async def _run(args: argparse.Namespace) -> int:
    defaults = _load_defaults(Path(args.defaults))

    source_target = args.source_version_target or str(defaults.get("source_version_target") or "")
    db_target = args.db_schema_version_target or str(defaults.get("db_schema_version_target") or "")
    data_target = args.data_model_version_target or str(defaults.get("data_model_version_target") or "")

    report = await build_report(
        apply=bool(args.apply),
        source_version_target=source_target,
        db_schema_version_target=db_target,
        data_model_version_target=data_target,
        defaults_path=Path(args.defaults),
    )

    s = report.get("summary", {})
    print("\n=== Mandant Update Apply V1 ===")
    print(f"Apply status: {s.get('apply_status')}")
    print(f"Delta count: {s.get('delta_count')}")
    print(f"Applied writes: {s.get('applied_writes')}")
    print(f"State row before/after: {s.get('state_row_exists_before')} -> {s.get('state_row_exists_after')}")
    print(f"Errors: {s.get('errors')}")

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nReport geschrieben: {output_path}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply mandant update version targets")
    parser.add_argument("--defaults", default=str(DEFAULTS_PATH), help="Pfad zu Runtime-Defaults")
    parser.add_argument("--source-version-target", default=None, help="Ziel fuer SOURCE_VERSION")
    parser.add_argument("--db-schema-version-target", default=None, help="Ziel fuer DB_SCHEMA_VERSION")
    parser.add_argument("--data-model-version-target", default=None, help="Ziel fuer DATA_MODEL_VERSION")
    parser.add_argument("--apply", action="store_true", help="Fuehrt Writes auf state/history aus")
    parser.add_argument("--output", default=str(_default_output_path()), help="Pfad fuer JSON-Report")
    args = parser.parse_args()
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())

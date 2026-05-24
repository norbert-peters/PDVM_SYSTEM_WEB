"""
Phase C Punkt 3: Batch-Runner mit Resume fuer STRUCT_VERSION_APPLIED.

Ziel:
1. Tabellenweise und batchweise aktive Datensaetze verarbeiten.
2. Resume je Tabelle ueber Checkpoint-Datei.
3. Optionaler Delta-Rerun ueber --changed-since (wenn Zeitstempelspalte vorhanden).

Usage:
  python backend/tools/phaseC_batch_reconcile_struct_version.py
  python backend/tools/phaseC_batch_reconcile_struct_version.py --apply
  python backend/tools/phaseC_batch_reconcile_struct_version.py --apply --batch-size 300
  python backend/tools/phaseC_batch_reconcile_struct_version.py --changed-since "2026-05-20T00:00:00"
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import asyncpg

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.connection_manager import ConnectionConfig, ConnectionManager
from tools.phaseB_persist_template_modes import (
    STRUCT_META_GROUP,
    STRUCT_VERSION_TARGET,
    SYSTEM_MANDANT_UIDS,
    _resolve_main_mandant_config,
    _table_mode,
)

CHECKPOINT_VERSION = 1
TIMESTAMP_COLUMNS = ["modified_at", "updated_at", "created_at"]
RUNTIME_DEFAULTS_VERSION = 1


def _default_runtime_profile() -> Dict[str, Any]:
    return {
        "version": RUNTIME_DEFAULTS_VERSION,
        "batch_size": 100,
        "run_interval_minutes": 15,
        "delta_rerun_window_hours": 24,
        "max_batches_per_table": 500,
        "abort_max_db_errors": 0,
        "abort_require_full_completion": True,
    }


def _default_runtime_defaults_path() -> Path:
    return BACKEND_DIR / "config" / "phaseC_batch_runtime_defaults_v1.json"


def _load_runtime_defaults(path: Path) -> Dict[str, Any]:
    defaults = _default_runtime_profile()
    if not path.exists():
        return defaults

    try:
        raw = _as_dict(json.loads(path.read_text(encoding="utf-8")))
    except Exception:
        return defaults

    for key in defaults.keys():
        if key in raw:
            defaults[key] = raw.get(key)
    return defaults


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
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


@dataclass
class TableMeta:
    table_name: str
    columns: List[str]

    @property
    def has_uid(self) -> bool:
        return "uid" in self.columns

    @property
    def has_daten(self) -> bool:
        return "daten" in self.columns

    @property
    def has_historisch(self) -> bool:
        return "historisch" in self.columns

    @property
    def timestamp_column(self) -> Optional[str]:
        for col in TIMESTAMP_COLUMNS:
            if col in self.columns:
                return col
        return None


async def _table_exists(conn: asyncpg.Connection, table_name: str) -> bool:
    exists = await conn.fetchval("SELECT to_regclass($1) IS NOT NULL", f"public.{table_name}")
    return bool(exists)


async def _resolve_meta_table(conn: asyncpg.Connection) -> Optional[str]:
    for t in ("sys_systemdaten", "asy_systemdaten", "msy_systemdaten"):
        if await _table_exists(conn, t):
            return t
    return None


async def _get_table_meta(conn: asyncpg.Connection) -> List[TableMeta]:
    rows = await conn.fetch(
        """
        SELECT c.table_name, c.column_name
        FROM information_schema.columns c
        JOIN information_schema.tables t
          ON t.table_schema = c.table_schema
         AND t.table_name = c.table_name
        WHERE c.table_schema = 'public'
          AND t.table_type = 'BASE TABLE'
        ORDER BY c.table_name, c.ordinal_position
        """
    )

    by_table: Dict[str, List[str]] = {}
    for row in rows:
        t = str(row.get("table_name"))
        c = str(row.get("column_name"))
        by_table.setdefault(t, []).append(c)

    return [TableMeta(table_name=t, columns=cols) for t, cols in sorted(by_table.items(), key=lambda kv: kv[0])]


async def _get_table_target_versions(conn: asyncpg.Connection, meta_table: str) -> Dict[str, int]:
    versions: Dict[str, int] = {}
    rows = await conn.fetch(
        f'''
        SELECT name, daten
        FROM "{meta_table}"
        WHERE COALESCE(historisch, 0) = 0
        '''
    )

    for row in rows:
        name = str(row.get("name") or "")
        if not name.startswith("TEMPLATE_META::"):
            continue
        table_name = name.split("::", 1)[1].strip()
        if not table_name:
            continue
        daten = _as_dict(row.get("daten"))
        group = _as_dict(daten.get(STRUCT_META_GROUP))
        version_raw = group.get("STRUCT_VERSION_TARGET", STRUCT_VERSION_TARGET)
        try:
            version = int(version_raw)
        except Exception:
            version = int(STRUCT_VERSION_TARGET)
        versions[table_name] = version

    return versions


def _load_checkpoint(path: Path, apply: bool, batch_size: int, changed_since: Optional[str]) -> Dict[str, Any]:
    if not path.exists():
        return {
            "checkpoint_version": CHECKPOINT_VERSION,
            "run_id": str(uuid.uuid4()),
            "started_at": _utc_now(),
            "finished_at": None,
            "apply": bool(apply),
            "batch_size": int(batch_size),
            "changed_since": changed_since,
            "tables": {},
        }

    data = _as_dict(path.read_text(encoding="utf-8"))
    if data.get("checkpoint_version") != CHECKPOINT_VERSION:
        return {
            "checkpoint_version": CHECKPOINT_VERSION,
            "run_id": str(uuid.uuid4()),
            "started_at": _utc_now(),
            "finished_at": None,
            "apply": bool(apply),
            "batch_size": int(batch_size),
            "changed_since": changed_since,
            "tables": {},
        }

    incompatible = bool(data.get("apply")) != bool(apply)
    incompatible = incompatible or int(data.get("batch_size") or 0) != int(batch_size)
    incompatible = incompatible or (data.get("changed_since") or None) != (changed_since or None)
    if incompatible:
        return {
            "checkpoint_version": CHECKPOINT_VERSION,
            "run_id": str(uuid.uuid4()),
            "started_at": _utc_now(),
            "finished_at": None,
            "apply": bool(apply),
            "batch_size": int(batch_size),
            "changed_since": changed_since,
            "tables": {},
        }

    data["finished_at"] = None
    data.setdefault("tables", {})
    return data


def _save_checkpoint(path: Path, checkpoint: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(checkpoint, ensure_ascii=False, indent=2), encoding="utf-8")


def _table_cp_key(db_label: str, table_name: str) -> str:
    return f"{db_label}.{table_name}"


def _build_batch_query(meta: TableMeta, changed_since: Optional[datetime]) -> Tuple[str, List[Any], Optional[str]]:
    clauses = ["uid::text > $1"]
    args: List[Any] = []
    next_param_index = 2
    ts_col = meta.timestamp_column
    if meta.has_historisch:
        clauses.append("COALESCE(historisch, 0) = 0")
    if changed_since and ts_col:
        clauses.append(f"{ts_col} >= ${next_param_index}::timestamptz")
        args.append(changed_since)
        next_param_index += 1

    sql = f'''
    SELECT uid::text AS uid, name, daten
    FROM "{meta.table_name}"
    WHERE {' AND '.join(clauses)}
    ORDER BY uid::text
    LIMIT ${next_param_index}
    '''
    return sql, args, ts_col


async def _update_row(conn: asyncpg.Connection, table_name: str, uid: str, daten: Dict[str, Any]) -> None:
    await conn.execute(
        f'UPDATE "{table_name}" SET daten = $1::jsonb WHERE uid::text = $2',
        json.dumps(daten, ensure_ascii=False),
        uid,
    )


async def _process_table(
    conn: asyncpg.Connection,
    db_label: str,
    meta: TableMeta,
    target_version: int,
    apply: bool,
    batch_size: int,
    changed_since: Optional[datetime],
    max_batches: Optional[int],
    checkpoint: Dict[str, Any],
    report_table: Dict[str, Any],
    checkpoint_path: Path,
) -> None:
    cp_key = _table_cp_key(db_label, meta.table_name)
    table_cp = _as_dict(checkpoint.get("tables", {}).get(cp_key))
    last_uid = str(table_cp.get("last_uid") or "")
    completed = bool(table_cp.get("completed", False))
    if completed:
        report_table["resumed_completed"] = True
        report_table["resume_last_uid"] = last_uid
        return

    sql, sql_args, ts_col = _build_batch_query(meta, changed_since=changed_since)
    if changed_since and not ts_col:
        report_table["delta_filter_skipped_reason"] = "timestamp_column_missing"

    batches = 0
    while True:
        if max_batches is not None and batches >= max_batches:
            report_table["stopped_by_max_batches"] = True
            break

        query_args: List[Any] = [last_uid]
        query_args.extend(sql_args)
        query_args.append(int(batch_size))
        rows = await conn.fetch(sql, *query_args)
        if not rows:
            completed = True
            break

        batches += 1
        report_table["batches_processed"] += 1

        for row in rows:
            uid = str(row.get("uid") or "")
            last_uid = uid
            if uid in SYSTEM_MANDANT_UIDS:
                report_table["rows_skipped_system_uids"] += 1
                continue

            report_table["rows_scanned"] += 1
            data = _as_dict(row.get("daten"))
            root = _as_dict(data.get("ROOT"))
            if not root:
                report_table["rows_skipped_invalid"] += 1
                continue

            current = root.get("STRUCT_VERSION_APPLIED")
            try:
                current_int = int(current)
            except Exception:
                current_int = None

            if current_int == int(target_version):
                report_table["rows_already_current"] += 1
                continue

            root["STRUCT_VERSION_APPLIED"] = int(target_version)
            data["ROOT"] = root
            report_table["rows_updated"] += 1
            if apply:
                await _update_row(conn, meta.table_name, uid, data)

        checkpoint["tables"][cp_key] = {
            "last_uid": last_uid,
            "completed": False,
            "target_version": int(target_version),
            "updated_at": _utc_now(),
        }
        _save_checkpoint(checkpoint_path, checkpoint)

    checkpoint["tables"][cp_key] = {
        "last_uid": last_uid,
        "completed": completed,
        "target_version": int(target_version),
        "updated_at": _utc_now(),
    }
    _save_checkpoint(checkpoint_path, checkpoint)
    report_table["resume_last_uid"] = last_uid
    report_table["completed"] = completed


async def _process_db(
    db_label: str,
    cfg: ConnectionConfig,
    apply: bool,
    batch_size: int,
    changed_since: Optional[datetime],
    max_batches: Optional[int],
    checkpoint: Dict[str, Any],
    checkpoint_path: Path,
) -> Dict[str, Any]:
    entry: Dict[str, Any] = {
        "db_label": db_label,
        "database": cfg.database,
        "meta_table": None,
        "summary": {
            "tables_total": 0,
            "tables_in_scope": 0,
            "tables_completed": 0,
            "rows_scanned": 0,
            "rows_updated": 0,
            "rows_already_current": 0,
            "rows_skipped_invalid": 0,
            "rows_skipped_system_uids": 0,
            "batches_processed": 0,
        },
        "tables": [],
        "error": None,
    }

    try:
        conn = await asyncpg.connect(**cfg.to_dict())
    except Exception as exc:
        entry["error"] = f"connect_failed: {exc}"
        return entry

    try:
        metas = await _get_table_meta(conn)
        entry["summary"]["tables_total"] = len(metas)

        meta_table = await _resolve_meta_table(conn)
        entry["meta_table"] = meta_table
        if not meta_table:
            entry["error"] = "no_systemdaten_table_found"
            return entry

        target_versions = await _get_table_target_versions(conn, meta_table)

        for tm in metas:
            mode = _table_mode(tm.table_name, tm.has_uid, tm.has_daten, tm.columns)
            if mode not in {"voll_templatefaehig", "teiltemplatefaehig"}:
                continue

            target_version = int(target_versions.get(tm.table_name, STRUCT_VERSION_TARGET))
            table_entry: Dict[str, Any] = {
                "table": tm.table_name,
                "mode": mode,
                "target_version": target_version,
                "timestamp_column": tm.timestamp_column,
                "batches_processed": 0,
                "rows_scanned": 0,
                "rows_updated": 0,
                "rows_already_current": 0,
                "rows_skipped_invalid": 0,
                "rows_skipped_system_uids": 0,
                "resume_last_uid": "",
                "completed": False,
                "resumed_completed": False,
                "stopped_by_max_batches": False,
            }

            entry["summary"]["tables_in_scope"] += 1

            await _process_table(
                conn=conn,
                db_label=db_label,
                meta=tm,
                target_version=target_version,
                apply=apply,
                batch_size=batch_size,
                changed_since=changed_since,
                max_batches=max_batches,
                checkpoint=checkpoint,
                report_table=table_entry,
                checkpoint_path=checkpoint_path,
            )

            if table_entry.get("completed") or table_entry.get("resumed_completed"):
                entry["summary"]["tables_completed"] += 1

            entry["summary"]["rows_scanned"] += int(table_entry.get("rows_scanned", 0))
            entry["summary"]["rows_updated"] += int(table_entry.get("rows_updated", 0))
            entry["summary"]["rows_already_current"] += int(table_entry.get("rows_already_current", 0))
            entry["summary"]["rows_skipped_invalid"] += int(table_entry.get("rows_skipped_invalid", 0))
            entry["summary"]["rows_skipped_system_uids"] += int(table_entry.get("rows_skipped_system_uids", 0))
            entry["summary"]["batches_processed"] += int(table_entry.get("batches_processed", 0))
            entry["tables"].append(table_entry)

    except Exception as exc:
        entry["error"] = f"process_failed: {exc}"
    finally:
        await conn.close()

    return entry


async def build_report(
    apply: bool,
    batch_size: int,
    changed_since: Optional[str],
    max_batches: Optional[int],
    checkpoint_path: Path,
    reset_resume: bool,
    runtime_defaults: Dict[str, Any],
    max_db_errors: int,
    require_full_completion: bool,
) -> Dict[str, Any]:
    system_cfg = await ConnectionManager.get_system_config()
    auth_cfg = await ConnectionManager.get_auth_config()
    mandant_cfg, mandant_info = await _resolve_main_mandant_config()

    targets: List[Tuple[str, ConnectionConfig]] = [("system", system_cfg), ("auth", auth_cfg)]
    if mandant_cfg:
        targets.append(("mandant_main", mandant_cfg))

    if reset_resume and checkpoint_path.exists():
        checkpoint_path.unlink()

    changed_since_dt: Optional[datetime] = None
    if changed_since:
        normalized = changed_since.strip().replace("Z", "+00:00")
        changed_since_dt = datetime.fromisoformat(normalized)

    checkpoint = _load_checkpoint(
        path=checkpoint_path,
        apply=apply,
        batch_size=batch_size,
        changed_since=changed_since,
    )
    _save_checkpoint(checkpoint_path, checkpoint)

    report: Dict[str, Any] = {
        "phase": "phaseC_batch_reconcile_struct_version",
        "apply": bool(apply),
        "batch_size": int(batch_size),
        "changed_since": changed_since,
        "max_batches": max_batches,
        "runtime_defaults": runtime_defaults,
        "abort_criteria": {
            "max_db_errors": int(max_db_errors),
            "require_full_completion": bool(require_full_completion),
        },
        "checkpoint": {
            "path": str(checkpoint_path),
            "run_id": checkpoint.get("run_id"),
            "checkpoint_version": checkpoint.get("checkpoint_version"),
        },
        "main_mandant": mandant_info,
        "databases": [],
        "summary": {
            "db_count": 0,
            "db_errors": 0,
            "tables_total": 0,
            "tables_in_scope": 0,
            "tables_completed": 0,
            "rows_scanned": 0,
            "rows_updated": 0,
            "rows_already_current": 0,
            "rows_skipped_invalid": 0,
            "rows_skipped_system_uids": 0,
            "batches_processed": 0,
        },
    }

    for db_label, cfg in targets:
        entry = await _process_db(
            db_label=db_label,
            cfg=cfg,
            apply=apply,
            batch_size=batch_size,
            changed_since=changed_since_dt,
            max_batches=max_batches,
            checkpoint=checkpoint,
            checkpoint_path=checkpoint_path,
        )
        report["databases"].append(entry)

    report["summary"]["db_count"] = len(report["databases"])
    for db in report["databases"]:
        if db.get("error"):
            report["summary"]["db_errors"] += 1
        s = db.get("summary", {})
        report["summary"]["tables_total"] += int(s.get("tables_total", 0))
        report["summary"]["tables_in_scope"] += int(s.get("tables_in_scope", 0))
        report["summary"]["tables_completed"] += int(s.get("tables_completed", 0))
        report["summary"]["rows_scanned"] += int(s.get("rows_scanned", 0))
        report["summary"]["rows_updated"] += int(s.get("rows_updated", 0))
        report["summary"]["rows_already_current"] += int(s.get("rows_already_current", 0))
        report["summary"]["rows_skipped_invalid"] += int(s.get("rows_skipped_invalid", 0))
        report["summary"]["rows_skipped_system_uids"] += int(s.get("rows_skipped_system_uids", 0))
        report["summary"]["batches_processed"] += int(s.get("batches_processed", 0))

    status = "ok"
    abort_reasons: List[str] = []
    if int(report["summary"].get("db_errors", 0)) > int(max_db_errors):
        status = "failed"
        abort_reasons.append("db_errors_exceeded")
    if require_full_completion and int(report["summary"].get("tables_completed", 0)) < int(
        report["summary"].get("tables_in_scope", 0)
    ):
        status = "failed"
        abort_reasons.append("tables_not_fully_completed")

    report["operational_status"] = {
        "status": status,
        "abort_reasons": abort_reasons,
    }

    checkpoint["finished_at"] = _utc_now()
    _save_checkpoint(checkpoint_path, checkpoint)
    return report


def _default_output_path() -> Path:
    return BACKEND_DIR / "reports" / "phaseC_batch_reconcile_struct_version_report.json"


def _default_checkpoint_path() -> Path:
    return BACKEND_DIR / "reports" / "phaseC_batch_reconcile_struct_version_checkpoint.json"


def _print_summary(report: Dict[str, Any]) -> None:
    s = report.get("summary", {})
    print("\n=== Phase C Punkt 3: Batch Reconcile STRUCT_VERSION_APPLIED ===")
    print(f"DBs: {s.get('db_count', 0)}")
    print(f"DB errors: {s.get('db_errors', 0)}")
    print(
        "Tabellen total/in-scope/completed: "
        f"{s.get('tables_total', 0)}/{s.get('tables_in_scope', 0)}/{s.get('tables_completed', 0)}"
    )
    print(f"Batches processed: {s.get('batches_processed', 0)}")
    print(f"Rows scanned: {s.get('rows_scanned', 0)}")
    print(f"Rows updated: {s.get('rows_updated', 0)}")
    print(f"Rows already current: {s.get('rows_already_current', 0)}")
    print(f"Rows skipped invalid: {s.get('rows_skipped_invalid', 0)}")
    print(f"Rows skipped system_uids: {s.get('rows_skipped_system_uids', 0)}")


async def _run(
    output_path: Path,
    checkpoint_path: Path,
    apply: bool,
    batch_size: int,
    changed_since: Optional[str],
    max_batches: Optional[int],
    reset_resume: bool,
    runtime_defaults: Dict[str, Any],
    max_db_errors: int,
    require_full_completion: bool,
) -> int:
    report = await build_report(
        apply=apply,
        batch_size=batch_size,
        changed_since=changed_since,
        max_batches=max_batches,
        checkpoint_path=checkpoint_path,
        reset_resume=reset_resume,
        runtime_defaults=runtime_defaults,
        max_db_errors=max_db_errors,
        require_full_completion=require_full_completion,
    )
    _print_summary(report)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nReport geschrieben: {output_path}")
    print(f"Checkpoint: {checkpoint_path}")
    if str(report.get("operational_status", {}).get("status")) != "ok":
        print(f"Operational status failed: {report.get('operational_status')}")
        return 3
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase C Punkt 3: batch reconcile STRUCT_VERSION_APPLIED")
    parser.add_argument(
        "--defaults",
        default=str(_default_runtime_defaults_path()),
        help="Pfad zur Runtime-Defaults JSON Datei",
    )
    parser.add_argument("--apply", action="store_true", help="Schreibt Datenbank-Updates")
    parser.add_argument("--batch-size", type=int, default=None, help="Batch-Groesse je Tabelle")
    parser.add_argument("--changed-since", default=None, help="ISO-Timestamp fuer Delta-Rerun")
    parser.add_argument("--max-batches", type=int, default=None, help="Maximale Batch-Anzahl je Tabelle")
    parser.add_argument(
        "--delta-window-hours",
        type=int,
        default=None,
        help="Fenster fuer Delta-Rerun in Stunden (wird bei --changed-since ignoriert)",
    )
    parser.add_argument(
        "--max-db-errors",
        type=int,
        default=None,
        help="Abbruchkriterium: maximal erlaubte DB-Errors",
    )
    parser.add_argument(
        "--allow-partial-completion",
        action="store_true",
        help="Deaktiviert Abbruchkriterium fuer unvollstaendige Tabellenabschluesse",
    )
    parser.add_argument("--reset-resume", action="store_true", help="Vorhandenen Checkpoint verwerfen")
    parser.add_argument("--output", default=str(_default_output_path()), help="Pfad fuer JSON-Report")
    parser.add_argument(
        "--checkpoint",
        default=str(_default_checkpoint_path()),
        help="Pfad fuer Resume-Checkpoint",
    )
    args = parser.parse_args()

    defaults = _load_runtime_defaults(Path(args.defaults))

    batch_size = int(args.batch_size) if args.batch_size is not None else int(defaults.get("batch_size", 100))
    max_batches = (
        int(args.max_batches)
        if args.max_batches is not None
        else int(defaults.get("max_batches_per_table", 500))
    )
    max_db_errors = (
        int(args.max_db_errors)
        if args.max_db_errors is not None
        else int(defaults.get("abort_max_db_errors", 0))
    )
    require_full_completion = bool(defaults.get("abort_require_full_completion", True))
    if args.allow_partial_completion:
        require_full_completion = False

    changed_since = args.changed_since
    if not changed_since:
        delta_window_hours = (
            int(args.delta_window_hours)
            if args.delta_window_hours is not None
            else int(defaults.get("delta_rerun_window_hours", 24))
        )
        if delta_window_hours > 0:
            changed_since = (datetime.utcnow() - timedelta(hours=delta_window_hours)).replace(microsecond=0).isoformat() + "Z"

    if batch_size <= 0:
        raise SystemExit("--batch-size muss > 0 sein")
    if max_batches <= 0:
        raise SystemExit("--max-batches muss > 0 sein")
    if max_db_errors < 0:
        raise SystemExit("--max-db-errors muss >= 0 sein")

    return asyncio.run(
        _run(
            output_path=Path(args.output),
            checkpoint_path=Path(args.checkpoint),
            apply=bool(args.apply),
            batch_size=batch_size,
            changed_since=changed_since,
            max_batches=max_batches,
            reset_resume=bool(args.reset_resume),
            runtime_defaults=defaults,
            max_db_errors=max_db_errors,
            require_full_completion=require_full_completion,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())

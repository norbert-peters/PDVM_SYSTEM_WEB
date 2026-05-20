"""
Phase C: Setzt STRUCT_VERSION_APPLIED auf Satzebene in ROOT.

Ziel:
1. Pro aktivem Datensatz ROOT.STRUCT_VERSION_APPLIED auf den je Tabelle definierten
   STRUCT_VERSION_TARGET-Wert setzen.
2. Zielversion wird aus TEMPLATE_META::<table> in der jeweiligen *systemdaten-Tabelle gelesen.
3. Scope: nur Tabellen mit TEMPLATE_MODE voll_templatefaehig oder teiltemplatefaehig.

Usage:
  python backend/tools/phaseC_apply_struct_version_applied.py
  python backend/tools/phaseC_apply_struct_version_applied.py --apply
  python backend/tools/phaseC_apply_struct_version_applied.py --output backend/reports/phaseC_apply_struct_version_applied_report.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
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


class TableMeta:
    def __init__(self, table_name: str, columns: List[str]) -> None:
        self.table_name = table_name
        self.columns = columns

    @property
    def has_uid(self) -> bool:
        return "uid" in self.columns

    @property
    def has_daten(self) -> bool:
        return "daten" in self.columns

    @property
    def has_name(self) -> bool:
        return "name" in self.columns

    @property
    def has_historisch(self) -> bool:
        return "historisch" in self.columns


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


async def _load_active_rows(conn: asyncpg.Connection, meta: TableMeta) -> List[Dict[str, Any]]:
    where_hist = "WHERE COALESCE(historisch, 0) = 0" if meta.has_historisch else ""
    rows = await conn.fetch(
        f'''
        SELECT uid::text AS uid, name, daten
        FROM "{meta.table_name}"
        {where_hist}
        '''
    )

    out: List[Dict[str, Any]] = []
    for row in rows:
        uid = str(row.get("uid") or "")
        if uid in SYSTEM_MANDANT_UIDS:
            continue
        out.append({"uid": uid, "name": str(row.get("name") or ""), "daten": _as_dict(row.get("daten"))})
    return out


async def _update_row(conn: asyncpg.Connection, table_name: str, uid: str, daten: Dict[str, Any]) -> None:
    await conn.execute(
        f'UPDATE "{table_name}" SET daten = $1::jsonb WHERE uid::text = $2',
        json.dumps(daten, ensure_ascii=False),
        uid,
    )


async def _process_db(db_label: str, cfg: ConnectionConfig, apply: bool) -> Dict[str, Any]:
    entry: Dict[str, Any] = {
        "db_label": db_label,
        "database": cfg.database,
        "meta_table": None,
        "summary": {
            "tables_total": 0,
            "tables_in_scope": 0,
            "rows_scanned": 0,
            "rows_updated": 0,
            "rows_already_current": 0,
            "rows_skipped_invalid": 0,
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
                "rows_scanned": 0,
                "rows_updated": 0,
                "rows_already_current": 0,
                "rows_skipped_invalid": 0,
            }
            entry["summary"]["tables_in_scope"] += 1

            rows = await _load_active_rows(conn, tm)
            for row in rows:
                table_entry["rows_scanned"] += 1
                entry["summary"]["rows_scanned"] += 1

                data = _as_dict(row.get("daten"))
                root = _as_dict(data.get("ROOT"))
                if not root:
                    table_entry["rows_skipped_invalid"] += 1
                    entry["summary"]["rows_skipped_invalid"] += 1
                    continue

                current_version = root.get("STRUCT_VERSION_APPLIED")
                try:
                    current_int = int(current_version)
                except Exception:
                    current_int = None

                if current_int == target_version:
                    table_entry["rows_already_current"] += 1
                    entry["summary"]["rows_already_current"] += 1
                    continue

                root["STRUCT_VERSION_APPLIED"] = target_version
                data["ROOT"] = root

                table_entry["rows_updated"] += 1
                entry["summary"]["rows_updated"] += 1
                if apply:
                    await _update_row(conn, tm.table_name, row["uid"], data)

            entry["tables"].append(table_entry)

    except Exception as exc:
        entry["error"] = f"process_failed: {exc}"
    finally:
        await conn.close()

    return entry


async def build_report(apply: bool) -> Dict[str, Any]:
    system_cfg = await ConnectionManager.get_system_config()
    auth_cfg = await ConnectionManager.get_auth_config()
    mandant_cfg, mandant_info = await _resolve_main_mandant_config()

    targets: List[Tuple[str, ConnectionConfig]] = [("system", system_cfg), ("auth", auth_cfg)]
    if mandant_cfg:
        targets.append(("mandant_main", mandant_cfg))

    report: Dict[str, Any] = {
        "phase": "phaseC_apply_struct_version_applied",
        "apply": bool(apply),
        "main_mandant": mandant_info,
        "databases": [],
        "summary": {
            "db_count": 0,
            "db_errors": 0,
            "tables_total": 0,
            "tables_in_scope": 0,
            "rows_scanned": 0,
            "rows_updated": 0,
            "rows_already_current": 0,
            "rows_skipped_invalid": 0,
        },
    }

    for db_label, cfg in targets:
        entry = await _process_db(db_label, cfg, apply=apply)
        report["databases"].append(entry)

    report["summary"]["db_count"] = len(report["databases"])
    for db in report["databases"]:
        if db.get("error"):
            report["summary"]["db_errors"] += 1
        s = db.get("summary", {})
        report["summary"]["tables_total"] += int(s.get("tables_total", 0))
        report["summary"]["tables_in_scope"] += int(s.get("tables_in_scope", 0))
        report["summary"]["rows_scanned"] += int(s.get("rows_scanned", 0))
        report["summary"]["rows_updated"] += int(s.get("rows_updated", 0))
        report["summary"]["rows_already_current"] += int(s.get("rows_already_current", 0))
        report["summary"]["rows_skipped_invalid"] += int(s.get("rows_skipped_invalid", 0))

    return report


def _default_output_path() -> Path:
    return BACKEND_DIR / "reports" / "phaseC_apply_struct_version_applied_report.json"


def _print_summary(report: Dict[str, Any]) -> None:
    s = report.get("summary", {})
    print("\n=== Phase C Apply STRUCT_VERSION_APPLIED ===")
    print(f"DBs: {s.get('db_count', 0)}")
    print(f"DB errors: {s.get('db_errors', 0)}")
    print(f"Tabellen total/in-scope: {s.get('tables_total', 0)}/{s.get('tables_in_scope', 0)}")
    print(f"Rows scanned: {s.get('rows_scanned', 0)}")
    print(f"Rows updated: {s.get('rows_updated', 0)}")
    print(f"Rows already current: {s.get('rows_already_current', 0)}")
    print(f"Rows skipped invalid: {s.get('rows_skipped_invalid', 0)}")


async def _run(output_path: Path, apply: bool) -> int:
    report = await build_report(apply=apply)
    _print_summary(report)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nReport geschrieben: {output_path}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase C apply STRUCT_VERSION_APPLIED on ROOT")
    parser.add_argument("--apply", action="store_true", help="Schreibt STRUCT_VERSION_APPLIED in Datensaetze")
    parser.add_argument("--output", default=str(_default_output_path()), help="Pfad fuer JSON-Report")
    args = parser.parse_args()
    return asyncio.run(_run(Path(args.output), apply=bool(args.apply)))


if __name__ == "__main__":
    raise SystemExit(main())

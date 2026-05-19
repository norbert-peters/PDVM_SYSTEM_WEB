"""
Phase B Validator: Prüft verbleibende Dropdown-Referenzen auf sys_systemdaten.

Ziel:
- Alle aktiven Datensätze (uid+daten) in system/auth/main_mandant durchsuchen.
- Jede Dropdown-Referenz auf table=sys_systemdaten als Fehler melden.

Usage:
  python backend/tools/phaseB_validate_dropdown_reference_integrity.py
  python backend/tools/phaseB_validate_dropdown_reference_integrity.py --strict
  python backend/tools/phaseB_validate_dropdown_reference_integrity.py --output backend/reports/phaseB_validate_dropdown_reference_integrity.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import asyncpg

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.connection_manager import ConnectionConfig, ConnectionManager

UID_555 = "55555555-5555-5555-5555-555555555555"
UID_666 = "66666666-6666-6666-6666-666666666666"
SYSTEM_MANDANT_UIDS = {UID_555, UID_666, "00000000-0000-0000-0000-000000000000"}


@dataclass
class TableMeta:
    table_name: str
    columns: List[str] = field(default_factory=list)

    @property
    def has_uid(self) -> bool:
        return "uid" in self.columns

    @property
    def has_daten(self) -> bool:
        return "daten" in self.columns

    @property
    def has_historisch(self) -> bool:
        return "historisch" in self.columns


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


def _is_dropdown_ref(path: Tuple[str, ...], obj: Dict[str, Any]) -> bool:
    path_text = ".".join(path).lower()
    if "dropdown" in path_text:
        return True
    if any("dropdown" in str(k).lower() for k in obj.keys()):
        return True
    t = str(obj.get("type") or "").strip().lower()
    return t == "dropdown"


def _scan_obj_for_legacy_dropdown_refs(obj: Any, path: Tuple[str, ...], findings: List[Dict[str, Any]]) -> None:
    if isinstance(obj, dict):
        table_val = str(obj.get("table") or "").strip().lower()
        if table_val == "sys_systemdaten" and _is_dropdown_ref(path, obj):
            findings.append(
                {
                    "path": ".".join(path),
                    "table": table_val,
                    "node_keys": sorted(str(k) for k in obj.keys()),
                }
            )
        for key, value in obj.items():
            _scan_obj_for_legacy_dropdown_refs(value, (*path, str(key)), findings)
    elif isinstance(obj, list):
        for idx, item in enumerate(obj):
            _scan_obj_for_legacy_dropdown_refs(item, (*path, str(idx)), findings)


async def _get_table_meta(conn: asyncpg.Connection) -> Dict[str, TableMeta]:
    rows = await conn.fetch(
        """
        SELECT table_name, column_name
        FROM information_schema.columns
        WHERE table_schema = 'public'
        ORDER BY table_name, ordinal_position
        """
    )
    by_table: Dict[str, List[str]] = {}
    for row in rows:
        t = str(row.get("table_name"))
        c = str(row.get("column_name"))
        by_table.setdefault(t, []).append(c)
    return {t: TableMeta(table_name=t, columns=cols) for t, cols in by_table.items()}


async def _load_active_rows(conn: asyncpg.Connection, meta: TableMeta) -> List[Dict[str, Any]]:
    where_hist = "WHERE COALESCE(historisch, 0) = 0" if meta.has_historisch else ""
    rows = await conn.fetch(
        f'''
        SELECT uid::text AS uid, daten
        FROM "{meta.table_name}"
        {where_hist}
        '''
    )
    out: List[Dict[str, Any]] = []
    for row in rows:
        uid = str(row.get("uid") or "")
        if uid in {UID_555, UID_666}:
            continue
        out.append({"uid": uid, "daten": _as_dict(row.get("daten"))})
    return out


async def _resolve_main_mandant_config() -> Tuple[Optional[ConnectionConfig], Optional[Dict[str, Any]]]:
    auth_cfg = await ConnectionManager.get_auth_config()
    conn = await asyncpg.connect(**auth_cfg.to_dict())
    try:
        source_table: Optional[str] = None
        for table_name in ("asy_mandanten", "sys_mandanten"):
            exists = await conn.fetchval("SELECT to_regclass($1) IS NOT NULL", f"public.{table_name}")
            if exists:
                source_table = table_name
                break

        if not source_table:
            return None, None

        rows = await conn.fetch(
            f'''
            SELECT uid::text AS uid, name, daten
            FROM "{source_table}"
            WHERE COALESCE(historisch, 0) = 0
            '''
        )

        candidates: List[Dict[str, Any]] = []
        for row in rows:
            uid = str(row.get("uid") or "")
            if uid in SYSTEM_MANDANT_UIDS:
                continue

            daten = _as_dict(row.get("daten"))
            mandant = _as_dict(daten.get("MANDANT"))
            host = str(mandant.get("HOST") or auth_cfg.host or "").strip()
            user = str(mandant.get("USER") or auth_cfg.user or "").strip()
            password = str(mandant.get("PASSWORD") or "").strip()
            if not password or password in {"postgres", "Polari$55"}:
                password = str(auth_cfg.password or "")
            database = str(mandant.get("DATABASE") or "").strip()
            port_raw = mandant.get("PORT") or auth_cfg.port
            try:
                port = int(port_raw)
            except Exception:
                continue

            if not (host and user and database):
                continue

            candidates.append(
                {
                    "uid": uid,
                    "name": str(row.get("name") or ""),
                    "database": database,
                    "host": host,
                    "port": port,
                    "user": user,
                    "password": password,
                    "source_table": source_table,
                }
            )

        if not candidates:
            return None, None

        chosen = sorted(candidates, key=lambda x: (x.get("name") or "").lower())[0]
        cfg = ConnectionConfig(
            host=chosen["host"],
            port=int(chosen["port"]),
            user=chosen["user"],
            password=chosen["password"],
            database=chosen["database"],
        )
        return cfg, chosen
    finally:
        await conn.close()


async def _process_db(db_label: str, cfg: ConnectionConfig) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "db_label": db_label,
        "database": cfg.database,
        "tables_scanned": 0,
        "rows_scanned": 0,
        "legacy_ref_count": 0,
        "legacy_refs": [],
        "skipped": False,
        "skip_reason": None,
        "error": None,
    }

    try:
        conn = await asyncpg.connect(**cfg.to_dict())
    except Exception as exc:
        out["error"] = f"connect_failed: {exc}"
        return out

    try:
        metas = await _get_table_meta(conn)
        candidate_tables = [m for m in metas.values() if m.has_uid and m.has_daten]
        out["tables_scanned"] = len(candidate_tables)

        for meta in sorted(candidate_tables, key=lambda m: m.table_name):
            rows = await _load_active_rows(conn, meta)
            out["rows_scanned"] += len(rows)
            for row in rows:
                findings: List[Dict[str, Any]] = []
                _scan_obj_for_legacy_dropdown_refs(
                    row.get("daten") or {},
                    (meta.table_name, str(row.get("uid") or ""), "daten"),
                    findings,
                )
                if findings:
                    out["legacy_ref_count"] += len(findings)
                    out["legacy_refs"].extend(
                        {
                            "table": meta.table_name,
                            "uid": str(row.get("uid") or ""),
                            "path": f.get("path"),
                            "node_keys": f.get("node_keys"),
                        }
                        for f in findings
                    )
    except Exception as exc:
        out["error"] = f"process_failed: {exc}"
    finally:
        await conn.close()

    return out


async def build_report() -> Dict[str, Any]:
    targets: List[Tuple[str, ConnectionConfig]] = []
    targets.append(("system", await ConnectionManager.get_system_config()))
    targets.append(("auth", await ConnectionManager.get_auth_config()))

    main_cfg, main_info = await _resolve_main_mandant_config()
    if main_cfg:
        targets.append(("main_mandant", main_cfg))

    report: Dict[str, Any] = {
        "phase": "phaseB",
        "title": "Validate dropdown reference integrity",
        "main_mandant": main_info,
        "databases": [],
        "summary": {
            "db_count": 0,
            "db_errors": 0,
            "tables_scanned": 0,
            "rows_scanned": 0,
            "legacy_ref_count": 0,
        },
    }

    for db_label, cfg in targets:
        entry = await _process_db(db_label, cfg)
        report["databases"].append(entry)
        report["summary"]["db_count"] += 1
        report["summary"]["tables_scanned"] += int(entry.get("tables_scanned", 0))
        report["summary"]["rows_scanned"] += int(entry.get("rows_scanned", 0))
        report["summary"]["legacy_ref_count"] += int(entry.get("legacy_ref_count", 0))
        if entry.get("error"):
            report["summary"]["db_errors"] += 1

    return report


def _default_output_path() -> Path:
    return BACKEND_DIR / "reports" / "phaseB_validate_dropdown_reference_integrity.json"


def _print_summary(report: Dict[str, Any]) -> None:
    s = report.get("summary", {})
    print("\n=== Phase B Validate Dropdown Reference Integrity ===")
    print(f"DB count: {s.get('db_count', 0)}")
    print(f"DB errors: {s.get('db_errors', 0)}")
    print(f"Tables scanned: {s.get('tables_scanned', 0)}")
    print(f"Rows scanned: {s.get('rows_scanned', 0)}")
    print(f"Legacy dropdown refs: {s.get('legacy_ref_count', 0)}")


async def _run(args: argparse.Namespace) -> int:
    report = await build_report()
    _print_summary(report)

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nReport geschrieben: {output}")

    if bool(args.strict) and int(report.get("summary", {}).get("legacy_ref_count", 0)) > 0:
        print("\nStrict mode: Legacy dropdown references gefunden -> Exit 2")
        return 2

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase B validate dropdown reference integrity")
    parser.add_argument("--strict", action="store_true", help="Exit!=0 wenn Legacy-Referenzen gefunden werden")
    parser.add_argument("--output", default=str(_default_output_path()), help="Pfad für JSON-Report")
    args = parser.parse_args()
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())

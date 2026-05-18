"""
Phase 8: Entfernt deprecated Control-Tabellen und erstellt Referenz-Report.

Ziel:
- System-DB: sys_control_dict_audit entfernen
- Mandanten-DBs: msy_control_dict_audit und msy_control_dict entfernen

Vor dem Drop werden potentielle DB-Objekt-Referenzen (Views/Functions/Trigger/Rules)
pro Datenbank ermittelt und im Report ausgegeben.

Usage:
  python backend/tools/phase8_remove_deprecated_control_tables.py
  python backend/tools/phase8_remove_deprecated_control_tables.py --apply
  python backend/tools/phase8_remove_deprecated_control_tables.py --output backend/reports/phase8_remove_deprecated_control_tables_report.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import asyncpg

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.connection_manager import ConnectionConfig, ConnectionManager


@dataclass(frozen=True)
class TableTarget:
    table_name: str
    db_scope: str  # "system" | "mandant"


SYSTEM_TARGETS: Sequence[TableTarget] = (
    TableTarget(table_name="sys_control_dict_audit", db_scope="system"),
)

MANDANT_TARGETS: Sequence[TableTarget] = (
    TableTarget(table_name="msy_control_dict_audit", db_scope="mandant"),
    TableTarget(table_name="msy_control_dict", db_scope="mandant"),
)


async def _fetchrow_dict(conn: asyncpg.Connection, query: str, *args: Any) -> Optional[Dict[str, Any]]:
    row = await conn.fetchrow(query, *args)
    return dict(row) if row else None


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


async def _table_exists(conn: asyncpg.Connection, table_name: str) -> bool:
    value = await conn.fetchval("SELECT to_regclass($1) IS NOT NULL", f"public.{table_name}")
    return bool(value)


async def _count_rows(conn: asyncpg.Connection, table_name: str) -> Optional[int]:
    if not await _table_exists(conn, table_name):
        return None
    value = await conn.fetchval(f'SELECT COUNT(*) FROM "{table_name}"')
    return int(value or 0)


async def _collect_references(conn: asyncpg.Connection, table_name: str) -> Dict[str, List[Dict[str, Any]]]:
    pattern = f"%{table_name}%"

    views = await conn.fetch(
        """
        SELECT schemaname AS schema_name, viewname AS object_name, definition
        FROM pg_views
        WHERE schemaname = 'public' AND definition ILIKE $1
        ORDER BY viewname
        """,
        pattern,
    )

    matviews = await conn.fetch(
        """
        SELECT schemaname AS schema_name, matviewname AS object_name, definition
        FROM pg_matviews
        WHERE schemaname = 'public' AND definition ILIKE $1
        ORDER BY matviewname
        """,
        pattern,
    )

    routines = await conn.fetch(
        """
        SELECT
          n.nspname AS schema_name,
          p.proname AS object_name,
          pg_get_functiondef(p.oid) AS definition
        FROM pg_proc p
        JOIN pg_namespace n ON n.oid = p.pronamespace
                WHERE n.nspname = 'public'
                    AND p.prokind IN ('f', 'p', 'w')
                    AND pg_get_functiondef(p.oid) ILIKE $1
        ORDER BY p.proname
        """,
        pattern,
    )

    triggers = await conn.fetch(
        """
        SELECT
          n.nspname AS schema_name,
          c.relname AS table_name,
          t.tgname AS object_name,
          pg_get_triggerdef(t.oid, true) AS definition
        FROM pg_trigger t
        JOIN pg_class c ON c.oid = t.tgrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE NOT t.tgisinternal
          AND n.nspname = 'public'
          AND pg_get_triggerdef(t.oid, true) ILIKE $1
        ORDER BY c.relname, t.tgname
        """,
        pattern,
    )

    rules = await conn.fetch(
        """
        SELECT
          schemaname AS schema_name,
          tablename AS table_name,
          rulename AS object_name,
          definition
        FROM pg_rules
        WHERE schemaname = 'public' AND definition ILIKE $1
        ORDER BY tablename, rulename
        """,
        pattern,
    )

    def _rows_to_dict(rows: Sequence[asyncpg.Record]) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            if "definition" in item and isinstance(item["definition"], str):
                item["definition_preview"] = item["definition"][:240]
                item.pop("definition", None)
            out.append(item)
        return out

    return {
        "views": _rows_to_dict(views),
        "materialized_views": _rows_to_dict(matviews),
        "functions": _rows_to_dict(routines),
        "triggers": _rows_to_dict(triggers),
        "rules": _rows_to_dict(rules),
    }


def _reference_count(refs: Dict[str, List[Dict[str, Any]]]) -> int:
    return sum(len(v) for v in refs.values())


async def _drop_table(conn: asyncpg.Connection, table_name: str) -> Dict[str, Any]:
    exists = await _table_exists(conn, table_name)
    if not exists:
        return {"table": table_name, "dropped": False, "reason": "not_exists"}

    await conn.execute(f'DROP TABLE IF EXISTS "{table_name}"')
    return {"table": table_name, "dropped": True}


def _extract_connection_config_from_mandant_row(
    daten: Dict[str, Any],
    *,
    auth_defaults: Optional[ConnectionConfig],
) -> Optional[ConnectionConfig]:
    mandant = daten.get("MANDANT") if isinstance(daten, dict) else {}
    if not isinstance(mandant, dict):
        return None

    host = str(mandant.get("HOST") or (auth_defaults.host if auth_defaults else "") or "").strip()
    user = str(mandant.get("USER") or (auth_defaults.user if auth_defaults else "") or "").strip()
    password = str(mandant.get("PASSWORD") or "")
    if (not password or password in {"postgres", "Polari$55"}) and auth_defaults:
        password = str(auth_defaults.password or "")

    database = str(mandant.get("DATABASE") or "").strip()
    if database in {"-eingeben-", "-nicht konfiguriert-"}:
        return None
    port_raw = mandant.get("PORT") or (auth_defaults.port if auth_defaults else None)

    if not (host and user and database and port_raw):
        return None

    try:
        port = int(port_raw)
    except Exception:
        return None

    return ConnectionConfig(host=host, port=port, user=user, password=password, database=database)


async def _load_mandant_configs_from_conn(
    conn: asyncpg.Connection,
    *,
    auth_defaults: Optional[ConnectionConfig],
) -> List[ConnectionConfig]:
    table_candidates = []
    if await _table_exists(conn, "asy_mandanten"):
        table_candidates.append("asy_mandanten")
    if await _table_exists(conn, "sys_mandanten"):
        table_candidates.append("sys_mandanten")

    seen = set()
    configs: List[ConnectionConfig] = []

    for table_name in table_candidates:
        rows = await conn.fetch(
            f'''
            SELECT uid::text AS uid, daten
            FROM "{table_name}"
            WHERE COALESCE(historisch, 0) = 0
            '''
        )
        for row in rows:
            cfg = _extract_connection_config_from_mandant_row(
                _as_dict(row.get("daten")),
                auth_defaults=auth_defaults,
            )
            if cfg is None:
                continue
            key = (cfg.host.lower(), int(cfg.port), cfg.user.lower(), cfg.database.lower())
            if key in seen:
                continue
            seen.add(key)
            configs.append(cfg)

    return configs


async def _load_mandant_configs() -> List[ConnectionConfig]:
    configs: List[ConnectionConfig] = []

    # Primärquelle: Auth-DB
    auth_cfg = await ConnectionManager.get_auth_config()
    conn = await asyncpg.connect(**auth_cfg.to_dict())
    try:
        configs = await _load_mandant_configs_from_conn(conn, auth_defaults=auth_cfg)
    finally:
        await conn.close()

    if configs:
        return configs

    # Fallback: System-DB (für Bestände, in denen Mandanten noch dort liegen)
    system_cfg = await ConnectionManager.get_system_config()
    conn = await asyncpg.connect(**system_cfg.to_dict())
    try:
        return await _load_mandant_configs_from_conn(conn, auth_defaults=auth_cfg)
    finally:
        await conn.close()


async def _analyze_db(
    cfg: ConnectionConfig,
    db_kind: str,
    targets: Sequence[TableTarget],
    apply: bool,
) -> Dict[str, Any]:
    entry: Dict[str, Any] = {
        "db_kind": db_kind,
        "database": cfg.database,
        "host": cfg.host,
        "port": cfg.port,
        "tables": [],
        "drop_actions": [],
        "error": None,
    }

    try:
        conn = await asyncpg.connect(**cfg.to_dict())
    except Exception as exc:
        entry["error"] = f"connect_failed: {exc}"
        return entry

    try:
        for target in targets:
            table = target.table_name
            exists = await _table_exists(conn, table)
            row_count = await _count_rows(conn, table)
            refs = await _collect_references(conn, table)

            table_entry = {
                "table": table,
                "exists": exists,
                "row_count": row_count,
                "reference_count": _reference_count(refs),
                "references": refs,
            }
            entry["tables"].append(table_entry)

            if apply and exists:
                if table_entry["reference_count"] > 0:
                    entry["drop_actions"].append(
                        {
                            "table": table,
                            "dropped": False,
                            "reason": "blocked_by_references",
                        }
                    )
                else:
                    result = await _drop_table(conn, table)
                    entry["drop_actions"].append(result)
    except Exception as exc:
        entry["error"] = f"analyze_failed: {exc}"
        entry["error_traceback"] = traceback.format_exc()
    finally:
        await conn.close()

    return entry


async def build_report(apply: bool) -> Dict[str, Any]:
    system_cfg = await ConnectionManager.get_system_config()
    mandant_cfgs = await _load_mandant_configs()

    report: Dict[str, Any] = {
        "phase": "phase8_remove_deprecated_control_tables",
        "apply": bool(apply),
        "summary": {
            "system_dbs": 0,
            "mandant_dbs": 0,
            "tables_existing": 0,
            "tables_dropped": 0,
            "tables_blocked_by_references": 0,
            "errors": 0,
        },
        "system": [],
        "mandant": [],
    }

    system_entry = await _analyze_db(system_cfg, "system", SYSTEM_TARGETS, apply)
    report["system"].append(system_entry)

    for cfg in mandant_cfgs:
        entry = await _analyze_db(cfg, "mandant", MANDANT_TARGETS, apply)
        report["mandant"].append(entry)

    report["summary"]["system_dbs"] = len(report["system"])
    report["summary"]["mandant_dbs"] = len(report["mandant"])

    for section in ("system", "mandant"):
        for db_entry in report[section]:
            if db_entry.get("error"):
                report["summary"]["errors"] += 1

            for table_entry in db_entry.get("tables", []):
                if table_entry.get("exists"):
                    report["summary"]["tables_existing"] += 1

            for action in db_entry.get("drop_actions", []):
                if action.get("dropped"):
                    report["summary"]["tables_dropped"] += 1
                elif action.get("reason") == "blocked_by_references":
                    report["summary"]["tables_blocked_by_references"] += 1

    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 8 deprecated control table cleanup")
    parser.add_argument("--apply", action="store_true", help="Fuehrt DROP TABLE fuer referenzfreie Ziele aus")
    parser.add_argument(
        "--output",
        default=str(BACKEND_DIR / "reports" / "phase8_remove_deprecated_control_tables_report.json"),
        help="Pfad fuer JSON-Report",
    )
    args = parser.parse_args()

    report = asyncio.run(build_report(apply=bool(args.apply)))

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(report.get("summary", {}), ensure_ascii=False, indent=2))
    print(f"\nReport geschrieben: {out_path}")


if __name__ == "__main__":
    main()

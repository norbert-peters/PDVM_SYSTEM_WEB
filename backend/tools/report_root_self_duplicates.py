"""
Pruef-Report fuer verbleibende ROOT-Duplikate ohne SELF-Praefix.

Geprueft wird je Tabelle (mit JSONB-Spalte daten):
- equal:   Legacy-Feld und SELF-Feld vorhanden und gleich
- diff:    Legacy-Feld und SELF-Feld vorhanden, aber unterschiedlich
- legacy_only: Legacy-Feld vorhanden, SELF-Feld fehlt

DB-Umfang:
- auth DB
- default system DB (pdvm_system)
- mandant/system DBs aus sys_mandanten

Ausschlussregel fuer Mandanten-DB Traversal:
- Aus den Reservesaetzen 000/555/666 in sys_mandanten wird
  MANDANT.DATABASE gelesen; diese DB-Namen werden vom Traversal ausgeschlossen.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

import asyncpg

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.connection_manager import ConnectionConfig, ConnectionManager
from app.core.database import DatabasePool

logger = logging.getLogger("report_root_self_duplicates")
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

RESERVED_BASE_UIDS = {
    "00000000-0000-0000-0000-000000000000",
    "55555555-5555-5555-5555-555555555555",
    "66666666-6666-6666-6666-666666666666",
}

KEY_PAIRS = [
    ("GUID", "SELF_GUID"),
    ("LINK_UID", "SELF_LINK_UID"),
    ("CREATED_AT", "SELF_CREATED_AT"),
    ("MODIFIED_AT", "SELF_MODIFIED_AT"),
    ("GILT_BIS", "SELF_GILT_BIS"),
]


def _cfg_key(cfg: ConnectionConfig) -> Tuple[str, int, str, str, str]:
    return (cfg.host, int(cfg.port), cfg.user, cfg.password, cfg.database)


def _quote_ident(identifier: str) -> str:
    return '"' + str(identifier).replace('"', '""') + '"'


async def _load_mandanten_records(auth_pool: asyncpg.Pool) -> tuple[List[Dict[str, Any]], Set[str]]:
    async with auth_pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT uid::text AS uid, daten, historisch
            FROM sys_mandanten
            ORDER BY created_at ASC NULLS LAST
            """
        )

    parsed_rows: List[Dict[str, Any]] = []
    for row in rows:
        daten = row["daten"]
        if isinstance(daten, str):
            try:
                daten = json.loads(daten)
            except Exception:
                daten = None
        if not isinstance(daten, dict):
            continue

        parsed_rows.append(
            {
                "uid": str(row["uid"]),
                "daten": daten,
                "historisch": int(row["historisch"] or 0),
            }
        )

    excluded_db_names: Set[str] = set()
    for rec in parsed_rows:
        if rec["uid"] not in RESERVED_BASE_UIDS:
            continue
        mandant_info = rec.get("daten", {}).get("MANDANT")
        if isinstance(mandant_info, dict):
            db_name = str(mandant_info.get("DATABASE") or "").strip()
            if db_name:
                excluded_db_names.add(db_name.lower())

    return parsed_rows, excluded_db_names


def _build_configs_from_mandant_record(record: Dict[str, Any]) -> Tuple[ConnectionConfig, ConnectionConfig]:
    daten = record.get("daten") or {}
    mandant_info = daten.get("MANDANT") if isinstance(daten, dict) else {}
    if not isinstance(mandant_info, dict):
        raise ValueError("MANDANT Konfiguration fehlt")

    host = mandant_info.get("HOST")
    port = mandant_info.get("PORT")
    user = mandant_info.get("USER")
    password = mandant_info.get("PASSWORD")
    database = mandant_info.get("DATABASE")
    system_db = mandant_info.get("SYSTEM_DB") or mandant_info.get("SYSTEM_DATABASE") or "pdvm_system"

    missing = [
        key
        for key, value in {
            "HOST": host,
            "PORT": port,
            "USER": user,
            "PASSWORD": password,
            "DATABASE": database,
        }.items()
        if not value
    ]
    if missing:
        raise ValueError(f"Fehlende MANDANT-Werte: {', '.join(missing)}")

    system_cfg = ConnectionConfig(
        host=str(host),
        port=int(port),
        user=str(user),
        password=str(password),
        database=str(system_db),
    )
    mandant_cfg = ConnectionConfig(
        host=str(host),
        port=int(port),
        user=str(user),
        password=str(password),
        database=str(database),
    )
    return system_cfg, mandant_cfg


async def _get_public_tables(conn: asyncpg.Connection) -> List[str]:
    rows = await conn.fetch(
        """
        SELECT tablename
        FROM pg_tables
        WHERE schemaname = 'public'
        ORDER BY tablename
        """
    )
    return [str(r["tablename"]) for r in rows]


async def _has_jsonb_daten(conn: asyncpg.Connection, table_name: str) -> bool:
    data_type = await conn.fetchval(
        """
        SELECT data_type
        FROM information_schema.columns
        WHERE table_name = $1 AND column_name = 'daten'
        """,
        table_name,
    )
    return str(data_type or "").lower() == "jsonb"


async def _report_for_table(conn: asyncpg.Connection, table_name: str) -> Dict[str, int]:
    q_table = _quote_ident(table_name)
    result: Dict[str, int] = {}

    for legacy_key, self_key in KEY_PAIRS:
        eq = await conn.fetchval(
            f"""
            SELECT COUNT(*)::bigint
            FROM {q_table}
            WHERE jsonb_typeof(COALESCE(daten, '{{}}'::jsonb)) = 'object'
              AND jsonb_typeof(COALESCE(daten, '{{}}'::jsonb)->'ROOT') = 'object'
              AND (daten->'ROOT' ? '{legacy_key}')
              AND (daten->'ROOT' ? '{self_key}')
              AND (daten->'ROOT'->>'{legacy_key}') = (daten->'ROOT'->>'{self_key}')
            """
        )
        diff = await conn.fetchval(
            f"""
            SELECT COUNT(*)::bigint
            FROM {q_table}
            WHERE jsonb_typeof(COALESCE(daten, '{{}}'::jsonb)) = 'object'
              AND jsonb_typeof(COALESCE(daten, '{{}}'::jsonb)->'ROOT') = 'object'
              AND (daten->'ROOT' ? '{legacy_key}')
              AND (daten->'ROOT' ? '{self_key}')
              AND (daten->'ROOT'->>'{legacy_key}') <> (daten->'ROOT'->>'{self_key}')
            """
        )
        legacy_only = await conn.fetchval(
            f"""
            SELECT COUNT(*)::bigint
            FROM {q_table}
            WHERE jsonb_typeof(COALESCE(daten, '{{}}'::jsonb)) = 'object'
              AND jsonb_typeof(COALESCE(daten, '{{}}'::jsonb)->'ROOT') = 'object'
              AND (daten->'ROOT' ? '{legacy_key}')
              AND NOT (daten->'ROOT' ? '{self_key}')
            """
        )

        result[f"{legacy_key}__equal"] = int(eq or 0)
        result[f"{legacy_key}__diff"] = int(diff or 0)
        result[f"{legacy_key}__legacy_only"] = int(legacy_only or 0)

    result["equal_total"] = sum(v for k, v in result.items() if k.endswith("__equal"))
    result["diff_total"] = sum(v for k, v in result.items() if k.endswith("__diff"))
    result["legacy_only_total"] = sum(v for k, v in result.items() if k.endswith("__legacy_only"))
    return result


async def _report_for_db(db_label: str, cfg: ConnectionConfig) -> Dict[str, Any]:
    pool = await asyncpg.create_pool(cfg.to_url(), min_size=1, max_size=2)
    try:
        summary: Dict[str, Any] = {
            "db": db_label,
            "host": cfg.host,
            "database": cfg.database,
            "tables": {},
            "totals": {
                "equal_total": 0,
                "diff_total": 0,
                "legacy_only_total": 0,
            },
        }

        async with pool.acquire() as conn:
            tables = await _get_public_tables(conn)
            for table_name in tables:
                if not await _has_jsonb_daten(conn, table_name):
                    continue
                table_stats = await _report_for_table(conn, table_name)
                summary["tables"][table_name] = table_stats
                summary["totals"]["equal_total"] += table_stats["equal_total"]
                summary["totals"]["diff_total"] += table_stats["diff_total"]
                summary["totals"]["legacy_only_total"] += table_stats["legacy_only_total"]

        return summary
    finally:
        await pool.close()


def _print_summary(summary: Dict[str, Any]) -> None:
    db_id = f"{summary['db']} ({summary['database']}@{summary['host']})"
    totals = summary["totals"]
    logger.info(
        "📊 %s -> equal=%s, diff=%s, legacy_only=%s",
        db_id,
        totals["equal_total"],
        totals["diff_total"],
        totals["legacy_only_total"],
    )

    interesting_tables = []
    for table_name, stats in summary["tables"].items():
        if stats["equal_total"] or stats["diff_total"] or stats["legacy_only_total"]:
            interesting_tables.append((table_name, stats))

    if not interesting_tables:
        logger.info("   ✅ Keine verbleibenden Legacy-Duplikate gefunden")
        return

    for table_name, stats in interesting_tables:
        logger.info(
            "   - %s: equal=%s, diff=%s, legacy_only=%s",
            table_name,
            stats["equal_total"],
            stats["diff_total"],
            stats["legacy_only_total"],
        )


async def main() -> None:
    await DatabasePool.create_pool()

    try:
        reports: List[Dict[str, Any]] = []
        reported_db_keys: Set[Tuple[str, int, str, str, str]] = set()

        auth_cfg = await ConnectionManager.get_auth_config()
        auth_key = _cfg_key(auth_cfg)
        if auth_key not in reported_db_keys:
            reported_db_keys.add(auth_key)
            reports.append(await _report_for_db("auth", auth_cfg))

        try:
            default_system_cfg = await ConnectionManager.get_system_config("pdvm_system")
            default_system_key = _cfg_key(default_system_cfg)
            if default_system_key not in reported_db_keys:
                reported_db_keys.add(default_system_key)
                reports.append(await _report_for_db("system-default", default_system_cfg))
        except Exception as e:
            logger.warning("⚠️ Default system report fehlgeschlagen: %s", e)

        mandanten, excluded_db_names = await _load_mandanten_records(DatabasePool._pool_auth)
        logger.info("📋 Mandanten-Einträge gesamt: %s", len(mandanten))
        if excluded_db_names:
            logger.info("⛔ Ausgeschlossene DB-Namen aus 000/555/666: %s", sorted(excluded_db_names))

        seen_system: Set[Tuple[str, int, str, str, str]] = set()
        seen_mandant: Set[Tuple[str, int, str, str, str]] = set()

        for rec in mandanten:
            uid = rec.get("uid")
            historisch = int(rec.get("historisch") or 0)
            if historisch == 1:
                continue

            try:
                system_cfg, mandant_cfg = _build_configs_from_mandant_record(rec)
            except Exception as cfg_err:
                logger.warning("⚠️ Mandant %s: Config ungültig: %s", uid, cfg_err)
                continue

            mandant_db_norm = str(mandant_cfg.database).strip().lower()
            if mandant_db_norm in excluded_db_names:
                logger.info("⏭️ Mandant %s: DB '%s' ausgeschlossen", uid, mandant_cfg.database)
                continue

            sys_key = _cfg_key(system_cfg)
            if sys_key not in seen_system:
                seen_system.add(sys_key)
                if sys_key not in reported_db_keys:
                    reported_db_keys.add(sys_key)
                    reports.append(await _report_for_db(f"system-from-{uid}", system_cfg))

            man_key = _cfg_key(mandant_cfg)
            if man_key not in seen_mandant:
                seen_mandant.add(man_key)
                if man_key not in reported_db_keys:
                    reported_db_keys.add(man_key)
                    reports.append(await _report_for_db(f"mandant-{uid}", mandant_cfg))

        logger.info("=" * 90)
        logger.info("ROOT-DUPLIKAT-REPORT")
        logger.info("=" * 90)

        grand = {"equal_total": 0, "diff_total": 0, "legacy_only_total": 0}
        for rep in reports:
            _print_summary(rep)
            grand["equal_total"] += rep["totals"]["equal_total"]
            grand["diff_total"] += rep["totals"]["diff_total"]
            grand["legacy_only_total"] += rep["totals"]["legacy_only_total"]

        logger.info("=" * 90)
        logger.info(
            "GESAMT -> equal=%s, diff=%s, legacy_only=%s",
            grand["equal_total"],
            grand["diff_total"],
            grand["legacy_only_total"],
        )

    finally:
        await DatabasePool.close_pool()


if __name__ == "__main__":
    asyncio.run(main())

"""
Lokales Einmal-Skript zur Voll-Normalisierung aller bekannten Datenbanken.

Enthaltene Schritte je Datenbank:
1. link_uid-Spalte in allen Tabellen mit uid ergänzen (falls fehlend)
2. link_uid = uid für bestehende Datensätze setzen (falls NULL)
3. ROOT.SELF_* Felder in daten JSONB synchronisieren

Datenquellen:
- auth DB: aus config.DATABASE_URL_AUTH
- system/mandant DBs: aus auth.sys_mandanten.MANDANT Konfiguration

Hinweis:
- Dieses Skript ist für die lokale Umgebung gedacht.
- Ubuntu-Server bleibt unberührt, solange das Skript nur lokal ausgeführt wird.
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
from app.core.mandant_db_maintenance import (
    run_auth_maintenance,
    run_mandant_maintenance,
    run_system_maintenance,
)

logger = logging.getLogger("normalize_all_databases_local")
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

RESERVED_BASE_UIDS = {
    "00000000-0000-0000-0000-000000000000",
    "55555555-5555-5555-5555-555555555555",
    "66666666-6666-6666-6666-666666666666",
}


def _cfg_key(cfg: ConnectionConfig) -> Tuple[str, int, str, str, str]:
    return (cfg.host, int(cfg.port), cfg.user, cfg.password, cfg.database)


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
        uid_text = str(row["uid"])
        parsed_rows.append(
            {
                "uid": uid_text,
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


async def _run_pool_maintenance(
    *,
    cfg: ConnectionConfig,
    mode: str,
    mandant_uid: str = "",
    mandant_daten: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    pool = await asyncpg.create_pool(cfg.to_url(), min_size=1, max_size=2)
    try:
        if mode == "auth":
            return await run_auth_maintenance(pool)
        if mode == "system":
            return await run_system_maintenance(pool)
        if mode == "mandant":
            return await run_mandant_maintenance(pool, mandant_uid, mandant_daten or {})
        raise ValueError(f"Unbekannter Mode: {mode}")
    finally:
        await pool.close()


async def main() -> None:
    await DatabasePool.create_pool()

    try:
        auth_cfg = await ConnectionManager.get_auth_config()
        logger.info("🔧 Normalisierung AUTH DB startet: %s", auth_cfg.database)
        auth_stats = await _run_pool_maintenance(cfg=auth_cfg, mode="auth")
        logger.info("✅ AUTH fertig: %s", auth_stats)

        try:
            default_system_cfg = await ConnectionManager.get_system_config("pdvm_system")
            logger.info(
                "🔧 Standard-System-DB Normalisierung: db=%s@%s:%s",
                default_system_cfg.database,
                default_system_cfg.host,
                default_system_cfg.port,
            )
            default_system_stats = await _run_pool_maintenance(cfg=default_system_cfg, mode="system")
            logger.info("✅ Standard-System-DB %s: %s", default_system_cfg.database, default_system_stats)
        except Exception as default_sys_err:
            logger.warning("⚠️ Standard-System-DB fehlgeschlagen (pdvm_system): %s", default_sys_err)

        mandanten, excluded_db_names = await _load_mandanten_records(DatabasePool._pool_auth)
        logger.info("📋 Gefundene Mandanten: %s", len(mandanten))
        if excluded_db_names:
            logger.info("⛔ Ausgeschlossene DB-Namen aus 000/555/666: %s", sorted(excluded_db_names))

        seen_system: Set[Tuple[str, int, str, str, str]] = set()
        seen_mandant: Set[Tuple[str, int, str, str, str]] = set()

        for rec in mandanten:
            uid = rec.get("uid")
            historisch = int(rec.get("historisch") or 0)
            if historisch == 1:
                logger.info("⏭️ Mandant %s historisch=1, übersprungen", uid)
                continue

            try:
                system_cfg, mandant_cfg = _build_configs_from_mandant_record(rec)
            except Exception as cfg_err:
                logger.warning("⚠️ Mandant %s: Config ungültig: %s", uid, cfg_err)
                continue

            mandant_db_norm = str(mandant_cfg.database).strip().lower()
            if mandant_db_norm in excluded_db_names:
                logger.info(
                    "⏭️ Mandant %s: DB '%s' durch 000/555/666 ausgeschlossen",
                    uid,
                    mandant_cfg.database,
                )
                continue

            sys_key = _cfg_key(system_cfg)
            if sys_key not in seen_system:
                seen_system.add(sys_key)
                logger.info(
                    "🔧 System-DB Normalisierung: mandant=%s db=%s@%s:%s",
                    uid,
                    system_cfg.database,
                    system_cfg.host,
                    system_cfg.port,
                )
                try:
                    sys_stats = await _run_pool_maintenance(cfg=system_cfg, mode="system")
                    logger.info("✅ System-DB %s: %s", system_cfg.database, sys_stats)
                except Exception as sys_err:
                    logger.warning("⚠️ System-DB fehlgeschlagen (%s): %s", system_cfg.database, sys_err)

            man_key = _cfg_key(mandant_cfg)
            if man_key not in seen_mandant:
                seen_mandant.add(man_key)
                logger.info(
                    "🔧 Mandanten-DB Normalisierung: mandant=%s db=%s@%s:%s",
                    uid,
                    mandant_cfg.database,
                    mandant_cfg.host,
                    mandant_cfg.port,
                )
                try:
                    man_stats = await _run_pool_maintenance(
                        cfg=mandant_cfg,
                        mode="mandant",
                        mandant_uid=str(uid),
                        mandant_daten=rec.get("daten") or {},
                    )
                    logger.info("✅ Mandanten-DB %s: %s", mandant_cfg.database, man_stats)
                except Exception as man_err:
                    logger.warning("⚠️ Mandanten-DB fehlgeschlagen (%s): %s", mandant_cfg.database, man_err)

        logger.info("🎉 Voll-Normalisierung abgeschlossen")

    finally:
        await DatabasePool.close_pool()


if __name__ == "__main__":
    asyncio.run(main())

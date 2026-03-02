"""Create control dictionary tables for all mandants.

Creates sys_contr_dict_man and sys_contr_dict_man_audit in each mandant DB.
"""
from __future__ import annotations

import asyncio
import logging

import asyncpg

from app.core.connection_manager import ConnectionManager
from app.core.pdvm_datenbank import PdvmDatabase

logger = logging.getLogger(__name__)


async def main() -> int:
    auth_cfg = await ConnectionManager.get_auth_config()
    conn = await asyncpg.connect(**auth_cfg.to_dict())
    try:
        rows = await conn.fetch("SELECT uid, name, daten FROM sys_mandanten")
    finally:
        await conn.close()

    if not rows:
        logger.info("Keine Mandanten gefunden")
        return 0

    for row in rows:
        mandant_id = str(row["uid"])
        mandant_name = row.get("name") or mandant_id
        mandant_record = {"uid": row["uid"], "name": mandant_name, "daten": row["daten"]}

        try:
            _, mandant_cfg = await ConnectionManager.get_mandant_config(mandant_id)
            mandant_db_url = mandant_cfg.to_url()
            await PdvmDatabase.ensure_mandant_tables(mandant_id, mandant_db_url, mandant_record)
            logger.info("✅ Mandant %s aktualisiert", mandant_name)
        except Exception as exc:
            logger.error("❌ Mandant %s fehlgeschlagen: %s", mandant_name, exc)

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

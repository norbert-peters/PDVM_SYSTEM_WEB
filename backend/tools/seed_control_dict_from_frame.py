"""Seed sys_control_dict from an existing sys_framedaten record.

Default frame UID is the requested sys_framedaten record.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import uuid

import asyncpg

from app.core.connection_manager import ConnectionManager
from app.core.pdvm_datenbank import PdvmDatabase

logger = logging.getLogger(__name__)

DEFAULT_FRAME_UID = "4413571e-6bf6-4f42-b81a-bc898db4880c"


def _pick_field_name(field_data: dict) -> str:
    return str(field_data.get("name") or field_data.get("feld") or "").strip()


async def main() -> int:
    parser = argparse.ArgumentParser(description="Seed sys_control_dict from sys_framedaten")
    parser.add_argument("--frame-uid", default=DEFAULT_FRAME_UID, help="UID of sys_framedaten record")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing controls")
    args = parser.parse_args()

    frame_uid = uuid.UUID(args.frame_uid)

    system_cfg = await ConnectionManager.get_system_config("pdvm_system")
    pool = await asyncpg.create_pool(system_cfg.to_url())

    try:
        frame_db = PdvmDatabase("sys_framedaten", system_pool=pool, mandant_pool=None)
        dict_db = PdvmDatabase("sys_control_dict", system_pool=pool, mandant_pool=None)

        frame_row = await frame_db.get_by_uid(frame_uid)
        if not frame_row:
            logger.error("Frame nicht gefunden: %s", frame_uid)
            return 1

        daten = frame_row.get("daten") or {}
        fields = daten.get("FIELDS") or daten.get("fields") or {}
        if not isinstance(fields, dict):
            logger.error("FIELDS nicht gefunden oder ungueltig")
            return 1

        created = 0
        skipped = 0
        updated = 0

        for key, field_data in fields.items():
            if not PdvmDatabase._is_guid_key(key):
                continue
            if not isinstance(field_data, dict):
                continue

            field_uid = uuid.UUID(str(key))
            existing = await dict_db.get_by_uid(field_uid)
            field_name = _pick_field_name(field_data)

            if existing and not args.overwrite:
                skipped += 1
                continue

            if existing:
                await dict_db.update(uid=field_uid, daten=field_data, name=field_name)
                updated += 1
            else:
                await dict_db.create(uid=field_uid, daten=field_data, name=field_name)
                created += 1

        logger.info("Fertig. erstellt=%s aktualisiert=%s uebersprungen=%s", created, updated, skipped)
        return 0
    finally:
        await pool.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

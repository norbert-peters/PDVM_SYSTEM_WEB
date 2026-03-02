"""Convert sys_framedaten FIELDS to dictionary controls (sys_control_dict).

- Creates or updates controls in sys_control_dict.
- Rewrites frame FIELDS to keep only overrides (tab/display_order/read_only).
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import uuid
from copy import deepcopy

import asyncpg

from app.core.connection_manager import ConnectionManager
from app.core.pdvm_datenbank import PdvmDatabase

logger = logging.getLogger(__name__)

DEFAULT_FRAME_UID = "4413571e-6bf6-4f42-b81a-bc898db4880c"
OVERRIDE_KEYS = {"tab", "display_order", "read_only", "label", "tooltip"}


def _pick_field_name(field_data: dict) -> str:
    return str(field_data.get("name") or field_data.get("feld") or "").strip()


def _build_overrides(field_data: dict) -> dict:
    overrides = {}
    for key in OVERRIDE_KEYS:
        if key in field_data:
            overrides[key] = field_data.get(key)
    return overrides


def _strip_overrides(field_data: dict) -> dict:
    base = deepcopy(field_data)
    for key in OVERRIDE_KEYS:
        base.pop(key, None)
    return base


async def main() -> int:
    parser = argparse.ArgumentParser(description="Convert frame fields to control dictionary")
    parser.add_argument("--frame-uid", default=DEFAULT_FRAME_UID, help="UID of sys_framedaten record")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing controls")
    args = parser.parse_args()

    frame_uid = uuid.UUID(args.frame_uid)

    system_cfg = await ConnectionManager.get_system_config("pdvm_system")
    system_pool = await asyncpg.create_pool(system_cfg.to_url(), min_size=1, max_size=2)

    try:
        frame_db = PdvmDatabase("sys_framedaten", system_pool=system_pool, mandant_pool=None)
        dict_db = PdvmDatabase("sys_control_dict", system_pool=system_pool, mandant_pool=None)

        frame_row = await frame_db.get_by_uid(frame_uid)
        if not frame_row:
            logger.error("Frame nicht gefunden: %s", frame_uid)
            return 1

        daten = frame_row.get("daten") or {}
        fields = daten.get("FIELDS") or daten.get("fields") or {}
        if not isinstance(fields, dict):
            logger.error("FIELDS nicht gefunden oder ungueltig")
            return 1

        new_fields = {}
        created = 0
        updated = 0
        skipped = 0

        for key, field_data in fields.items():
            if not PdvmDatabase._is_guid_key(key):
                new_fields[key] = field_data
                continue
            if not isinstance(field_data, dict):
                new_fields[key] = field_data
                continue

            field_uid = uuid.UUID(str(key))
            existing = await dict_db.get_by_uid(field_uid)
            field_name = _pick_field_name(field_data)

            base_data = _strip_overrides(field_data)
            overrides = _build_overrides(field_data)

            if existing and not args.overwrite:
                skipped += 1
            elif existing:
                await dict_db.update(uid=field_uid, daten=base_data, name=field_name)
                updated += 1
            else:
                await dict_db.create(uid=field_uid, daten=base_data, name=field_name)
                created += 1

            new_fields[key] = overrides

        daten["FIELDS"] = new_fields
        await frame_db.update(uid=frame_uid, daten=daten, name=frame_row.get("name"))

        logger.info("Fertig. erstellt=%s aktualisiert=%s uebersprungen=%s", created, updated, skipped)
        return 0
    finally:
        await system_pool.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

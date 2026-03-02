"""Migration: Template+Delta Storage für sys_control_dict und sys_framedaten.

Ziel:
- sys_control_dict: nur Overrides ggü. 555-Template speichern
- sys_framedaten.FIELDS: nur lokale Overrides ggü. referenziertem Control speichern

Usage:
  python backend/tools/migrate_template_delta_storage_v1.py --dry-run
  python backend/tools/migrate_template_delta_storage_v1.py --apply
"""
from __future__ import annotations

import argparse
import asyncio
import copy
import json
import uuid
from dataclasses import dataclass
from typing import Any, Dict, Optional

import asyncpg

from app.core.connection_manager import ConnectionManager
from app.core.pdvm_datenbank import PdvmDatabase

TEMPLATE_555 = uuid.UUID("55555555-5555-5555-5555-555555555555")
TEMPLATE_666 = uuid.UUID("66666666-6666-6666-6666-666666666666")


@dataclass
class Stats:
    control_scanned: int = 0
    control_changed: int = 0
    frame_scanned: int = 0
    frame_changed: int = 0


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _is_guid(value: Any) -> bool:
    try:
        uuid.UUID(str(value))
        return True
    except Exception:
        return False


def _overrides(effective: Dict[str, Any], defaults: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for key, value in effective.items():
        if key not in defaults or defaults.get(key) != value:
            out[key] = value
    return out


async def _load_555_defaults(pool: asyncpg.Pool, modul_type: str) -> Dict[str, Any]:
    modul_norm = str(modul_type or "").strip().lower()
    if not modul_norm:
        return {}

    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT daten FROM sys_control_dict WHERE uid = $1", TEMPLATE_555)
    if not row:
        return {}

    data = row["daten"]
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except Exception:
            data = {}
    if not isinstance(data, dict):
        return {}

    defaults: Dict[str, Any] = {}
    templates = data.get("TEMPLATES")
    if isinstance(templates, dict):
        ctrl_tpl = templates.get("CONTROL")
        if isinstance(ctrl_tpl, dict):
            defaults.update(copy.deepcopy(ctrl_tpl))

    modul_map = data.get("MODUL")
    if isinstance(modul_map, dict):
        ci_map = {str(k).strip().lower(): k for k in modul_map.keys()}
        real_key = ci_map.get(modul_norm)
        if real_key is not None and isinstance(modul_map.get(real_key), dict):
            defaults.update(copy.deepcopy(modul_map[real_key]))

    defaults["modul_type"] = modul_norm
    return defaults


async def _migrate_control_dict(pool: asyncpg.Pool, *, apply_changes: bool, stats: Stats) -> None:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT uid, name, daten
            FROM sys_control_dict
            WHERE historisch = 0
            ORDER BY created_at ASC
            """
        )

    for row in rows:
        uid = row["uid"]
        if uid in {TEMPLATE_555, TEMPLATE_666}:
            continue

        stats.control_scanned += 1

        daten = row["daten"]
        if isinstance(daten, str):
            try:
                daten = json.loads(daten)
            except Exception:
                daten = {}
        daten = _as_dict(daten)

        modul_type = str(daten.get("modul_type") or "").strip().lower()
        if not modul_type:
            continue

        defaults = await _load_555_defaults(pool, modul_type)
        if not defaults:
            continue

        compact = _overrides(daten, defaults)
        compact["modul_type"] = modul_type

        if compact == daten:
            continue

        stats.control_changed += 1
        if apply_changes:
            async with pool.acquire() as conn:
                await conn.execute(
                    """
                    UPDATE sys_control_dict
                    SET daten = $1, modified_at = NOW()
                    WHERE uid = $2
                    """,
                    json.dumps(compact),
                    uid,
                )


async def _resolve_control_cached(
    guid_str: str,
    *,
    system_pool: asyncpg.Pool,
    cache: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    if guid_str in cache:
        return cache[guid_str]

    row = await PdvmDatabase.load_control_definition(
        uuid.UUID(guid_str),
        system_pool=system_pool,
        mandant_pool=None,
    )
    data = _as_dict((row or {}).get("daten"))
    cache[guid_str] = data
    return data


async def _migrate_framedaten(pool: asyncpg.Pool, *, apply_changes: bool, stats: Stats) -> None:
    frame_db = PdvmDatabase("sys_framedaten", system_pool=pool, mandant_pool=None)
    rows = await frame_db.list_all()
    cache: Dict[str, Dict[str, Any]] = {}

    for row in rows:
        stats.frame_scanned += 1
        daten = _as_dict(row.get("daten"))
        fields = _as_dict(daten.get("FIELDS"))
        if not fields:
            continue

        changed = False
        normalized_fields: Dict[str, Any] = {}

        for key, value in fields.items():
            item = _as_dict(value)
            dict_ref = item.get("dict_ref")
            base_guid = str(dict_ref if dict_ref else key)

            if _is_guid(base_guid):
                base_data = await _resolve_control_cached(base_guid, system_pool=pool, cache=cache)
                if base_data:
                    overrides = _overrides(item, base_data)
                    if dict_ref:
                        overrides["dict_ref"] = str(dict_ref)
                    normalized_fields[key] = overrides
                    if overrides != item:
                        changed = True
                    continue

            normalized_fields[key] = item

        if not changed:
            continue

        stats.frame_changed += 1
        if apply_changes:
            out = dict(daten)
            out["FIELDS"] = normalized_fields
            await frame_db.update(
                uid=row["uid"],
                daten=out,
                name=row.get("name"),
                historisch=row.get("historisch"),
            )


async def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate template+delta storage for controls and frames")
    parser.add_argument("--dry-run", action="store_true", help="Nur analysieren, keine Updates")
    parser.add_argument("--apply", action="store_true", help="Updates schreiben")
    args = parser.parse_args()

    apply_changes = bool(args.apply)
    if not apply_changes and not args.dry_run:
        args.dry_run = True

    system_cfg = await ConnectionManager.get_system_config("pdvm_system")
    pool = await asyncpg.create_pool(system_cfg.to_url(), min_size=1, max_size=3)

    try:
        stats = Stats()
        await _migrate_control_dict(pool, apply_changes=apply_changes, stats=stats)
        await _migrate_framedaten(pool, apply_changes=apply_changes, stats=stats)

        mode = "APPLY" if apply_changes else "DRY-RUN"
        print(f"\n=== TEMPLATE-DELTA MIGRATION ({mode}) ===")
        print(f"sys_control_dict: scanned={stats.control_scanned}, changed={stats.control_changed}")
        print(f"sys_framedaten : scanned={stats.frame_scanned}, changed={stats.frame_changed}")
        return 0
    finally:
        await pool.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

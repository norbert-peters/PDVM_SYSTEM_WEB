import asyncio
import json
import re
import uuid
from typing import Any, Dict, Tuple

import asyncpg

from app.core.database import get_database_url

TEMPLATE_UID = "55555555-5555-5555-5555-555555555555"
GUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$", re.IGNORECASE)


def is_guid(value: str) -> bool:
    return bool(GUID_RE.match(value or ""))


def normalize_columns(columns: Dict[str, Any]) -> Tuple[Dict[str, Any], bool]:
    if not isinstance(columns, dict):
        return {}, True

    updated: Dict[str, Any] = {}
    changed = False
    fallback_index = 1

    for key, raw_cfg in columns.items():
        if key == TEMPLATE_UID:
            updated[key] = dict(raw_cfg) if isinstance(raw_cfg, dict) else {}
            continue

        cfg = dict(raw_cfg) if isinstance(raw_cfg, dict) else {}
        label = str(cfg.get("label") or cfg.get("name") or "").strip()
        canon_key = str(cfg.get("key") or "").strip()

        if is_guid(key):
            if not canon_key:
                canon_key = label
            if not label:
                label = canon_key
            if not canon_key:
                canon_key = f"COLUMN_{fallback_index}"
                label = label or canon_key
                fallback_index += 1
            cfg["key"] = canon_key
            cfg["label"] = label
            updated[key] = cfg
            if cfg != raw_cfg:
                changed = True
            continue

        if not canon_key:
            canon_key = str(key).strip()
        if not label:
            label = canon_key

        new_uid = str(uuid.uuid4())
        cfg["key"] = canon_key
        cfg["label"] = label
        updated[new_uid] = cfg
        changed = True

    return updated, changed


async def migrate_table(db_name: str, table_name: str) -> int:
    url = get_database_url(db_name)
    conn = await asyncpg.connect(url)
    updated_count = 0
    try:
        rows = await conn.fetch(f"SELECT uid, daten FROM {table_name}")
        for row in rows:
            daten = row.get("daten") or {}
            if not isinstance(daten, dict):
                continue
            config = daten.get("CONFIG") if isinstance(daten.get("CONFIG"), dict) else {}
            columns = config.get("COLUMNS") if isinstance(config.get("COLUMNS"), dict) else {}
            normalized, changed = normalize_columns(columns)
            if not changed:
                continue
            config = dict(config)
            config["COLUMNS"] = normalized
            daten = dict(daten)
            daten["CONFIG"] = config
            await conn.execute(
                f"UPDATE {table_name} SET daten=$1::jsonb, modified_at=NOW() WHERE uid=$2::uuid",
                json.dumps(daten),
                row["uid"],
            )
            updated_count += 1
    finally:
        await conn.close()
    return updated_count


async def main() -> None:
    total = 0
    total += await migrate_table("system", "sys_ext_table")
    total += await migrate_table("mandant", "sys_ext_table_man")
    total += await migrate_table("pdvm_standard", "sys_ext_table_man")
    print(f"Updated rows: {total}")


if __name__ == "__main__":
    asyncio.run(main())

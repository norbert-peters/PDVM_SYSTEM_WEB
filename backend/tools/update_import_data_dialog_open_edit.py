"""Set OPEN_EDIT=double_click for import_data dialogs."""
from __future__ import annotations

import asyncio
import json
from typing import Any, Dict

import asyncpg

from app.core.connection_manager import ConnectionManager


async def main() -> None:
    cfg = await ConnectionManager.get_system_config("pdvm_system")
    db_url = cfg.to_url()
    conn = await asyncpg.connect(db_url)
    try:
        rows = await conn.fetch(
            """
            SELECT uid, daten
            FROM sys_dialogdaten
            WHERE daten->'ROOT'->>'EDIT_TYPE' = 'import_data'
            """
        )
        for row in rows:
            daten = row["daten"]
            if isinstance(daten, str):
                daten = json.loads(daten)
            if not isinstance(daten, dict):
                continue
            root = daten.get("ROOT") if isinstance(daten.get("ROOT"), dict) else {}
            root = dict(root)
            root["OPEN_EDIT"] = "double_click"
            daten = dict(daten)
            daten["ROOT"] = root
            await conn.execute(
                "UPDATE sys_dialogdaten SET daten=$1::jsonb WHERE uid=$2::uuid",
                json.dumps(daten),
                row["uid"],
            )
        print(f"✅ Updated {len(rows)} import_data dialogs to OPEN_EDIT=double_click")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())

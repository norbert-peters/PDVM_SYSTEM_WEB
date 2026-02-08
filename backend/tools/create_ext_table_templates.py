import asyncio
import json
from typing import Dict

import asyncpg

from app.core.database import get_database_url

TEMPLATE_UID = "55555555-5555-5555-5555-555555555555"


def build_template_dataset() -> Dict[str, object]:
    return {
        "ROOT": {
            "DATASET_KEY": "template",
            "NAME": "EXT_TABLE_TEMPLATE",
            "EDIT_TYPE": "import_data",
            "MATCH_KEYS": [],
            "CONFLICT_POLICY": "field_priority",
            "CONFLICT_RULES": {},
            "ALLOW_ROW_DELETE": True,
            "ALLOW_OVERWRITE": True,
            "ALLOW_INSERT_NEW": True,
        },
        "CONFIG": {
            "COLUMNS": {},
            "NORMALIZE": {},
            "ROW_UID_MODE": "new_guid",
            "KEY_MERGE_PRIORITY": [],
        },
        "DATAS": {},
    }


async def ensure_template(db_name: str, table_name: str) -> None:
    url = get_database_url(db_name)
    conn = await asyncpg.connect(url)
    try:
        daten = build_template_dataset()
        await conn.execute(
            f"""
            INSERT INTO {table_name} (uid, daten, name, created_at, modified_at)
            VALUES ($1::uuid, $2::jsonb, $3, NOW(), NOW())
            ON CONFLICT (uid) DO NOTHING
            """,
            TEMPLATE_UID,
            json.dumps(daten),
            "TEMPLATE",
        )
    finally:
        await conn.close()


async def main() -> None:
    await ensure_template("system", "sys_ext_table")
    await ensure_template("mandant", "sys_ext_table_man")
    await ensure_template("pdvm_standard", "sys_ext_table_man")
    print("Template records ensured.")


if __name__ == "__main__":
    asyncio.run(main())

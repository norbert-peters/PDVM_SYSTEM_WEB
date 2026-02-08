import asyncio
from pathlib import Path

import asyncpg

ROOT = Path(r"C:/Users/norbe/OneDrive/Dokumente/PDVM_SYSTEM_WEB")
ADMIN_URL = "postgresql://postgres:Polari$55@localhost:5432/postgres"

DB_SCHEMAS = {
    "pdvm_system": ROOT / "database" / "schema_pdvm_system.sql",
    "auth": ROOT / "database" / "schema_auth.sql",
    "mandant": ROOT / "database" / "schema_mandant.sql",
    "pdvm_standard": ROOT / "database" / "schema_mandant.sql",
}


async def ensure_databases() -> None:
    conn = await asyncpg.connect(ADMIN_URL)
    try:
        for db_name in DB_SCHEMAS:
            exists = await conn.fetchval("SELECT 1 FROM pg_database WHERE datname=$1", db_name)
            if not exists:
                await conn.execute(f'CREATE DATABASE "{db_name}"')
    finally:
        await conn.close()


async def apply_schemas() -> None:
    for db_name, schema_path in DB_SCHEMAS.items():
        db_url = ADMIN_URL.rsplit("/", 1)[0] + "/" + db_name
        sql = schema_path.read_text(encoding="utf-8")
        conn = await asyncpg.connect(db_url)
        try:
            await conn.execute(sql)
        finally:
            await conn.close()


async def main() -> None:
    await ensure_databases()
    await apply_schemas()
    print("Database setup completed.")


if __name__ == "__main__":
    asyncio.run(main())

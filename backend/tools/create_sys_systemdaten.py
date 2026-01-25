import asyncio
import os
import re
from pathlib import Path

import asyncpg


def load_env_var(path: Path, key: str) -> str | None:
    if not path.exists():
        return None
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or line.strip().startswith("#"):
            continue
        if line.startswith(key + "="):
            return line.split("=", 1)[1].strip()
    return None


def to_system_db_url(auth_url: str) -> str:
    # replace trailing db name with pdvm_system
    return re.sub(r"/[^/?]+$", "/pdvm_system", auth_url)


CREATE_FUNC_SQL = """
CREATE OR REPLACE FUNCTION create_pdvm_table(table_name TEXT)
RETURNS void AS $$
BEGIN
    EXECUTE format('
        CREATE TABLE IF NOT EXISTS %I (
            uid UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            daten JSONB NOT NULL,
            name TEXT,
            historisch INTEGER DEFAULT 0,
            source_hash TEXT,
            sec_id UUID,
            gilt_bis TEXT DEFAULT ''9999365.00000'',
            created_at TIMESTAMP DEFAULT NOW(),
            modified_at TIMESTAMP DEFAULT NOW(),
            daten_backup JSONB
        );
        
        CREATE INDEX IF NOT EXISTS idx_%I_sec_id ON %I(sec_id);
        CREATE INDEX IF NOT EXISTS idx_%I_historisch ON %I(historisch);
        CREATE INDEX IF NOT EXISTS idx_%I_name ON %I(name);
        CREATE INDEX IF NOT EXISTS idx_%I_modified_at ON %I(modified_at);
        CREATE INDEX IF NOT EXISTS idx_%I_daten ON %I USING GIN(daten);
    ', table_name, table_name, table_name, table_name, table_name, table_name, table_name, table_name, table_name, table_name, table_name);
END;
$$ LANGUAGE plpgsql;
"""


async def main() -> None:
    env_path = Path(__file__).resolve().parents[1] / ".env"
    auth_url = load_env_var(env_path, "DATABASE_URL_AUTH")
    if not auth_url:
        raise RuntimeError("DATABASE_URL_AUTH nicht gefunden in .env")

    system_url = to_system_db_url(auth_url)
    conn = await asyncpg.connect(system_url)
    try:
        await conn.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp";')
        await conn.execute(CREATE_FUNC_SQL)
        await conn.execute("SELECT create_pdvm_table('sys_systemdaten');")
        print("✅ sys_systemdaten wurde in pdvm_system erstellt (oder existierte bereits).")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())

import argparse
import asyncio
import sys
from pathlib import Path

import asyncpg

# Allow running this script from repo root (adds `backend/` to sys.path)
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.database import get_database_url


async def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect Postgres table columns")
    parser.add_argument("db", help="auth|system|mandant")
    parser.add_argument("table")
    args = parser.parse_args()

    url = get_database_url(args.db)
    conn = await asyncpg.connect(url)
    try:
        rows = await conn.fetch(
            """
            SELECT column_name, data_type, udt_name
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = $1
            ORDER BY ordinal_position
            """,
            args.table,
        )
        print(f"db={args.db} table={args.table} cols={len(rows)}")
        for r in rows:
            print(f"- {r['column_name']}: {r['data_type']} ({r['udt_name']})")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())

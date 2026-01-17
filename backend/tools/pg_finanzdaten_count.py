import asyncio
from pathlib import Path
import sys

import asyncpg

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.database import get_database_url


async def main() -> None:
    url = get_database_url("mandant")
    conn = await asyncpg.connect(url)
    try:
        count = await conn.fetchval("SELECT COUNT(*) FROM finanzdaten")
        print(f"finanzdaten_count={count}")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())

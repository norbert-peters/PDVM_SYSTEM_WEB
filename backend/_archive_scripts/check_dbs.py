import asyncio
import asyncpg

async def test():
    # Verbinde zu postgres DB
    conn = await asyncpg.connect(
        database='postgres',
        host='localhost',
        port=5432,
        user='postgres',
        password='Postgres_2024!'
    )
    
    # Liste Datenbanken
    dbs = await conn.fetch("SELECT datname FROM pg_database WHERE datname LIKE '%test%' OR datname = 'mandant'")
    print("Gefundene Datenbanken:")
    for db in dbs:
        print(f"  - {db['datname']}")
    
    await conn.close()

asyncio.run(test())

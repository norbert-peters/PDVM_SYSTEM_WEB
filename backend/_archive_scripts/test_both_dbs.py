"""
Minimal test - nur zur mandant DB verbinden
"""
import asyncio
import asyncpg

async def test():
    print("Test 1: Verbindung zu 'mandant' (funktioniert)...")
    try:
        conn = await asyncpg.connect(
            host="localhost",
            port=5432,
            user="postgres",
            password="Polari@55",
            database="mandant",
            timeout=5
        )
        tables = await conn.fetch("SELECT tablename FROM pg_tables WHERE schemaname='public' LIMIT 5")
        print(f"✅ Verbindung OK, {len(tables)} Tabellen gefunden:")
        for t in tables:
            print(f"   - {t['tablename']}")
        await conn.close()
    except Exception as e:
        print(f"❌ Fehler: {type(e).__name__}: {e}")
    
    print("\nTest 2: Verbindung zu 'ganz_neu1' (failiert)...")
    try:
        conn = await asyncpg.connect(
            host="localhost",
            port=5432,
            user="postgres",
            password="Polari@55",
            database="ganz_neu1",
            timeout=5
        )
        tables = await conn.fetch("SELECT tablename FROM pg_tables WHERE schemaname='public'")
        print(f"✅ Verbindung OK, {len(tables)} Tabellen:")
        for t in tables:
            print(f"   - {t['tablename']}")
        await conn.close()
    except Exception as e:
        print(f"❌ Fehler: {type(e).__name__}: {e}")

asyncio.run(test())

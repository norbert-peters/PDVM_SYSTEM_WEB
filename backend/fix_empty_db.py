"""
Legt Init-Tabelle in leeren Datenbanken an
Verwendung: python fix_empty_db.py
"""
import asyncio
import asyncpg

async def fix_empty_db():
    # Verbinde zu filiale_test_2
    conn = await asyncpg.connect(
        'postgresql://postgres:Polari$55@localhost:5432/filiale_test_2'
    )
    
    try:
        # Lege Init-Tabelle an
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS _db_init (
                uid UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                created_at TIMESTAMP DEFAULT NOW(),
                info TEXT DEFAULT 'Database initialization marker'
            )
        """)
        print("✅ Init-Tabelle '_db_init' angelegt")
        
        # Prüfe ob Tabelle existiert
        tables = await conn.fetch("""
            SELECT tablename FROM pg_tables 
            WHERE schemaname = 'public'
        """)
        print(f"📋 Tabellen in filiale_test_2: {[t['tablename'] for t in tables]}")
        
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(fix_empty_db())

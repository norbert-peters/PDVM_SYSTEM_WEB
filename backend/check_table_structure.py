"""
Prüft Spalten-Struktur von sys_framedaten
"""
import asyncio
import asyncpg

DB_URL = "postgresql://postgres:Polari$55@localhost:5432/pdvm_system"

async def check_table_structure():
    """Prüft Spalten von sys_framedaten"""
    conn = await asyncpg.connect(DB_URL)
    
    try:
        print("=" * 80)
        print("🔍 sys_framedaten Struktur")
        print("=" * 80)
        
        cols = await conn.fetch("""
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = 'sys_framedaten'
            ORDER BY ordinal_position
        """)
        
        print(f"\n📋 Spalten: {len(cols)}")
        for col in cols:
            print(f"   {col['column_name']:20s} {col['data_type']:20s} NULL: {col['is_nullable']}")
        
        # Beispiel-Datensatz
        print("\n" + "=" * 80)
        print("📄 Beispiel-Datensatz")
        print("=" * 80)
        
        row = await conn.fetchrow("""
            SELECT *
            FROM public.sys_framedaten
            LIMIT 1
        """)
        
        if row:
            for key, value in row.items():
                print(f"   {key:20s}: {value}")
        
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(check_table_structure())

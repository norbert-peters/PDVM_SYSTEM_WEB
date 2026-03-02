"""
Prüft verfügbare Schemas und Tabellen
"""
import asyncio
import asyncpg

DB_URL = "postgresql://postgres:Polari$55@localhost:5432/pdvm_system"

async def check_schemas():
    """Prüft Schemas und Tabellen"""
    conn = await asyncpg.connect(DB_URL)
    
    try:
        print("=" * 80)
        print("🔍 Schema & Tabellen Analyse")
        print("=" * 80)
        
        # Alle Schemas
        schemas = await conn.fetch("""
            SELECT schema_name 
            FROM information_schema.schemata
            WHERE schema_name NOT IN ('pg_catalog', 'information_schema')
            ORDER BY schema_name
        """)
        
        print(f"\n📦 Verfügbare Schemas: {len(schemas)}")
        for row in schemas:
            print(f"   - {row['schema_name']}")
        
        # Tabellen mit 'frame' oder 'control' im Namen suchen
        print("\n" + "=" * 80)
        print("🔍 Tabellen mit 'frame' oder 'control' oder 'sys_'")
        print("=" * 80)
        
        tables = await conn.fetch("""
            SELECT table_schema, table_name
            FROM information_schema.tables
            WHERE table_type = 'BASE TABLE'
              AND table_schema NOT IN ('pg_catalog', 'information_schema')
              AND (
                  table_name ILIKE '%frame%' 
                  OR table_name ILIKE '%control%'
                  OR table_name ILIKE 'sys_%'
              )
            ORDER BY table_schema, table_name
        """)
        
        if tables:
            for row in tables:
                print(f"\n📋 {row['table_schema']}.{row['table_name']}")
        else:
            print("\n❌ Keine passenden Tabellen gefunden")
            
            # Alle Tabellen anzeigen
            print("\n" + "=" * 80)
            print("📦 Alle Tabellen in der Datenbank:")
            print("=" * 80)
            
            all_tables = await conn.fetch("""
                SELECT table_schema, table_name
                FROM information_schema.tables
                WHERE table_type = 'BASE TABLE'
                  AND table_schema NOT IN ('pg_catalog', 'information_schema')
                ORDER BY table_schema, table_name
            """)
            
            for row in all_tables:
                print(f"   - {row['table_schema']}.{row['table_name']}")
        
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(check_schemas())

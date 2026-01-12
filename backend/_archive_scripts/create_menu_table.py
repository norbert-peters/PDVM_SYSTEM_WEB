"""
Erstellt die sys_menudaten Tabelle
"""
import asyncio
import asyncpg

DATABASE_URL = "postgresql://postgres:Polari$55@localhost:5432/pdvm_system"

async def create_menu_table():
    """Erstellt sys_menudaten Tabelle"""
    
    print("🔧 Erstelle sys_menudaten Tabelle...")
    
    conn = await asyncpg.connect(DATABASE_URL)
    
    try:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS sys_menudaten (
                uid UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                name TEXT NOT NULL,
                daten JSONB NOT NULL,
                historisch INT DEFAULT 0,
                source_hash TEXT,
                sec_id UUID,
                gilt_bis TIMESTAMP,
                created_at TIMESTAMP DEFAULT NOW(),
                modified_at TIMESTAMP DEFAULT NOW(),
                daten_backup JSONB
            )
        """)
        
        print("✅ Tabelle sys_menudaten erstellt!")
        
        # Prüfen
        result = await conn.fetchval("""
            SELECT COUNT(*) FROM sys_menudaten
        """)
        
        print(f"📊 Anzahl Einträge: {result}")
        
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(create_menu_table())

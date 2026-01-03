#!/usr/bin/env python3
"""
Erstellt Session-Tabellen in Mandanten-Datenbank

sys_anwendungsdaten: User-spezifische Anwendungsdaten (Filter, Suchen, etc.)
sys_systemsteuerung: User-spezifische Systemsteuerung (Stichtag, Properties, etc.)
"""
import asyncio
import asyncpg

async def create_session_tables():
    """Erstellt die beiden Session-Tabellen in allen Mandanten-Datenbanken"""
    
    # Für jede Mandanten-DB (aktuell nur mandant)
    databases = [
        ("mandant", "postgresql://postgres:Polari$55@localhost:5432/mandant")
    ]
    
    for db_name, db_url in databases:
        print(f"\n🔧 Erstelle Session-Tabellen in {db_name}...")
        
        conn = await asyncpg.connect(db_url)
        
        try:
            # sys_systemsteuerung: Pro User eine Zeile mit Settings
            # Struktur: uid (user_guid), daten (JSONB mit Properties wie stichtag, expert_mode, version)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS sys_systemsteuerung (
                    uid UUID PRIMARY KEY,
                    daten JSONB NOT NULL DEFAULT '{}',
                    name TEXT,
                    historisch INTEGER DEFAULT 0,
                    source_hash TEXT,
                    sec_id UUID,
                    gilt_bis FLOAT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    modified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    daten_backup JSONB
                )
            """)
            print("  ✅ sys_systemsteuerung erstellt")
            
            # sys_anwendungsdaten: Pro User eine Zeile mit App-Daten
            # Struktur: uid (user_guid), daten (JSONB mit Gruppen wie view_guid, darin Filter/Suchen)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS sys_anwendungsdaten (
                    uid UUID PRIMARY KEY,
                    daten JSONB NOT NULL DEFAULT '{}',
                    name TEXT,
                    historisch INTEGER DEFAULT 0,
                    source_hash TEXT,
                    sec_id UUID,
                    gilt_bis FLOAT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    modified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    daten_backup JSONB
                )
            """)
            print("  ✅ sys_anwendungsdaten erstellt")
            
            # Indizes für Performance
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_systemsteuerung_historisch 
                ON sys_systemsteuerung(historisch)
            """)
            
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_anwendungsdaten_historisch 
                ON sys_anwendungsdaten(historisch)
            """)
            
            print(f"  ✅ Indizes erstellt")
            
            # Zähle Einträge
            count_sys = await conn.fetchval("SELECT COUNT(*) FROM sys_systemsteuerung")
            count_app = await conn.fetchval("SELECT COUNT(*) FROM sys_anwendungsdaten")
            
            print(f"\n📊 {db_name} Status:")
            print(f"  sys_systemsteuerung: {count_sys} Einträge")
            print(f"  sys_anwendungsdaten: {count_app} Einträge")
            
        finally:
            await conn.close()
    
    print("\n✅ Session-Tabellen erstellt!")

if __name__ == "__main__":
    asyncio.run(create_session_tables())

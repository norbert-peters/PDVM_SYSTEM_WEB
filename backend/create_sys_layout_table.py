"""
Erstellt sys_layout Tabelle in pdvm_system
"""
import asyncio
import asyncpg

DB_PASSWORD = "Polari$55"

async def create_sys_layout_table():
    """Erstellt sys_layout Tabelle mit Standard-Struktur"""
    conn = await asyncpg.connect(f"postgresql://postgres:{DB_PASSWORD}@localhost:5432/pdvm_system")
    
    try:
        # CREATE FUNCTION falls nicht vorhanden
        await conn.execute("""
            CREATE OR REPLACE FUNCTION create_pdvm_table(table_name TEXT) 
            RETURNS void AS $$
            BEGIN
                EXECUTE format('
                    CREATE TABLE IF NOT EXISTS %I (
                        uid UUID PRIMARY KEY DEFAULT gen_random_uuid(),
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
        """)
        
        print("✅ create_pdvm_table Funktion erstellt")
        
        # Erstelle sys_layout Tabelle
        await conn.execute("SELECT create_pdvm_table('sys_layout')")
        
        print("✅ sys_layout Tabelle erstellt")
        
        # Prüfe ob Tabelle existiert
        exists = await conn.fetchval("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'sys_layout'
            )
        """)
        
        if exists:
            print("✅ Verifikation: sys_layout existiert")
        else:
            print("❌ Fehler: sys_layout wurde nicht erstellt")
            
    except Exception as e:
        print(f"❌ Fehler: {e}")
        raise
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(create_sys_layout_table())

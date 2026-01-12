"""
Prüfe und erstelle sys_systemsteuerung Struktur wenn nötig
"""
import asyncio
import asyncpg
from urllib.parse import urlparse

# Parse DATABASE_URL_MANDANT
DATABASE_URL = "postgresql://postgres:password@localhost:5432/mandant"
parsed = urlparse(DATABASE_URL)

async def check_systemsteuerung():
    # Verbinde mit Mandanten-DB
    conn = await asyncpg.connect(
        host=parsed.hostname,
        port=parsed.port,
        user=parsed.username,
        password=parsed.password,
        database=parsed.path[1:]  # Remove leading /
    )
    
    try:
        # Prüfe ob Tabelle existiert
        exists = await conn.fetchval("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = 'sys_systemsteuerung'
            )
        """)
        
        print(f"✅ Tabelle sys_systemsteuerung existiert: {exists}")
        
        if exists:
            # Zeige Struktur
            columns = await conn.fetch("""
                SELECT column_name, data_type, is_nullable
                FROM information_schema.columns
                WHERE table_name = 'sys_systemsteuerung'
                ORDER BY ordinal_position
            """)
            
            print("\n📊 Struktur von sys_systemsteuerung:")
            for col in columns:
                print(f"  - {col['column_name']}: {col['data_type']} {'NULL' if col['is_nullable'] == 'YES' else 'NOT NULL'}")
            
            # Prüfe ob benötigte Spalten existieren
            col_names = [col['column_name'] for col in columns]
            required = ['user_guid', 'gruppe', 'feld', 'wert', 'stichtag']
            missing = [c for c in required if c not in col_names]
            
            if missing:
                print(f"\n⚠️  Fehlende Spalten: {missing}")
                print("Füge fehlende Spalten hinzu...")
                
                for col in missing:
                    if col == 'user_guid':
                        await conn.execute("ALTER TABLE sys_systemsteuerung ADD COLUMN user_guid UUID")
                    elif col == 'gruppe':
                        await conn.execute("ALTER TABLE sys_systemsteuerung ADD COLUMN gruppe TEXT")
                    elif col == 'feld':
                        await conn.execute("ALTER TABLE sys_systemsteuerung ADD COLUMN feld TEXT")
                    elif col == 'wert':
                        await conn.execute("ALTER TABLE sys_systemsteuerung ADD COLUMN wert TEXT")
                    elif col == 'stichtag':
                        await conn.execute("ALTER TABLE sys_systemsteuerung ADD COLUMN stichtag DATE")
                
                print("✅ Spalten hinzugefügt")
            else:
                print("\n✅ Alle benötigten Spalten vorhanden")
            
            # Prüfe Index/Constraint
            constraints = await conn.fetch("""
                SELECT constraint_name, constraint_type
                FROM information_schema.table_constraints
                WHERE table_name = 'sys_systemsteuerung'
            """)
            
            print(f"\n📋 Constraints: {len(constraints)}")
            for c in constraints:
                print(f"  - {c['constraint_name']}: {c['constraint_type']}")
            
            # Erstelle Unique Constraint falls nicht vorhanden
            has_unique = any(c['constraint_type'] == 'UNIQUE' for c in constraints)
            if not has_unique and not missing:
                print("\nErstelle UNIQUE Constraint...")
                try:
                    await conn.execute("""
                        ALTER TABLE sys_systemsteuerung
                        ADD CONSTRAINT sys_systemsteuerung_unique
                        UNIQUE (user_guid, gruppe, feld, COALESCE(stichtag, '1900-01-01'::date))
                    """)
                    print("✅ UNIQUE Constraint erstellt")
                except Exception as e:
                    print(f"⚠️  Constraint konnte nicht erstellt werden: {e}")
            
            # Zeige Beispieldaten
            count = await conn.fetchval("SELECT COUNT(*) FROM sys_systemsteuerung")
            print(f"\n📊 Anzahl Einträge: {count}")
            
            if count > 0:
                rows = await conn.fetch("SELECT * FROM sys_systemsteuerung LIMIT 5")
                print("\n📄 Beispieldaten:")
                for row in rows:
                    print(f"  {dict(row)}")
        
        else:
            print("⚠️  Tabelle existiert nicht, bitte Schema ausführen")
    
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(check_systemsteuerung())

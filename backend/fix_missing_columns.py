"""
Script zum Hinzufügen der daten_backup Spalte über API/Backend
Nutzt den bereits laufenden Backend-Server und dessen Connection Pools
"""
import requests
import asyncio
from app.core.database import get_system_pool, get_mandant_pool
import asyncpg

async def add_columns_via_backend():
    """Fügt daten_backup Spalte über Backend Connection Pools hinzu"""
    print("🚀 Starte Hinzufügen der daten_backup Spalte über Backend")
    print("=" * 60)
    
    # Filialen-Datenbanken
    databases = [
        'filale_test_1',
        'filiale_test_2',
    ]
    
    # Tabellen
    tables = [
        'sys_systemsteuerung',
        'sys_anwendungsdaten',
        'sys_layout',
    ]
    
    for db_name in databases:
        print(f"\n🔧 Bearbeite Datenbank: {db_name}")
        
        try:
            # Direkte Connection zur Filialen-DB
            conn = await asyncpg.connect(
                host='localhost',
                port=5432,
                user='postgres',
                password='Postgres_2024!',
                database=db_name
            )
            
            for table in tables:
                # Prüfe ob Tabelle existiert
                table_exists = await conn.fetchval(
                    """
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables 
                        WHERE table_name = $1
                    )
                    """,
                    table
                )
                
                if not table_exists:
                    print(f"  ⚠️  {table} existiert nicht")
                    continue
                
                # Prüfe ob Spalte existiert
                column_exists = await conn.fetchval(
                    """
                    SELECT EXISTS (
                        SELECT FROM information_schema.columns 
                        WHERE table_name = $1 AND column_name = 'daten_backup'
                    )
                    """,
                    table
                )
                
                if column_exists:
                    print(f"  ✅ {table}: daten_backup bereits vorhanden")
                else:
                    # Spalte hinzufügen
                    await conn.execute(
                        f"ALTER TABLE {table} ADD COLUMN daten_backup jsonb DEFAULT '{{}}'::jsonb"
                    )
                    print(f"  ✅ {table}: daten_backup Spalte hinzugefügt")
            
            await conn.close()
            print(f"  ✅ {db_name} erfolgreich aktualisiert")
            
        except Exception as e:
            print(f"  ❌ Fehler bei {db_name}: {e}")
    
    print("\n" + "=" * 60)
    print("✅ Fertig!")

if __name__ == "__main__":
    print("\n⚠️  WICHTIG: Stelle sicher, dass PostgreSQL läuft!")
    print("Falls der Server nicht läuft, starte ihn mit: pg_ctl start -D <data_dir>\n")
    
    try:
        asyncio.run(add_columns_via_backend())
    except Exception as e:
        print(f"\n❌ Kritischer Fehler: {e}")
        print("\n💡 Lösungsvorschläge:")
        print("  1. Prüfe ob PostgreSQL läuft")
        print("  2. Prüfe die Credentials (User: postgres, Pass: Postgres_2024!)")
        print("  3. Prüfe ob die Datenbanken existieren")

"""
Script zum Hinzufügen der daten_backup JSONB Spalte zu allen relevanten Tabellen
"""
import asyncio
import asyncpg


async def main():
    """Hauptfunktion"""
    print("🚀 Starte Hinzufügen der daten_backup Spalte")
    print("=" * 60)
    
    # Liste der Mandanten-Datenbanken und Tabellen
    databases = [
        'filale_test_1',
        'filiale_test_2',
    ]
    
    tables = [
        'sys_anwendungsdaten',
        'sys_systemsteuerung',
        'sys_layout',
    ]
    
    for db_name in databases:
        print(f"\n🔧 Bearbeite Datenbank: {db_name}")
        
        try:
            conn = await asyncpg.connect(
                database=db_name,
                host='localhost',
                port=5432,
                user='postgres',
                password='Postgres_2024!'
            )
            
            for table in tables:
                try:
                    # Prüfe ob Tabelle existiert
                    table_exists = await conn.fetchval(
                        "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = $1)",
                        table
                    )
                    
                    if not table_exists:
                        print(f"  ⚠️  {table} existiert nicht")
                        continue
                    
                    # Prüfe ob Spalte existiert
                    column_exists = await conn.fetchval(
                        "SELECT EXISTS (SELECT FROM information_schema.columns WHERE table_name = $1 AND column_name = 'daten_backup')",
                        table
                    )
                    
                    if column_exists:
                        print(f"  ✅ {table}: daten_backup vorhanden")
                    else:
                        # Spalte hinzufügen
                        await conn.execute(
                            f"ALTER TABLE {table} ADD COLUMN daten_backup jsonb DEFAULT '{{}}'::jsonb"
                        )
                        print(f"  ✅ {table}: daten_backup hinzugefügt")
                        
                except Exception as e:
                    print(f"  ❌ {table}: {e}")
            
            await conn.close()
            
        except Exception as e:
            print(f"❌ Fehler bei {db_name}: {e}")
    
    print("\n" + "=" * 60)
    print("✅ Fertig!")


if __name__ == "__main__":
    asyncio.run(main())

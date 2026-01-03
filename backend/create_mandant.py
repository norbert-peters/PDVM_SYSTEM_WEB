"""
Script zum Anlegen eines neuen Mandanten
Kann später als Handler im System aufgerufen werden
"""
import asyncio
import uuid
from app.core.database import DatabasePool
from app.core.pdvm_central_mandanten import PdvmCentralMandanten
from app.core.pdvm_datenbank import PdvmDatabase


async def create_new_mandant(
    name: str,
    mandant_db: str,
    system_db: str = "pdvm_system",
    host: str = "localhost",
    port: int = 5432,
    user: str = "postgres",
    password: str = "password"
):
    """
    Erstellt einen neuen Mandanten
    
    Args:
        name: Name des Mandanten (z.B. "Testfirma GmbH")
        mandant_db: Name der Mandanten-Datenbank (z.B. "mandant_test2")
        system_db: Name der System-Datenbank (Standard: "pdvm_system")
        host: DB-Host (Standard: "localhost")
        port: DB-Port (Standard: 5432)
        user: DB-User (Standard: "postgres")
        password: DB-Passwort (Standard: "password")
    """
    print(f"\n🔧 Erstelle Mandant: {name}")
    print(f"   Mandanten-DB: {mandant_db}")
    
    # 1. Datenbank-Pools initialisieren
    await DatabasePool.create_pool()
    print("✅ Database Pools initialisiert")
    
    # 2. Mandanten in sys_mandanten anlegen
    mandant_guid = await PdvmCentralMandanten.create_mandant(
        name=name,
        mandant_db=mandant_db,
        system_db=system_db,
        host=host,
        port=port,
        user=user,
        password=password
    )
    
    print(f"✅ Mandant angelegt: {mandant_guid}")
    
    # 3. Mandanten-Datenbank erstellen (falls noch nicht vorhanden)
    print(f"\n🔧 Erstelle Datenbank '{mandant_db}'...")
    
    # Verbindung zur postgres-Datenbank für CREATE DATABASE
    import asyncpg
    conn = await asyncpg.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        database='postgres'
    )
    
    try:
        # Prüfen ob DB existiert
        exists = await conn.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = $1",
            mandant_db
        )
        
        if not exists:
            await conn.execute(f'CREATE DATABASE "{mandant_db}"')
            print(f"✅ Datenbank '{mandant_db}' erstellt")
        else:
            print(f"ℹ️  Datenbank '{mandant_db}' existiert bereits")
    finally:
        await conn.close()
    
    # 4. Schema in Mandanten-DB anlegen
    print(f"\n🔧 Erstelle Schema in '{mandant_db}'...")
    
    # Schema-SQL laden und ausführen
    import os
    schema_file = os.path.join(os.path.dirname(__file__), '..', 'database', 'schema_mandant.sql')
    
    if os.path.exists(schema_file):
        with open(schema_file, 'r', encoding='utf-8') as f:
            schema_sql = f.read()
        
        # Verbindung zur neuen Mandanten-DB
        mandant_conn = await asyncpg.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            database=mandant_db
        )
        
        try:
            await mandant_conn.execute(schema_sql)
            print(f"✅ Schema in '{mandant_db}' erstellt")
        finally:
            await mandant_conn.close()
    else:
        print(f"⚠️  Schema-Datei nicht gefunden: {schema_file}")
    
    # 5. Connection Pool für neuen Mandanten erstellen
    mandant_central = PdvmCentralMandanten(mandant_guid)
    await mandant_central.create_database_pool()
    print(f"✅ Connection Pool für Mandant erstellt")
    
    # 6. Pools schließen
    await DatabasePool.close_pool()
    print("✅ Database Pools geschlossen")
    
    print(f"\n✅ Mandant erfolgreich angelegt!")
    print(f"   GUID: {mandant_guid}")
    print(f"   Name: {name}")
    print(f"   Datenbank: {mandant_db}")
    
    return mandant_guid


async def main():
    """Hauptfunktion - kann mit eigenen Parametern aufgerufen werden"""
    
    # Beispiel: Zweiten Mandanten anlegen
    mandant_guid = await create_new_mandant(
        name="Zweite Testfirma GmbH",
        mandant_db="mandant_test2",
        system_db="pdvm_system",
        host="localhost",
        port=5432,
        user="postgres",
        password="password"
    )
    
    print(f"\n🎉 Mandant angelegt: {mandant_guid}")
    print(f"\nSie können sich jetzt mit diesem Mandanten anmelden!")


if __name__ == "__main__":
    asyncio.run(main())

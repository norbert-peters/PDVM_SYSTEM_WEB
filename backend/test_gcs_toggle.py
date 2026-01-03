"""
Teste GCS-Integration für toggle_menu
Simuliert das Speichern und Laden von Menu-Toggle-Status
"""
import asyncio
import asyncpg
from urllib.parse import urlparse

# Parse DATABASE_URL_MANDANT
DATABASE_URL = "postgresql://postgres:password@localhost:5432/mandant"
parsed = urlparse(DATABASE_URL)

async def test_gcs():
    # Verbinde mit Mandanten-DB
    conn = await asyncpg.connect(
        host=parsed.hostname,
        port=parsed.port,
        user=parsed.username,
        password=parsed.password,
        database=parsed.path[1:]
    )
    
    try:
        # Test-Daten
        user_guid = '7f7e9c5d-4e8f-4b5e-9f3c-8d7a6b5c4d3e'  # Admin-User
        menu_guid = '3424b00f-bb4d-4759-9689-e9e08249117b'  # Admin-Menü
        
        print("=" * 60)
        print("GCS Toggle-Menu Test")
        print("=" * 60)
        
        # 1. Prüfe Tabellenstruktur
        print("\n1️⃣ Prüfe sys_systemsteuerung Struktur...")
        columns = await conn.fetch("""
            SELECT column_name, data_type 
            FROM information_schema.columns
            WHERE table_name = 'sys_systemsteuerung'
            ORDER BY ordinal_position
        """)
        
        print("   Spalten:")
        for col in columns:
            print(f"   - {col['column_name']}: {col['data_type']}")
        
        # 2. Lösche alte Test-Daten
        print(f"\n2️⃣ Lösche alte Test-Daten...")
        await conn.execute("""
            DELETE FROM sys_systemsteuerung
            WHERE user_guid = $1 AND gruppe = $2 AND feld = 'toggle_menu'
        """, user_guid, menu_guid)
        print("   ✅ Alte Daten gelöscht")
        
        # 3. Speichere toggle_menu Status
        print(f"\n3️⃣ Speichere toggle_menu=0 (ausgeblendet)...")
        await conn.execute("""
            INSERT INTO sys_systemsteuerung (user_guid, gruppe, feld, wert, stichtag)
            VALUES ($1, $2, $3, $4, NULL)
        """, user_guid, menu_guid, 'toggle_menu', '0')
        print("   ✅ Status gespeichert")
        
        # 4. Lade toggle_menu Status
        print(f"\n4️⃣ Lade toggle_menu Status...")
        row = await conn.fetchrow("""
            SELECT wert, stichtag
            FROM sys_systemsteuerung
            WHERE user_guid = $1 AND gruppe = $2 AND feld = $3
        """, user_guid, menu_guid, 'toggle_menu')
        
        if row:
            print(f"   ✅ Status geladen: wert={row['wert']}, stichtag={row['stichtag']}")
        else:
            print("   ❌ Kein Status gefunden!")
        
        # 5. Update Status auf 1 (eingeblendet)
        print(f"\n5️⃣ Update Status auf 1 (eingeblendet)...")
        await conn.execute("""
            UPDATE sys_systemsteuerung
            SET wert = $1
            WHERE user_guid = $2 AND gruppe = $3 AND feld = $4
        """, '1', user_guid, menu_guid, 'toggle_menu')
        print("   ✅ Status aktualisiert")
        
        # 6. Prüfe Update
        print(f"\n6️⃣ Prüfe aktualisierten Status...")
        row = await conn.fetchrow("""
            SELECT wert
            FROM sys_systemsteuerung
            WHERE user_guid = $1 AND gruppe = $2 AND feld = $3
        """, user_guid, menu_guid, 'toggle_menu')
        
        if row:
            print(f"   ✅ Neuer Status: wert={row['wert']}")
        
        # 7. Zeige alle Systemsteuerung-Einträge für diesen User
        print(f"\n7️⃣ Alle Systemsteuerung-Einträge für User:")
        rows = await conn.fetch("""
            SELECT gruppe, feld, wert, stichtag
            FROM sys_systemsteuerung
            WHERE user_guid = $1
            ORDER BY gruppe, feld
        """, user_guid)
        
        print(f"   Anzahl: {len(rows)}")
        for row in rows:
            print(f"   - {row['gruppe'][:8]}... / {row['feld']}: {row['wert']}")
        
        print("\n" + "=" * 60)
        print("✅ GCS Test erfolgreich!")
        print("=" * 60)
        
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(test_gcs())

"""
Setze MEINEAPPS für Admin-User in sys_systemsteuerung
"""
import asyncio
import asyncpg

# sys_systemsteuerung ist in mandanten.db (alle Tabellen außer auth/system)
DATABASE_URL = "postgresql://postgres:Polari$55@localhost:5432/mandanten"
ADMIN_USER_GUID = "2e3c7b09-65eb-46e3-b5ec-fa163fb3a9b6"
STARTMENU_GUID = "5ca6674e-b9ce-4581-9756-64e742883f80"

async def setup_meineapps():
    print("🔧 Setze MEINEAPPS für Admin-User...\n")
    
    conn = await asyncpg.connect(DATABASE_URL)
    
    try:
        # 1. Prüfe aktuellen Stand
        print("1. Aktueller MEINEAPPS-Wert:")
        current = await conn.fetchval("""
            SELECT daten->'MEINEAPPS'
            FROM sys_systemsteuerung
            WHERE user_guid = $1
        """, ADMIN_USER_GUID)
        print(f"   {current}\n")
        
        # 2. Setze MEINEAPPS-Struktur
        meineapps = {
            "START": {
                "MENU": STARTMENU_GUID
            },
            "PERSONALWESEN": {
                "MENU": "dummy-guid-personalwesen"
            },
            "FINANZWESEN": {
                "MENU": "dummy-guid-finanzwesen"
            },
            "BENUTZERDATEN": {
                "MENU": "dummy-guid-benutzerdaten"
            },
            "ADMINISTRATION": {
                "MENU": "dummy-guid-administration"
            },
            "TESTBEREICH": {
                "MENU": "dummy-guid-testbereich"
            }
        }
        
        print("2. Setze neue MEINEAPPS-Struktur:")
        await conn.execute("""
            UPDATE sys_systemsteuerung
            SET daten = jsonb_set(
                COALESCE(daten, '{}'::jsonb),
                '{MEINEAPPS}',
                $1::jsonb
            )
            WHERE user_guid = $2
        """, str(meineapps).replace("'", '"'), ADMIN_USER_GUID)
        
        # 3. Prüfe Ergebnis
        updated = await conn.fetchval("""
            SELECT daten->'MEINEAPPS'
            FROM sys_systemsteuerung
            WHERE user_guid = $1
        """, ADMIN_USER_GUID)
        print(f"   ✅ MEINEAPPS gesetzt!")
        print(f"   START.MENU: {updated.get('START', {}).get('MENU') if isinstance(updated, dict) else 'ERROR'}")
        
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(setup_meineapps())

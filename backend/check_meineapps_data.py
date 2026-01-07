"""
Prüft MEINEAPPS-Daten in sys_systemsteuerung (Desktop-Pattern)
"""
import asyncio
import asyncpg

# sys_systemsteuerung ist in mandanten.db
MANDANTEN_DB = "postgresql://postgres:Polari$55@localhost:5432/mandanten"
ADMIN_USER_GUID = "2e3c7b09-65eb-46e3-b5ec-fa163fb3a9b6"

async def check_meineapps():
    print("🔍 Prüfe MEINEAPPS-Daten...\n")
    
    conn = await asyncpg.connect(MANDANTEN_DB)
    
    try:
        # 1. Prüfe ob sys_systemsteuerung existiert
        table_exists = await conn.fetchval("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'sys_systemsteuerung'
            )
        """)
        print(f"1. Tabelle sys_systemsteuerung existiert: {table_exists}")
        
        if not table_exists:
            print("   ❌ Tabelle muss erst erstellt werden!")
            return
        
        # 2. Prüfe User-Record
        user_record = await conn.fetchrow("""
            SELECT uid, name, daten 
            FROM sys_systemsteuerung 
            WHERE user_guid = $1
        """, ADMIN_USER_GUID)
        
        if not user_record:
            print(f"\n2. ❌ Kein Record für User {ADMIN_USER_GUID}")
            print("   Record muss erst erstellt werden!")
            return
        
        print(f"\n2. ✅ User-Record gefunden:")
        print(f"   uid: {user_record['uid']}")
        print(f"   name: {user_record['name']}")
        
        # 3. Prüfe MEINEAPPS in daten
        daten = user_record['daten'] or {}
        print(f"\n3. Daten-Felder: {list(daten.keys())}")
        
        if 'MEINEAPPS' in daten:
            meineapps = daten['MEINEAPPS']
            print(f"\n4. ✅ MEINEAPPS vorhanden:")
            print(f"   Keys: {list(meineapps.keys()) if isinstance(meineapps, dict) else 'nicht Dict!'}")
            
            if isinstance(meineapps, dict) and 'START' in meineapps:
                start = meineapps['START']
                print(f"\n5. ✅ START vorhanden:")
                print(f"   START = {start}")
                
                if isinstance(start, dict) and 'MENU' in start:
                    print(f"\n6. ✅ MENU-GUID: {start['MENU']}")
                else:
                    print(f"\n6. ❌ Kein MENU in START!")
            else:
                print(f"\n5. ❌ Kein START in MEINEAPPS!")
        else:
            print(f"\n4. ❌ MEINEAPPS nicht in daten!")
            print(f"   MEINEAPPS muss gesetzt werden!")
        
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(check_meineapps())

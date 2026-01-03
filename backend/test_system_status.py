#!/usr/bin/env python3
"""Teste Mandanten-Laden und User-Auth"""
import asyncio
import asyncpg

async def test_system():
    print("🔍 Prüfe System-Status...\n")
    
    # 1. Auth-DB prüfen
    print("=" * 60)
    print("1. AUTH-DATENBANK")
    print("=" * 60)
    
    conn_auth = await asyncpg.connect("postgresql://postgres:Polari$55@localhost:5432/auth")
    
    try:
        # Tabellen prüfen
        tables = await conn_auth.fetch("""
            SELECT tablename FROM pg_tables 
            WHERE schemaname = 'public'
            ORDER BY tablename
        """)
        print(f"✅ Tabellen: {', '.join([t['tablename'] for t in tables])}")
        
        # User prüfen
        user = await conn_auth.fetchrow("""
            SELECT uid, benutzer, daten FROM sys_benutzer 
            WHERE benutzer = 'admin@example.com'
        """)
        
        if user:
            print(f"\n✅ User gefunden: {user['benutzer']}")
            print(f"   UID: {user['uid']}")
            
            import json
            daten = json.loads(user['daten']) if isinstance(user['daten'], str) else user['daten']
            
            # MEINEAPPS prüfen
            meineapps = daten.get('MEINEAPPS', {})
            start_menu = meineapps.get('START', {}).get('MENU')
            print(f"   MEINEAPPS.START.MENU: {start_menu}")
            
            if not start_menu:
                print("   ⚠️ KEIN START.MENU definiert!")
        else:
            print("❌ User admin@example.com nicht gefunden!")
        
        # Mandanten prüfen
        mandanten = await conn_auth.fetch("""
            SELECT uid, name, daten FROM sys_mandanten
            WHERE historisch = 0
        """)
        
        print(f"\n✅ Mandanten: {len(mandanten)}")
        for m in mandanten:
            print(f"   - {m['name']} ({m['uid']})")
    
    finally:
        await conn_auth.close()
    
    # 2. Mandanten-DB prüfen
    print("\n" + "=" * 60)
    print("2. MANDANTEN-DATENBANK")
    print("=" * 60)
    
    conn_mandant = await asyncpg.connect("postgresql://postgres:Polari$55@localhost:5432/mandant")
    
    try:
        tables = await conn_mandant.fetch("""
            SELECT tablename FROM pg_tables 
            WHERE schemaname = 'public'
            ORDER BY tablename
        """)
        print(f"✅ Tabellen: {', '.join([t['tablename'] for t in tables])}")
        
        # Session-Tabellen prüfen
        for table in ['sys_systemsteuerung', 'sys_anwendungsdaten']:
            exists = await conn_mandant.fetchval(f"""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = '{table}'
                )
            """)
            
            if exists:
                count = await conn_mandant.fetchval(f"SELECT COUNT(*) FROM {table}")
                print(f"   ✅ {table}: {count} Einträge")
            else:
                print(f"   ❌ {table} existiert nicht!")
    
    finally:
        await conn_mandant.close()
    
    # 3. PDVM System-DB prüfen
    print("\n" + "=" * 60)
    print("3. PDVM_SYSTEM-DATENBANK")
    print("=" * 60)
    
    conn_system = await asyncpg.connect("postgresql://postgres:Polari$55@localhost:5432/pdvm_system")
    
    try:
        # sys_menudaten prüfen
        menu_exists = await conn_system.fetchval("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'sys_menudaten'
            )
        """)
        
        if menu_exists:
            menu_count = await conn_system.fetchval("""
                SELECT COUNT(*) FROM sys_menudaten WHERE historisch = 0
            """)
            print(f"✅ sys_menudaten: {menu_count} Menüs")
            
            # Startmenü prüfen
            startmenu = await conn_system.fetchrow("""
                SELECT uid, name FROM sys_menudaten 
                WHERE uid = '5ca6674e-b9ce-4581-9756-64e742883f80'
            """)
            
            if startmenu:
                print(f"   ✅ Startmenü gefunden: {startmenu['name']}")
            else:
                print("   ⚠️ Startmenü nicht gefunden!")
        else:
            print("❌ sys_menudaten existiert nicht!")
    
    finally:
        await conn_system.close()
    
    print("\n" + "=" * 60)
    print("ZUSAMMENFASSUNG")
    print("=" * 60)
    print("Alle Datenbanken sind erreichbar.")
    print("Prüfe Backend-Logs für weitere Fehlerdetails.")

if __name__ == "__main__":
    asyncio.run(test_system())

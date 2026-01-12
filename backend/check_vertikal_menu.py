"""
Quick-Check: VERTIKAL Menu Entries

Prüft ob VERTIKAL-Menü-Einträge existieren
"""

import asyncio
import asyncpg
import json

async def check_vertikal():
    """Prüfe VERTIKAL-Einträge im Startmenü"""
    
    conn = await asyncpg.connect(
        "postgresql://postgres:Polari$55@localhost:5432/pdvm_system"
    )
    
    try:
        # Hole ALLE Menüs aus sys_menudaten
        all_menus = await conn.fetch("SELECT uid, name FROM sys_menudaten")
        
        if not all_menus:
            print("❌ Keine Menüs in sys_menudaten gefunden!")
            print("\n💡 Tipp: Menü muss erst erstellt werden (setup_startmenu.py)")
            return
        
        print(f"📋 Gefundene Menüs in sys_menudaten:")
        for menu in all_menus:
            print(f"   - {menu['name']} ({menu['uid']})")
        
        # Hole erstes Menü
        menu_row = all_menus[0]
        full_menu = await conn.fetchrow("""
            SELECT uid, name, daten 
            FROM sys_menudaten 
            WHERE uid = $1
        """, menu_row['uid'])
        
        if not full_menu:
            print("❌ Menü konnte nicht geladen werden!")
            return
            
        print(f"\n✅ Analysiere Menü: {full_menu['name']} ({full_menu['uid']})")
        menu_data = full_menu['daten']
        
        # Parse JSON string zu dict
        if isinstance(menu_data, str):
            menu_data = json.loads(menu_data)
        
        # Prüfe VERTIKAL Gruppe
        if 'VERTIKAL' not in menu_data:
            print("❌ VERTIKAL Gruppe fehlt im Startmenü!")
            print(f"   Verfügbare Gruppen: {list(menu_data.keys())}")
            return
            
        vertikal = menu_data['VERTIKAL']
        print(f"\n✅ VERTIKAL Gruppe gefunden mit {len(vertikal)} Einträgen:")
        
        # Zeige alle VERTIKAL Einträge
        for guid, item in vertikal.items():
            visible = "✓" if item.get('visible', False) else "✗"
            enabled = "✓" if item.get('enabled', False) else "✗"
            parent = item.get('parent_guid', 'ROOT')
            sort_order = item.get('sort_order', 0)
            print(f"  [{visible}{enabled}] {item.get('label', 'NO LABEL'):30} | Order: {sort_order:3} | Parent: {parent[:8]}...")
            
        # Zähle sichtbare
        visible_count = sum(1 for item in vertikal.values() if item.get('visible'))
        print(f"\n📊 {visible_count} von {len(vertikal)} Einträgen sind sichtbar")
        
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(check_vertikal())

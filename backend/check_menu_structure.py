"""Check GRUND menu structure in imported menus"""
import asyncio
import asyncpg
import json

async def main():
    conn = await asyncpg.connect('postgresql://postgres:Polari$55@localhost:5432/pdvm_system')
    
    menus = await conn.fetch('SELECT uid, name, daten FROM sys_menudaten ORDER BY name')
    
    print('\n' + '='*70)
    print('GRUND-Menü Struktur:')
    print('='*70)
    
    for menu in menus:
        uid = menu['uid']
        name = menu['name'] or 'N/A'
        daten = menu['daten']
        
        if isinstance(daten, str):
            daten = json.loads(daten)
        
        grund = daten.get('GRUND', {})
        grund_items = len(grund)
        
        # Filtere nur Top-Level Items (keine parent_guid oder nicht SUBMENU)
        top_level = [item for guid, item in grund.items() 
                     if not item.get('parent_guid') and item.get('type') != 'SUBMENU']
        
        print(f"\n{name} ({uid})")
        print(f"  GRUND Items gesamt: {grund_items}")
        print(f"  Top-Level Items: {len(top_level)}")
        
        if top_level:
            for item in top_level[:3]:  # Zeige max 3
                label = item.get('label', 'N/A')
                item_type = item.get('type', 'N/A')
                handler = item.get('command', {}).get('handler', 'N/A') if item.get('command') else 'N/A'
                print(f"    - {label} ({item_type}) → {handler}")
    
    await conn.close()

if __name__ == '__main__':
    asyncio.run(main())

"""Show all imported menus"""
import asyncio
import asyncpg
import json

async def main():
    conn = await asyncpg.connect('postgresql://postgres:Polari$55@localhost:5432/pdvm_system')
    
    menus = await conn.fetch('SELECT uid, name FROM sys_menudaten ORDER BY name')
    
    print('\n' + '='*70)
    print('Verfügbare Menüs in sys_menudaten:')
    print('='*70)
    
    for menu in menus:
        uid = menu['uid']
        name = menu['name'] or 'N/A'
        print(f"{uid} - {name}")
    
    await conn.close()

if __name__ == '__main__':
    asyncio.run(main())

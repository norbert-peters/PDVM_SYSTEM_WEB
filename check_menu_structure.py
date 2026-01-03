"""
Überprüft die Struktur des Startmenüs in der Datenbank
"""
import asyncio
import asyncpg
import json

async def check_menu():
    conn = await asyncpg.connect('postgresql://postgres:Polari$55@localhost/pdvm_system')
    
    try:
        menu = await conn.fetchrow(
            "SELECT uid, name, daten FROM sys_menudaten WHERE uid = '5ca6674e-b9ce-4581-9756-64e742883f80'"
        )
        
        if not menu:
            print("❌ Menü nicht gefunden!")
            return
        
        print("=== Startmenü ===")
        print(f"UID: {menu['uid']}")
        print(f"Name: {menu['name']}")
        print()
        
        daten = menu['daten']
        if isinstance(daten, str):
            daten = json.loads(daten)
        
        print("Menü-Struktur:")
        print(json.dumps(daten, indent=2, ensure_ascii=False))
        
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(check_menu())

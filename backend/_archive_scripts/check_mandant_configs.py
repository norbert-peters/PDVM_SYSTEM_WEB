"""Check mandant connection configurations in sys_mandanten"""
import asyncio
import asyncpg
import json

async def check_mandant_configs():
    conn = await asyncpg.connect(
        host='localhost',
        port=5432,
        user='postgres',
        password='Polari$55',
        database='auth',
        ssl=False
    )
    
    try:
        rows = await conn.fetch(
            'SELECT uid, name, daten FROM sys_mandanten WHERE historisch = 0 ORDER BY name'
        )
        
        print("\n=== SYS_MANDANTEN CONNECTION CONFIGS ===\n")
        
        for row in rows:
            name = row['name']
            daten_str = row['daten']
            
            # Parse JSON
            try:
                daten = json.loads(daten_str) if isinstance(daten_str, str) else daten_str
            except:
                daten = None
            
            # Extract database name from daten.MANDANT.DATABASE
            database = daten.get('MANDANT', {}).get('DATABASE', 'N/A') if daten else 'N/A'
            
            print(f"📋 {name} (DB: {database})")
            print(f"   UID: {row['uid']}")
            
            if daten:
                mandant_config = daten.get('MANDANT', {})
                if mandant_config:
                    print(f"   MANDANT-Config vorhanden:")
                    print(f"     HOST: {mandant_config.get('HOST', 'FEHLT!')}")
                    print(f"     PORT: {mandant_config.get('PORT', 'FEHLT!')}")
                    print(f"     USER: {mandant_config.get('USER', 'FEHLT!')}")
                    pwd = mandant_config.get('PASSWORD')
                    print(f"     PASSWORD: {'***' + pwd[-4:] if pwd and len(pwd) > 4 else ('VORHANDEN' if pwd else 'FEHLT!')}")
                    print(f"     DATABASE: {mandant_config.get('DATABASE', 'FEHLT!')}")
                    print(f"     SYSTEM_DB: {mandant_config.get('SYSTEM_DB', 'FEHLT!')}")
                else:
                    print(f"   ❌ MANDANT-Config FEHLT in daten!")
            else:
                print(f"   ❌ KEINE DATEN!")
            
            print()
        
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(check_mandant_configs())

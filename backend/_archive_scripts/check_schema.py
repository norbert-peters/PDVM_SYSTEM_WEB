import asyncio
import asyncpg

async def check():
    conn = await asyncpg.connect("postgresql://postgres:Polari$55@localhost:5432/auth")
    columns = await conn.fetch("""
        SELECT column_name, data_type 
        FROM information_schema.columns 
        WHERE table_name = 'sys_benutzer'
        ORDER BY ordinal_position
    """)
    
    print("sys_benutzer Spalten:")
    for col in columns:
        print(f"  - {col['column_name']}: {col['data_type']}")
    
    # Alle User anzeigen
    users = await conn.fetch("SELECT uid, name FROM sys_benutzer")
    print(f"\n{len(users)} User:")
    for u in users:
        print(f"  - {u['name']} ({u['uid']})")
    
    await conn.close()

asyncio.run(check())

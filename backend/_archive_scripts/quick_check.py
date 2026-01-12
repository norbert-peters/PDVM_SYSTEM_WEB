import asyncio
import asyncpg
from app.core.config import settings
from app.core.security import verify_password

async def check():
    conn = await asyncpg.connect(settings.DATABASE_URL_AUTH)
    user = await conn.fetchrow(
        'SELECT uid, benutzer, passwort, name FROM sys_benutzer WHERE benutzer = $1', 
        'admin@example.com'
    )
    
    if user:
        print(f"✅ User gefunden: {user['benutzer']}")
        print(f"   Name: {user['name']}")
        print(f"   Hat Passwort: {bool(user['passwort'])}")
        
        if user['passwort']:
            for pwd in ['admin', 'Admin123!', 'password']:
                if verify_password(pwd, user['passwort']):
                    print(f"   ✅ Passwort ist: {pwd}")
                    break
    else:
        print("❌ User nicht gefunden")
    
    await conn.close()

asyncio.run(check())

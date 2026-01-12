"""Test login directly"""
import asyncio
import asyncpg
import bcrypt

async def test():
    conn = await asyncpg.connect(
        host='localhost',
        port=5432,
        user='postgres',
        password='Polari$55',
        database='auth'
    )
    
    # Lade User
    user = await conn.fetchrow("""
        SELECT benutzer, passwort 
        FROM sys_benutzer 
        WHERE benutzer = $1
    """, 'admin@example.com')
    
    if not user:
        print("❌ User nicht gefunden mit 'admin@example.com'")
        
        # Versuche alle User zu finden
        users = await conn.fetch("SELECT benutzer FROM sys_benutzer")
        print("\n📋 Alle Benutzer:")
        for u in users:
            print(f"  - '{u['benutzer']}'")
    else:
        print(f"✅ User gefunden: {user['benutzer']}")
        print(f"   Passwort-Hash: {user['passwort'][:70]}...")
        
        # Teste Passwort
        password = 'admin'
        try:
            if bcrypt.checkpw(password.encode('utf-8'), user['passwort'].encode('utf-8')):
                print(f"\n✅ Passwort '{password}' ist KORREKT!")
            else:
                print(f"\n❌ Passwort '{password}' ist FALSCH!")
        except Exception as e:
            print(f"\n❌ Fehler beim Test: {e}")
    
    await conn.close()

asyncio.run(test())

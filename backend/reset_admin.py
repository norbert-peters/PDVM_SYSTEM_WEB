"""Reset admin password to 'admin'"""
import asyncio
import asyncpg
import bcrypt

async def main():
    # Direkte Verbindung
    conn = await asyncpg.connect(
        host='localhost',
        port=5432,
        user='postgres',
        password='Polari$55',
        database='auth'
    )
    
    # Generiere bcrypt hash für 'admin'
    password = 'admin'
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    hashed_str = hashed.decode('utf-8')
    
    print(f"Neuer Passwort-Hash: {hashed_str}")
    
    # Update in DB
    result = await conn.execute("""
        UPDATE sys_benutzer 
        SET passwort = $1 
        WHERE benutzer = $2
    """, hashed_str, 'admin@example.com')
    
    print(f"Update-Resultat: {result}")
    
    # Verifiziere
    user = await conn.fetchrow("""
        SELECT benutzer, passwort 
        FROM sys_benutzer 
        WHERE benutzer = $1
    """, 'admin@example.com')
    
    if user:
        print(f"\n✅ User: {user['benutzer']}")
        print(f"   Hash: {user['passwort'][:60]}...")
        
        # Test verification
        if bcrypt.checkpw(password.encode('utf-8'), user['passwort'].encode('utf-8')):
            print(f"   ✅ Passwort-Verifikation erfolgreich!")
        else:
            print(f"   ❌ Passwort-Verifikation fehlgeschlagen!")
    
    await conn.close()
    print("\n✅ Fertig! Passwort ist jetzt 'admin'")

if __name__ == "__main__":
    asyncio.run(main())

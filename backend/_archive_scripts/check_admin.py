"""Check if admin user exists"""
import asyncio
from app.core.user_manager import UserManager

async def main():
    um = UserManager()
    
    # Prüfe admin@example.com
    print("\n=== Prüfe admin@example.com ===")
    admin = await um.get_user_by_email("admin@example.com")
    if admin:
        print("✅ Admin-User gefunden!")
        print(f"UID: {admin.get('uid')}")
        daten = admin.get('daten', {})
        print(f"Name: {daten.get('vorname', 'N/A')} {daten.get('nachname', 'N/A')}")
        
        # Versuche Login
        print("\n=== Teste Passwort-Authentifizierung ===")
        
        # Prüfe gespeicherten Passwort-Hash
        from app.core.security import verify_password
        stored_hash = daten.get('password')
        
        if stored_hash:
            print(f"Gespeicherter Hash: {stored_hash[:50]}...")
            
            # Teste verschiedene Passwörter
            for pwd in ["admin", "Admin123!", "password", "admin123", "test"]:
                if verify_password(pwd, stored_hash):
                    print(f"✅ Korrektes Passwort ist: '{pwd}'")
                    break
            else:
                print("❌ Keines der Test-Passwörter ist korrekt")
                print("Versuche ein neues Passwort zu setzen...")
                
                # Setze Passwort auf 'admin'
                from app.core.security import get_password_hash
                new_hash = get_password_hash("admin")
                
                from app.core.database import DatabasePool
                pool = DatabasePool.get_pool("auth")
                async with pool.acquire() as conn:
                    # Update Passwort
                    await conn.execute("""
                        UPDATE sys_benutzer
                        SET daten = jsonb_set(daten, '{password}', to_jsonb($1::text))
                        WHERE uid = $2
                    """, new_hash, admin.get('uid'))
                    print("✅ Passwort auf 'admin' zurückgesetzt")
        else:
            print("❌ Kein Passwort-Hash gefunden!")
    else:
        print("❌ Admin-User nicht gefunden!")
        print("\nErstelle Admin-User...")
        
        # Erstelle Admin-User
        from app.core.security import get_password_hash
        from app.core.database import DatabasePool
        import uuid
        
        user_id = str(uuid.uuid4())
        mandant_id = "00000000-0000-0000-0000-000000000001"  # Standard-Mandant
        password_hash = get_password_hash("admin")
        
        user_data = {
            "email": "admin@example.com",
            "password": password_hash,
            "vorname": "Admin",
            "nachname": "User",
            "aktiv": True,
            "mandant_id": mandant_id
        }
        
        pool = DatabasePool.get_pool("auth")
        async with pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO sys_benutzer (uid, name, daten, historisch)
                VALUES ($1, $2, $3, 0)
            """, user_id, "Admin User", user_data)
            
        print(f"✅ Admin-User erstellt mit Passwort 'admin'")
        print(f"UID: {user_id}")

if __name__ == "__main__":
    asyncio.run(main())

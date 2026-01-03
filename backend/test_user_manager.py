"""
Test-Script: Erstelle Demo-User mit bcrypt-Hash

Demonstriert:
- Email-Normalisierung
- Password-Hashing mit bcrypt
- Passwort-Komplexitäts-Validierung
"""
import asyncio
from app.core.user_manager import UserManager

async def test_user_manager():
    """Teste User-Manager Funktionen"""
    
    user_manager = UserManager()
    
    print("\n" + "=" * 60)
    print("USER MANAGER TEST")
    print("=" * 60)
    
    # 1. Email-Validierung
    print("\n[1] Email-Validierung:")
    test_emails = [
        "admin@example.com",
        "Admin@Example.COM",  # Case-insensitive
        "invalid-email",
        "test@test"
    ]
    for email in test_emails:
        valid = user_manager.validate_email(email)
        normalized = user_manager.normalize_email(email)
        print(f"  {email:25s} → Valid: {valid:5s} | Normalized: {normalized}")
    
    # 2. Password-Komplexität
    print("\n[2] Passwort-Komplexität:")
    test_passwords = [
        "admin",  # Zu kurz
        "Password123",  # Kein Sonderzeichen
        "Password@123",  # ✅ Gültig
        "@Pdvm2025"  # ✅ Gültig (Desktop-Standard)
    ]
    for pwd in test_passwords:
        valid, error = user_manager.validate_password_complexity(pwd)
        status = "✅" if valid else "❌"
        msg = error if error else "OK"
        print(f"  {status} {pwd:20s} → {msg}")
    
    # 3. Password-Hashing & Verifizierung
    print("\n[3] Password-Hashing (bcrypt):")
    password = "@Pdvm2025"
    hashed = user_manager.hash_password(password)
    print(f"  Original: {password}")
    print(f"  Hash:     {hashed[:60]}...")
    print(f"  Länge:    {len(hashed)} Zeichen")
    
    # Verifizierung
    print("\n[4] Passwort-Verifizierung:")
    test_passwords_verify = [
        ("@Pdvm2025", hashed, True),  # Korrekt
        ("@pdvm2025", hashed, False),  # Falsch (case-sensitive)
        ("wrong", hashed, False),      # Falsch
    ]
    for pwd, hash_val, expected in test_passwords_verify:
        result = user_manager.verify_password(pwd, hash_val)
        status = "✅" if result == expected else "❌"
        print(f"  {status} '{pwd}' → {result}")
    
    # 5. User aus DB laden
    print("\n[5] User aus Datenbank laden:")
    user = await user_manager.get_user_by_email("admin@example.com")
    if user:
        print(f"  ✅ User gefunden:")
        print(f"     UUID:  {user['uid']}")
        print(f"     Email: {user['benutzer']}")
        print(f"     Name:  {user['name']}")
        print(f"     Hash:  {user['passwort'][:40]}...")
        
        # Teste Passwort-Verifizierung mit DB-Hash
        print("\n[6] Passwort-Verifizierung gegen DB:")
        test_pwd = "admin"  # Das Passwort aus der DB
        result = user_manager.verify_password(test_pwd, user['passwort'])
        print(f"  {'✅' if result else '❌'} Passwort 'admin' → {result}")
    else:
        print("  ❌ User nicht gefunden!")
    
    # 6. Account-Lock Status
    print("\n[7] Account-Lock Status:")
    is_locked = await user_manager.is_account_locked("admin@example.com")
    print(f"  Account gesperrt: {is_locked}")
    
    # 7. Password-Change-Required
    print("\n[8] Password-Change-Required:")
    change_required = await user_manager.check_password_change_required("admin@example.com")
    print(f"  Passwort-Änderung erforderlich: {change_required}")
    
    print("\n" + "=" * 60)
    print("TEST ABGESCHLOSSEN")
    print("=" * 60 + "\n")

if __name__ == "__main__":
    asyncio.run(test_user_manager())

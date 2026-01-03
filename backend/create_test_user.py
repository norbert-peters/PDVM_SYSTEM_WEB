"""
Erstellt Test-Benutzer für PDVM System
Mit vollständiger PDVM-Datenstruktur
"""
import asyncio
import asyncpg
import bcrypt
import json
import sys
from pathlib import Path

# Add parent directory
sys.path.insert(0, str(Path(__file__).parent))

from app.core.pdvm_datetime import now_pdvm, now_pdvm_str

# Database URL
DATABASE_URL = "postgresql://postgres:Polari$55@localhost:5432/auth"

async def create_test_user():
    """Erstellt Test-Admin-Benutzer mit vollständiger Struktur"""
    
    # User Daten
    email = "admin@example.com"
    password = "admin"  # Klartext-Passwort
    name = "Norbert Peters"
    
    # Passwort hashen mit bcrypt
    password_bytes = password.encode('utf-8')
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password_bytes, salt)
    hashed_password = hashed.decode('utf-8')
    
    print(f"📧 Email: {email}")
    print(f"🔑 Passwort: {password}")
    print(f"🔐 Hash: {hashed_password[:50]}...")
    
    # Aktuelle Zeit im PDVM-Format
    now = now_pdvm()
    
    try:
        conn = await asyncpg.connect(DATABASE_URL)
        
        # Prüfe ob Benutzer bereits existiert
        existing = await conn.fetchrow(
            "SELECT uid, benutzer FROM sys_benutzer WHERE benutzer = $1",
            email
        )
        
        # Hole Mandanten-UIDs für LIST
        mandanten = await conn.fetch(
            "SELECT uid FROM sys_mandanten ORDER BY name"
        )
        mandanten_uids = [str(m['uid']) for m in mandanten]
        
        if not mandanten_uids:
            print("⚠️  Warnung: Keine Mandanten gefunden. Führe erst 'python setup_mandanten.py' aus!")
            mandanten_uids = []
        
        # Vollständige PDVM-Datenstruktur
        user_data = {
            "ROOT": {
                "SELF_GUID": None,  # Wird nach INSERT gesetzt
                "TABLE": "sys_benutzer",
                "DB": "auth"
            },
            "USER": {
                "ANREDE": "Herr",
                "NAME": "Peters",
                "VORNAME": "Norbert"
            },
            "SETTINGS": {
                "THEME": "light",
                "LANGUAGE": "DEU",
                "COUNTRY": "DEU",
                "MODE": "admin",
                "FONT_SIZE": 10,
                "STICHTAG": now,
                "EXPERT_MODE": False
            },
            "MANDANTEN": {
                "LIST": mandanten_uids,  # Alle Mandanten
                "DEFAULT": mandanten_uids[0] if mandanten_uids else None
            },
            "PERMISSIONS": {
                "ROLES": ["admin"],
                "SEC_PROFILES": ["sec-admin-full"]
            },
            "MEINEAPPS": {
                "START": {
                    "MENU": "5ca6674e-b9ce-4581-9756-64e742883f80"  # Admin-Startmenü
                },
                "PERSONALWESEN": {
                    "MENU": "3424b00f-bb4d-4759-9689-e9e08249117b"  # Admin-Menü
                },
                "FINANZWESEN": {
                    "MENU": "3424b00f-bb4d-4759-9689-e9e08249117b"  # Admin-Menü
                },
                "BENUTZERDATEN": {
                    "MENU": "e1e77039-d1b5-46ff-b12b-cced0ae0da7c"  # Admin-Benutzermenü
                },
                "ADMINISTRATION": {
                    "MENU": "4cfbf1ac-c7db-4a3a-ab37-c5b457b89440"  # Admin-Administration
                },
                "TESTBEREICH": {
                    "MENU": "113c6a2c-af9a-4022-929b-6544799e8954"  # Admin-Testmenü
                }
            },
            "SECURITY": {
                "LAST_LOGIN": 0.0,
                "FAILED_LOGINS": 0,
                "FAILED_LOGIN_ATTEMPTS": 0,
                "PASSWORD_CHANGE_REQUIRED": False,
                "LAST_PASSWORD_CHANGE": now,
                "ACCOUNT_LOCKED": False
            },
            "AUDIT": {
                "MODIFIED_AT": now,
                "MODIFIED_BY": "admin@super.de"
            }
        }
        
        if existing:
            print(f"\n⚠️  Benutzer existiert bereits: {existing['benutzer']}")
            print(f"   UUID: {existing['uid']}")
            print(f"\n🔄 Aktualisiere Passwort und Datenstruktur...")
            
            # Update SELF_GUID in ROOT
            user_data["ROOT"]["SELF_GUID"] = str(existing['uid'])
            
            # Update existing user
            await conn.execute("""
                UPDATE sys_benutzer 
                SET passwort = $1,
                    daten = $2::jsonb,
                    name = $3
                WHERE benutzer = $4
            """, hashed_password, json.dumps(user_data), name, email)
            
            print(f"✅ Passwort und Datenstruktur erfolgreich aktualisiert!")
        else:
            # Create new user
            import uuid
            user_id = uuid.uuid4()
            
            # Setze SELF_GUID
            user_data["ROOT"]["SELF_GUID"] = str(user_id)
            
            await conn.execute("""
                INSERT INTO sys_benutzer (uid, benutzer, passwort, name, daten)
                VALUES ($1, $2, $3, $4, $5::jsonb)
            """, user_id, email, hashed_password, name, json.dumps(user_data))
            
            print(f"\n✅ Benutzer erfolgreich angelegt!")
            print(f"   UUID: {user_id}")
        
        # Verify
        user = await conn.fetchrow(
            "SELECT uid, benutzer, name, daten FROM sys_benutzer WHERE benutzer = $1",
            email
        )
        
        if user:
            # Parse daten wenn String
            daten = user['daten']
            if isinstance(daten, str):
                daten = json.loads(daten)
            
            print(f"\n✓ Verifizierung:")
            print(f"  UUID: {user['uid']}")
            print(f"  Email: {user['benutzer']}")
            print(f"  Name: {user['name']}")
            print(f"\n📊 Datenstruktur:")
            print(f"  • ROOT.SELF_GUID: {daten['ROOT']['SELF_GUID']}")
            print(f"  • USER: {daten['USER']['VORNAME']} {daten['USER']['NAME']}")
            print(f"  • SETTINGS.MODE: {daten['SETTINGS']['MODE']}")
            print(f"  • MANDANTEN.LIST: {len(daten['MANDANTEN']['LIST'])} Mandanten")
            print(f"  • MANDANTEN.DEFAULT: {daten['MANDANTEN']['DEFAULT']}")
            print(f"  • PERMISSIONS.ROLES: {daten['PERMISSIONS']['ROLES']}")
            print(f"  • MEINEAPPS.START.MENU: {daten['MEINEAPPS']['START']['MENU']}")
            print(f"  • SECURITY.LAST_PASSWORD_CHANGE: {daten['SECURITY']['LAST_PASSWORD_CHANGE']}")
            print(f"  • AUDIT.MODIFIED_AT: {daten['AUDIT']['MODIFIED_AT']}")
        
        await conn.close()
        
        print(f"\n🎉 Test-Benutzer bereit!")
        print(f"   Login: {email}")
        print(f"   Passwort: {password}")
        print(f"   Rolle: admin")
        print(f"   Start-Menu: {user_data['MEINEAPPS']['START']['MENU']}")
        
    except Exception as e:
        print(f"\n❌ Fehler: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(create_test_user())

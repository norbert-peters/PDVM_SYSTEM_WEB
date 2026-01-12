"""Set admin password"""
import asyncio
from app.core.security import get_password_hash
from app.core.database import DatabasePool

async def main():
    # Generiere Hash für 'admin'
    password_hash = get_password_hash("admin")
    print(f"Neuer Passwort-Hash: {password_hash[:50]}...")
    
    # Update User
    pool = DatabasePool.get_pool("auth")
    async with pool.acquire() as conn:
        # Hole aktuellen User
        row = await conn.fetchrow("""
            SELECT uid, daten, passwort, benutzer FROM sys_benutzer
            WHERE daten->>'email' = 'admin@example.com'
        """)
        
        if row:
            print(f"User gefunden: {row['uid']}")
            print(f"Benutzer-Feld: {row['benutzer']}")
            print(f"Aktuelles Passwort-Feld: {row['passwort'][:50] if row['passwort'] else 'NULL'}...")
            
            # Update Passwort in der passwort-Spalte
            await conn.execute("""
                UPDATE sys_benutzer
                SET passwort = $1
                WHERE uid = $2
            """, password_hash, row['uid'])
            
            # Update auch das benutzer-Feld (muss gleich email sein)
            await conn.execute("""
                UPDATE sys_benutzer
                SET benutzer = $1
                WHERE uid = $2
            """, "admin@example.com", row['uid'])
            
            # Setze auch mandant_id falls nicht vorhanden
            await conn.execute("""
                UPDATE sys_benutzer
                SET daten = jsonb_set(
                    COALESCE(daten, '{}'::jsonb),
                    '{mandant_id}',
                    to_jsonb($1::text)
                )
                WHERE uid = $2 AND (daten->>'mandant_id' IS NULL OR daten->>'mandant_id' = '')
            """, "00000000-0000-0000-0000-000000000001", row['uid'])
            
            print("✅ Passwort erfolgreich auf 'admin' gesetzt (in passwort-Spalte)")
            print("✅ Benutzer-Feld auf 'admin@example.com' gesetzt")
            print("✅ Mandant-ID gesetzt")
            
            # Verifiziere
            updated = await conn.fetchrow("""
                SELECT daten, passwort, benutzer FROM sys_benutzer WHERE uid = $1
            """, row['uid'])
            
            print(f"\n=== Verifizierung ===")
            print(f"Email (in daten): {updated['daten'].get('email')}")
            print(f"Benutzer (Spalte): {updated['benutzer']}")
            print(f"Hat Passwort in Spalte: {updated['passwort'] is not None}")
            print(f"Mandant-ID: {updated['daten'].get('mandant_id')}")
            
            # Teste Passwort
            from app.core.security import verify_password
            if verify_password("admin", updated['passwort']):
                print(f"\n✅✅✅ Passwort 'admin' funktioniert!")
            else:
                print(f"\n❌ Passwort-Verifikation fehlgeschlagen")
        else:
            print("❌ User nicht gefunden")

if __name__ == "__main__":
    asyncio.run(main())

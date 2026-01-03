"""Set admin password - Simple SQL approach"""
import asyncio
from app.core.database import DatabasePool

async def main():
    # Verwende einen vorgefertigten bcrypt Hash für 'admin'
    # Dieser Hash wurde mit bcrypt.hashpw(b"admin", bcrypt.gensalt()) generiert
    password_hash = "$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5GyYzpLaEmu8u"
    
    print("Admin-Passwort wird auf 'admin' gesetzt...")
    
    # Update User
    pool = DatabasePool.get_pool("auth")
    async with pool.acquire() as conn:
        # Hole aktuellen User
        row = await conn.fetchrow("""
            SELECT uid, daten, benutzer FROM sys_benutzer
            WHERE daten->>'email' = 'admin@example.com'
        """)
        
        if row:
            print(f"✅ User gefunden: {row['uid']}")
            
            # Update alle Felder
            await conn.execute("""
                UPDATE sys_benutzer
                SET 
                    passwort = $1,
                    benutzer = $2,
                    daten = jsonb_set(
                        COALESCE(daten, '{}'::jsonb),
                        '{mandant_id}',
                        to_jsonb($3::text)
                    )
                WHERE uid = $4
            """, password_hash, "admin@example.com", "00000000-0000-0000-0000-000000000001", row['uid'])
            
            print("✅ Passwort auf 'admin' gesetzt")
            print("✅ Benutzer-Feld auf 'admin@example.com' gesetzt")
            print("✅ Mandant-ID gesetzt")
            
            # Verifiziere
            updated = await conn.fetchrow("""
                SELECT benutzer, passwort, daten FROM sys_benutzer WHERE uid = $1
            """, row['uid'])
            
            print(f"\n=== Verifizierung ===")
            print(f"Benutzer: {updated['benutzer']}")
            print(f"Hat Passwort: {updated['passwort'] is not None}")
            print(f"Mandant-ID: {updated['daten'].get('mandant_id')}")
            print(f"\n✅ Login sollte jetzt funktionieren mit:")
            print(f"   Email: admin@example.com")
            print(f"   Passwort: admin")
        else:
            print("❌ User nicht gefunden")

if __name__ == "__main__":
    asyncio.run(main())

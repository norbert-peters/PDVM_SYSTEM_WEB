"""
Löscht die fehlerhafte ganz_neu1 Datenbank für Neuanlage
"""
import asyncio
import asyncpg

async def drop_database():
    # Verbinde mit postgres DB (nicht mit ganz_neu1)
    conn = await asyncpg.connect(
        host="localhost",
        port=5432,
        user="postgres",
        password="Norbertw1958",
        database="postgres"
    )
    
    try:
        # Prüfe ob DB existiert
        exists = await conn.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = $1",
            "ganz_neu1"
        )
        
        if exists:
            print("🗑️ Lösche Datenbank 'ganz_neu1'...")
            
            # Beende alle aktiven Verbindungen
            await conn.execute("""
                SELECT pg_terminate_backend(pg_stat_activity.pid)
                FROM pg_stat_activity
                WHERE pg_stat_activity.datname = 'ganz_neu1'
                  AND pid <> pg_backend_pid()
            """)
            
            # Lösche Datenbank
            await conn.execute('DROP DATABASE "ganz_neu1"')
            print("✅ Datenbank 'ganz_neu1' gelöscht")
            print("ℹ️ Sie können jetzt den Mandanten neu über die UI erstellen")
        else:
            print("ℹ️ Datenbank 'ganz_neu1' existiert nicht")
    
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(drop_database())

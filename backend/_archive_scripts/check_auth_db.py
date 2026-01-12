"""
Check PostgreSQL auth database structure
"""
import asyncpg
import asyncio

async def check_auth_db():
    # Verbindung zur auth-Datenbank
    conn = await asyncpg.connect(
        host='localhost',
        port=5432,
        user='postgres',
        password='Polari$55',
        database='auth'
    )
    
    try:
        # Tabellen anzeigen
        tables = await conn.fetch("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public'
        """)
        print("📋 Tabellen in auth-Datenbank:")
        for table in tables:
            print(f"  - {table['table_name']}")
        
        # sys_benutzer Struktur
        columns = await conn.fetch("""
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_name = 'sys_benutzer'
            ORDER BY ordinal_position
        """)
        print("\n🔧 Spalten in sys_benutzer:")
        for col in columns:
            nullable = "NULL" if col['is_nullable'] == 'YES' else "NOT NULL"
            print(f"  - {col['column_name']:20s} {col['data_type']:15s} {nullable}")
        
        # Beispiel-Benutzer (ohne Passwort)
        users = await conn.fetch("""
            SELECT uid, benutzer, name 
            FROM sys_benutzer 
            LIMIT 5
        """)
        print("\n👥 Beispiel-Benutzer:")
        for user in users:
            print(f"  - {user['uid']}: {user['benutzer']} ({user['name']})")
        
        # Anzahl Benutzer
        count = await conn.fetchval("SELECT COUNT(*) FROM sys_benutzer")
        print(f"\n📊 Gesamt: {count} Benutzer")
        
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(check_auth_db())

"""
Test PostgreSQL Connection direkt
"""
import asyncio
import asyncpg

async def test_connection():
    """Test verschiedene Connection-Strings"""
    
    # Test 1: Mit $ im Passwort
    print("\n🔍 Test 1: Passwort mit $ (Polari$55)")
    try:
        conn = await asyncpg.connect(
            host="localhost",
            port=5432,
            user="postgres",
            password="Polari$55",
            database="auth",
            ssl=False
        )
        print("✅ ERFOLGREICH mit Polari$55")
        result = await conn.fetchval("SELECT 1")
        print(f"   Query result: {result}")
        await conn.close()
    except Exception as e:
        print(f"❌ FEHLER mit Polari$55: {e}")
    
    # Test 2: Mit @ im Passwort
    print("\n🔍 Test 2: Passwort mit @ (Polari@55)")
    try:
        conn = await asyncpg.connect(
            host="localhost",
            port=5432,
            user="postgres",
            password="Polari@55",
            database="auth",
            ssl=False
        )
        print("✅ ERFOLGREICH mit Polari@55")
        result = await conn.fetchval("SELECT 1")
        print(f"   Query result: {result}")
        await conn.close()
    except Exception as e:
        print(f"❌ FEHLER mit Polari@55: {e}")
    
    # Test 3: Prüfe alle Datenbanken
    print("\n🔍 Test 3: Liste aller Datenbanken")
    try:
        # Versuche mit dem Passwort, das funktioniert
        conn = await asyncpg.connect(
            host="localhost",
            port=5432,
            user="postgres",
            password="Polari$55",
            database="postgres",
            ssl=False
        )
        databases = await conn.fetch("SELECT datname FROM pg_database WHERE datistemplate = false")
        print("✅ Verfügbare Datenbanken:")
        for db in databases:
            print(f"   - {db['datname']}")
        await conn.close()
    except Exception as e:
        print(f"❌ FEHLER beim Auflisten: {e}")

if __name__ == "__main__":
    asyncio.run(test_connection())

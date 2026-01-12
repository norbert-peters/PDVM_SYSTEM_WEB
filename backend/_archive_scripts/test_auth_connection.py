"""
Test-Script: Direkte Verbindung zur auth-Datenbank testen
"""
import asyncio
import asyncpg

async def test_connection():
    """Teste verschiedene Verbindungsvarianten"""
    
    # Test 1: Mit SSL=False
    print("=" * 60)
    print("Test 1: Connection mit ssl=False")
    print("=" * 60)
    try:
        conn = await asyncpg.connect(
            host="localhost",
            port=5432,
            user="postgres",
            password="Polari@55",
            database="auth",
            ssl=False
        )
        print("✅ Verbindung erfolgreich!")
        version = await conn.fetchval("SELECT version()")
        print(f"PostgreSQL Version: {version}")
        await conn.close()
    except Exception as e:
        print(f"❌ Fehler: {type(e).__name__}: {e}")
    
    # Test 2: Mit SSL='prefer'
    print("\n" + "=" * 60)
    print("Test 2: Connection mit ssl='prefer'")
    print("=" * 60)
    try:
        conn = await asyncpg.connect(
            host="localhost",
            port=5432,
            user="postgres",
            password="Polari@55",
            database="auth",
            ssl='prefer'
        )
        print("✅ Verbindung erfolgreich!")
        await conn.close()
    except Exception as e:
        print(f"❌ Fehler: {type(e).__name__}: {e}")
    
    # Test 3: Ohne SSL-Parameter
    print("\n" + "=" * 60)
    print("Test 3: Connection ohne SSL-Parameter")
    print("=" * 60)
    try:
        conn = await asyncpg.connect(
            host="localhost",
            port=5432,
            user="postgres",
            password="Polari@55",
            database="auth"
        )
        print("✅ Verbindung erfolgreich!")
        await conn.close()
    except Exception as e:
        print(f"❌ Fehler: {type(e).__name__}: {e}")
    
    # Test 4: Connection zur postgres-DB (sollte immer existieren)
    print("\n" + "=" * 60)
    print("Test 4: Connection zur postgres-DB (Test ob Server erreichbar)")
    print("=" * 60)
    try:
        conn = await asyncpg.connect(
            host="localhost",
            port=5432,
            user="postgres",
            password="Polari@55",
            database="postgres",
            ssl=False
        )
        print("✅ Verbindung erfolgreich!")
        
        # Prüfe ob auth-DB existiert
        exists = await conn.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = 'auth'"
        )
        if exists:
            print("✅ Datenbank 'auth' existiert")
        else:
            print("❌ Datenbank 'auth' existiert NICHT!")
        
        await conn.close()
    except Exception as e:
        print(f"❌ Fehler: {type(e).__name__}: {e}")
    
    # Test 5: Mit timeout
    print("\n" + "=" * 60)
    print("Test 5: Connection mit timeout=10")
    print("=" * 60)
    try:
        conn = await asyncpg.connect(
            host="localhost",
            port=5432,
            user="postgres",
            password="Polari@55",
            database="auth",
            ssl=False,
            timeout=10
        )
        print("✅ Verbindung erfolgreich!")
        await conn.close()
    except Exception as e:
        print(f"❌ Fehler: {type(e).__name__}: {e}")

if __name__ == "__main__":
    asyncio.run(test_connection())

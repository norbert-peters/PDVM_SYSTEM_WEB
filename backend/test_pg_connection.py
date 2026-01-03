"""
Test PostgreSQL Verbindung mit verschiedenen Methoden
"""
import sys

print("=" * 60)
print("PostgreSQL Connection Test")
print("=" * 60)

# Test 1: asyncpg
print("\n1️⃣ Test mit asyncpg...")
try:
    import asyncio
    import asyncpg
    
    async def test_asyncpg():
        try:
            conn = await asyncpg.connect(
                host="localhost",
                port=5432,
                user="postgres",
                password="Norbertw1958",
                database="postgres",
                timeout=5
            )
            version = await conn.fetchval("SELECT version()")
            await conn.close()
            return f"✅ asyncpg OK: {version[:50]}..."
        except Exception as e:
            return f"❌ asyncpg FEHLER: {type(e).__name__}: {str(e)[:100]}"
    
    result = asyncio.run(test_asyncpg())
    print(result)
except Exception as e:
    print(f"❌ asyncpg nicht verfügbar: {e}")

# Test 2: psycopg2 (sync)
print("\n2️⃣ Test mit psycopg2 (synchron)...")
try:
    import psycopg2
    
    conn = psycopg2.connect(
        host="localhost",
        port=5432,
        user="postgres",
        password="Norbertw1958",
        database="postgres"
    )
    cursor = conn.cursor()
    cursor.execute("SELECT version()")
    version = cursor.fetchone()[0]
    cursor.close()
    conn.close()
    print(f"✅ psycopg2 OK: {version[:50]}...")
except ImportError:
    print("⚠️ psycopg2 nicht installiert")
except Exception as e:
    print(f"❌ psycopg2 FEHLER: {type(e).__name__}: {str(e)[:100]}")

# Test 3: Datenbankenliste
print("\n3️⃣ Liste aller Datenbanken...")
try:
    import psycopg2
    
    conn = psycopg2.connect(
        host="localhost",
        port=5432,
        user="postgres",
        password="Norbertw1958",
        database="postgres"
    )
    cursor = conn.cursor()
    cursor.execute("SELECT datname FROM pg_database ORDER BY datname")
    databases = [row[0] for row in cursor.fetchall()]
    cursor.close()
    conn.close()
    
    print(f"✅ Gefundene Datenbanken ({len(databases)}):")
    for db in databases:
        print(f"   - {db}")
        
    if "ganz_neu1" in databases:
        print("\n⚠️ 'ganz_neu1' existiert noch!")
    else:
        print("\n✅ 'ganz_neu1' existiert nicht")
        
except Exception as e:
    print(f"❌ Fehler: {e}")

print("\n" + "=" * 60)

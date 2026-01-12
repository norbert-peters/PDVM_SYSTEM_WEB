"""
Test mit psycopg2 (synchron) und korrektem Passwort
"""
import psycopg2

try:
    conn = psycopg2.connect(
        host="localhost",
        port=5432,
        user="postgres",
        password="Polari@55",
        database="postgres",
        client_encoding='latin1'  # Verwende latin1 um UTF-8 Fehler zu umgehen
    )
    
    cursor = conn.cursor()
    cursor.execute("SELECT datname FROM pg_database WHERE datname IN ('auth', 'mandant', 'pdvm_system', 'ganz_neu1') ORDER BY datname")
    databases = cursor.fetchall()
    
    print("✅ Verbindung erfolgreich mit psycopg2!")
    print(f"\nGefundene Datenbanken:")
    for db in databases:
        print(f"  - {db[0]}")
    
    cursor.close()
    conn.close()
    
except Exception as e:
    print(f"❌ Fehler: {type(e).__name__}: {e}")

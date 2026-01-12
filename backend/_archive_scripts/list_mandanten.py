"""
Prüfe vorhandene Mandanten für Farbschema-Zuweisung
"""
import psycopg2
import sys

try:
    # Prüfe auth Datenbank für Mandanten
    conn = psycopg2.connect(
        host="localhost",
        port=5432,
        database="auth",
        user="postgres",
        password="Polari$55"
    )
    cur = conn.cursor()
    
    # Erst Tabellen prüfen
    cur.execute("""
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = 'public' 
        AND table_type = 'BASE TABLE'
        ORDER BY table_name
    """)
    
    tables = cur.fetchall()
    print("\n=== Tabellen in pdvm_system ===\n")
    for t in tables:
        print(f"  - {t[0]}")
    print()
    
    # Versuche Mandanten zu laden
    cur.execute("""
        SELECT mandant_guid, name, kuerzel, created_at
        FROM sys_mandanten 
        ORDER BY created_at
        LIMIT 10
    """)
    
    mandanten = cur.fetchall()
    
    print("\n=== Vorhandene Mandanten ===\n")
    for i, m in enumerate(mandanten, 1):
        print(f"{i}. {m[1]} ({m[2]})")
        print(f"   GUID: {m[0]}")
        print(f"   Erstellt: {m[3]}")
        print()
    
    print(f"Gesamt: {len(mandanten)} Mandanten gefunden")
    
    cur.close()
    conn.close()
    
except Exception as e:
    print(f"Fehler: {e}")
    sys.exit(1)

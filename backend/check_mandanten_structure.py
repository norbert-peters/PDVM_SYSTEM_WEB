"""
Struktur der sys_mandanten Tabelle prüfen
"""
import psycopg2

try:
    conn = psycopg2.connect(
        host="localhost",
        database="auth",
        user="postgres",
        password="Polari$55"
    )
    cur = conn.cursor()
    
    # Spalten prüfen
    cur.execute("""
        SELECT column_name, data_type, is_nullable
        FROM information_schema.columns 
        WHERE table_name = 'sys_mandanten'
        ORDER BY ordinal_position
    """)
    
    cols = cur.fetchall()
    print("\n=== Spalten in sys_mandanten ===\n")
    for c in cols:
        print(f"  - {c[0]:<25} {c[1]:<20} NULL: {c[2]}")
    
    # Erste 5 Mandanten
    cur.execute("SELECT * FROM sys_mandanten LIMIT 5")
    mandanten = cur.fetchall()
    colnames = [desc[0] for desc in cur.description]
    
    print("\n=== Erste 5 Mandanten ===\n")
    for m in mandanten:
        print(f"Mandant:")
        for i, col in enumerate(colnames):
            print(f"  {col}: {m[i]}")
        print()
    
    cur.close()
    conn.close()
    
except Exception as e:
    print(f"Fehler: {e}")

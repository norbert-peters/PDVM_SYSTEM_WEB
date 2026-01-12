"""
Prüfe PostgreSQL Encoding und Locale
"""
import psycopg2

try:
    # Setze Client-Encoding explizit
    conn = psycopg2.connect(
        host="localhost",
        port=5432,
        user="postgres",
        password="Norbertw1958",
        database="postgres",
        client_encoding='UTF8'
    )
    
    cursor = conn.cursor()
    
    # Prüfe Server-Encoding
    cursor.execute("SHOW server_encoding")
    server_enc = cursor.fetchone()[0]
    print(f"Server Encoding: {server_enc}")
    
    # Prüfe Client-Encoding
    cursor.execute("SHOW client_encoding")
    client_enc = cursor.fetchone()[0]
    print(f"Client Encoding: {client_enc}")
    
    # Prüfe Locale
    cursor.execute("SHOW lc_messages")
    lc_messages = cursor.fetchone()[0]
    print(f"LC_MESSAGES: {lc_messages}")
    
    # Liste Datenbanken mit ihrem Encoding
    cursor.execute("""
        SELECT datname, pg_encoding_to_char(encoding) as encoding
        FROM pg_database
        WHERE datname IN ('postgres', 'mandant', 'ganz_neu1', 'template0', 'template1')
        ORDER BY datname
    """)
    
    print("\nDatenbank Encodings:")
    for row in cursor.fetchall():
        print(f"  {row[0]}: {row[1]}")
    
    cursor.close()
    conn.close()
    
except Exception as e:
    print(f"Fehler: {type(e).__name__}: {e}")

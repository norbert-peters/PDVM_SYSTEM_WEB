"""
Sucht sys_layout Tabelle in allen Datenbanken
"""
import psycopg2

databases = ["auth", "pdvm_system", "mandant"]

for db_name in databases:
    try:
        conn = psycopg2.connect(
            host="localhost",
            port=5432,
            user="postgres",
            password="Polari$55",
            database=db_name
        )
        
        cur = conn.cursor()
        
        # Suche in allen Schemas
        cur.execute("""
            SELECT 
                schemaname, 
                tablename 
            FROM pg_tables 
            WHERE tablename = 'sys_layout'
        """)
        
        results = cur.fetchall()
        
        if results:
            print(f"✅ {db_name}: {results}")
            
            # Zähle Einträge
            for schema, table in results:
                cur.execute(f"SELECT COUNT(*) FROM {schema}.{table} WHERE historisch = 0")
                count = cur.fetchone()[0]
                print(f"   {schema}.{table}: {count} Einträge")
        
        cur.close()
        conn.close()
        
    except Exception as e:
        print(f"❌ {db_name}: {e}")

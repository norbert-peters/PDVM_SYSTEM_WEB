"""
Check Theme Colors in Database
"""
import psycopg2
import json

def check_themes():
    conn = psycopg2.connect(
        host="localhost",
        port=5432,
        user="postgres",
        password="Polari$55",
        database="pdvm_system"
    )
    
    cur = conn.cursor()
    
    print("=== THEME COLORS CHECK ===\n")
    
    cur.execute("""
        SELECT 
            uid,
            name,
            daten->'mandant_name' as mandant_name,
            daten->'theme' as theme,
            daten->'colors'->'primary'->>'500' as primary_500
        FROM pdvm_system.sys_layout
        WHERE historisch = 0
        ORDER BY name
    """)
    
    rows = cur.fetchall()
    
    for row in rows:
        uid, name, mandant_name, theme, primary = row
        print(f"📋 {name}")
        print(f"   Mandant: {mandant_name}")
        print(f"   Theme: {theme}")
        print(f"   Primary Color: {primary}")
        print()
    
    # Detailed check for one theme
    print("\n=== DETAILED CHECK: First Theme ===\n")
    cur.execute("""
        SELECT daten
        FROM pdvm_system.sys_layout
        WHERE historisch = 0
        ORDER BY name
        LIMIT 1
    """)
    
    result = cur.fetchone()
    if result:
        theme_data = result[0]
        print(json.dumps(theme_data, indent=2))
    
    cur.close()
    conn.close()

if __name__ == "__main__":
    check_themes()

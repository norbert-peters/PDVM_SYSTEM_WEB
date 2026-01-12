"""
Zeigt alle Themes aus pdvm_system.sys_layout
"""
import psycopg2
import json

conn = psycopg2.connect(
    host="localhost",
    port=5432,
    user="postgres",
    password="Polari$55",
    database="pdvm_system"
)

cur = conn.cursor()

print("=== THEME FARBEN ===\n")

try:
    cur.execute("""
        SELECT 
            name,
            daten->>'mandant_name' as mandant_name,
            daten->>'mandant_uid' as mandant_uid,
            daten->>'theme' as theme,
            daten->'colors'->'primary'->>'500' as primary
        FROM public.sys_layout
        WHERE historisch = 0
        ORDER BY mandant_name, theme
    """)
    
    rows = cur.fetchall()
    
    if rows:
        print(f"✅ {len(rows)} Themes gefunden:\n")
        
        current_mandant = None
        for row in rows:
            name, mandant_name, mandant_uid, theme, primary = row
            
            if mandant_name != current_mandant:
                current_mandant = mandant_name
                print(f"\n🏢 {mandant_name}")
                print(f"   UID: {mandant_uid}")
            
            print(f"   {theme.upper()}: {primary}")
    else:
        print("❌ Keine Themes gefunden")
        
except Exception as e:
    print(f"❌ Fehler: {e}")

cur.close()
conn.close()

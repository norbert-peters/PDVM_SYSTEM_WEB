"""
Prüft ob sys_layout Tabelle existiert und zeigt Daten
"""
import psycopg2
import json

# Verbindung zu pdvm_system
conn = psycopg2.connect(
    host="localhost",
    port=5432,
    user="postgres",
    password="Polari$55",
    database="pdvm_system"
)

cur = conn.cursor()

# Prüfe ob Tabelle existiert
print("=== PRÜFE sys_layout TABELLE ===\n")
cur.execute("""
    SELECT EXISTS (
        SELECT FROM information_schema.tables 
        WHERE table_schema = 'pdvm_system' 
        AND table_name = 'sys_layout'
    )
""")

exists = cur.fetchone()[0]
print(f"Tabelle sys_layout existiert: {exists}\n")

if exists:
    # Zähle Einträge
    cur.execute("SELECT COUNT(*) FROM pdvm_system.sys_layout WHERE historisch = 0")
    count = cur.fetchone()[0]
    print(f"Anzahl aktiver Layouts: {count}\n")
    
    # Zeige alle Layouts
    cur.execute("""
        SELECT 
            name,
            daten->>'mandant_name' as mandant_name,
            daten->>'theme' as theme,
            daten->'colors'->'primary'->>'500' as primary_color
        FROM pdvm_system.sys_layout
        WHERE historisch = 0
        ORDER BY name
    """)
    
    print("=== GESPEICHERTE THEMES ===\n")
    for row in cur.fetchall():
        name, mandant_name, theme, primary = row
        print(f"📋 {name}")
        print(f"   Mandant: {mandant_name}")
        print(f"   Theme: {theme}")
        print(f"   Primary: {primary}")
        print()

else:
    print("❌ Tabelle muss erstellt werden!")
    print("\nTabelle mit CREATE TABLE erstellen:")
    print("python setup_layouts.py")

cur.close()
conn.close()

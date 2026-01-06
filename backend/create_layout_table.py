"""
Erstellt sys_layout Tabelle in pdvm_system
"""
import psycopg2

conn = psycopg2.connect(
    host="localhost",
    port=5432,
    user="postgres",
    password="Polari$55",
    database="pdvm_system"
)

cur = conn.cursor()

print("🏗️  Erstelle sys_layout Tabelle...")

# Erstelle Tabelle im pdvm_system Schema
cur.execute("""
    CREATE TABLE IF NOT EXISTS pdvm_system.sys_layout (
        uid UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        daten JSONB NOT NULL DEFAULT '{}'::jsonb,
        name TEXT NOT NULL,
        historisch INTEGER NOT NULL DEFAULT 0,
        source_hash TEXT,
        sec_id INTEGER,
        gilt_bis NUMERIC(10,5),
        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        modified_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
    )
""")

# Index für schnellere Suche
cur.execute("""
    CREATE INDEX IF NOT EXISTS idx_sys_layout_historisch 
    ON pdvm_system.sys_layout(historisch)
""")

cur.execute("""
    CREATE INDEX IF NOT EXISTS idx_sys_layout_mandant_theme 
    ON pdvm_system.sys_layout((daten->>'mandant_uid'), (daten->>'theme'))
    WHERE historisch = 0
""")

conn.commit()

print("✅ sys_layout Tabelle erstellt!")
print("\nNächster Schritt:")
print("python setup_layouts.py")

cur.close()
conn.close()

"""
Neue Theme-Struktur für sys_layout
Themes werden zentral definiert und von Mandanten referenziert
"""
import psycopg2
from uuid import uuid4
import json

conn = psycopg2.connect(
    host="localhost",
    port=5432,
    user="postgres",
    password="Polari$55",
    database="pdvm_system"
)

cur = conn.cursor()

# Generiere echte UUIDs für die 3 Themes
THEME_BLUE_UID = str(uuid4())
THEME_GREEN_UID = str(uuid4())
THEME_ORANGE_UID = str(uuid4())

print(f"🎨 Theme UIDs generiert:")
print(f"   Blue:   {THEME_BLUE_UID}")
print(f"   Green:  {THEME_GREEN_UID}")
print(f"   Orange: {THEME_ORANGE_UID}\n")

# Farbschemata
COLORS_BLUE = {
    "light": {
        "primary": {"50": "#e3f2fd", "100": "#bbdefb", "200": "#90caf9", "300": "#64b5f6", "400": "#42a5f5", "500": "#2196f3", "600": "#1e88e5", "700": "#1976d2", "800": "#1565c0", "900": "#0d47a1"},
        "secondary": {"50": "#fff3e0", "100": "#ffe0b2", "200": "#ffcc80", "300": "#ffb74d", "400": "#ffa726", "500": "#ff9800", "600": "#fb8c00", "700": "#f57c00", "800": "#ef6c00", "900": "#e65100"},
        "neutral": {"50": "#fafafa", "100": "#f5f5f5", "200": "#eeeeee", "300": "#e0e0e0", "400": "#bdbdbd", "500": "#9e9e9e", "600": "#757575", "700": "#616161", "800": "#424242", "900": "#212121"},
        "success": "#4caf50", "warning": "#ff9800", "error": "#f44336", "info": "#2196f3",
        "background": {"primary": "#ffffff", "secondary": "#f5f5f5", "tertiary": "#eeeeee"},
        "text": {"primary": "#212121", "secondary": "#757575", "disabled": "#bdbdbd", "inverse": "#ffffff"},
        "border": {"light": "#e0e0e0", "medium": "#bdbdbd", "dark": "#757575"}
    },
    "dark": {
        "primary": {"50": "#e3f2fd", "100": "#bbdefb", "200": "#90caf9", "300": "#64b5f6", "400": "#42a5f5", "500": "#42a5f5", "600": "#1e88e5", "700": "#1976d2", "800": "#1565c0", "900": "#0d47a1"},
        "secondary": {"50": "#fff3e0", "100": "#ffe0b2", "200": "#ffcc80", "300": "#ffb74d", "400": "#ffa726", "500": "#ffb74d", "600": "#fb8c00", "700": "#f57c00", "800": "#ef6c00", "900": "#e65100"},
        "neutral": {"50": "#1a1a1a", "100": "#2a2a2a", "200": "#3a3a3a", "300": "#4a4a4a", "400": "#6a6a6a", "500": "#8a8a8a", "600": "#aaaaaa", "700": "#cacaca", "800": "#e0e0e0", "900": "#f5f5f5"},
        "success": "#66bb6a", "warning": "#ffb74d", "error": "#ef5350", "info": "#42a5f5",
        "background": {"primary": "#121212", "secondary": "#1e1e1e", "tertiary": "#2a2a2a"},
        "text": {"primary": "#ffffff", "secondary": "#b0b0b0", "disabled": "#6a6a6a", "inverse": "#212121"},
        "border": {"light": "#333333", "medium": "#4a4a4a", "dark": "#6a6a6a"}
    }
}

COLORS_GREEN = {
    "light": {
        "primary": {"50": "#e8f5e9", "100": "#c8e6c9", "200": "#a5d6a7", "300": "#81c784", "400": "#66bb6a", "500": "#4caf50", "600": "#43a047", "700": "#388e3c", "800": "#2e7d32", "900": "#1b5e20"},
        "secondary": {"50": "#f3e5f5", "100": "#e1bee7", "200": "#ce93d8", "300": "#ba68c8", "400": "#ab47bc", "500": "#9c27b0", "600": "#8e24aa", "700": "#7b1fa2", "800": "#6a1b9a", "900": "#4a148c"},
        "neutral": {"50": "#fafafa", "100": "#f5f5f5", "200": "#eeeeee", "300": "#e0e0e0", "400": "#bdbdbd", "500": "#9e9e9e", "600": "#757575", "700": "#616161", "800": "#424242", "900": "#212121"},
        "success": "#4caf50", "warning": "#ff9800", "error": "#f44336", "info": "#2196f3",
        "background": {"primary": "#fafafa", "secondary": "#f0f0f0", "tertiary": "#e5e5e5"},
        "text": {"primary": "#1b5e20", "secondary": "#616161", "disabled": "#bdbdbd", "inverse": "#ffffff"},
        "border": {"light": "#c8e6c9", "medium": "#a5d6a7", "dark": "#81c784"}
    },
    "dark": {
        "primary": {"50": "#e8f5e9", "100": "#c8e6c9", "200": "#a5d6a7", "300": "#81c784", "400": "#66bb6a", "500": "#66bb6a", "600": "#43a047", "700": "#388e3c", "800": "#2e7d32", "900": "#1b5e20"},
        "secondary": {"50": "#f3e5f5", "100": "#e1bee7", "200": "#ce93d8", "300": "#ba68c8", "400": "#ab47bc", "500": "#ba68c8", "600": "#8e24aa", "700": "#7b1fa2", "800": "#6a1b9a", "900": "#4a148c"},
        "neutral": {"50": "#1a1a1a", "100": "#2a2a2a", "200": "#3a3a3a", "300": "#4a4a4a", "400": "#6a6a6a", "500": "#8a8a8a", "600": "#aaaaaa", "700": "#cacaca", "800": "#e0e0e0", "900": "#f5f5f5"},
        "success": "#66bb6a", "warning": "#ffb74d", "error": "#ef5350", "info": "#42a5f5",
        "background": {"primary": "#121212", "secondary": "#1e1e1e", "tertiary": "#2a2a2a"},
        "text": {"primary": "#ffffff", "secondary": "#b0b0b0", "disabled": "#6a6a6a", "inverse": "#212121"},
        "border": {"light": "#2a4a2a", "medium": "#3a5a3a", "dark": "#4a6a4a"}
    }
}

COLORS_ORANGE = {
    "light": {
        "primary": {"50": "#fff3e0", "100": "#ffe0b2", "200": "#ffcc80", "300": "#ffb74d", "400": "#ffa726", "500": "#ff9800", "600": "#fb8c00", "700": "#f57c00", "800": "#ef6c00", "900": "#e65100"},
        "secondary": {"50": "#e3f2fd", "100": "#bbdefb", "200": "#90caf9", "300": "#64b5f6", "400": "#42a5f5", "500": "#2196f3", "600": "#1e88e5", "700": "#1976d2", "800": "#1565c0", "900": "#0d47a1"},
        "neutral": {"50": "#fafafa", "100": "#f5f5f5", "200": "#eeeeee", "300": "#e0e0e0", "400": "#bdbdbd", "500": "#9e9e9e", "600": "#757575", "700": "#616161", "800": "#424242", "900": "#212121"},
        "success": "#4caf50", "warning": "#ff9800", "error": "#f44336", "info": "#2196f3",
        "background": {"primary": "#ffffff", "secondary": "#fff8f0", "tertiary": "#fff3e0"},
        "text": {"primary": "#e65100", "secondary": "#616161", "disabled": "#bdbdbd", "inverse": "#ffffff"},
        "border": {"light": "#ffe0b2", "medium": "#ffcc80", "dark": "#ffb74d"}
    },
    "dark": {
        "primary": {"50": "#fff3e0", "100": "#ffe0b2", "200": "#ffcc80", "300": "#ffb74d", "400": "#ffa726", "500": "#ffb74d", "600": "#fb8c00", "700": "#f57c00", "800": "#ef6c00", "900": "#e65100"},
        "secondary": {"50": "#e3f2fd", "100": "#bbdefb", "200": "#90caf9", "300": "#64b5f6", "400": "#42a5f5", "500": "#64b5f6", "600": "#1e88e5", "700": "#1976d2", "800": "#1565c0", "900": "#0d47a1"},
        "neutral": {"50": "#1a1a1a", "100": "#2a2a2a", "200": "#3a3a3a", "300": "#4a4a4a", "400": "#6a6a6a", "500": "#8a8a8a", "600": "#aaaaaa", "700": "#cacaca", "800": "#e0e0e0", "900": "#f5f5f5"},
        "success": "#66bb6a", "warning": "#ffb74d", "error": "#ef5350", "info": "#42a5f5",
        "background": {"primary": "#121212", "secondary": "#1e1e1e", "tertiary": "#2a2a2a"},
        "text": {"primary": "#ffffff", "secondary": "#b0b0b0", "disabled": "#6a6a6a", "inverse": "#212121"},
        "border": {"light": "#3a2a1a", "medium": "#4a3a2a", "dark": "#5a4a3a"}
    }
}

TYPOGRAPHY = {
    "fontFamily": {"primary": "Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif", "secondary": "Georgia, serif", "mono": "'Fira Code', 'Courier New', monospace"},
    "fontSize": {"xs": "0.75rem", "sm": "0.875rem", "base": "1rem", "lg": "1.125rem", "xl": "1.25rem", "2xl": "1.5rem", "3xl": "1.875rem", "4xl": "2.25rem", "scale": 1.0},
    "fontWeight": {"light": 300, "normal": 400, "medium": 500, "semibold": 600, "bold": 700},
    "lineHeight": {"tight": 1.25, "normal": 1.5, "relaxed": 1.75}
}

CUSTOMIZATIONS = {
    "animations": {"enabled": True, "duration": "200ms", "easing": "cubic-bezier(0.4, 0, 0.2, 1)"},
    "shadows": {"enabled": True, "intensity": "medium"},
    "borderRadius": {"sm": "4px", "md": "8px", "lg": "12px", "full": "9999px"}
}

print("🎨 Migriere auf neue Theme-Struktur...")
print("=" * 60)

# 0. Füge 'gruppe' Spalte hinzu falls nicht vorhanden
print("\n0️⃣ Prüfe/Erstelle 'gruppe' Spalte...")
cur.execute("""
    ALTER TABLE public.sys_layout 
    ADD COLUMN IF NOT EXISTS gruppe TEXT DEFAULT 'ROOT'
""")
conn.commit()
print("   ✅ Spalte 'gruppe' bereit")

# 1. Lösche alte Layouts
print("\n1️⃣ Lösche alte Layouts...")
cur.execute("DELETE FROM public.sys_layout")
deleted = cur.rowcount
conn.commit()
print(f"   ✅ {deleted} alte Layouts gelöscht")

# 2. Erstelle neue Theme-Datensätze
print("\n2️⃣ Erstelle neue Theme-Datensätze...")

themes = [
    (THEME_BLUE_UID, "Blue Theme", COLORS_BLUE),
    (THEME_GREEN_UID, "Green Theme", COLORS_GREEN),
    (THEME_ORANGE_UID, "Orange Theme", COLORS_ORANGE),
]

for theme_uid, theme_name, colors in themes:
    # Ein Datensatz pro Theme mit allen Gruppen im daten-JSON
    theme_data = {
        "ROOT": {
            "bezeichnung": theme_name,
            "description": f"{theme_name} color scheme",
            "created": "2026-01-05"
        },
        "light": {
            "colors": colors["light"],
            "typography": TYPOGRAPHY,
            "customizations": CUSTOMIZATIONS
        },
        "dark": {
            "colors": colors["dark"],
            "typography": TYPOGRAPHY,
            "customizations": CUSTOMIZATIONS
        }
    }
    
    cur.execute("""
        INSERT INTO public.sys_layout (uid, daten, name, historisch, created_at, modified_at)
        VALUES (%s, %s, %s, 0, NOW(), NOW())
    """, (theme_uid, json.dumps(theme_data), theme_name))
    
    print(f"   ✅ {theme_name} erstellt (1 Datensatz mit ROOT, light, dark Gruppen)")

conn.commit()

# 3. Aktualisiere Mandanten-Konfiguration
print("\n3️⃣ Aktualisiere Mandanten-Konfiguration...")

# Mapping: Mandant → Theme
mandant_themes = {
    "e51a8688-2cca-4a16-855d-52a69677fb50": THEME_ORANGE_UID,  # Filiale Test 1
    "790a8e80-92f6-43b9-92fa-90d5699c6709": THEME_BLUE_UID,    # Filiale Test 2
    "91b106b8-b90b-4450-a07b-4eb3556dc407": THEME_GREEN_UID,   # Ganz neu
    "1804094a-a8fc-4c58-b9ad-d837a15b98e6": THEME_ORANGE_UID,  # PDVM Hauptmandant
    "55555555-5555-5555-5555-555555555555": THEME_GREEN_UID,   # Properies_control
    "66666666-6666-6666-6666-666666666666": THEME_BLUE_UID,    # Template neuer Satz
}

# Verbinde mit auth DB für sys_mandanten
conn_auth = psycopg2.connect(
    host="localhost",
    port=5432,
    user="postgres",
    password="Polari$55",
    database="auth"
)
cur_auth = conn_auth.cursor()

for mandant_uid, theme_uid in mandant_themes.items():
    # Lese aktuelle daten
    cur_auth.execute("SELECT daten FROM sys_mandanten WHERE uid = %s", (mandant_uid,))
    row = cur_auth.fetchone()
    
    if row:
        daten = row[0] if isinstance(row[0], dict) else json.loads(row[0])
        
        # Füge Theme-Config hinzu
        if 'config' not in daten:
            daten['config'] = {}
        
        daten['config']['THEME_GUID'] = theme_uid
        daten['config']['THEME_LIGHT'] = 'light'
        daten['config']['THEME_DARK'] = 'dark'
        
        # Update
        cur_auth.execute("""
            UPDATE sys_mandanten 
            SET daten = %s, modified_at = NOW()
            WHERE uid = %s
        """, (json.dumps(daten), mandant_uid))
        
        print(f"   ✅ {daten.get('name', mandant_uid)}: Theme {theme_uid[:8]}...")

conn_auth.commit()
conn_auth.close()

# 4. Zusammenfassung
print("\n" + "=" * 60)
print("✅ Migration abgeschlossen!")
print("\nNeue Struktur:")
print(f"  • 3 Theme-Datensätze (Blue, Green, Orange)")
print(f"  • Jedes Theme enthält ROOT, light, dark Gruppen im daten-JSON")
print(f"  • 6 Mandanten mit THEME_GUID Referenzen")
print("\nVorteile:")
print("  ✓ Zugriff: THEME_GUID → Datensatz → Gruppe lesen")
print("  ✓ Weitere Layouts zu jedem Farbschema hinzufügbar")
print("  ✓ Themes zentral definiert")
print("  ✓ Einfach erweiterbar (neue Themes/Modi)")

cur.close()
conn.close()

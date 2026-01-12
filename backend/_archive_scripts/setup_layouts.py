"""
Setup Layout-Daten für bestehende Mandanten
Erstellt Hell/Dunkel-Themes für alle aktiven Mandanten
"""
import asyncio
import asyncpg
import json
from uuid import uuid4

DB_PASSWORD = "Polari$55"

# Farbschemata für verschiedene Mandanten
COLOR_SCHEMES = {
    "blue": {
        "light": {
            "primary": {"50": "#e3f2fd", "100": "#bbdefb", "200": "#90caf9", "300": "#64b5f6", "400": "#42a5f5", "500": "#2196f3", "600": "#1e88e5", "700": "#1976d2", "800": "#1565c0", "900": "#0d47a1"},
            "secondary": {"50": "#fff3e0", "100": "#ffe0b2", "200": "#ffcc80", "300": "#ffb74d", "400": "#ffa726", "500": "#ff9800", "600": "#fb8c00", "700": "#f57c00", "800": "#ef6c00", "900": "#e65100"},
            "neutral": {"50": "#fafafa", "100": "#f5f5f5", "200": "#eeeeee", "300": "#e0e0e0", "400": "#bdbdbd", "500": "#9e9e9e", "600": "#757575", "700": "#616161", "800": "#424242", "900": "#212121"},
            "success": "#4caf50",
            "warning": "#ff9800",
            "error": "#f44336",
            "info": "#2196f3",
            "background": {"primary": "#ffffff", "secondary": "#f5f5f5", "tertiary": "#eeeeee"},
            "text": {"primary": "#212121", "secondary": "#757575", "disabled": "#bdbdbd", "inverse": "#ffffff"},
            "border": {"light": "#e0e0e0", "medium": "#bdbdbd", "dark": "#757575"}
        },
        "dark": {
            "primary": {"50": "#e3f2fd", "100": "#bbdefb", "200": "#90caf9", "300": "#64b5f6", "400": "#42a5f5", "500": "#42a5f5", "600": "#1e88e5", "700": "#1976d2", "800": "#1565c0", "900": "#0d47a1"},
            "secondary": {"50": "#fff3e0", "100": "#ffe0b2", "200": "#ffcc80", "300": "#ffb74d", "400": "#ffa726", "500": "#ffb74d", "600": "#fb8c00", "700": "#f57c00", "800": "#ef6c00", "900": "#e65100"},
            "neutral": {"50": "#1a1a1a", "100": "#2a2a2a", "200": "#3a3a3a", "300": "#4a4a4a", "400": "#6a6a6a", "500": "#8a8a8a", "600": "#aaaaaa", "700": "#cacaca", "800": "#e0e0e0", "900": "#f5f5f5"},
            "success": "#66bb6a",
            "warning": "#ffb74d",
            "error": "#ef5350",
            "info": "#42a5f5",
            "background": {"primary": "#121212", "secondary": "#1e1e1e", "tertiary": "#2a2a2a"},
            "text": {"primary": "#ffffff", "secondary": "#b0b0b0", "disabled": "#6a6a6a", "inverse": "#212121"},
            "border": {"light": "#333333", "medium": "#4a4a4a", "dark": "#6a6a6a"}
        }
    },
    "green": {
        "light": {
            "primary": {"50": "#e8f5e9", "100": "#c8e6c9", "200": "#a5d6a7", "300": "#81c784", "400": "#66bb6a", "500": "#4caf50", "600": "#43a047", "700": "#388e3c", "800": "#2e7d32", "900": "#1b5e20"},
            "secondary": {"50": "#f3e5f5", "100": "#e1bee7", "200": "#ce93d8", "300": "#ba68c8", "400": "#ab47bc", "500": "#9c27b0", "600": "#8e24aa", "700": "#7b1fa2", "800": "#6a1b9a", "900": "#4a148c"},
            "neutral": {"50": "#fafafa", "100": "#f5f5f5", "200": "#eeeeee", "300": "#e0e0e0", "400": "#bdbdbd", "500": "#9e9e9e", "600": "#757575", "700": "#616161", "800": "#424242", "900": "#212121"},
            "success": "#4caf50",
            "warning": "#ff9800",
            "error": "#f44336",
            "info": "#2196f3",
            "background": {"primary": "#fafafa", "secondary": "#f0f0f0", "tertiary": "#e5e5e5"},
            "text": {"primary": "#1b5e20", "secondary": "#616161", "disabled": "#bdbdbd", "inverse": "#ffffff"},
            "border": {"light": "#e0e0e0", "medium": "#bdbdbd", "dark": "#757575"}
        },
        "dark": {
            "primary": {"50": "#e8f5e9", "100": "#c8e6c9", "200": "#a5d6a7", "300": "#81c784", "400": "#66bb6a", "500": "#66bb6a", "600": "#43a047", "700": "#388e3c", "800": "#2e7d32", "900": "#1b5e20"},
            "secondary": {"50": "#f3e5f5", "100": "#e1bee7", "200": "#ce93d8", "300": "#ba68c8", "400": "#ab47bc", "500": "#ba68c8", "600": "#8e24aa", "700": "#7b1fa2", "800": "#6a1b9a", "900": "#4a148c"},
            "neutral": {"50": "#1a1a1a", "100": "#2a2a2a", "200": "#3a3a3a", "300": "#4a4a4a", "400": "#6a6a6a", "500": "#8a8a8a", "600": "#aaaaaa", "700": "#cacaca", "800": "#e0e0e0", "900": "#f5f5f5"},
            "success": "#66bb6a",
            "warning": "#ffb74d",
            "error": "#ef5350",
            "info": "#42a5f5",
            "background": {"primary": "#1a1a1a", "secondary": "#252525", "tertiary": "#303030"},
            "text": {"primary": "#e8f5e9", "secondary": "#aaaaaa", "disabled": "#6a6a6a", "inverse": "#212121"},
            "border": {"light": "#333333", "medium": "#4a4a4a", "dark": "#6a6a6a"}
        }
    },
    "orange": {
        "light": {
            "primary": {"50": "#fff3e0", "100": "#ffe0b2", "200": "#ffcc80", "300": "#ffb74d", "400": "#ffa726", "500": "#ff9800", "600": "#fb8c00", "700": "#f57c00", "800": "#ef6c00", "900": "#e65100"},
            "secondary": {"50": "#e3f2fd", "100": "#bbdefb", "200": "#90caf9", "300": "#64b5f6", "400": "#42a5f5", "500": "#2196f3", "600": "#1e88e5", "700": "#1976d2", "800": "#1565c0", "900": "#0d47a1"},
            "neutral": {"50": "#fafafa", "100": "#f5f5f5", "200": "#eeeeee", "300": "#e0e0e0", "400": "#bdbdbd", "500": "#9e9e9e", "600": "#757575", "700": "#616161", "800": "#424242", "900": "#212121"},
            "success": "#4caf50",
            "warning": "#ff9800",
            "error": "#f44336",
            "info": "#2196f3",
            "background": {"primary": "#ffffff", "secondary": "#fff8f3", "tertiary": "#fff0e5"},
            "text": {"primary": "#e65100", "secondary": "#757575", "disabled": "#bdbdbd", "inverse": "#ffffff"},
            "border": {"light": "#e0e0e0", "medium": "#bdbdbd", "dark": "#757575"}
        },
        "dark": {
            "primary": {"50": "#fff3e0", "100": "#ffe0b2", "200": "#ffcc80", "300": "#ffb74d", "400": "#ffa726", "500": "#ffb74d", "600": "#fb8c00", "700": "#f57c00", "800": "#ef6c00", "900": "#e65100"},
            "secondary": {"50": "#e3f2fd", "100": "#bbdefb", "200": "#90caf9", "300": "#64b5f6", "400": "#42a5f5", "500": "#42a5f5", "600": "#1e88e5", "700": "#1976d2", "800": "#1565c0", "900": "#0d47a1"},
            "neutral": {"50": "#1a1a1a", "100": "#2a2a2a", "200": "#3a3a3a", "300": "#4a4a4a", "400": "#6a6a6a", "500": "#8a8a8a", "600": "#aaaaaa", "700": "#cacaca", "800": "#e0e0e0", "900": "#f5f5f5"},
            "success": "#66bb6a",
            "warning": "#ffb74d",
            "error": "#ef5350",
            "info": "#42a5f5",
            "background": {"primary": "#1a1200", "secondary": "#251a10", "tertiary": "#302015"},
            "text": {"primary": "#ffe0b2", "secondary": "#aaaaaa", "disabled": "#6a6a6a", "inverse": "#212121"},
            "border": {"light": "#333333", "medium": "#4a4a4a", "dark": "#6a6a6a"}
        }
    }
}

# Typografie-Einstellungen
TYPOGRAPHY_BASE = {
    "fontFamily": {
        "primary": "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
        "secondary": "'Roboto', sans-serif",
        "mono": "'Fira Code', 'Courier New', monospace"
    },
    "fontSize": {
        "scale": 1.0,
        "base": "16px",
        "xs": "0.75rem",
        "sm": "0.875rem",
        "md": "1rem",
        "lg": "1.125rem",
        "xl": "1.25rem",
        "2xl": "1.5rem",
        "3xl": "1.875rem",
        "4xl": "2.25rem"
    },
    "fontWeight": {
        "light": 300,
        "normal": 400,
        "medium": 500,
        "semibold": 600,
        "bold": 700
    },
    "lineHeight": {
        "tight": 1.25,
        "normal": 1.5,
        "relaxed": 1.75
    }
}

# Anpassungen
CUSTOMIZATIONS_BASE = {
    "animations": {
        "enabled": True,
        "duration": "200ms",
        "easing": "cubic-bezier(0.4, 0, 0.2, 1)"
    },
    "shadows": {
        "enabled": True,
        "intensity": "medium"
    },
    "borderRadius": {
        "sm": "4px",
        "md": "8px",
        "lg": "12px",
        "full": "9999px"
    }
}


async def get_mandanten():
    """Lädt alle aktiven Mandanten"""
    conn = await asyncpg.connect(f"postgresql://postgres:{DB_PASSWORD}@localhost:5432/auth")
    try:
        rows = await conn.fetch("SELECT uid, name, daten FROM sys_mandanten WHERE historisch = 0")
        return [dict(row) for row in rows]
    finally:
        await conn.close()


async def check_sys_layout_exists():
    """Prüft ob sys_layout Tabelle existiert"""
    conn = await asyncpg.connect(f"postgresql://postgres:{DB_PASSWORD}@localhost:5432/pdvm_system")
    try:
        result = await conn.fetchval("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'sys_layout'
            )
        """)
        return result
    finally:
        await conn.close()


async def create_layout_for_mandant(mandant_uid: str, mandant_name: str, color_scheme: str):
    """Erstellt Layout-Einträge (light + dark) für einen Mandanten"""
    conn = await asyncpg.connect(f"postgresql://postgres:{DB_PASSWORD}@localhost:5432/pdvm_system")
    
    try:
        colors = COLOR_SCHEMES.get(color_scheme, COLOR_SCHEMES["blue"])
        
        # Light Theme
        light_daten = {
            "mandant_uid": mandant_uid,
            "mandant_name": mandant_name,
            "theme": "light",
            "colors": colors["light"],
            "typography": TYPOGRAPHY_BASE,
            "customizations": CUSTOMIZATIONS_BASE,
            "assets": {
                "logo": {
                    "light": f"/assets/{mandant_name.lower()}/logo_light.svg",
                    "dark": f"/assets/{mandant_name.lower()}/logo_dark.svg"
                }
            }
        }
        
        await conn.execute("""
            INSERT INTO sys_layout (uid, daten, name, historisch, gilt_bis, created_at, modified_at)
            VALUES ($1, $2, $3, 0, '9999365.00000', NOW(), NOW())
            ON CONFLICT (uid) DO NOTHING
        """, uuid4(), json.dumps(light_daten), f"{mandant_name} - Light Theme")
        
        # Dark Theme
        dark_daten = {
            "mandant_uid": mandant_uid,
            "mandant_name": mandant_name,
            "theme": "dark",
            "colors": colors["dark"],
            "typography": TYPOGRAPHY_BASE,
            "customizations": CUSTOMIZATIONS_BASE,
            "assets": {
                "logo": {
                    "light": f"/assets/{mandant_name.lower()}/logo_light.svg",
                    "dark": f"/assets/{mandant_name.lower()}/logo_dark.svg"
                }
            }
        }
        
        await conn.execute("""
            INSERT INTO sys_layout (uid, daten, name, historisch, gilt_bis, created_at, modified_at)
            VALUES ($1, $2, $3, 0, '9999365.00000', NOW(), NOW())
            ON CONFLICT (uid) DO NOTHING
        """, uuid4(), json.dumps(dark_daten), f"{mandant_name} - Dark Theme")
        
        print(f"✅ Layout erstellt für: {mandant_name} ({color_scheme})")
        
    finally:
        await conn.close()


async def main():
    print("🎨 Layout-Setup für PDVM System")
    print("=" * 50)
    
    # Prüfe ob sys_layout existiert
    if not await check_sys_layout_exists():
        print("❌ sys_layout Tabelle existiert nicht!")
        print("   Führe zuerst schema_pdvm_system.sql aus")
        return
    
    print("✅ sys_layout Tabelle gefunden")
    
    # Lade Mandanten
    mandanten = await get_mandanten()
    print(f"\n📋 {len(mandanten)} aktive Mandanten gefunden:")
    
    for m in mandanten:
        print(f"   - {m['name']} ({m['uid']})")
    
    # Weise Farbschemata zu (Round-Robin)
    schemes = ["blue", "green", "orange"]
    
    print("\n🎨 Erstelle Layouts...")
    for idx, mandant in enumerate(mandanten):
        color_scheme = schemes[idx % len(schemes)]
        await create_layout_for_mandant(
            str(mandant['uid']),
            mandant['name'],
            color_scheme
        )
    
    print("\n✅ Layout-Setup abgeschlossen!")
    print("\nNächste Schritte:")
    print("1. Backend API-Endpoint erstellen (GET /api/layout/{mandant_uid})")
    print("2. Frontend Theme-Loader implementieren")
    print("3. CSS Custom Properties dynamisch laden")


if __name__ == "__main__":
    asyncio.run(main())

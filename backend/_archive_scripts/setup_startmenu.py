"""
Erstellt das Startmenü in sys_menudaten
Basierend auf Desktop-Version mit VERTIKAL, GRUND, ZUSATZ Bereichen
"""
import asyncio
import asyncpg
import json
from app.core.pdvm_datetime import now_pdvm

# Database URL
DATABASE_URL = "postgresql://postgres:Polari$55@localhost:5432/pdvm_system"

# Startmenü-GUID (wird in MEINEAPPS.START.MENU verwendet)
STARTMENU_GUID = "5ca6674e-b9ce-4581-9756-64e742883f80"

# Startmenü-Struktur (aus Desktop-Version)
STARTMENU_DATA = {
    "VERTIKAL": {
        "c8bef35f-2cdf-49b6-934b-4cddf5b80303": {
            "type": "BUTTON",
            "label": "Personalwesen",
            "sort_order": 0,
            "parent_guid": None,
            "template_guid": None,
            "icon": None,
            "visible": True,
            "enabled": True,
            "tooltip": None,
            "command": {
                "handler": "open_app_menu",
                "params": {
                    "app_name": "PERSONALWESEN"
                }
            }
        },
        "cea83e84-32ea-4361-8b33-8cea9df12b1c": {
            "type": "BUTTON",
            "label": "Finanzwesen",
            "sort_order": 1,
            "parent_guid": None,
            "template_guid": None,
            "icon": None,
            "visible": True,
            "enabled": True,
            "tooltip": None,
            "command": {
                "handler": "open_app_menu",
                "params": {
                    "app_name": "FINANZWESEN"
                }
            }
        },
        "3f9005ad-2507-44a0-a856-146272d5c267": {
            "type": "BUTTON",
            "label": "Benutzerdaten",
            "sort_order": 2,
            "parent_guid": None,
            "template_guid": None,
            "icon": None,
            "visible": True,
            "enabled": True,
            "tooltip": None,
            "command": {
                "handler": "open_app_menu",
                "params": {
                    "app_name": "BENUTZERDATEN"
                }
            }
        },
        "37a77e4a-7d27-4349-92ee-4daae15f9a8d": {
            "type": "BUTTON",
            "label": "Administration",
            "sort_order": 3,
            "parent_guid": None,
            "template_guid": None,
            "icon": None,
            "visible": True,
            "enabled": True,
            "tooltip": None,
            "command": {
                "handler": "open_app_menu",
                "params": {
                    "app_name": "ADMINISTRATION"
                }
            }
        },
        "5412d2d5-0402-42ce-bff6-f1886858a67e": {
            "type": "BUTTON",
            "label": "Testbereich",
            "sort_order": 4,
            "parent_guid": None,
            "template_guid": None,
            "icon": None,
            "visible": True,
            "enabled": True,
            "tooltip": None,
            "command": {
                "handler": "open_app_menu",
                "params": {
                    "app_name": "TESTBEREICH"
                }
            }
        },
        "6353ee28-c72b-4843-9b00-3d5f846a5de9": {
            "type": "SEPARATOR",
            "label": "Unbekannt",
            "sort_order": 3,
            "parent_guid": "fecf6732-8ec4-4b0b-8bfd-eddf0c18af88",
            "template_guid": None,
            "icon": None,
            "visible": True,
            "enabled": True,
            "tooltip": None,
            "command": None
        }
    },
    "GRUND": {
        "fecf6732-8ec4-4b0b-8bfd-eddf0c18af88": {
            "type": "SUBMENU",
            "label": "Basis",
            "sort_order": 0,
            "parent_guid": None,
            "template_guid": None,
            "icon": None,
            "visible": True,
            "enabled": True,
            "tooltip": None,
            "command": None
        },
        "c9662797-e446-4f59-a37d-f652c42d15b9": {
            "type": "BUTTON",
            "label": "Hilfe",
            "sort_order": 0,
            "parent_guid": "fecf6732-8ec4-4b0b-8bfd-eddf0c18af88",
            "template_guid": None,
            "icon": None,
            "visible": True,
            "enabled": True,
            "tooltip": None,
            "command": {
                "handler": "show_help",
                "params": {
                    "help_text": "Admin-Startmenü Hilfe",
                    "help_type": "dialog"
                }
            }
        },
        "ae473e8a-12a9-4dda-97f0-a743d0f96498": {
            "type": "SEPARATOR",
            "label": "Separator",
            "sort_order": 1,
            "parent_guid": "fecf6732-8ec4-4b0b-8bfd-eddf0c18af88",
            "template_guid": None,
            "icon": None,
            "visible": True,
            "enabled": True,
            "tooltip": None,
            "command": None
        },
        "ca8bbdcb-afea-44d6-8b10-f28ebf13d88e": {
            "guid": "ca8bbdcb-afea-44d6-8b10-f28ebf13d88e",
            "type": "BUTTON",
            "label": "Abmelden",
            "icon": None,
            "command": {
                "handler": "logout",
                "params": {}
            },
            "parent_guid": "fecf6732-8ec4-4b0b-8bfd-eddf0c18af88",
            "sort_order": 2,
            "visible": True,
            "enabled": True,
            "tooltip": None,
            "_gruppe": "GRUND",
            "template_guid": None
        }
    },
    "ZUSATZ": {},
    "ROOT": {
        "VERSION": "V3",
        "MIGRATED_FROM": "V2",
        "VERTIKAL": "vert",
        "GRUND": "hori_1",
        "ZUSATZ": "hori_2"
    }
}


async def setup_startmenu():
    """Erstellt das Startmenü in der Datenbank"""
    
    print("🔧 Erstelle Startmenü in sys_menudaten...")
    print(f"   Menü-GUID: {STARTMENU_GUID}")
    
    conn = await asyncpg.connect(DATABASE_URL)
    
    try:
        # Prüfen ob Menü bereits existiert
        existing = await conn.fetchrow(
            "SELECT uid, name FROM sys_menudaten WHERE uid = $1",
            STARTMENU_GUID
        )
        
        if existing:
            print(f"\n⚠️  Startmenü existiert bereits!")
            print(f"   UUID: {existing['uid']}")
            print(f"   Name: {existing['name']}")
            
            # Aktualisieren
            await conn.execute("""
                UPDATE sys_menudaten 
                SET daten = $1,
                    modified_at = NOW()
                WHERE uid = $2
            """, json.dumps(STARTMENU_DATA), STARTMENU_GUID)
            
            print(f"\n🔄 Startmenü aktualisiert!")
        else:
            # Neu erstellen
            await conn.execute("""
                INSERT INTO sys_menudaten (uid, name, daten, historisch, created_at, modified_at)
                VALUES ($1, $2, $3, 0, NOW(), NOW())
            """, STARTMENU_GUID, "Admin Startmenü", json.dumps(STARTMENU_DATA))
            
            print(f"\n✅ Startmenü erstellt!")
        
        # Menü laden und anzeigen
        menu = await conn.fetchrow(
            "SELECT uid, name, daten FROM sys_menudaten WHERE uid = $1",
            STARTMENU_GUID
        )
        
        menu_data = json.loads(menu['daten']) if isinstance(menu['daten'], str) else menu['daten']
        
        print(f"\n📊 Menü-Struktur:")
        print(f"   • VERTIKAL: {len(menu_data['VERTIKAL'])} Items")
        for item_guid, item in menu_data['VERTIKAL'].items():
            print(f"     - {item['label']} ({item['type']})")
        
        print(f"   • GRUND: {len(menu_data['GRUND'])} Items")
        for item_guid, item in menu_data['GRUND'].items():
            parent = f" → {item['parent_guid'][:8]}..." if item.get('parent_guid') else ""
            print(f"     - {item['label']} ({item['type']}){parent}")
        
        print(f"   • ZUSATZ: {len(menu_data['ZUSATZ'])} Items")
        print(f"   • ROOT: Version {menu_data['ROOT']['VERSION']}")
        
        print(f"\n🎯 Verwendung:")
        print(f"   User MEINEAPPS.START.MENU = {STARTMENU_GUID}")
        print(f"   API: GET /api/menu/{STARTMENU_GUID}")
        
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(setup_startmenu())

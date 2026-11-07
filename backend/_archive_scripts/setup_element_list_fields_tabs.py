"""
Setup Element-List FIELDS und TABS
===================================

Erstellt:
1. Element-List Definitionen für FIELDS und TABS in sys_framedaten
2. Control-Definitionen in sys_control_dict für beide Listen
3. Einzelne Feld-Definitionen in sys_control_dict für List-Felder

GUIDs:
- FIELDS: 9ccb9eb8-ae9f-4308-97b7-a9e78b3d5c78
- TABS: d0bc10ca-3f00-46c7-96ad-91118e31c1f8
"""

import asyncio
import asyncpg
import json
import uuid
from datetime import datetime

DEFAULT_DB_URL = "postgresql://postgres:Polari$55@localhost:5432/pdvm_system"

# =============================================================================
# GUIDs für Element-Lists
# =============================================================================
FIELDS_LIST_GUID = "9ccb9eb8-ae9f-4308-97b7-a9e78b3d5c78"
TABS_LIST_GUID = "d0bc10ca-3f00-46c7-96ad-91118e31c1f8"

# =============================================================================
# Feld-Definitionen für FIELDS Element-List
# =============================================================================
FIELDS_LIST_FIELDS = {
    "name": {
        "guid": "f1a1a1a1-0001-4001-8001-100000000001",
        "name": "name",
        "label": "Feldname",
        "type": "string",
        "table": "sys_framedaten",
        "gruppe": "FIELDS",
        "display_order": 10,
        "read_only": False,
        "help_text": "Technischer Name des Feldes (z.B. 'familienname')"
    },
    "label": {
        "guid": "f1a1a1a1-0002-4001-8001-100000000002",
        "name": "label",
        "label": "Anzeigelabel",
        "type": "string",
        "table": "sys_framedaten",
        "gruppe": "FIELDS",
        "display_order": 20,
        "read_only": False,
        "help_text": "Anzeigename für das Feld (z.B. 'Familienname')"
    },
    "type": {
        "guid": "f1a1a1a1-0003-4001-8001-100000000003",
        "name": "type",
        "label": "Feldtyp",
        "type": "dropdown",
        "table": "sys_framedaten",
        "gruppe": "FIELDS",
        "display_order": 30,
        "read_only": False,
        "help_text": "Datentyp des Feldes",
        "configs": {
            "dropdown": {
                "options": [
                    {"value": "string", "label": "Text (einzeilig)"},
                    {"value": "text", "label": "Text (mehrzeilig)"},
                    {"value": "dropdown", "label": "Auswahlliste"},
                    {"value": "true_false", "label": "Ja/Nein"},
                    {"value": "date", "label": "Datum"},
                    {"value": "datetime", "label": "Datum + Zeit"},
                    {"value": "number", "label": "Zahl"},
                    {"value": "guid", "label": "GUID-Referenz"}
                ]
            }
        }
    },
    "table": {
        "guid": "f1a1a1a1-0004-4001-8001-100000000004",
        "name": "table",
        "label": "Zieltabelle",
        "type": "string",
        "table": "sys_framedaten",
        "gruppe": "FIELDS",
        "display_order": 40,
        "read_only": False,
        "help_text": "Datenbank-Tabelle (z.B. 'persondaten')"
    },
    "gruppe": {
        "guid": "f1a1a1a1-0005-4001-8001-100000000005",
        "name": "gruppe",
        "label": "Datengruppe",
        "type": "string",
        "table": "sys_framedaten",
        "gruppe": "FIELDS",
        "display_order": 50,
        "read_only": False,
        "help_text": "Logische Gruppe in der Tabelle (z.B. 'PERSDATEN')"
    },
    "feld": {
        "guid": "f1a1a1a1-0006-4001-8001-100000000006",
        "name": "feld",
        "label": "Feldschlüssel",
        "type": "string",
        "table": "sys_framedaten",
        "gruppe": "FIELDS",
        "display_order": 60,
        "read_only": False,
        "help_text": "Feldschlüssel in der Datengruppe (z.B. 'FAMILIENNAME')"
    },
    "display_order": {
        "guid": "f1a1a1a1-0007-4001-8001-100000000007",
        "name": "display_order",
        "label": "Anzeigereihenfolge",
        "type": "number",
        "table": "sys_framedaten",
        "gruppe": "FIELDS",
        "display_order": 70,
        "read_only": False,
        "help_text": "Position in der Anzeige (niedrigere Zahlen zuerst)"
    },
    "read_only": {
        "guid": "f1a1a1a1-0008-4001-8001-100000000008",
        "name": "read_only",
        "label": "Nur Lesen",
        "type": "true_false",
        "table": "sys_framedaten",
        "gruppe": "FIELDS",
        "display_order": 80,
        "read_only": False,
        "help_text": "Feld kann nicht bearbeitet werden"
    }
}

# =============================================================================
# Feld-Definitionen für TABS Element-List
# =============================================================================
TABS_LIST_FIELDS = {
    "tab_id": {
        "guid": "a1a1a1a1-0001-4001-8001-200000000001",
        "name": "tab_id",
        "label": "Tab-ID",
        "type": "number",
        "table": "sys_framedaten",
        "gruppe": "TABS",
        "display_order": 10,
        "read_only": False,
        "help_text": "Eindeutige Nummer des Tabs (1, 2, 3, ...)"
    },
    "tab_label": {
        "guid": "a1a1a1a1-0002-4001-8001-200000000002",
        "name": "tab_label",
        "label": "Tab-Bezeichnung",
        "type": "string",
        "table": "sys_framedaten",
        "gruppe": "TABS",
        "display_order": 20,
        "read_only": False,
        "help_text": "Anzeigename des Tabs (z.B. 'Stammdaten', 'Kontakt')"
    },
    "tab_icon": {
        "guid": "a1a1a1a1-0003-4001-8001-200000000003",
        "name": "tab_icon",
        "label": "Tab-Icon",
        "type": "string",
        "table": "sys_framedaten",
        "gruppe": "TABS",
        "display_order": 30,
        "read_only": False,
        "help_text": "Icon-Name für den Tab (optional)"
    },
    "tab_order": {
        "guid": "a1a1a1a1-0004-4001-8001-200000000004",
        "name": "tab_order",
        "label": "Tab-Reihenfolge",
        "type": "number",
        "table": "sys_framedaten",
        "gruppe": "TABS",
        "display_order": 40,
        "read_only": False,
        "help_text": "Position des Tabs (1 = erster Tab)"
    },
    "tab_visible": {
        "guid": "a1a1a1a1-0005-4001-8001-200000000005",
        "name": "tab_visible",
        "label": "Tab sichtbar",
        "type": "true_false",
        "table": "sys_framedaten",
        "gruppe": "TABS",
        "display_order": 50,
        "read_only": False,
        "help_text": "Tab ist standardmäßig sichtbar"
    }
}


async def setup_element_lists():
    """Erstellt Element-List Struktur für FIELDS und TABS."""
    conn = await asyncpg.connect(DEFAULT_DB_URL)
    
    try:
        # =============================================================================
        # 1. Einzelne Feld-Definitionen in sys_control_dict erstellen
        # =============================================================================
        print("\n📝 Erstelle Feld-Definitionen in sys_control_dict...")
        
        # FIELDS List Felder
        for field_key, field_def in FIELDS_LIST_FIELDS.items():
            field_guid = uuid.UUID(field_def["guid"])
            field_daten = {
                "name": field_def["name"],
                "label": field_def["label"],
                "type": field_def["type"],
                "table": field_def["table"],
                "gruppe": field_def["gruppe"],
                "display_order": field_def["display_order"],
                "read_only": field_def["read_only"]
            }
            
            if "help_text" in field_def:
                field_daten["help_text"] = field_def["help_text"]
            
            if "configs" in field_def:
                field_daten["configs"] = field_def["configs"]
            
            await conn.execute("""
                INSERT INTO sys_control_dict (uid, name, daten, historisch, created_at, modified_at)
                VALUES ($1, $2, $3, 0, NOW(), NOW())
                ON CONFLICT (uid) DO UPDATE
                SET daten = EXCLUDED.daten, modified_at = NOW()
            """, field_guid, field_def["name"], json.dumps(field_daten))
            
            print(f"  ✅ {field_def['name']} ({field_def['label']})")
        
        # TABS List Felder
        for field_key, field_def in TABS_LIST_FIELDS.items():
            field_guid = uuid.UUID(field_def["guid"])
            field_daten = {
                "name": field_def["name"],
                "label": field_def["label"],
                "type": field_def["type"],
                "table": field_def["table"],
                "gruppe": field_def["gruppe"],
                "display_order": field_def["display_order"],
                "read_only": field_def["read_only"]
            }
            
            if "help_text" in field_def:
                field_daten["help_text"] = field_def["help_text"]
            
            await conn.execute("""
                INSERT INTO sys_control_dict (uid, name, daten, historisch, created_at, modified_at)
                VALUES ($1, $2, $3, 0, NOW(), NOW())
                ON CONFLICT (uid) DO UPDATE
                SET daten = EXCLUDED.daten, modified_at = NOW()
            """, field_guid, field_def["name"], json.dumps(field_daten))
            
            print(f"  ✅ {field_def['name']} ({field_def['label']})")
        
        # =============================================================================
        # 2. Element-List Definitionen in sys_control_dict
        # =============================================================================
        print("\n📋 Erstelle Element-List Definitionen in sys_control_dict...")
        
        # FIELDS Element-List
        fields_list_daten = {
            "name": "FIELDS",
            "label": "Feld-Liste",
            "type": "element_list",
            "table": "sys_framedaten",
            "gruppe": "ELEMENTS",
            "element_fields": [
                field_def["guid"] for field_def in FIELDS_LIST_FIELDS.values()
            ],
            "display_order": 100,
            "read_only": False,
            "help_text": "Liste von Feld-Definitionen für das Frame"
        }
        
        fields_list_guid = uuid.UUID(FIELDS_LIST_GUID)
        await conn.execute("""
            INSERT INTO sys_control_dict (uid, name, daten, historisch, created_at, modified_at)
            VALUES ($1, $2, $3, 0, NOW(), NOW())
            ON CONFLICT (uid) DO UPDATE
            SET daten = EXCLUDED.daten, modified_at = NOW()
        """, fields_list_guid, "FIELDS", json.dumps(fields_list_daten))
        
        print(f"  ✅ FIELDS Element-List ({FIELDS_LIST_GUID})")
        
        # TABS Element-List
        tabs_list_daten = {
            "name": "TABS",
            "label": "Tab-Liste",
            "type": "element_list",
            "table": "sys_framedaten",
            "gruppe": "ELEMENTS",
            "element_fields": [
                field_def["guid"] for field_def in TABS_LIST_FIELDS.values()
            ],
            "display_order": 200,
            "read_only": False,
            "help_text": "Liste von Tab-Definitionen für das Frame"
        }
        
        tabs_list_guid = uuid.UUID(TABS_LIST_GUID)
        await conn.execute("""
            INSERT INTO sys_control_dict (uid, name, daten, historisch, created_at, modified_at)
            VALUES ($1, $2, $3, 0, NOW(), NOW())
            ON CONFLICT (uid) DO UPDATE
            SET daten = EXCLUDED.daten, modified_at = NOW()
        """, tabs_list_guid, "TABS", json.dumps(tabs_list_daten))
        
        print(f"  ✅ TABS Element-List ({TABS_LIST_GUID})")
        
        # =============================================================================
        # 3. Frame-Definitionen in sys_framedaten
        # =============================================================================
        print("\n🎯 Erstelle Frame-Definitionen in sys_framedaten...")
        
        # FIELDS Frame
        fields_frame_guid = uuid.UUID("55555555-0001-4001-8001-000000000001")
        fields_frame_daten = {
            "ROOT": {
                "FRAME_TYPE": "element_list",
                "TABLE": "sys_framedaten",
                "GRUPPE": "ELEMENTS"
            },
            "FIELDS": {
                field_def["guid"]: {
                    "dict_ref": field_def["guid"]
                }
                for field_def in FIELDS_LIST_FIELDS.values()
            }
        }
        
        await conn.execute("""
            INSERT INTO sys_framedaten (uid, name, daten, historisch, created_at, modified_at)
            VALUES ($1, $2, $3, 0, NOW(), NOW())
            ON CONFLICT (uid) DO UPDATE
            SET daten = EXCLUDED.daten, modified_at = NOW()
        """, fields_frame_guid, "Element-List FIELDS Template", json.dumps(fields_frame_daten))
        
        print(f"  ✅ FIELDS Frame-Template ({fields_frame_guid})")
        
        # TABS Frame
        tabs_frame_guid = uuid.UUID("55555555-0002-4001-8001-000000000002")
        tabs_frame_daten = {
            "ROOT": {
                "FRAME_TYPE": "element_list",
                "TABLE": "sys_framedaten",
                "GRUPPE": "ELEMENTS"
            },
            "TABS": {
                field_def["guid"]: {
                    "dict_ref": field_def["guid"]
                }
                for field_def in TABS_LIST_FIELDS.values()
            }
        }
        
        await conn.execute("""
            INSERT INTO sys_framedaten (uid, name, daten, historisch, created_at, modified_at)
            VALUES ($1, $2, $3, 0, NOW(), NOW())
            ON CONFLICT (uid) DO UPDATE
            SET daten = EXCLUDED.daten, modified_at = NOW()
        """, tabs_frame_guid, "Element-List TABS Template", json.dumps(tabs_frame_daten))
        
        print(f"  ✅ TABS Frame-Template ({tabs_frame_guid})")
        
        # =============================================================================
        # Zusammenfassung
        # =============================================================================
        print("\n" + "="*80)
        print("✅ SETUP ERFOLGREICH ABGESCHLOSSEN")
        print("="*80)
        print(f"\n📊 Erstellt:")
        print(f"  • {len(FIELDS_LIST_FIELDS)} Feld-Definitionen für FIELDS")
        print(f"  • {len(TABS_LIST_FIELDS)} Feld-Definitionen für TABS")
        print(f"  • 2 Element-List Definitionen in sys_control_dict")
        print(f"  • 2 Frame-Templates in sys_framedaten")
        print(f"\n🔑 GUIDs:")
        print(f"  • FIELDS Element-List: {FIELDS_LIST_GUID}")
        print(f"  • TABS Element-List: {TABS_LIST_GUID}")
        print(f"  • FIELDS Frame-Template: {fields_frame_guid}")
        print(f"  • TABS Frame-Template: {tabs_frame_guid}")
        
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(setup_element_lists())

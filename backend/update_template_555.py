#!/usr/bin/env python3
"""
Aktualisiert Template 555555... mit neuer configs.element_list Struktur

Änderungen:
1. configs.element_list statt configs.element_list.frame_guid
2. help_text/tooltip entfernt
3. SELF_NAME Regel: Tabellenpräfix (sys_)
"""

import asyncpg
import asyncio
import json
from uuid import UUID

async def main():
    conn = await asyncpg.connect('postgresql://postgres:Polari$55@localhost:5432/pdvm_system')
    
    try:
        # Neues Template mit Standards
        new_template = {
            "MODUL": {
                "edit": {
                    "name": "",
                    "type": "string",
                    "label": "",
                    "table": "",
                    "gruppe": "",
                    "feld": "",
                    "SELF_NAME": "",
                    "modul_type": "edit",
                    "parent_guid": None,
                    "display_order": 0,
                    "read_only": False,
                    "abdatum": False,
                    "historical": False,
                    "source_path": "root",
                    "configs": {
                        "element_list": {
                            "frame_guid": {},
                            "element_list_parent": ""
                        }
                    }
                },
                "view": {
                    "name": "",
                    "type": "string",
                    "label": "",
                    "table": "",
                    "gruppe": "",
                    "feld": "",
                    "SELF_NAME": "",
                    "modul_type": "view",
                    "parent_guid": None,
                    "display_order": 99,
                    "show": True,
                    "sortable": True,
                    "searchable": True,
                    "filterType": "contains",
                    "sortDirection": "asc",
                    "sortByOriginal": False,
                    "expert_mode": True,
                    "expert_order": 99,
                    "control_type": "base",
                    "default": "",
                    "dropdown": None,
                    "configs": {
                        "element_list": {
                            "frame_guid": {},
                            "element_list_parent": ""
                        }
                    }
                },
                "tabs": {
                    "name": "",
                    "type": "element_list",
                    "label": "",
                    "table": "",
                    "gruppe": "",
                    "SELF_NAME": "",
                    "modul_type": "tabs",
                    "parent_guid": None,
                    "display_order": 200,
                    "read_only": False,
                    "element_fields": [],
                    "element_frame_guid": None,
                    "configs": {
                        "element_list": {
                            "frame_guid": {},
                            "element_list_parent": ""
                        }
                    }
                }
            }
        }
        
        # Altes Template laden
        print("=" * 70)
        print("📄 Altes Template 555555...")
        print("=" * 70)
        old_template = await conn.fetchrow(
            'SELECT daten FROM sys_control_dict WHERE uid = $1',
            UUID('55555555-5555-5555-5555-555555555555')
        )
        
        if old_template:
            print(json.dumps(old_template['daten'], indent=2, ensure_ascii=False))
        
        # Neues Template speichern
        print("\n" + "=" * 70)
        print("💾 Aktualisiere Template 555555...")
        print("=" * 70)
        
        await conn.execute("""
            UPDATE sys_control_dict
            SET daten = $1,
                modified_at = NOW()
            WHERE uid = $2
        """, json.dumps(new_template), UUID('55555555-5555-5555-5555-555555555555'))
        
        print("✅ Template aktualisiert")
        
        # Neues Template anzeigen
        print("\n" + "=" * 70)
        print("📄 Neues Template 555555...")
        print("=" * 70)
        print(json.dumps(new_template, indent=2, ensure_ascii=False))
        
        # Änderungen zusammenfassen
        print("\n" + "=" * 70)
        print("📊 Änderungen:")
        print("=" * 70)
        print("✅ configs.element_list Struktur standardisiert")
        print("✅ help_text/tooltip entfernt (wird über configs referenziert)")
        print("✅ SELF_NAME Feld hinzugefügt (Regel: Tabellenpräfix)")
        print("✅ modul_type explizit in jedem Template")
        print("✅ Alle Standard-Felder definiert")
        
    finally:
        await conn.close()

if __name__ == '__main__':
    asyncio.run(main())

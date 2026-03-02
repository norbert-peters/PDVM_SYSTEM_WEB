#!/usr/bin/env python3
"""
Erstellt Frame für configs.element_list (Referenzen zu help/dropdown/etc)

Struktur:
{
  "label": "",   // Display-Label für UI
  "key": "",     // Referenz-Key (z.B. "help", "dropdown")
  "feld": "",    // Feldname in Zieltabelle
  "table": "",   // Zieltabelle (z.B. sys_systemdaten)
  "gruppe": ""   // Gruppe (wenn leer → Sprache in Großbuchstaben)
}
"""

import asyncpg
import asyncio
import json
import uuid
from uuid import UUID

async def main():
    conn = await asyncpg.connect('postgresql://postgres:Polari$55@localhost:5432/pdvm_system')
    
    try:
        # Frame GUID
        frame_guid = uuid.uuid4()
        
        # Frame-Struktur
        frame_data = {
            "ROOT": {
                "TABLE": "sys_control_dict",
                "SELF_GUID": str(frame_guid),
                "SELF_NAME": "Config Reference Frame",
                "IS_ELEMENT": True,
                "TABS": 0
            },
            "FIELDS": {
                # label - Display-Label für UI
                str(uuid.uuid4()): {
                    "name": "label",
                    "type": "string",
                    "label": "Label",
                    "feld": "label",
                    "gruppe": "ROOT",
                    "table": "sys_control_dict",
                    "display_order": 10,
                    "read_only": False,
                    "SELF_NAME": "config_ref_label"
                },
                # key - Referenz-Key (help, dropdown, etc)
                str(uuid.uuid4()): {
                    "name": "key",
                    "type": "string",
                    "label": "Key",
                    "feld": "key",
                    "gruppe": "ROOT",
                    "table": "sys_control_dict",
                    "display_order": 20,
                    "read_only": False,
                    "SELF_NAME": "config_ref_key"
                },
                # feld - Feldname in Zieltabelle
                str(uuid.uuid4()): {
                    "name": "feld",
                    "type": "string",
                    "label": "Feld",
                    "feld": "feld",
                    "gruppe": "ROOT",
                    "table": "sys_control_dict",
                    "display_order": 30,
                    "read_only": False,
                    "SELF_NAME": "config_ref_feld"
                },
                # table - Zieltabelle
                str(uuid.uuid4()): {
                    "name": "table",
                    "type": "string",
                    "label": "Tabelle",
                    "feld": "table",
                    "gruppe": "ROOT",
                    "table": "sys_control_dict",
                    "display_order": 40,
                    "read_only": False,
                    "SELF_NAME": "config_ref_table"
                },
                # gruppe - Gruppe (leer = Sprache)
                str(uuid.uuid4()): {
                    "name": "gruppe",
                    "type": "string",
                    "label": "Gruppe",
                    "feld": "gruppe",
                    "gruppe": "ROOT",
                    "table": "sys_control_dict",
                    "display_order": 50,
                    "read_only": False,
                    "SELF_NAME": "config_ref_gruppe"
                }
            },
            "TABS": {}
        }
        
        # Frame in sys_framedaten einfügen
        print("=" * 70)
        print("📦 Erstelle Config Reference Frame")
        print("=" * 70)
        print(f"GUID: {frame_guid}")
        print()
        
        await conn.execute("""
            INSERT INTO sys_framedaten (
                uid, name, daten, historisch, created_at, modified_at
            ) VALUES (
                $1, $2, $3, 0, NOW(), NOW()
            )
        """, frame_guid, "Config Reference Frame", json.dumps(frame_data))
        
        print("✅ Frame erstellt")
        print()
        print(json.dumps(frame_data, indent=2, ensure_ascii=False))
        
        # Dokumentation
        print("\n" + "=" * 70)
        print("📋 Verwendung")
        print("=" * 70)
        print("1. In Template 555555... configs.element_list.frame_guid setzen:")
        print(f'   "frame_guid": "{frame_guid}"')
        print()
        print("2. Element-Struktur:")
        print("""   {
     "label": "Hilfetext",
     "key": "help",
     "feld": "feldname",
     "table": "sys_systemdaten",
     "gruppe": ""  // Leer = Sprache in Großbuchstaben (DE-DE)
   }""")
        print()
        print("3. Sprach-Regel:")
        print("   gruppe leer → Sprache aus GCS (z.B. DE-DE)")
        print("   gruppe gesetzt → Exakte Gruppe verwenden")
        
        # Template-Update Hinweis
        print("\n" + "=" * 70)
        print("⚠️  WICHTIG: Template 555555... manuell aktualisieren")
        print("=" * 70)
        print("UPDATE sys_control_dict")
        print("SET daten = jsonb_set(")
        print("  daten,")
        print("  '{MODUL,edit,configs,element_list,frame_guid}',")
        print(f"  '\"{frame_guid}\"'::jsonb")
        print(")")
        print(f"WHERE uid = '55555555-5555-5555-5555-555555555555';")
        
    finally:
        await conn.close()

if __name__ == '__main__':
    asyncio.run(main())

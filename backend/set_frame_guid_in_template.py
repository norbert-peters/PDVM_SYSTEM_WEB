#!/usr/bin/env python3
"""
Setzt frame_guid in Template 555555... für alle Modul-Typen
"""

import asyncpg
import asyncio
import json
from uuid import UUID

FRAME_GUID = "c22edb00-c930-4a0b-8884-542b6d34e83d"

async def main():
    conn = await asyncpg.connect('postgresql://postgres:Polari$55@localhost:5432/pdvm_system')
    
    try:
        # Template laden
        template = await conn.fetchrow(
            'SELECT daten FROM sys_control_dict WHERE uid = $1',
            UUID('55555555-5555-5555-5555-555555555555')
        )
        
        if not template:
            print("❌ Template 555555... nicht gefunden")
            return
        
        # Parse JSON wenn String
        template_data = template['daten']
        if isinstance(template_data, str):
            template_data = json.loads(template_data)
        
        # frame_guid in allen Modul-Typen setzen
        for modul_type in ['edit', 'view', 'tabs']:
            if modul_type in template_data['MODUL']:
                template_data['MODUL'][modul_type]['configs']['element_list']['frame_guid'] = FRAME_GUID
        
        # Template aktualisieren
        await conn.execute("""
            UPDATE sys_control_dict
            SET daten = $1,
                modified_at = NOW()
            WHERE uid = $2
        """, json.dumps(template_data), UUID('55555555-5555-5555-5555-555555555555'))
        
        print("=" * 70)
        print("✅ Template 555555... aktualisiert")
        print("=" * 70)
        print(f"frame_guid: {FRAME_GUID}")
        print()
        print("Gesetzt in:")
        print("  • MODUL.edit.configs.element_list.frame_guid")
        print("  • MODUL.view.configs.element_list.frame_guid")
        print("  • MODUL.tabs.configs.element_list.frame_guid")
        print()
        print(json.dumps(template_data, indent=2, ensure_ascii=False))
        
    finally:
        await conn.close()

if __name__ == '__main__':
    asyncio.run(main())

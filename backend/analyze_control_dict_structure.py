#!/usr/bin/env python3
"""
Analysiert sys_control_dict Struktur und Templates für edit_dict Implementation
"""

import asyncpg
import asyncio
import json
from uuid import UUID

async def main():
    conn = await asyncpg.connect('postgresql://postgres:Polari$55@localhost:5432/pdvm_system')
    
    try:
        # 1. Template 666666... (Standard Template neuer Satz)
        print('=' * 70)
        print('📄 Template 666666... (Standard neuer Satz)')
        print('=' * 70)
        template_666 = await conn.fetchrow(
            'SELECT * FROM sys_control_dict WHERE uid = $1',
            UUID('66666666-6666-6666-6666-666666666666')
        )
        if template_666:
            print(f"Name: {template_666['name']}")
            print(json.dumps(template_666['daten'], indent=2, ensure_ascii=False))
        else:
            print("❌ Template nicht gefunden")
        
        # 2. Template 555555... (Modul-Templates)
        print('\n' + '=' * 70)
        print('📄 Template 555555... (Modul-Templates)')
        print('=' * 70)
        template_555 = await conn.fetchrow(
            'SELECT * FROM sys_control_dict WHERE uid = $1',
            UUID('55555555-5555-5555-5555-555555555555')
        )
        if template_555:
            print(f"Name: {template_555['name']}")
            print(json.dumps(template_555['daten'], indent=2, ensure_ascii=False))
        else:
            print("❌ Template nicht gefunden")
        
        # 3. Vorhandene MODUL_TYPE
        print('\n' + '=' * 70)
        print('📋 Vorhandene MODUL_TYPE in sys_control_dict')
        print('=' * 70)
        modul_types = await conn.fetch("""
            SELECT 
                daten->>'modul_type' as modul_type,
                COUNT(*) as anzahl
            FROM sys_control_dict
            WHERE historisch = 0
              AND uid NOT IN (
                  '00000000-0000-0000-0000-000000000000', 
                  '66666666-6666-6666-6666-666666666666',
                  '55555555-5555-5555-5555-555555555555'
              )
            GROUP BY daten->>'modul_type'
            ORDER BY anzahl DESC
        """)
        
        for mt in modul_types:
            print(f"  • {mt['modul_type'] or 'NULL'}: {mt['anzahl']} Controls")
        
        # 4. Control-Struktur Beispiele
        print('\n' + '=' * 70)
        print('📋 Control-Struktur Beispiele')
        print('=' * 70)
        
        for mtype in ['edit', 'tabs', 'view']:
            example = await conn.fetchrow("""
                SELECT name, daten
                FROM sys_control_dict
                WHERE historisch = 0
                  AND daten->>'modul_type' = $1
                  AND uid NOT IN (
                      '00000000-0000-0000-0000-000000000000', 
                      '66666666-6666-6666-6666-666666666666',
                      '55555555-5555-5555-5555-555555555555'
                  )
                LIMIT 1
            """, mtype)
            
            if example:
                print(f"\n{mtype.upper()} Control: {example['name']}")
                print(json.dumps(example['daten'], indent=2, ensure_ascii=False))
        
        # 5. Prüfe auf configs (element_list)
        print('\n' + '=' * 70)
        print('🔍 Controls mit configs (element_list)')
        print('=' * 70)
        
        configs_check = await conn.fetch("""
            SELECT name, daten->'configs' as configs
            FROM sys_control_dict
            WHERE historisch = 0
              AND daten ? 'configs'
              AND uid NOT IN (
                  '00000000-0000-0000-0000-000000000000', 
                  '66666666-6666-6666-6666-666666666666',
                  '55555555-5555-5555-5555-555555555555'
              )
        """)
        
        if configs_check:
            print(f"✅ {len(configs_check)} Controls mit configs gefunden:")
            for c in configs_check:
                print(f"  • {c['name']}: {c['configs']}")
        else:
            print("⚠️  Keine Controls mit configs gefunden")
        
        # 6. Prüfe auf tooltip_ref
        print('\n' + '=' * 70)
        print('🔍 Controls mit tooltip_ref')
        print('=' * 70)
        
        tooltip_check = await conn.fetch("""
            SELECT name, daten->'tooltip_ref' as tooltip_ref
            FROM sys_control_dict
            WHERE historisch = 0
              AND daten ? 'tooltip_ref'
              AND uid NOT IN (
                  '00000000-0000-0000-0000-000000000000', 
                  '66666666-6666-6666-6666-666666666666',
                  '55555555-5555-5555-5555-555555555555'
              )
        """)
        
        if tooltip_check:
            print(f"✅ {len(tooltip_check)} Controls mit tooltip_ref gefunden:")
            for c in tooltip_check:
                print(f"  • {c['name']}: {c['tooltip_ref']}")
        else:
            print("⚠️  Keine Controls mit tooltip_ref gefunden")
        
        # 7. Struktur-Felder in Controls
        print('\n' + '=' * 70)
        print('📊 Häufige Felder in Control.daten')
        print('=' * 70)
        
        # Hole alle Keys aus allen Controls
        all_controls = await conn.fetch("""
            SELECT daten
            FROM sys_control_dict
            WHERE historisch = 0
              AND uid NOT IN (
                  '00000000-0000-0000-0000-000000000000', 
                  '66666666-6666-6666-6666-666666666666',
                  '55555555-5555-5555-5555-555555555555'
              )
        """)
        
        key_counts = {}
        for ctrl in all_controls:
            for key in ctrl['daten'].keys():
                key_counts[key] = key_counts.get(key, 0) + 1
        
        sorted_keys = sorted(key_counts.items(), key=lambda x: x[1], reverse=True)
        for key, count in sorted_keys[:15]:
            percentage = (count / len(all_controls)) * 100
            print(f"  • {key:20s}: {count:2d} Controls ({percentage:.0f}%)")
    
    finally:
        await conn.close()

if __name__ == '__main__':
    asyncio.run(main())

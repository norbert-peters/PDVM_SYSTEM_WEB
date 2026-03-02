#!/usr/bin/env python3
"""
Markiert alle alten Controls in sys_control_dict mit 'old_' Präfix

Zweck: Vorbereitung für Neuanlage mit edit_dict
Ausnahmen: Templates (000000..., 666666..., 555555...)
"""

import asyncpg
import asyncio
from uuid import UUID

FICTIONAL_GUIDS = [
    UUID('00000000-0000-0000-0000-000000000000'),
    UUID('66666666-6666-6666-6666-666666666666'),
    UUID('55555555-5555-5555-5555-555555555555')
]

async def main():
    conn = await asyncpg.connect('postgresql://postgres:Polari$55@localhost:5432/pdvm_system')
    
    try:
        # Hole alle Controls außer Templates
        controls = await conn.fetch("""
            SELECT uid, name
            FROM sys_control_dict
            WHERE historisch = 0
              AND uid NOT IN ($1, $2, $3)
            ORDER BY name
        """, *FICTIONAL_GUIDS)
        
        print(f"🔧 Markiere {len(controls)} Controls mit 'old_' Präfix")
        print("=" * 70)
        
        updated = 0
        skipped = 0
        
        for ctrl in controls:
            current_name = ctrl['name']
            
            # Skip wenn bereits old_ Präfix
            if current_name.startswith('old_'):
                print(f"⏭️  {current_name} - bereits markiert")
                skipped += 1
                continue
            
            # Neuer Name mit old_ Präfix
            new_name = f"old_{current_name}"
            
            # Update
            await conn.execute("""
                UPDATE sys_control_dict
                SET name = $1,
                    modified_at = NOW()
                WHERE uid = $2
            """, new_name, ctrl['uid'])
            
            print(f"✅ {current_name} → {new_name}")
            updated += 1
        
        print("\n" + "=" * 70)
        print(f"📊 Ergebnis:")
        print(f"   Aktualisiert: {updated}")
        print(f"   Übersprungen: {skipped}")
        print(f"   Templates:    {len(FICTIONAL_GUIDS)} (unverändert)")
        
    finally:
        await conn.close()

if __name__ == '__main__':
    asyncio.run(main())

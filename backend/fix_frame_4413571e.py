"""
Korrigiert das Edit Frame 4413571e-6bf6-4f42-b81a-bc898db4880c
damit es sich selbst darstellen kann.
"""
import asyncio
import asyncpg
import json

async def fix_frame():
    conn = await asyncpg.connect('postgresql://postgres:Polari$55@localhost:5432/pdvm_system')
    
    try:
        # 1. Aktuellen Zustand laden
        row = await conn.fetchrow(
            'SELECT uid, name, daten FROM sys_framedaten WHERE uid = $1',
            '4413571e-6bf6-4f42-b81a-bc898db4880c'
        )
        
        if not row:
            print("❌ Frame nicht gefunden!")
            return
        
        print("📋 Aktueller Zustand:")
        print(f"  UID: {row['uid']}")
        print(f"  Name: {row['name']}")
        
        daten = row['daten']
        if isinstance(daten, str):
            daten = json.loads(daten)
        
        print(f"  ROOT.TABLE: {daten.get('ROOT', {}).get('TABLE', 'NICHT GESETZT')}")
        
        # 2. ROOT.TABLE korrigieren
        if 'ROOT' not in daten:
            daten['ROOT'] = {}
        
        daten['ROOT']['TABLE'] = 'sys_framedaten'
        
        # Sicherstellen, dass EDIT_TYPE gesetzt ist
        if 'EDIT_TYPE' not in daten['ROOT']:
            daten['ROOT']['EDIT_TYPE'] = 'edit_frame'
        
        # 3. Update in Datenbank
        await conn.execute(
            'UPDATE sys_framedaten SET daten = $1, modified_at = NOW() WHERE uid = $2',
            json.dumps(daten),
            '4413571e-6bf6-4f42-b81a-bc898db4880c'
        )
        
        print("\n✅ Frame korrigiert:")
        print(f"  ROOT.TABLE: {daten['ROOT']['TABLE']}")
        print(f"  ROOT.EDIT_TYPE: {daten['ROOT'].get('EDIT_TYPE')}")
        
        # 4. Erneut prüfen
        row = await conn.fetchrow(
            'SELECT daten FROM sys_framedaten WHERE uid = $1',
            '4413571e-6bf6-4f42-b81a-bc898db4880c'
        )
        
        check_daten = row['daten']
        if isinstance(check_daten, str):
            check_daten = json.loads(check_daten)
        
        print(f"\n🔍 Verifikation:")
        print(f"  ROOT.TABLE: {check_daten.get('ROOT', {}).get('TABLE')}")
        
        # 5. Zeige Controls-Übersicht
        print(f"\n📦 Controls im Frame:")
        if 'FIELDS' in daten:
            for control_guid, control_data in daten['FIELDS'].items():
                if isinstance(control_data, dict):
                    label = control_data.get('label', 'Kein Label')
                    ctrl_type = control_data.get('type', 'unknown')
                    print(f"  • {control_guid[:8]}... - {label} ({ctrl_type})")
        
        print("\n✅ Frame ist jetzt self-editing und sollte sich selbst darstellen können!")
    
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(fix_frame())

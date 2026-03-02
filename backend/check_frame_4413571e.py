"""
Prüft den sys_framedaten Datensatz 4413571e-6bf6-4f42-b81a-bc898db4880c
"""
import asyncio
import asyncpg
import json

async def check_frame():
    conn = await asyncpg.connect('postgresql://postgres:Polari$55@localhost:5432/pdvm_system')
    
    try:
        # Datensatz laden
        row = await conn.fetchrow(
            'SELECT uid, name, daten FROM sys_framedaten WHERE uid = $1',
            '4413571e-6bf6-4f42-b81a-bc898db4880c'
        )
        
        if not row:
            print("❌ Datensatz nicht gefunden!")
            return
        
        print("="*80)
        print(f"📋 Frame-Datensatz: {row['uid']}")
        print(f"📝 Name: {row['name']}")
        print("="*80)
        
        daten = row['daten']
        if isinstance(daten, str):
            daten = json.loads(daten)
        
        if not daten:
            print("❌ Keine Daten im JSONB-Feld!")
            return
        
        print("\n📊 Daten-Struktur:")
        print(f"  • Hauptgruppen: {list(daten.keys())}")
        
        if 'ROOT' in daten:
            print(f"\n🎯 ROOT:")
            for key, value in daten['ROOT'].items():
                print(f"    • {key}: {value}")
        
        # Zähle Controls in allen Gruppen
        total_controls = 0
        for key, value in daten.items():
            if key != 'ROOT' and isinstance(value, dict):
                controls = len(value)
                total_controls += controls
                print(f"\n📦 Gruppe {key}: {controls} Controls")
                # Zeige erste 3 Control-GUIDs
                for i, (control_guid, control_data) in enumerate(list(value.items())[:3]):
                    if isinstance(control_data, dict):
                        name = control_data.get('name', control_data.get('feld', '???'))
                        label = control_data.get('label', '???')
                        print(f"    [{i+1}] {control_guid[:8]}... - {name} ({label})")
        
        print(f"\n📊 Gesamt: {total_controls} Controls")
        
        # Prüfe ob es ein Edit-Frame für sich selbst ist
        if 'ROOT' in daten:
            table = daten['ROOT'].get('TABLE', '')
            if table == 'sys_framedaten':
                print(f"\n✅ Frame ist self-editing (TABLE=sys_framedaten)")
            else:
                print(f"\n⚠️ Frame zeigt auf andere Tabelle: {table}")
    
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(check_frame())

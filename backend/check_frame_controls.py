"""
Prüft alle Controls im Frame 4413571e und ob sie in sys_control_dict existieren
"""
import asyncio
import asyncpg
import json

async def check_controls():
    conn = await asyncpg.connect('postgresql://postgres:Polari$55@localhost:5432/pdvm_system')
    
    try:
        # 1. Frame laden
        row = await conn.fetchrow(
            'SELECT daten FROM sys_framedaten WHERE uid = $1',
            '4413571e-6bf6-4f42-b81a-bc898db4880c'
        )
        
        daten = row['daten']
        if isinstance(daten, str):
            daten = json.loads(daten)
        
        print("="*80)
        print("🔍 Prüfe Controls im Frame")
        print("="*80)
        
        if 'FIELDS' not in daten:
            print("❌ Keine FIELDS Gruppe im Frame!")
            return
        
        fields = daten['FIELDS']
        
        for control_guid, control_data in fields.items():
            print(f"\n📦 Control GUID: {control_guid}")
            
            # Prüfe ob GUID-Format
            try:
                guid_obj = control_guid
                # In sys_control_dict nachschauen
                dict_row = await conn.fetchrow(
                    'SELECT uid, name, daten FROM sys_control_dict WHERE uid = $1',
                    control_guid
                )
                
                if dict_row:
                    dict_daten = dict_row['daten']
                    if isinstance(dict_daten, str):
                        dict_daten = json.loads(dict_daten)
                    
                    print(f"  ✅ Gefunden in sys_control_dict:")
                    print(f"     Name: {dict_row['name']}")
                    print(f"     Label: {dict_daten.get('label', 'N/A')}")
                    print(f"     Type: {dict_daten.get('type', 'NICHT GESETZT')}")
                    print(f"     Table: {dict_daten.get('table', 'N/A')}")
                    print(f"     Gruppe: {dict_daten.get('gruppe', 'N/A')}")
                    
                    # Zeige merged result
                    if isinstance(control_data, dict):
                        merged = {**dict_daten, **control_data}
                        print(f"  📝 Nach Merge:")
                        print(f"     Type: {merged.get('type', 'NICHT GESETZT')}")
                        print(f"     Label: {merged.get('label', 'N/A')}")
                else:
                    print(f"  ❌ NICHT in sys_control_dict gefunden!")
                    if isinstance(control_data, dict):
                        print(f"     Local Data: {control_data}")
            
            except Exception as e:
                print(f"  ⚠️ Fehler: {e}")
        
        print("\n" + "="*80)
        
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(check_controls())

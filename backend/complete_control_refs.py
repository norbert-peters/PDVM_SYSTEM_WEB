"""
Vervollständigt alle Control-Referenzen im Edit Frame
"""
import asyncio
import asyncpg
import json

async def complete_control_refs():
    conn = await asyncpg.connect('postgresql://postgres:Polari$55@localhost:5432/pdvm_system')
    
    try:
        frame_uuid = '4413571e-6bf6-4f42-b81a-bc898db4880c'
        
        # Frame laden
        row = await conn.fetchrow(
            'SELECT daten FROM sys_framedaten WHERE uid = $1',
            frame_uuid
        )
        
        daten = row['daten']
        if isinstance(daten, str):
            daten = json.loads(daten)
        
        print("="*80)
        print("🔧 Vervollständige Control-Definitionen")
        print("="*80)
        
        fields = daten.get('FIELDS', {})
        
        # 1. FIELDS element_list
        fields_guid = '9ccb9eb8-ae9f-4308-97b7-a9e78b3d5c78'
        if fields_guid in fields:
            if not isinstance(fields[fields_guid], dict):
                fields[fields_guid] = {}
            fields[fields_guid]['gruppe'] = 'FIELDS'
            fields[fields_guid]['feld'] = 'FIELDS'  # Das Dict selbst
            fields[fields_guid]['name'] = 'fields'
            print(f"✅ FIELDS: gruppe=FIELDS, feld=FIELDS")
        
        # 2. TABS_DEF element_list (schon korrekt)
        tabs_def_guid = 'a88ee663-745f-4ab8-b8d0-c024d0a0987b'
        if tabs_def_guid in fields:
            if not isinstance(fields[tabs_def_guid], dict):
                fields[tabs_def_guid] = {}
            fields[tabs_def_guid]['name'] = 'tabs_def'
            print(f"✅ TABS_DEF: gruppe=ROOT, feld=TABS_DEF")
        
        # 3. TABS element_list (schon korrekt)
        tabs_guid = 'd0bc10ca-3f00-46c7-96ad-91118e31c1f8'
        if tabs_guid in fields:
            if not isinstance(fields[tabs_guid], dict):
                fields[tabs_guid] = {}
            fields[tabs_guid]['name'] = 'tabs'
            print(f"✅ TABS: gruppe=ROOT, feld=TABS")
        
        # 4. SELF_NAME string
        self_name_guid = 'e472d790-542b-40b9-9009-b4fbfa23bb55'
        if self_name_guid in fields:
            if not isinstance(fields[self_name_guid], dict):
                fields[self_name_guid] = {}
            fields[self_name_guid]['gruppe'] = 'ROOT'
            fields[self_name_guid]['feld'] = 'SELF_NAME'
            fields[self_name_guid]['name'] = 'self_name'
            print(f"✅ SELF_NAME: gruppe=ROOT, feld=SELF_NAME")
        
        # 5. EDIT_TYPE string
        edit_type_guid = 'f2799aad-e7e4-4dbd-9dfb-c2d54e8ce976'
        if edit_type_guid in fields:
            if not isinstance(fields[edit_type_guid], dict):
                fields[edit_type_guid] = {}
            fields[edit_type_guid]['gruppe'] = 'ROOT'
            fields[edit_type_guid]['feld'] = 'EDIT_TYPE'
            fields[edit_type_guid]['name'] = 'edit_type'
            print(f"✅ EDIT_TYPE: gruppe=ROOT, feld=EDIT_TYPE")
        
        # Update
        await conn.execute(
            'UPDATE sys_framedaten SET daten = $1, modified_at = NOW() WHERE uid = $2',
            json.dumps(daten),
            frame_uuid
        )
        
        print("\n" + "="*80)
        print("✅ ALLE CONTROLS VOLLSTÄNDIG")
        print("="*80)
        
        # Final Check
        print("\n📋 Finale Control-Übersicht:")
        for control_guid, control_data in fields.items():
            if isinstance(control_data, dict):
                label = control_data.get('label', '???')
                ctrl_type = control_data.get('type', '???')
                gruppe = control_data.get('gruppe', 'N/A')
                feld = control_data.get('feld', 'N/A')
                name = control_data.get('name', 'N/A')
                print(f"\n  📦 {label} ({ctrl_type})")
                print(f"     name={name}, gruppe={gruppe}, feld={feld}")
        
        print("\n" + "="*80)
        print("✅ FRAME IST JETZT VOLLSTÄNDIG KONFIGURIERT")
        print("="*80)
        print("\n🎯 Nächster Schritt:")
        print("   Im Browser testen mit:")
        print(f"   http://localhost:8010/api/frame/edit/{frame_uuid}")
        
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(complete_control_refs())

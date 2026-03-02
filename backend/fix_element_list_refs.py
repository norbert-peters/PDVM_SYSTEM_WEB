"""
Korrigiert die Gruppen-Referenzen im Edit Frame
damit element_list Controls auf die richtigen Daten zeigen
"""
import asyncio
import asyncpg
import json

async def fix_element_list_references():
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
        print("🔧 Korrigiere element_list Referenzen")
        print("="*80)
        
        # 1. FIELDS element_list: soll auf die FIELDS-Gruppe zeigen
        fields_guid = '9ccb9eb8-ae9f-4308-97b7-a9e78b3d5c78'
        if fields_guid in daten.get('FIELDS', {}):
            if not isinstance(daten['FIELDS'][fields_guid], dict):
                daten['FIELDS'][fields_guid] = {}
            
            # Lokales Override: Gruppe auf FIELDS setzen
            daten['FIELDS'][fields_guid]['gruppe'] = 'FIELDS'
            print(f"✅ FIELDS element_list → Gruppe: FIELDS")
        
        # 2. TABS_DEF element_list: soll auf ROOT.TABS_DEF zeigen
        tabs_def_guid = 'a88ee663-745f-4ab8-b8d0-c024d0a0987b'
        if tabs_def_guid in daten.get('FIELDS', {}):
            if not isinstance(daten['FIELDS'][tabs_def_guid], dict):
                daten['FIELDS'][tabs_def_guid] = {}
            
            # Lokales Override
            daten['FIELDS'][tabs_def_guid]['gruppe'] = 'ROOT'
            daten['FIELDS'][tabs_def_guid]['feld'] = 'TABS_DEF'
            print(f"✅ TABS_DEF element_list → Gruppe: ROOT, Feld: TABS_DEF")
        
        # 3. TABS element_list: sollte auf ROOT.TABS oder eine eigene Gruppe zeigen
        tabs_guid = 'd0bc10ca-3f00-46c7-96ad-91118e31c1f8'
        if tabs_guid in daten.get('FIELDS', {}):
            if not isinstance(daten['FIELDS'][tabs_guid], dict):
                daten['FIELDS'][tabs_guid] = {}
            
            # Lokales Override
            daten['FIELDS'][tabs_guid]['gruppe'] = 'ROOT'
            daten['FIELDS'][tabs_guid]['feld'] = 'TABS'
            print(f"✅ TABS element_list → Gruppe: ROOT, Feld: TABS")
        
        # 4. SELF_NAME und EDIT_TYPE schon korrekt
        
        # Update in DB
        await conn.execute(
            'UPDATE sys_framedaten SET daten = $1, modified_at = NOW() WHERE uid = $2',
            json.dumps(daten),
            frame_uuid
        )
        
        print("\n" + "="*80)
        print("✅ KORREKTUR ABGESCHLOSSEN")
        print("="*80)
        
        # Verifikation
        print("\n🔍 Verifikation:")
        for control_guid, control_data in daten['FIELDS'].items():
            if isinstance(control_data, dict):
                label = control_data.get('label', '???')
                gruppe = control_data.get('gruppe', 'NICHT GESETZT')
                feld = control_data.get('feld', control_data.get('name', '???'))
                print(f"  • {label}: Gruppe={gruppe}, Feld={feld}")
        
        print("\n✅ Das Frame sollte jetzt die Daten korrekt laden können!")
        
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(fix_element_list_references())

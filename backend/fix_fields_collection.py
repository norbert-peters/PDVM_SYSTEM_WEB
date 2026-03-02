"""
Korrigiert das FIELDS element_list Control:
Verwendet speziellen Marker für "bearbeite ganze Gruppe"
"""
import asyncio
import asyncpg
import json

async def fix_fields_element_list():
    conn = await asyncpg.connect('postgresql://postgres:Polari$55@localhost:5432/pdvm_system')
    
    try:
        frame_uuid = '4413571e-6bf6-4f42-b81a-bc898db4880c'
        
        print("="*80)
        print("🔧 Korrigiere FIELDS element_list Control")
        print("="*80)
        
        # Frame laden
        row = await conn.fetchrow(
            'SELECT daten FROM sys_framedaten WHERE uid = $1',
            frame_uuid
        )
        
        daten = row['daten']
        if isinstance(daten, str):
            daten = json.loads(daten)
        
        # FIELDS Control korrigieren
        fields_guid = '9ccb9eb8-ae9f-4308-97b7-a9e78b3d5c78'
        
        if fields_guid in daten.get('FIELDS', {}):
            if not isinstance(daten['FIELDS'][fields_guid], dict):
                daten['FIELDS'][fields_guid] = {}
            
            # Lösung: feld auf "__COLLECTION__" setzen
            # Das signalisiert dem Frontend: Bearbeite die ganze Gruppe als Dict
            daten['FIELDS'][fields_guid]['feld'] = '__COLLECTION__'
            
            # Alternative: feld leer lassen oder auf None setzen
            # daten['FIELDS'][fields_guid]['feld'] = None
            
            print(f"✅ FIELDS element_list korrigiert:")
            print(f"   gruppe=FIELDS, feld=__COLLECTION__")
            print(f"   → Frontend soll komplettes daten.FIELDS Dict bearbeiten")
        
        # Update in DB
        await conn.execute(
            'UPDATE sys_framedaten SET daten = $1, modified_at = NOW() WHERE uid = $2',
            json.dumps(daten),
            frame_uuid
        )
        
        print("\n" + "="*80)
        print("✅ KORREKTUR ABGESCHLOSSEN")
        print("="*80)
        
        print("\n📝 WICHTIG:")
        print("   Das Frontend muss __COLLECTION__ erkennen und:")
        print("   1. Das komplette Dict laden (nicht einzelnes Feld)")
        print("   2. Jedes Key-Value-Pair als Element der Liste behandeln")
        print("   3. Neue Elemente mit neuen GUIDs als Keys hinzufügen")
        
        print("\n📋 Alternative Lösungen:")
        print("   A) Eigenen edit_type für 'meta_editor' erstellen")
        print("   B) FIELDS-Daten in separate Liste transformieren")
        print("   C) Verschiedene Frames für Meta vs. Daten verwenden")
        
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(fix_fields_element_list())

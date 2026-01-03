"""
Prüft die Template-Struktur in der Datenbank
"""
import asyncio
import sys
import json
sys.path.insert(0, '.')
from app.core.pdvm_datenbank import PdvmDatabase
import uuid

async def check_template():
    db = PdvmDatabase('sys_mandanten')
    
    # Template laden
    template_uid = uuid.UUID('66666666-6666-6666-6666-666666666666')
    template = await db.get_by_uid(template_uid)
    
    if template:
        print('=== TEMPLATE DATEN-STRUKTUR ===')
        print(json.dumps(template['daten'], indent=2, ensure_ascii=False))
        
        print('\n=== GRUPPEN ===')
        for group in template['daten'].keys():
            print(f"\n{group}:")
            if isinstance(template['daten'][group], dict):
                for field in template['daten'][group].keys():
                    print(f"  - {field}")
    else:
        print('❌ Template nicht gefunden')
    
    # Properties laden
    properties_uid = uuid.UUID('55555555-5555-5555-5555-555555555555')
    properties = await db.get_by_uid(properties_uid)
    
    if properties:
        print('\n\n=== PROPERTIES CONTROL ===')
        props = properties['daten'].get('PROPERTIES_CONTROL', {})
        print(f"Anzahl Properties: {len(props)}")
        for field_name in sorted(props.keys())[:10]:  # Erste 10
            prop = props[field_name]
            print(f"  {field_name}: type={prop.get('type')}, label={prop.get('label')}")

asyncio.run(check_template())

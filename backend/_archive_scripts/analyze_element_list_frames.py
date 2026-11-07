"""
Analysiert element_lists und ihre Frame-Templates für Phase 4
"""
import asyncio
import asyncpg
import json

DB_URL = "postgresql://postgres:Polari$55@localhost:5432/pdvm_system"

async def analyze_element_lists():
    """Analysiert element_lists und potentielle Frame-Zuordnungen"""
    conn = await asyncpg.connect(DB_URL)
    
    try:
        print("=" * 80)
        print("🔍 Element-List Frame-Zuordnung Analyse (Phase 4)")
        print("=" * 80)
        
        # Alle element_list Controls laden
        controls = await conn.fetch("""
            SELECT uid, name, daten
            FROM public.sys_control_dict
            WHERE historisch = 0
        """)
        
        element_lists = []
        
        for row in controls:
            uid = row['uid']
            name = row['name']
            daten = row['daten']
            
            if isinstance(daten, str):
                daten = json.loads(daten)
            
            if daten.get('type') == 'element_list':
                element_lists.append({
                    'uid': str(uid),
                    'name': name,
                    'modul_type': daten.get('modul_type'),
                    'label': daten.get('label', ''),
                    'self_name': daten.get('SELF_NAME', name),
                    'element_frame_guid': daten.get('element_frame_guid')
                })
        
        print(f"\n📋 {len(element_lists)} element_lists gefunden:\n")
        
        for el in element_lists:
            print(f"🔷 {el['name']} ({el['modul_type']})")
            print(f"   UID: {el['uid']}")
            print(f"   Label: {el['label']}")
            print(f"   element_frame_guid: {el['element_frame_guid'] or 'NICHT GESETZT'}")
        
        # Alle Frames laden
        print("\n" + "=" * 80)
        print("📦 Verfügbare Frame-Templates")
        print("=" * 80)
        
        frames = await conn.fetch("""
            SELECT uid, name, daten
            FROM public.sys_framedaten
            WHERE historisch = 0
        """)
        
        template_frames = []
        
        for row in frames:
            uid = row['uid']
            name = row['name']
            daten = row['daten']
            
            if isinstance(daten, str):
                daten = json.loads(daten)
            
            # Frames mit "Template" im Namen oder spezielle element_list Frames
            if 'template' in name.lower() or 'element-list' in name.lower():
                root = daten.get('ROOT', {})
                template_frames.append({
                    'uid': str(uid),
                    'name': name,
                    'is_element': root.get('IS_ELEMENT', False),
                    'groups': list(daten.keys())
                })
        
        print(f"\n{len(template_frames)} Template-Frames gefunden:\n")
        
        for frame in template_frames:
            print(f"📄 {frame['name']}")
            print(f"   UID: {frame['uid']}")
            print(f"   IS_ELEMENT: {frame['is_element']}")
            print(f"   Gruppen: {', '.join(frame['groups'])}")
        
        # Vorschlag für Zuordnung
        print("\n" + "=" * 80)
        print("🎯 VORGESCHLAGENE ZUORDNUNG")
        print("=" * 80)
        
        mapping = []
        
        # tabs_def → Element-List TABS Template
        tabs_def = next((el for el in element_lists if el['name'] == 'tabs_def'), None)
        tabs_template = next((f for f in template_frames if 'TABS' in f['name'] and 'Element-List' in f['name']), None)
        
        if tabs_def and tabs_template:
            mapping.append({
                'element_list': tabs_def,
                'frame': tabs_template,
                'reason': 'tabs_def verwaltet Tab-Definitionen'
            })
        
        # fields → Element-List FIELDS Template
        fields = next((el for el in element_lists if el['name'] == 'fields'), None)
        fields_template = next((f for f in template_frames if 'FIELDS' in f['name'] and 'Element-List' in f['name']), None)
        
        if fields and fields_template:
            mapping.append({
                'element_list': fields,
                'frame': fields_template,
                'reason': 'fields verwaltet Feld-Definitionen'
            })
        
        # tabs → noch unklar (könnte eigenes Template brauchen)
        tabs = next((el for el in element_lists if el['name'] == 'tabs'), None)
        if tabs:
            mapping.append({
                'element_list': tabs,
                'frame': None,
                'reason': 'Noch unklar - eventuell eigenes Template nötig'
            })
        
        print()
        for m in mapping:
            el = m['element_list']
            frame = m['frame']
            print(f"✅ {el['name']} → {frame['name'] if frame else 'KEIN FRAME'}")
            print(f"   Element UID: {el['uid']}")
            if frame:
                print(f"   Frame UID: {frame['uid']}")
            print(f"   Grund: {m['reason']}")
            print()
        
        # Zusammenfassung
        print("=" * 80)
        print("📊 ZUSAMMENFASSUNG FÜR PHASE 4")
        print("=" * 80)
        
        print(f"\n   element_lists gesamt: {len(element_lists)}")
        print(f"   Mit element_frame_guid: {len([el for el in element_lists if el['element_frame_guid']])}")
        print(f"   Ohne element_frame_guid: {len([el for el in element_lists if not el['element_frame_guid']])}")
        print(f"   Template-Frames: {len(template_frames)}")
        print(f"   Gültige Zuordnungen: {len([m for m in mapping if m['frame']])}")
        
        return mapping
        
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(analyze_element_lists())

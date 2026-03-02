"""
Analysiert Control-Hierarchien für Phase 3
Identifiziert welche Controls zu welchen element_lists gehören
"""
import asyncio
import asyncpg
import json

DB_URL = "postgresql://postgres:Polari$55@localhost:5432/pdvm_system"

async def analyze_hierarchy():
    """Analysiert Control-Hierarchie"""
    conn = await asyncpg.connect(DB_URL)
    
    try:
        print("=" * 80)
        print("🔍 Control-Hierarchie Analyse (Phase 3 Vorbereitung)")
        print("=" * 80)
        
        # Alle Controls laden
        rows = await conn.fetch("""
            SELECT uid, name, daten
            FROM public.sys_control_dict
            WHERE historisch = 0
            ORDER BY name
        """)
        
        print(f"\n📦 {len(rows)} Controls gefunden\n")
        
        # Controls gruppieren
        element_lists = []
        edit_controls = []
        tabs_controls = []
        view_controls = []
        
        for row in rows:
            uid = row['uid']
            name = row['name']
            daten = row['daten']
            
            if isinstance(daten, str):
                daten = json.loads(daten)
            
            modul_type = daten.get('modul_type')
            control_type = daten.get('type')
            parent_guid = daten.get('parent_guid')
            self_name = daten.get('SELF_NAME', name)
            
            control_info = {
                'uid': str(uid),
                'name': name,
                'self_name': self_name,
                'modul_type': modul_type,
                'type': control_type,
                'parent_guid': str(parent_guid) if parent_guid else None
            }
            
            if control_type == 'element_list':
                element_lists.append(control_info)
            elif modul_type == 'edit':
                edit_controls.append(control_info)
            elif modul_type == 'tabs':
                tabs_controls.append(control_info)
            elif modul_type == 'view':
                view_controls.append(control_info)
        
        # Element Lists anzeigen
        print("=" * 80)
        print("📋 ELEMENT LISTS (Potentielle Parents)")
        print("=" * 80)
        
        for el in element_lists:
            print(f"\n🔷 {el['name']} ({el['modul_type']})")
            print(f"   UID: {el['uid']}")
            print(f"   SELF_NAME: {el['self_name']}")
            print(f"   Type: {el['type']}")
        
        # Hierarchie-Mapping ermitteln
        print("\n" + "=" * 80)
        print("🔗 HIERARCHIE-MAPPING (basierend auf Namens-Pattern)")
        print("=" * 80)
        
        hierarchy_map = {}
        
        # TABS element_list: tabs_def
        tabs_def = next((el for el in element_lists if el['name'] == 'tabs_def'), None)
        if tabs_def:
            print(f"\n📁 tabs_def → Child Controls:")
            hierarchy_map[tabs_def['uid']] = []
            
            # Alle Controls die mit "tab" beginnen und edit sind
            for ctrl in edit_controls:
                if ctrl['name'].startswith('tab') and not ctrl['name'] == 'tab_icon' and not ctrl['name'] == 'tab_label' and not ctrl['name'] == 'tab_id':
                    # tab01_head, tab01_gruppe, tab02_head, etc.
                    if ctrl['parent_guid'] is None or ctrl['parent_guid'] == 'None':
                        print(f"   → {ctrl['name']} ({ctrl['self_name']})")
                        hierarchy_map[tabs_def['uid']].append({
                            'uid': ctrl['uid'],
                            'name': ctrl['name'],
                            'self_name': ctrl['self_name']
                        })
        
        # FIELDS element_list: fields_def (falls vorhanden)
        fields_def = next((el for el in element_lists if el['name'] in ['fields_def', 'fields']), None)
        if fields_def:
            print(f"\n📁 {fields_def['name']} → Child Controls:")
            hierarchy_map[fields_def['uid']] = []
            
            # Hier wären field-spezifische Controls
            # (momentan keine erkennbar)
            print("   (keine Child-Controls identifiziert)")
        
        # Zusammenfassung
        print("\n" + "=" * 80)
        print("📊 ZUSAMMENFASSUNG")
        print("=" * 80)
        
        total_children = sum(len(children) for children in hierarchy_map.values())
        
        print(f"\n   Element Lists: {len(element_lists)}")
        print(f"   Child Controls: {total_children}")
        print(f"   Edit Controls (ohne parent): {len([c for c in edit_controls if not c['parent_guid'] or c['parent_guid'] == 'None'])}")
        
        # Migration-Kandidaten
        print("\n" + "=" * 80)
        print("🎯 MIGRATIONS-KANDIDATEN FÜR PHASE 3")
        print("=" * 80)
        
        for parent_uid, children in hierarchy_map.items():
            parent = next(el for el in element_lists if el['uid'] == parent_uid)
            if children:
                print(f"\n✅ {parent['name']} ({len(children)} Children)")
                for child in children:
                    print(f"   • {child['name']} → parent_guid = {parent_uid}")
        
        if total_children == 0:
            print("\n⚠️  Keine Child-Controls identifiziert")
            print("   Möglicherweise sind alle Controls bereits zugeordnet")
            print("   oder das Naming-Pattern ist anders als erwartet")
        
        return hierarchy_map
        
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(analyze_hierarchy())

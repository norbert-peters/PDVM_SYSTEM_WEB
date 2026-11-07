"""
Zeigt vollständige Control-Hierarchie nach Phase 3
"""
import asyncio
import asyncpg
import json

DB_URL = "postgresql://postgres:Polari$55@localhost:5432/pdvm_system"

async def show_hierarchy():
    """Zeigt Control-Hierarchie"""
    conn = await asyncpg.connect(DB_URL)
    
    try:
        print("=" * 80)
        print("🔍 Control-Hierarchie nach Phase 3")
        print("=" * 80)
        
        # Alle Controls laden
        rows = await conn.fetch("""
            SELECT uid, name, daten
            FROM public.sys_control_dict
            WHERE historisch = 0
            ORDER BY name
        """)
        
        print(f"\n📦 {len(rows)} Controls\n")
        
        # Nach Typ gruppieren
        element_lists = []
        children = []
        orphans = []
        
        for row in rows:
            uid = row['uid']
            name = row['name']
            daten = row['daten']
            
            if isinstance(daten, str):
                daten = json.loads(daten)
            
            control_type = daten.get('type')
            parent_guid = daten.get('parent_guid')
            modul_type = daten.get('modul_type')
            self_name = daten.get('SELF_NAME', name)
            label = daten.get('label', '')
            
            ctrl = {
                'uid': str(uid),
                'name': name,
                'self_name': self_name,
                'label': label,
                'type': control_type,
                'modul_type': modul_type,
                'parent_guid': str(parent_guid) if parent_guid and parent_guid != 'None' else None
            }
            
            if control_type == 'element_list':
                element_lists.append(ctrl)
            elif ctrl['parent_guid']:
                children.append(ctrl)
            else:
                orphans.append(ctrl)
        
        # Hierarchie anzeigen
        print("=" * 80)
        print("🌲 HIERARCHIE-BAUM")
        print("=" * 80)
        
        for el in element_lists:
            print(f"\n📦 {el['name']} ({el['modul_type']})")
            print(f"   UID: {el['uid']}")
            print(f"   Label: {el['label']}")
            
            # Children finden
            el_children = [c for c in children if c['parent_guid'] == el['uid']]
            
            if el_children:
                print(f"   └─ Children ({len(el_children)}):")
                for child in el_children:
                    print(f"      ├─ {child['name']}")
                    print(f"      │  Label: {child['label']}")
                    print(f"      │  SELF_NAME: {child['self_name']}")
            else:
                print(f"   └─ (keine Children)")
        
        # Orphans (Controls ohne parent)
        print("\n" + "=" * 80)
        print("🔓 CONTROLS OHNE PARENT (nicht zu element_list gehörend)")
        print("=" * 80)
        
        print(f"\n{len(orphans)} Controls:")
        for orphan in orphans:
            print(f"   • {orphan['name']} ({orphan['type']}, {orphan['modul_type']})")
        
        # Statistik
        print("\n" + "=" * 80)
        print("📊 STATISTIK")
        print("=" * 80)
        
        print(f"\n   📋 Element Lists: {len(element_lists)}")
        print(f"   🔗 Controls mit parent_guid: {len(children)}")
        print(f"   🔓 Controls ohne parent_guid: {len(orphans)}")
        print(f"   📦 Gesamt: {len(rows)}")
        
        # Validierung
        expected_children = 6  # Aus Phase 3 Migration
        if len(children) == expected_children:
            print(f"\n   ✅ Erwartete Anzahl Children: {expected_children}")
        else:
            print(f"\n   ⚠️  Erwartete {expected_children}, gefunden {len(children)}")
        
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(show_hierarchy())

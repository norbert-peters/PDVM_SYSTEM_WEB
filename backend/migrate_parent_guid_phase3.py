"""
Phase 3 Migration: parent_guid Hierarchie setzen
Etabliert hierarchische Beziehungen zwischen element_lists und Child-Controls
"""
import asyncio
import asyncpg
import json

DB_URL = "postgresql://postgres:Polari$55@localhost:5432/pdvm_system"

# Hierarchie-Mapping: parent_name → [child_names]
HIERARCHY_MAP = {
    'tabs_def': [
        'tab_order',
        'tab_visible',
        'tab01_gruppe',
        'tab01_head',
        'tab02_gruppe',
        'tab02_head'
    ],
    # 'fields' würde hier weitere Controls haben
    # 'tabs' ist selbst eine element_list aber kein parent
}

async def migrate_parent_guid():
    """Setzt parent_guid für Child-Controls"""
    conn = await asyncpg.connect(DB_URL)
    
    try:
        print("=" * 80)
        print("🔧 Phase 3: parent_guid Hierarchie Migration")
        print("=" * 80)
        
        # Alle Controls laden
        rows = await conn.fetch("""
            SELECT uid, name, daten
            FROM public.sys_control_dict
            WHERE historisch = 0
        """)
        
        print(f"\n📦 {len(rows)} Controls geladen\n")
        
        # UID-Mapping erstellen (name → uid)
        name_to_uid = {}
        controls_dict = {}
        
        for row in rows:
            uid = row['uid']
            name = row['name']
            daten = row['daten']
            
            if isinstance(daten, str):
                daten = json.loads(daten)
            
            name_to_uid[name] = str(uid)
            controls_dict[name] = {
                'uid': uid,
                'name': name,
                'daten': daten
            }
        
        # Migration durchführen
        migrated = 0
        skipped = 0
        errors = []
        
        for parent_name, child_names in HIERARCHY_MAP.items():
            # Parent-UID finden
            if parent_name not in name_to_uid:
                errors.append(f"❌ Parent '{parent_name}' nicht gefunden!")
                continue
            
            parent_uid = name_to_uid[parent_name]
            
            print(f"📁 {parent_name} (Parent-UID: {parent_uid})")
            
            for child_name in child_names:
                # Child finden
                if child_name not in controls_dict:
                    errors.append(f"  ❌ Child '{child_name}' nicht gefunden!")
                    continue
                
                child = controls_dict[child_name]
                child_uid = child['uid']
                child_daten = child['daten']
                
                # Prüfen ob parent_guid bereits gesetzt ist
                current_parent = child_daten.get('parent_guid')
                
                if current_parent and current_parent != 'None' and str(current_parent) != parent_uid:
                    print(f"   ⚠️  {child_name}: parent_guid bereits gesetzt = {current_parent}")
                    skipped += 1
                    continue
                
                # parent_guid setzen
                child_daten['parent_guid'] = parent_uid
                
                # Update in DB
                await conn.execute("""
                    UPDATE public.sys_control_dict
                    SET daten = $1,
                        modified_at = NOW()
                    WHERE uid = $2
                """, json.dumps(child_daten), child_uid)
                
                print(f"   ✅ {child_name} → parent_guid = {parent_uid}")
                migrated += 1
        
        # Zusammenfassung
        print("\n" + "=" * 80)
        print("📊 MIGRATIONS-ERGEBNIS")
        print("=" * 80)
        print(f"\n   ✅ Migriert: {migrated}")
        print(f"   ⏭️  Übersprungen: {skipped}")
        
        if errors:
            print(f"   ❌ Fehler: {len(errors)}")
            for err in errors:
                print(f"      {err}")
        
        # Validierung
        print("\n" + "=" * 80)
        print("🔍 Validierung")
        print("=" * 80)
        
        rows = await conn.fetch("""
            SELECT uid, name, daten
            FROM public.sys_control_dict
            WHERE historisch = 0
        """)
        
        with_parent = 0
        without_parent = 0
        element_lists = 0
        
        for row in rows:
            daten = row['daten']
            if isinstance(daten, str):
                daten = json.loads(daten)
            
            control_type = daten.get('type')
            parent_guid = daten.get('parent_guid')
            
            if control_type == 'element_list':
                element_lists += 1
            elif parent_guid and parent_guid != 'None':
                with_parent += 1
            else:
                without_parent += 1
        
        print(f"\n   📋 Element Lists: {element_lists}")
        print(f"   🔗 Controls mit parent_guid: {with_parent}")
        print(f"   🔓 Controls ohne parent_guid: {without_parent}")
        
        if migrated > 0:
            print("\n🎉 Phase 3 Migration erfolgreich!")
        
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(migrate_parent_guid())

"""
Phase 4 Migration: element_frame_guid und IS_ELEMENT Flag setzen
"""
import asyncio
import asyncpg
import json

DB_URL = "postgresql://postgres:Polari$55@localhost:5432/pdvm_system"

# Zuordnung element_list → Frame Template
ELEMENT_FRAME_MAPPING = {
    # element_list name → frame_uid
    'tabs_def': '55555555-0002-4001-8001-000000000002',  # Element-List TABS Template
    'fields': '55555555-0001-4001-8001-000000000001',    # Element-List FIELDS Template
    # 'tabs' bleibt erstmal ohne Zuordnung
}

# Frames die als element_list Templates fungieren
ELEMENT_FRAME_UIDS = [
    '55555555-0001-4001-8001-000000000001',  # Element-List FIELDS Template
    '55555555-0002-4001-8001-000000000002',  # Element-List TABS Template
]

async def migrate_phase4():
    """Migriert element_frame_guid und IS_ELEMENT"""
    conn = await asyncpg.connect(DB_URL)
    
    try:
        print("=" * 80)
        print("🔧 Phase 4: element_list Frame-Referenzen Migration")
        print("=" * 80)
        
        # Teil 1: element_frame_guid zu Controls hinzufügen
        print("\n📝 Teil 1: element_frame_guid zu element_list Controls")
        print("-" * 80)
        
        migrated_controls = 0
        
        for element_name, frame_uid in ELEMENT_FRAME_MAPPING.items():
            # Control laden
            row = await conn.fetchrow("""
                SELECT uid, name, daten
                FROM public.sys_control_dict
                WHERE name = $1 AND historisch = 0
            """, element_name)
            
            if not row:
                print(f"   ❌ Control '{element_name}' nicht gefunden!")
                continue
            
            uid = row['uid']
            daten = row['daten']
            
            if isinstance(daten, str):
                daten = json.loads(daten)
            
            # Prüfen ob bereits gesetzt
            current_frame = daten.get('element_frame_guid')
            
            if current_frame and str(current_frame) == frame_uid:
                print(f"   ⏭️  {element_name}: element_frame_guid bereits gesetzt")
                continue
            
            # element_frame_guid setzen
            daten['element_frame_guid'] = frame_uid
            
            # Update in DB
            await conn.execute("""
                UPDATE public.sys_control_dict
                SET daten = $1,
                    modified_at = NOW()
                WHERE uid = $2
            """, json.dumps(daten), uid)
            
            print(f"   ✅ {element_name} → element_frame_guid = {frame_uid}")
            migrated_controls += 1
        
        # Teil 2: IS_ELEMENT Flag in Frames setzen
        print("\n📝 Teil 2: IS_ELEMENT Flag in Frame-Templates")
        print("-" * 80)
        
        migrated_frames = 0
        
        for frame_uid in ELEMENT_FRAME_UIDS:
            # Frame laden
            row = await conn.fetchrow("""
                SELECT uid, name, daten
                FROM public.sys_framedaten
                WHERE uid = $1 AND historisch = 0
            """, frame_uid)
            
            if not row:
                print(f"   ❌ Frame '{frame_uid}' nicht gefunden!")
                continue
            
            name = row['name']
            daten = row['daten']
            
            if isinstance(daten, str):
                daten = json.loads(daten)
            
            # ROOT holen/erstellen
            if 'ROOT' not in daten:
                daten['ROOT'] = {}
            
            root = daten['ROOT']
            
            # Prüfen ob IS_ELEMENT bereits gesetzt
            if root.get('IS_ELEMENT') is True:
                print(f"   ⏭️  {name}: IS_ELEMENT bereits true")
                continue
            
            # IS_ELEMENT setzen
            root['IS_ELEMENT'] = True
            
            # Update in DB
            await conn.execute("""
                UPDATE public.sys_framedaten
                SET daten = $1,
                    modified_at = NOW()
                WHERE uid = $2
            """, json.dumps(daten), frame_uid)
            
            print(f"   ✅ {name} → IS_ELEMENT = true")
            migrated_frames += 1
        
        # Zusammenfassung
        print("\n" + "=" * 80)
        print("📊 MIGRATIONS-ERGEBNIS")
        print("=" * 80)
        print(f"\n   ✅ Controls migriert: {migrated_controls}")
        print(f"   ✅ Frames migriert: {migrated_frames}")
        
        # Validierung
        print("\n" + "=" * 80)
        print("🔍 Validierung")
        print("=" * 80)
        
        # Controls prüfen
        controls = await conn.fetch("""
            SELECT uid, name, daten
            FROM public.sys_control_dict
            WHERE historisch = 0
        """)
        
        element_lists_with_frame = 0
        element_lists_without_frame = 0
        
        for row in controls:
            daten = row['daten']
            if isinstance(daten, str):
                daten = json.loads(daten)
            
            if daten.get('type') == 'element_list':
                if daten.get('element_frame_guid'):
                    element_lists_with_frame += 1
                else:
                    element_lists_without_frame += 1
        
        print(f"\n   element_lists mit Frame: {element_lists_with_frame}")
        print(f"   element_lists ohne Frame: {element_lists_without_frame}")
        
        # Frames prüfen
        frames = await conn.fetch("""
            SELECT uid, name, daten
            FROM public.sys_framedaten
            WHERE historisch = 0
        """)
        
        frames_with_is_element = 0
        
        for row in frames:
            daten = row['daten']
            if isinstance(daten, str):
                daten = json.loads(daten)
            
            root = daten.get('ROOT', {})
            if root.get('IS_ELEMENT') is True:
                frames_with_is_element += 1
        
        print(f"   Frames mit IS_ELEMENT: {frames_with_is_element}")
        
        if migrated_controls > 0 or migrated_frames > 0:
            print("\n🎉 Phase 4 Migration erfolgreich!")
        
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(migrate_phase4())

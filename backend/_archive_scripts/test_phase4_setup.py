"""
Simpler Test für element_list Setup nach Phase 4
Prüft ohne GCS-Abhängigkeit
"""
import asyncio
import asyncpg
import json
from uuid import UUID

DB_URL = "postgresql://postgres:Polari$55@localhost:5432/pdvm_system"


async def test_phase4_setup():
    """Testet Phase 4 Setup"""
    conn = await asyncpg.connect(DB_URL)
    
    try:
        print("=" * 80)
        print("🧪 Phase 4 Setup Test")
        print("=" * 80)
        
        # Test 1: element_lists mit element_frame_guid
        print("\nTest 1: element_lists mit element_frame_guid")
        print("-" * 80)
        
        controls = await conn.fetch("""
            SELECT uid, name, daten
            FROM public.sys_control_dict
            WHERE historisch = 0
        """)
        
        element_lists = []
        
        for row in controls:
            daten = row['daten']
            if isinstance(daten, str):
                daten = json.loads(daten)
            
            if daten.get('type') == 'element_list':
                element_lists.append({
                    'uid': str(row['uid']),
                    'name': row['name'],
                    'element_frame_guid': daten.get('element_frame_guid')
                })
        
        print(f"\n{len(element_lists)} element_lists gefunden:")
        
        for el in element_lists:
            status = "✅" if el['element_frame_guid'] else "❌"
            frame_info = el['element_frame_guid'] or "NICHT GESETZT"
            print(f"{status} {el['name']}: {frame_info}")
        
        # Test 2: Frames mit IS_ELEMENT
        print("\n" + "=" * 80)
        print("Test 2: Frames mit IS_ELEMENT Flag")
        print("-" * 80)
        
        frames = await conn.fetch("""
            SELECT uid, name, daten
            FROM public.sys_framedaten
            WHERE historisch = 0
        """)
        
        element_frames = []
        
        for row in frames:
            daten = row['daten']
            if isinstance(daten, str):
                daten = json.loads(daten)
            
            root = daten.get('ROOT', {})
            if root.get('IS_ELEMENT') is True:
                element_frames.append({
                    'uid': str(row['uid']),
                    'name': row['name']
                })
        
        print(f"\n{len(element_frames)} Frames mit IS_ELEMENT=true gefunden:")
        
        for frame in element_frames:
            print(f"✅ {frame['name']} ({frame['uid']})")
        
        # Test 3: Referenz-Integrität prüfen
        print("\n" + "=" * 80)
        print("Test 3: Referenz-Integrität")
        print("-" * 80)
        
        issues = []
        
        for el in element_lists:
            if not el['element_frame_guid']:
                continue
            
            # Frame existiert?
            frame_exists = any(
                f['uid'] == el['element_frame_guid']
                for f in element_frames
            )
            
            if not frame_exists:
                issues.append(f"element_list '{el['name']}' referenziert nicht-existentes Frame {el['element_frame_guid']}")
        
        if issues:
            print("\n⚠️  Issues gefunden:")
            for issue in issues:
                print(f"   • {issue}")
        else:
            print("\n✅ Alle Referenzen gültig")
        
        # Test 4: Frame-Template für tabs_def laden
        print("\n" + "=" * 80)
        print("Test 4: Frame-Template für tabs_def laden")
        print("-" * 80)
        
        tabs_def = next((el for el in element_lists if el['name'] == 'tabs_def'), None)
        
        if tabs_def and tabs_def['element_frame_guid']:
            frame_row = await conn.fetchrow("""
                SELECT uid, name, daten
                FROM public.sys_framedaten
                WHERE uid = $1 AND historisch = 0
            """, UUID(tabs_def['element_frame_guid']))
            
            if frame_row:
                frame_daten = frame_row['daten']
                if isinstance(frame_daten, str):
                    frame_daten = json.loads(frame_daten)
                
                root = frame_daten.get('ROOT', {})
                fields = frame_daten.get('FIELDS', {})
                tabs = frame_daten.get('TABS', {})
                
                print(f"\n✅ Frame geladen:")
                print(f"   Name: {frame_row['name']}")
                print(f"   UID: {frame_row['uid']}")
                print(f"   IS_ELEMENT: {root.get('IS_ELEMENT')}")
                print(f"   FIELDS: {len(fields)} controls")
                print(f"   TABS: {len(tabs)} tabs")
                
                # Fields anzeigen
                if fields:
                    print(f"\n   Fields im Template:")
                    for key, field in list(fields.items())[:5]:  # Nur erste 5 zeigen
                        print(f"      • {key}: {field}")
        
        # Zusammenfassung
        print("\n" + "=" * 80)
        print("📊 ZUSAMMENFASSUNG")
        print("=" * 80)
        
        print(f"\n   element_lists gesamt: {len(element_lists)}")
        print(f"   mit element_frame_guid: {len([el for el in element_lists if el['element_frame_guid']])}")
        print(f"   Frames mit IS_ELEMENT: {len(element_frames)}")
        print(f"   Referenz-Issues: {len(issues)}")
        
        if len(issues) == 0 and len([el for el in element_lists if el['element_frame_guid']]) > 0:
            print(f"\n   ✅ Phase 4 Setup erfolgreich validiert!")
        
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(test_phase4_setup())

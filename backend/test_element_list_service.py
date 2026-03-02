"""
Test Script für element_list_service (Phase 4)
"""
import asyncio
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from uuid import UUID
from app.core.pdvm_central_systemsteuerung import get_gcs
from app.core.element_list_service import (
    load_element_list_frame,
    get_element_list_children,
    validate_element_list_setup
)


async def test_element_list_service():
    """Testet element_list Service Funktionen"""
    print("=" * 80)
    print("🧪 Element-List Service Tests (Phase 4)")
    print("=" * 80)
    
    # GCS initialisieren
    gcs = get_gcs()
    if not gcs:
        print("❌ GCS nicht verfügbar - Test abgebrochen")
        return
    
    print(f"\n✅ GCS initialisiert")
    
    # Test 1: Validierung
    print("\n" + "-" * 80)
    print("Test 1: validate_element_list_setup()")
    print("-" * 80)
    
    try:
        result = await validate_element_list_setup(gcs)
        print(f"\n   Valid: {result['valid']}")
        print(f"   element_lists: {result['element_lists']}")
        print(f"   element_frames: {result['element_frames']}")
        
        if result['issues']:
            print(f"\n   ⚠️  Issues:")
            for issue in result['issues']:
                print(f"      • {issue}")
        else:
            print(f"\n   ✅ Keine Issues gefunden")
    except Exception as e:
        print(f"   ❌ Error: {e}")
    
    # Test 2: Frame laden für tabs_def
    print("\n" + "-" * 80)
    print("Test 2: load_element_list_frame() für tabs_def")
    print("-" * 80)
    
    tabs_def_uid = UUID("a88ee663-745f-4ab8-b8d0-c024d0a0987b")
    
    try:
        frame = await load_element_list_frame(gcs, tabs_def_uid)
        print(f"\n   ✅ Frame geladen:")
        print(f"      UID: {frame['uid']}")
        print(f"      Name: {frame['name']}")
        print(f"      IS_ELEMENT: {frame['root'].get('IS_ELEMENT')}")
        print(f"      FIELDS: {len(frame['fields'])} controls")
        print(f"      TABS: {len(frame['tabs'])} tabs")
    except Exception as e:
        print(f"   ❌ Error: {e}")
    
    # Test 3: Frame laden für fields
    print("\n" + "-" * 80)
    print("Test 3: load_element_list_frame() für fields")
    print("-" * 80)
    
    fields_uid = UUID("9ccb9eb8-ae9f-4308-97b7-a9e78b3d5c78")
    
    try:
        frame = await load_element_list_frame(gcs, fields_uid)
        print(f"\n   ✅ Frame geladen:")
        print(f"      UID: {frame['uid']}")
        print(f"      Name: {frame['name']}")
        print(f"      IS_ELEMENT: {frame['root'].get('IS_ELEMENT')}")
        print(f"      FIELDS: {len(frame['fields'])} controls")
    except Exception as e:
        print(f"   ❌ Error: {e}")
    
    # Test 4: Children laden für tabs_def
    print("\n" + "-" * 80)
    print("Test 4: get_element_list_children() für tabs_def")
    print("-" * 80)
    
    try:
        children = await get_element_list_children(gcs, tabs_def_uid)
        print(f"\n   ✅ {len(children)} Children gefunden:")
        
        for child in children:
            print(f"      • {child['name']} ({child['type']})")
            print(f"        SELF_NAME: {child['self_name']}")
    except Exception as e:
        print(f"   ❌ Error: {e}")
    
    # Zusammenfassung
    print("\n" + "=" * 80)
    print("✅ Tests abgeschlossen")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(test_element_list_service())

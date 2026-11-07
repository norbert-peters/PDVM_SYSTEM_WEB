#!/usr/bin/env python3
"""
Test: Control Template Service
Demonstriert Modul-Auswahl und Template-Merge
"""

import asyncpg
import asyncio
import json
import sys
from pathlib import Path

# Backend Module importieren
backend_path = Path(__file__).parent
sys.path.insert(0, str(backend_path))

# Direkt importieren (nicht über app.core)
import importlib.util
spec = importlib.util.spec_from_file_location(
    "control_template_service",
    backend_path / "app" / "core" / "control_template_service.py"
)
cts_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cts_module)

ControlTemplateService = cts_module.ControlTemplateService
create_control = cts_module.create_control


async def test_create_new_control():
    """Test: Neues Control mit Modul-Auswahl erstellen"""
    
    conn = await asyncpg.connect('postgresql://postgres:Polari$55@localhost:5432/pdvm_system')
    
    try:
        service = ControlTemplateService(conn)
        
        print("=" * 70)
        print("🧪 Test 1: Basis-Template laden")
        print("=" * 70)
        
        base_template = await service.load_base_template()
        print("✅ Basis-Template (666666...):")
        print(json.dumps(base_template, indent=2, ensure_ascii=False))
        
        print("\n" + "=" * 70)
        print("🧪 Test 2: Modul-Templates laden")
        print("=" * 70)
        
        for modul_type in ['edit', 'view', 'tabs']:
            print(f"\n📦 Modul-Template: {modul_type}")
            print("-" * 70)
            modul_template = await service.load_modul_template(modul_type)
            print(json.dumps(modul_template, indent=2, ensure_ascii=False)[:500] + "...")
        
        print("\n" + "=" * 70)
        print("🧪 Test 3: Neues Control erstellen (edit)")
        print("=" * 70)
        
        # User-Daten für neues Control
        field_data = {
            'name': 'test_field',
            'label': 'Test Feld',
            'type': 'string',
            'table': 'sys_control_dict',
            'gruppe': 'ROOT',
            'feld': 'test_field',
            'display_order': 100
        }
        
        new_control = await service.create_new_control('edit', 'sys_', field_data)
        
        print(f"✅ Neues Control erstellt:")
        print(f"   UUID: {new_control['uid']}")
        print(f"   Name: {new_control['name']}")
        print(f"   SELF_NAME: {new_control['daten'].get('SELF_NAME')}")
        print(f"   modul_type: {new_control['daten'].get('modul_type')}")
        print()
        print("Daten-Struktur:")
        print(json.dumps(new_control['daten'], indent=2, ensure_ascii=False))
        
        print("\n" + "=" * 70)
        print("🧪 Test 4: MODUL_TYPE Switching (edit → view)")
        print("=" * 70)
        
        # Erst Control in DB einfügen für Switching-Test
        control_uid = new_control['uid']
        await conn.execute("""
            INSERT INTO sys_control_dict (uid, name, daten, historisch, created_at, modified_at)
            VALUES ($1, $2, $3, 0, NOW(), NOW())
        """, control_uid, new_control['name'], json.dumps(new_control['daten']))
        
        print(f"✅ Control in DB eingefügt: {control_uid}")
        
        # Alte Daten anzeigen
        print("\n📊 VOR Switching (edit):")
        print(f"   Felder: {list(new_control['daten'].keys())}")
        print(f"   read_only: {new_control['daten'].get('read_only')}")
        print(f"   abdatum: {new_control['daten'].get('abdatum')}")
        
        # MODUL_TYPE wechseln
        switched_data = await service.switch_modul_type(control_uid, 'view')
        
        print("\n📊 NACH Switching (view):")
        print(f"   Felder: {list(switched_data.keys())}")
        print(f"   show: {switched_data.get('show')}")
        print(f"   sortable: {switched_data.get('sortable')}")
        print(f"   read_only: {switched_data.get('read_only')} (sollte weg sein)")
        print()
        print(json.dumps(switched_data, indent=2, ensure_ascii=False))
        
        # Cleanup
        await conn.execute("DELETE FROM sys_control_dict WHERE uid = $1", control_uid)
        print(f"\n🗑️  Test-Control gelöscht: {control_uid}")
        
        print("\n" + "=" * 70)
        print("✅ Alle Tests erfolgreich!")
        print("=" * 70)
        
    except Exception as e:
        print(f"\n❌ Fehler: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        await conn.close()


async def test_convenience_function():
    """Test: create_control Convenience Function"""
    
    conn = await asyncpg.connect('postgresql://postgres:Polari$55@localhost:5432/pdvm_system')
    
    try:
        print("\n" + "=" * 70)
        print("🧪 Test 5: create_control() Convenience Function")
        print("=" * 70)
        
        field_data = {
            'name': 'convenience_test',
            'label': 'Convenience Test',
            'type': 'text',
            'table': 'sys_control_dict',
            'gruppe': 'ROOT',
            'feld': 'convenience_test'
        }
        
        control_uid = await create_control(conn, 'edit', 'sys_control_dict', field_data)
        
        print(f"✅ Control erstellt mit UUID: {control_uid}")
        
        # Verifizieren
        result = await conn.fetchrow(
            'SELECT name, daten FROM sys_control_dict WHERE uid = $1',
            control_uid
        )
        
        # Parse daten wenn String
        daten = result['daten']
        if isinstance(daten, str):
            daten = json.loads(daten)
        
        print(f"   Name: {result['name']}")
        print(f"   SELF_NAME: {daten.get('SELF_NAME')}")
        print(f"   modul_type: {daten.get('modul_type')}")
        print(f"   label: {daten.get('label')}")
        
        # Cleanup
        await conn.execute("DELETE FROM sys_control_dict WHERE uid = $1", control_uid)
        print(f"\n🗑️  Test-Control gelöscht: {control_uid}")
        
    finally:
        await conn.close()


async def main():
    """Hauptfunktion - Alle Tests"""
    
    print("🚀 Control Template Service - Test Suite")
    print("=" * 70)
    
    await test_create_new_control()
    await test_convenience_function()
    
    print("\n" + "=" * 70)
    print("🎉 Test Suite abgeschlossen!")
    print("=" * 70)


if __name__ == '__main__':
    asyncio.run(main())

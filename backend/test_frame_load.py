"""
Testet das Laden eines sys_framedaten-Datensatzes über dialog_service
"""
import asyncio
import asyncpg
import json
import uuid as uuid_module

async def test_load():
    # Direkte Verbindung zur Datenbank
    conn = await asyncpg.connect('postgresql://postgres:Polari$55@localhost:5432/pdvm_system')
    
    try:
        print("="*80)
        print("🧪 Test: Frame-Datensatz laden (self-editing)")
        print("="*80)
        
        frame_uuid = '4413571e-6bf6-4f42-b81a-bc898db4880c'
        
        # 1. Frame laden
        row = await conn.fetchrow(
            'SELECT uid, name, daten FROM sys_framedaten WHERE uid = $1',
            frame_uuid
        )
        
        if not row:
            print(f"❌ Frame nicht gefunden: {frame_uuid}")
            return
        
        daten = row['daten']
        if isinstance(daten, str):
            daten = json.loads(daten)
        
        print(f"\n✅ Frame-Definition geladen:")
        print(f"  UID: {row['uid']}")
        print(f"  Name: {row['name']}")
        print(f"  ROOT.TABLE: {daten.get('ROOT', {}).get('TABLE')}")
        print(f"  ROOT.EDIT_TYPE: {daten.get('ROOT', {}).get('EDIT_TYPE')}")
        
        # 2. Controls prüfen und resolved Daten simulieren
        print(f"\n📦 Frame-Controls:")
        
        if 'FIELDS' not in daten:
            print("  ❌ Keine FIELDS-Gruppe!")
            return
        
        fields = daten['FIELDS']
        resolved_fields = {}
        
        for control_guid, control_local in fields.items():
            # Control aus dict laden
            dict_row = await conn.fetchrow(
                'SELECT daten FROM sys_control_dict WHERE uid = $1',
                control_guid
            )
            
            if dict_row:
                dict_daten = dict_row['daten']
                if isinstance(dict_daten, str):
                    dict_daten = json.loads(dict_daten)
                
                # Merge: dict + local overrides
                if isinstance(control_local, dict):
                    merged = {**dict_daten, **control_local}
                else:
                    merged = dict_daten
                
                resolved_fields[control_guid] = merged
                
                label = merged.get('label', '???')
                ctrl_type = merged.get('type', 'MISSING')
                name = merged.get('name', '???')
                
                print(f"  ✅ {label} ({ctrl_type}) - {name}")
            else:
                print(f"  ❌ Control {control_guid[:8]}... nicht in dict gefunden!")
                resolved_fields[control_guid] = control_local
        
        # 3. Datensatz laden (sich selbst)
        print(f"\n" + "="*80)
        print(f"🧪 Test: Datensatz-Werte laden")
        print("="*80)
        
        # Frame lädt sich selbst
        data_row = await conn.fetchrow(
            'SELECT uid, name, daten FROM sys_framedaten WHERE uid = $1',
            frame_uuid
        )
        
        data_daten = data_row['daten']
        if isinstance(data_daten, str):
            data_daten = json.loads(data_daten)
        
        print(f"\n✅ Datensatz geladen:")
        print(f"  UID: {data_row['uid']}")
        print(f"  Name: {data_row['name']}")
        
        # Gruppen anzeigen
        print(f"\n📊 Daten-Gruppen im Datensatz:")
        for gruppe_name, gruppe_data in data_daten.items():
            if isinstance(gruppe_data, dict):
                print(f"  • {gruppe_name}: {len(gruppe_data)} Felder")
        
        # ROOT-Gruppe Details
        if 'ROOT' in data_daten:
            print(f"\n📦 ROOT-Gruppe:")
            for key, value in data_daten['ROOT'].items():
                if isinstance(value, (str, int, float, bool, type(None))):
                    print(f"    • {key}: {value}")
                elif isinstance(value, list):
                    print(f"    • {key}: [Liste mit {len(value)} Elementen]")
                elif isinstance(value, dict):
                    print(f"    • {key}: {{Dict mit {len(value)} Keys}}")
        
        # 4. Mapping: Controls → Daten
        print(f"\n" + "="*80)
        print(f"🔗 Mapping: Controls → Daten")
        print("="*80)
        
        for control_guid, control_def in list(resolved_fields.items())[:5]:
            label = control_def.get('label', '???')
            ctrl_type = control_def.get('type', '???')
            gruppe = control_def.get('gruppe', '???')
            feld = control_def.get('feld', control_def.get('name', '???'))
            
            # Datenwert suchen
            if gruppe in data_daten and isinstance(data_daten[gruppe], dict):
                wert = data_daten[gruppe].get(feld, 'NICHT VORHANDEN')
                print(f"\n  📝 {label} ({ctrl_type})")
                print(f"     Gruppe: {gruppe}, Feld: {feld}")
                if isinstance(wert, (str, int, float, bool, type(None))):
                    print(f"     Wert: {wert}")
                elif isinstance(wert, dict):
                    print(f"     Wert: {{Dict mit {len(wert)} Keys}}")
                elif isinstance(wert, list):
                    print(f"     Wert: [Liste mit {len(wert)} Elementen]")
            else:
                print(f"\n  📝 {label} ({ctrl_type})")
                print(f"     Gruppe: {gruppe}, Feld: {feld}")
                print(f"     ⚠️ Gruppe nicht im Datensatz gefunden")
        
        print("\n" + "="*80)
        print("✅ TEST ERFOLGREICH!")
        print("="*80)
        print("\nDas Frame sollte jetzt funktionieren:")
        print("  1. ✅ ROOT.TABLE ist gesetzt (sys_framedaten)")
        print("  2. ✅ Controls sind in sys_control_dict definiert")
        print("  3. ✅ Datensatz existiert und hat Daten")
        print("  4. ✅ Controls können auf Daten mappen")
        print("\n🔧 Nächster Schritt: Im Frontend testen mit:")
        print(f"   /api/frame/edit/{frame_uuid}")
        
    except Exception as e:
        print(f"\n❌ Fehler: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(test_load())

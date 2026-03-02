"""
Simuliert die komplette API-Antwort für den Edit Frame
und prüft, ob alle Daten korrekt gemappt werden können
"""
import asyncio
import asyncpg
import json
import uuid as uuid_module

async def simulate_api_response():
    conn = await asyncpg.connect('postgresql://postgres:Polari$55@localhost:5432/pdvm_system')
    
    try:
        frame_uid = '4413571e-6bf6-4f42-b81a-bc898db4880c'
        
        print("="*80)
        print("🧪 SIMULIERE KOMPLETTE API-ANTWORT")
        print("="*80)
        
        # 1. Frame-Definition laden (wie API)
        frame_row = await conn.fetchrow(
            'SELECT uid, name, daten FROM sys_framedaten WHERE uid = $1',
            frame_uid
        )
        
        frame_daten = frame_row['daten']
        if isinstance(frame_daten, str):
            frame_daten = json.loads(frame_daten)
        
        # Resolve FIELDS Controls (wie _resolve_frame_fields)
        fields = frame_daten.get('FIELDS', {})
        resolved_fields = {}
        
        for control_guid, control_local in fields.items():
            # Control aus sys_control_dict laden
            dict_row = await conn.fetchrow(
                'SELECT daten FROM sys_control_dict WHERE uid = $1',
                control_guid
            )
            
            if dict_row:
                dict_daten = dict_row['daten']
                if isinstance(dict_daten, str):
                    dict_daten = json.loads(dict_daten)
                
                # Merge: dict + local
                if isinstance(control_local, dict):
                    merged = {**dict_daten, **control_local}
                else:
                    merged = dict_daten
                
                resolved_fields[control_guid] = merged
            else:
                resolved_fields[control_guid] = control_local
        
        frame_definition = {
            "uid": str(frame_row['uid']),
            "name": frame_row['name'],
            "daten": {
                **frame_daten,
                "FIELDS": resolved_fields
            },
            "root": frame_daten.get('ROOT', {})
        }
        
        print("\n📋 FRAME DEFINITION:")
        print(f"  UID: {frame_definition['uid']}")
        print(f"  Name: {frame_definition['name']}")
        print(f"  ROOT.TABLE: {frame_definition['root'].get('TABLE')}")
        print(f"  Controls: {len(resolved_fields)}")
        
        # 2. Datensatz laden (wie load_dialog_record)
        record_row = await conn.fetchrow(
            'SELECT uid, name, daten, historisch, modified_at FROM sys_framedaten WHERE uid = $1',
            frame_uid
        )
        
        record_daten = record_row['daten']
        if isinstance(record_daten, str):
            record_daten = json.loads(record_daten)
        
        record_response = {
            "uid": str(record_row['uid']),
            "name": record_row['name'],
            "daten": record_daten,
            "historisch": record_row['historisch'] or 0,
            "modified_at": record_row['modified_at'].isoformat() if record_row['modified_at'] else None
        }
        
        print("\n📊 RECORD RESPONSE:")
        print(f"  UID: {record_response['uid']}")
        print(f"  Name: {record_response['name']}")
        print(f"  Daten-Gruppen: {list(record_response['daten'].keys())}")
        
        # 3. Mapping: Controls → Werte
        print("\n" + "="*80)
        print("🔗 MAPPING: Controls → Werte")
        print("="*80)
        
        success_count = 0
        missing_count = 0
        
        for control_guid, control_def in resolved_fields.items():
            label = control_def.get('label', '???')
            ctrl_type = control_def.get('type', '???')
            gruppe = control_def.get('gruppe')
            feld = control_def.get('feld')
            
            print(f"\n📝 {label} ({ctrl_type})")
            print(f"   Control-GUID: {control_guid}")
            print(f"   gruppe={gruppe}, feld={feld}")
            
            if not gruppe or not feld:
                print(f"   ❌ FEHLER: gruppe oder feld nicht gesetzt!")
                missing_count += 1
                continue
            
            # Wert aus record_response holen
            if gruppe in record_response['daten']:
                gruppe_data = record_response['daten'][gruppe]
                
                if isinstance(gruppe_data, dict):
                    if feld in gruppe_data:
                        wert = gruppe_data[feld]
                        
                        if isinstance(wert, (str, int, float, bool, type(None))):
                            print(f"   ✅ Wert: {wert}")
                            success_count += 1
                        elif isinstance(wert, dict):
                            print(f"   ✅ Wert: Dict mit {len(wert)} Keys")
                            # Erste 3 Keys zeigen
                            for i, (k, v) in enumerate(list(wert.items())[:3]):
                                print(f"      [{i+1}] {k}: {v if isinstance(v, (str, int, bool)) else '<complex>'}")
                            success_count += 1
                        elif isinstance(wert, list):
                            print(f"   ✅ Wert: Liste mit {len(wert)} Elementen")
                            success_count += 1
                    else:
                        print(f"   ⚠️ Feld '{feld}' nicht in Gruppe '{gruppe}' gefunden")
                        print(f"      Verfügbare Felder: {list(gruppe_data.keys())}")
                        missing_count += 1
                else:
                    print(f"   ⚠️ Gruppe '{gruppe}' ist kein Dict: {type(gruppe_data)}")
                    missing_count += 1
            else:
                print(f"   ⚠️ Gruppe '{gruppe}' nicht in daten gefunden")
                print(f"      Verfügbare Gruppen: {list(record_response['daten'].keys())}")
                missing_count += 1
        
        # Zusammenfassung
        print("\n" + "="*80)
        print("📊 ZUSAMMENFASSUNG")
        print("="*80)
        print(f"  ✅ Erfolgreich gemappt: {success_count}")
        print(f"  ❌ Fehlend/Fehler: {missing_count}")
        print(f"  📦 Gesamt Controls: {len(resolved_fields)}")
        
        if missing_count == 0:
            print("\n✅ ALLE CONTROLS KÖNNEN DATEN LADEN!")
            print("   Problem liegt wahrscheinlich im Frontend.")
        else:
            print("\n⚠️ EINIGE CONTROLS KÖNNEN KEINE DATEN LADEN!")
            print("   Backend muss angepasst werden.")
        
        # Debug: Zeige komplette Struktur
        print("\n" + "="*80)
        print("🔍 DEBUG: Komplette Daten-Struktur")
        print("="*80)
        print("\nrecord_response['daten']:")
        print(json.dumps(record_response['daten'], indent=2, ensure_ascii=False)[:1000])
        
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(simulate_api_response())

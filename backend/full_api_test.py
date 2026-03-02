"""
VOLLSTÄNDIGER API-TEST
Simuliert exakt, was das Frontend von der API bekommt
"""
import asyncio
import asyncpg
import json

async def full_api_test():
    conn = await asyncpg.connect('postgresql://postgres:Polari$55@localhost:5432/pdvm_system')
    
    try:
        dialog_guid = '4413571e-6bf6-4f42-b81a-bc898db4880c'  # Edit Frame als Dialog
        
        print("="*80)
        print("🧪 VOLLSTÄNDIGER API-TEST")
        print("="*80)
        print(f"\nDialog-GUID: {dialog_guid}")
        print("\n" + "="*80)
        
        # =========================================================================
        # SCHRITT 1: Dialog-Definition laden  (GET /api/dialogs/{dialog_guid})
        # =========================================================================
        print("\n📥 SCHRITT 1: Dialog-Definition laden")
        print("-"*80)
        
        dialog_row = await conn.fetchrow(
            'SELECT uid, name, daten FROM sys_dialogdaten WHERE uid = $1',
            dialog_guid
        )
        
        if not dialog_row:
            print(f"❌ Dialog nicht gefunden. Erstelle einen...")
            
            # Dialog erstellen
            dialog_daten = {
                "ROOT": {
                    "TABLE": "sys_framedaten",
                    "EDIT_TYPE": "edit_frame",
                    "VIEW_GUID": None,
                    "FRAME_GUID": dialog_guid  # Frame ist das Edit Frame selbst
                }
            }
            
            await conn.execute("""
                INSERT INTO sys_dialogdaten (uid, name, daten, historisch, created_at, modified_at)
                VALUES ($1, $2, $3, 0, NOW(), NOW())
                ON CONFLICT (uid) DO UPDATE
                SET daten = EXCLUDED.daten, modified_at = NOW()
            """, dialog_guid, "Edit Frame Dialog", json.dumps(dialog_daten))
            
            print(f"✅ Dialog erstellt: {dialog_guid}")
            
            dialog_row = await conn.fetchrow(
                'SELECT uid, name, daten FROM sys_dialogdaten WHERE uid = $1',
                dialog_guid
            )
        
        dialog_daten = dialog_row['daten']
        if isinstance(dialog_daten, str):
            dialog_daten = json.loads(dialog_daten)
        
        root_table = dialog_daten.get('ROOT', {}).get('TABLE', '')
        frame_guid = dialog_daten.get('ROOT', {}).get('FRAME_GUID', '')
        edit_type = dialog_daten.get('ROOT', {}).get('EDIT_TYPE', 'show_json')
        
        print(f"✅ Dialog geladen:")
        print(f"   Name: {dialog_row['name']}")
        print(f"   ROOT.TABLE: {root_table}")
        print(f"   ROOT.FRAME_GUID: {frame_guid}")
        print(f"   ROOT.EDIT_TYPE: {edit_type}")
        
        # =========================================================================
        # SCHRITT 2: Frame-Definition laden (Teil von Dialog-Response)
        # =========================================================================
        print("\n" + "="*80)
        print("📥 SCHRITT 2: Frame-Definition laden")
        print("-"*80)
        
        frame_row = await conn.fetchrow(
            'SELECT uid, name, daten FROM sys_framedaten WHERE uid = $1',
            frame_guid
        )
        
        if not frame_row:
            print(f"❌ Frame nicht gefunden!")
            return
        
        frame_daten = frame_row['daten']
        if isinstance(frame_daten, str):
            frame_daten = json.loads(frame_daten)
        
        # Resolve FIELDS
        fields = frame_daten.get('FIELDS', {})
        resolved_fields = {}
        
        for control_guid, control_local in fields.items():
            dict_row = await conn.fetchrow(
                'SELECT daten FROM sys_control_dict WHERE uid = $1',
                control_guid
            )
            
            if dict_row:
                dict_daten = dict_row['daten']
                if isinstance(dict_daten, str):
                    dict_daten = json.loads(dict_daten)
                
                merged = {**dict_daten, **(control_local if isinstance(control_local, dict) else {})}
                resolved_fields[control_guid] = merged
            else:
                resolved_fields[control_guid] = control_local
        
        print(f"✅ Frame geladen:")
        print(f"   Name: {frame_row['name']}")
        print(f"   Controls: {len(resolved_fields)}")
        
        for control_guid, control_def in list(resolved_fields.items())[:5]:
            label = control_def.get('label', '???')
            ctrl_type = control_def.get('type', '???')
            print(f"      • {label} ({ctrl_type})")
        
       # =========================================================================
        # SCHRITT 3: Datensatz laden (GET /api/dialogs/{dialog_guid}/record/{record_uid})
        # =========================================================================
        print("\n" + "="*80)
        print("📥 SCHRITT 3: Datensatz laden")
        print("-"*80)
        
        record_uid = frame_guid  # Frame bearbeitet sich selbst
        
        record_row = await conn.fetchrow(
            'SELECT uid, name, daten, historisch, modified_at FROM sys_framedaten WHERE uid = $1',
            record_uid
        )
        
        if not record_row:
            print(f"❌ Datensatz nicht gefunden!")
            return
        
        record_daten = record_row['daten']
        if isinstance(record_daten, str):
            record_daten = json.loads(record_daten)
        
        print(f"✅ Datensatz geladen:")
        print(f"   UID: {record_row['uid']}")
        print(f"   Name: {record_row['name']}")
        print(f"   Gruppen: {list(record_daten.keys())}")
        
        # =========================================================================
        # SCHRITT 4: API-Response zusammenbauen (was Frontend bekommt)
        # =========================================================================
        print("\n" + "="*80)
        print("📦 SCHRITT 4: Frontend bekommt folgende Struktur")
        print("-"*80)
        
        api_response = {
            "dialog": {
                "uid": str(dialog_row['uid']),
                "name": dialog_row['name'],
                "root_table": root_table,
                "edit_type": edit_type,
                "frame": {
                    "uid": str(frame_row['uid']),
                    "name": frame_row['name'],
                    "daten": {
                        "ROOT": frame_daten.get('ROOT'),
                        "FIELDS": resolved_fields
                    }
                }
            },
            "record": {
                "uid": str(record_row['uid']),
                "name": record_row['name'],
                "daten": record_daten,
                "historisch": record_row['historisch'] or 0,
                "modified_at": record_row['modified_at'].isoformat() if record_row['modified_at'] else None
            }
        }
        
        print("\n📋 VOLLSTÄNDIGE API-ANTWORT:")
        print(json.dumps(api_response, indent=2, ensure_ascii=False))
        
        # =========================================================================
        # SCHRITT 5: Prüfe Werte für jedes Control
        # =========================================================================
        print("\n" + "="*80)
        print("🔍 SCHRITT 5: Werte-Mapping für Frontend")
        print("-"*80)
        
        record_daten = api_response['record']['daten']
        controls = api_response['dialog']['frame']['daten']['FIELDS']
        
        print("\nFrontend sollte folgende Werte anzeigen:\n")
        
        for control_guid, control_def in controls.items():
            label = control_def.get('label', 'N/A')
            ctrl_type = control_def.get('type', 'N/A')
            gruppe = control_def.get('gruppe')
            feld = control_def.get('feld')
            
            print(f"Control: {label} ({ctrl_type})")
            print(f"  GUID: {control_guid}")
            
            if gruppe and feld:
                if gruppe in record_daten and isinstance(record_daten[gruppe], dict):
                    if feld in record_daten[gruppe]:
                        wert = record_daten[gruppe][feld]
                        print(f"  ✅ Wert: {wert if not isinstance(wert, dict) else f'Dict[{len(wert)}]'}")
                    else:
                        print(f"  ❌ FEHLER: Feld '{feld}' nicht in Gruppe gefunden")
                else:
                    print(f"  ❌ FEHLER: Gruppe '{gruppe}' nicht gefunden")
            else:
                print(f"  ⚠️  WARNING: gruppe oder feld nicht gesetzt")
            
            print()
        
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(full_api_test())

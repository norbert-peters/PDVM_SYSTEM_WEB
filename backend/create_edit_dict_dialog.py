"""
Erstellt sys_dialogdaten Entry für edit_dict Dialog

edit_dict ist der Dialog zum Bearbeiten von sys_control_dict mit Template-Merge-Logik.

WICHTIG: Benötigt:
- sys_viewdaten für sys_control_dict View
- sys_framedaten für Edit-Frame
- edit_type="edit_dict" in ROOT
"""

import asyncio
import asyncpg
import json
import uuid
from datetime import datetime

# ===== Konfiguration =====

SYSTEM_DB_URL = "postgresql://postgres:postgres@localhost:5432/pdvm_system"

# GUIDs für Dialog
DIALOG_GUID = uuid.UUID("ed1cd1c7-0000-0000-0000-000000000001")  # ed1cdict-...
VIEW_GUID = uuid.UUID("ed1cd1c7-0000-0000-0000-000000000002")
FRAME_GUID = uuid.UUID("ed1cd1c7-0000-0000-0000-000000000003")

# Fake User GUID (wird später durch echte ersetzt)
USER_GUID = uuid.UUID("11111111-1111-1111-1111-111111111111")


async def main():
    print("🚀 Erstelle edit_dict Dialog-System...")
    print(f"   Dialog-GUID: {DIALOG_GUID}")
    print(f"   View-GUID:   {VIEW_GUID}")
    print(f"   Frame-GUID:  {FRAME_GUID}")
    
    conn = await asyncpg.connect(SYSTEM_DB_URL)
    
    try:
        # ===== 1. sys_viewdaten: View auf sys_control_dict =====
        
        print("\n📊 Erstelle sys_viewdaten Entry...")
        
        view_daten = {
            "ROOT": {
                "TABLE": "sys_control_dict",
                "SELF_GUID": str(VIEW_GUID),
                "SELF_NAME": "edit_dict_view"
            },
            "VIEW": {
                "columns": [
                    {"key": "uid", "label": "UID", "width": 80, "show": False},
                    {"key": "name", "label": "Name", "width": 200, "show": True, "sortable": True},
                    {"key": "modul_type", "label": "MODUL", "width": 100, "show": True, "sortable": True},
                    {"key": "created_at", "label": "Erstellt", "width": 150, "show": True, "sortable": True},
                    {"key": "updated_at", "label": "Geändert", "width": 150, "show": True, "sortable": True}
                ],
                "filters": [],
                "sort": {"column": "name", "ascending": True}
            }
        }
        
        await conn.execute("""
            INSERT INTO sys_viewdaten (uid, user_guid, name, daten, historisch, created_at, modified_at)
            VALUES ($1, $2, $3, $4, 0, NOW(), NOW())
            ON CONFLICT (uid) DO UPDATE
            SET daten = EXCLUDED.daten, modified_at = NOW()
        """, VIEW_GUID, USER_GUID, "edit_dict View", json.dumps(view_daten))
        
        print("✅ sys_viewdaten erstellt")
        
        # ===== 2. sys_framedaten: Edit-Frame (noch minimal) =====
        
        print("\n🖼️ Erstelle sys_framedaten Entry...")
        
        frame_daten = {
            "ROOT": {
                "TABLE": "sys_control_dict",
                "SELF_GUID": str(FRAME_GUID),
                "SELF_NAME": "edit_dict_frame"
            },
            "FRAME": {
                "layout": "form",
                "fields": [
                    {
                        "key": "name",
                        "label": "Name",
                        "type": "string",
                        "required": True
                    },
                    {
                        "key": "modul_type",
                        "label": "MODUL-Typ",
                        "type": "string",
                        "read_only": True,
                        "help": "edit, view, tabs - wird bei Erstellung gewählt"
                    },
                    {
                        "key": "daten",
                        "label": "Daten (JSON)",
                        "type": "text",
                        "rows": 20
                    }
                ]
            }
        }
        
        await conn.execute("""
            INSERT INTO sys_framedaten (uid, user_guid, name, daten, historisch, created_at, modified_at)
            VALUES ($1, $2, $3, $4, 0, NOW(), NOW())
            ON CONFLICT (uid) DO UPDATE
            SET daten = EXCLUDED.daten, modified_at = NOW()
        """, FRAME_GUID, USER_GUID, "edit_dict Frame", json.dumps(frame_daten))
        
        print("✅ sys_framedaten erstellt")
        
        # ===== 3. sys_dialogdaten: Dialog mit edit_type="edit_dict" =====
        
        print("\n🎭 Erstelle sys_dialogdaten Entry...")
        
        dialog_daten = {
            "ROOT": {
                "TABLE": "sys_control_dict",
                "EDIT_TYPE": "edit_dict",
                "VIEW_GUID": str(VIEW_GUID),
                "FRAME_GUID": str(FRAME_GUID),
                "SELF_GUID": str(DIALOG_GUID),
                "SELF_NAME": "edit_dict Dialog"
            },
            "DIALOG": {
                "title": "Control Dictionary Editor",
                "description": "Erstelle und bearbeite Controls mit Template-Merge-System",
                "tabs": [
                    {
                        "key": "view",
                        "label": "Controls (Liste)",
                        "type": "view",
                        "view_guid": str(VIEW_GUID)
                    },
                    {
                        "key": "edit",
                        "label": "Control (Bearbeiten)",
                        "type": "edit",
                        "frame_guid": str(FRAME_GUID)
                    }
                ]
            }
        }
        
        await conn.execute("""
            INSERT INTO sys_dialogdaten (uid, user_guid, name, daten, historisch, created_at, modified_at)
            VALUES ($1, $2, $3, $4, 0, NOW(), NOW())
            ON CONFLICT (uid) DO UPDATE
            SET daten = EXCLUDED.daten, modified_at = NOW()
        """, DIALOG_GUID, USER_GUID, "edit_dict Dialog", json.dumps(dialog_daten))
        
        print("✅ sys_dialogdaten erstellt")
        
        # ===== 4. Verifikation =====
        
        print("\n🔍 Verifikation...")
        
        check = await conn.fetchrow("""
            SELECT uid, name, daten FROM sys_dialogdaten WHERE uid = $1
        """, DIALOG_GUID)
        
        if check:
            daten = check['daten']
            if isinstance(daten, str):
                daten = json.loads(daten)
            
            print(f"✅ Dialog '{check['name']}' gefunden")
            print(f"   edit_type: {daten['ROOT']['EDIT_TYPE']}")
            print(f"   VIEW_GUID: {daten['ROOT']['VIEW_GUID']}")
            print(f"   FRAME_GUID: {daten['ROOT']['FRAME_GUID']}")
        else:
            print("❌ Dialog nicht gefunden!")
        
        print("\n" + "="*60)
        print("✅ edit_dict Dialog-System komplett erstellt!")
        print("="*60)
        print("\nZum Testen:")
        print(f"1. Backend: http://localhost:8000/docs")
        print(f"2. API-Test: GET /api/dialogs/{DIALOG_GUID}")
        print(f"3. Modul-Auswahl: GET /api/dialogs/{DIALOG_GUID}/modul-selection")
        print(f"4. Neuer Satz: POST /api/dialogs/{DIALOG_GUID}/record")
        print(f"   → Mit modul_type='edit' im Body")
        
    except Exception as e:
        print(f"\n❌ Fehler: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())

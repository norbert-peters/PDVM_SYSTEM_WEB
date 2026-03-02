-- =====================================================
-- edit_dict Dialog System Setup
-- =====================================================
-- 
-- Erstellt sys_dialogdaten, sys_viewdaten und sys_framedaten
-- für den edit_dict Dialog (Control Dictionary Editor)
--
-- WICHTIG: edit_type="edit_dict" aktiviert Template-Merge-Logik
-- =====================================================

-- ===== GUIDs festlegen =====

-- Dialog
\set dialog_guid 'ed1cd1c7-0000-0000-0000-000000000001'
\set view_guid   'ed1cd1c7-0000-0000-0000-000000000002'
\set frame_guid  'ed1cd1c7-0000-0000-0000-000000000003'
\set user_guid   '11111111-1111-1111-1111-111111111111'

-- ===== 1. sys_viewdaten: View auf sys_control_dict =====

INSERT INTO sys_viewdaten (uid, user_guid, name, daten, historisch, created_at, modified_at)
VALUES (
    'ed1cd1c7-0000-0000-0000-000000000002'::uuid,
    '11111111-1111-1111-1111-111111111111'::uuid,
    'edit_dict View',
    '{
        "ROOT": {
            "TABLE": "sys_control_dict",
            "SELF_GUID": "ed1cd1c7-0000-0000-0000-000000000002",
            "SELF_NAME": "edit_dict_view"
        },
        "VIEW": {
            "columns": [
                {"key": "uid", "label": "UID", "width": 80, "show": false},
                {"key": "name", "label": "Name", "width": 200, "show": true, "sortable": true},
                {"key": "modul_type", "label": "MODUL", "width": 100, "show": true, "sortable": true},
                {"key": "created_at", "label": "Erstellt", "width": 150, "show": true, "sortable": true},
                {"key": "updated_at", "label": "Geändert", "width": 150, "show": true, "sortable": true}
            ],
            "filters": [],
            "sort": {"column": "name", "ascending": true}
        }
    }'::jsonb,
    0,
    NOW(),
    NOW()
)
ON CONFLICT (uid) DO UPDATE
SET daten = EXCLUDED.daten, modified_at = NOW();

-- ===== 2. sys_framedaten: Edit-Frame (noch minimal) =====

INSERT INTO sys_framedaten (uid, user_guid, name, daten, historisch, created_at, modified_at)
VALUES (
    'ed1cd1c7-0000-0000-0000-000000000003'::uuid,
    '11111111-1111-1111-1111-111111111111'::uuid,
    'edit_dict Frame',
    '{
        "ROOT": {
            "TABLE": "sys_control_dict",
            "SELF_GUID": "ed1cd1c7-0000-0000-0000-000000000003",
            "SELF_NAME": "edit_dict_frame"
        },
        "FRAME": {
            "layout": "form",
            "fields": [
                {
                    "key": "name",
                    "label": "Name",
                    "type": "string",
                    "required": true
                },
                {
                    "key": "modul_type",
                    "label": "MODUL-Typ",
                    "type": "string",
                    "read_only": true,
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
    }'::jsonb,
    0,
    NOW(),
    NOW()
)
ON CONFLICT (uid) DO UPDATE
SET daten = EXCLUDED.daten, modified_at = NOW();

-- ===== 3. sys_dialogdaten: Dialog mit edit_type="edit_dict" =====

INSERT INTO sys_dialogdaten (uid, user_guid, name, daten, historisch, created_at, modified_at)
VALUES (
    'ed1cd1c7-0000-0000-0000-000000000001'::uuid,
    '11111111-1111-1111-1111-111111111111'::uuid,
    'edit_dict Dialog',
    '{
        "ROOT": {
            "TABLE": "sys_control_dict",
            "EDIT_TYPE": "edit_dict",
            "VIEW_GUID": "ed1cd1c7-0000-0000-0000-000000000002",
            "FRAME_GUID": "ed1cd1c7-0000-0000-0000-000000000003",
            "SELF_GUID": "ed1cd1c7-0000-0000-0000-000000000001",
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
                    "view_guid": "ed1cd1c7-0000-0000-0000-000000000002"
                },
                {
                    "key": "edit",
                    "label": "Control (Bearbeiten)",
                    "type": "edit",
                    "frame_guid": "ed1cd1c7-0000-0000-0000-000000000003"
                }
            ]
        }
    }':: jsonb,
    0,
    NOW(),
    NOW()
)
ON CONFLICT (uid) DO UPDATE
SET daten = EXCLUDED.daten, modified_at = NOW();

-- ===== Verifikation =====

SELECT 
    'sys_dialogdaten' AS tabelle,
    uid, 
    name,
    daten->>'ROOT' AS root_config
FROM sys_dialogdaten 
WHERE uid = 'ed1cd1c7-0000-0000-0000-000000000001'::uuid;

SELECT 
    'sys_viewdaten' AS tabelle,
    uid, 
    name
FROM sys_viewdaten 
WHERE uid = 'ed1cd1c7-0000-0000-0000-000000000002'::uuid;

SELECT 
    'sys_framedaten' AS tabelle,
    uid, 
    name
FROM sys_framedaten 
WHERE uid = 'ed1cd1c7-0000-0000-0000-000000000003'::uuid;

-- =====================================================
-- ✅ edit_dict Dialog-System komplett erstellt!
-- =====================================================
--
-- Zum Testen:
-- 1. Backend: http://localhost:8000/docs
-- 2. API-Test: GET /api/dialogs/ed1cd1c7-0000-0000-0000-000000000001
-- 3. Modul-Auswahl: GET /api/dialogs/ed1cd1c7-0000-0000-0000-000000000001/modul-selection
-- 4. Neuer Satz: POST /api/dialogs/ed1cd1c7-0000-0000-0000-000000000001/record
--    → Mit modul_type='edit' im Body
-- =====================================================

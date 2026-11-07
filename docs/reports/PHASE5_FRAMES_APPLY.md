# Phase 5: sys_framedaten bereinigen (APPLY)

21 Frames geaendert, 62 neue Controls.

- neues Control `SYS_VALIDATE_ACTION`
- neues Control `SYS_BUILD_ACTION`
- neues Control `SYS_ABORT_ACTION`
- neues Control `SYS_CREATE_CONTROL_ACTION`
- neues Control `SYS_DICTIONARY_SEARCH`
- neues Control `SYS_FIELDS_TYPE`
- neues Control `SYS_CONTROL_FIELD`
- neues Control `SYS_ROOT_CONTROL`
- neues Control `SYS_ROOT_SELF_GUID`
- neues Control `SYS_ROOT_SELF_NAME`
- neues Control `SYS_ROOT_TABLE`
- neues Control `SYS_DIALOG_TYPE`
- neues Control `SYS_ROOT_TABS`
- neues Control `SYS_ROOT_MODULE`
- neues Control `SYS_TAB_ELEMENTS`
- neues Control `SYS_OPEN_EDIT`
- neues Control `SYS_ROOT_TABLE_2`
- neues Control `SYS_ROOT_HEAD`
- neues Control `SYS_ROOT_TYPE`
- neues Control `SYS_SELECTION_MODE`
- neues Control `SYS_ROOT_GUID`
- neues Control `SYS_ROOT_TAB`
- neues Control `SYS_EDIT_TYPE`
- neues Control `SYS_ROOT_DIALOG_TYPE`
- neues Control `SYS_ROOT_TAB_ELEMENTS`
- neues Control `SYS_ROOT_SELF_NAME_2`
- neues Control `SYS_WORKFLOW_NAME`
- neues Control `SYS_FIELDS_DIALOG_TYPE`
- neues Control `SYS_FIELDS_OPEN_EDIT`
- neues Control `SYS_FIELDS_SELECTION_MODE`
- neues Control `SYS_FIELDS_TABLE`
- neues Control `SYS_SAVE_VIEW_ACTION`
- neues Control `SYS_FIELDS_NAME`
- neues Control `SYS_VIEW_PROJECTION`
- neues Control `SYS_SOURCE_COMMIT`
- neues Control `SYS_FIELDS_TYPE_2`
- neues Control `SYS_TARGET_ENV`
- neues Control `SYS_SOURCE_DB_ROLE`
- neues Control `SYS_PACKAGE_HASH`
- neues Control `SYS_POLICY_MODE`
- neues Control `SYS_TARGET_DB_ROLE`
- neues Control `SYS_ELEMENT_FELD`
- neues Control `SYS_ELEMENT_GRUPPE`
- neues Control `SYS_ELEMENT_KEY`
- neues Control `SYS_APPLY_ACTION`
- neues Control `SYS_DRY_RUN_ACTION`
- neues Control `SYS_FRAME_GUID`
- neues Control `SYS_TAB_REF`
- neues Control `SYS_VIEW_GUID`
- neues Control `SYS_FIELDS_EDIT_TYPE`
- neues Control `SYS_SAVE_CONTENT_ACTION`
- neues Control `SYS_CREATE_PROPERTY_ACTION`
- neues Control `SYS_TABLE_PREFIX_FILTER`
- neues Control `SYS_FIELDS_DICTIONARY_SEARCH`
- neues Control `SYS_CONTROL_CONFIGS`
- neues Control `SYS_FIELDS_SELF_NAME`
- neues Control `SYS_FIELDS_HEADER`
- neues Control `SYS_FIELDS_TABLE_2`
- neues Control `SYS_FIELDS_SELECTION_MODE_2`
- neues Control `SYS_FIELDS_OPEN_EDIT_2`
- neues Control `SYS_ROOT_TAB_ELEMENTS_2`
- neues Control `SYS_ROOT_TAB_ELEMENTS_3`

## Benutzer Edit (0d024e06)
- 1.10b: Verweis a12c4a2e auf nicht vorhandenes Control entfernt
- 1.10b: Verweis a7a8de14 auf nicht vorhandenes Control entfernt
- 1.10b: Verweis bdf1b157 auf nicht vorhandenes Control entfernt
- 1.10b: Verweis c0bfce8f auf nicht vorhandenes Control entfernt
- 1.10b: Verweis e4c5aa98 auf nicht vorhandenes Control entfernt
- 1.10b: FIELDS 30 -> 25 Eintraege normalisiert
## Edit Frame (4413571e)
- 1.10b: FIELDS 6 -> 6 Eintraege normalisiert
## Frame ConfigElements allg (f46fcf0c)
- 1.10b: Feld FELD (31941830) -> neues Control SYS_ELEMENT_FELD
- 1.10b: Feld GRUPPE (a611fe31) -> neues Control SYS_ELEMENT_GRUPPE
- 1.10b: Feld KEY (ba8fb7a3) -> neues Control SYS_ELEMENT_KEY
- 1.10b: FIELDS 4 -> 4 Eintraege normalisiert
## Für Dialog Aufbau (20de7493)
- 1.10b: Feld EDIT_TYPE (0f83e550) -> neues Control SYS_EDIT_TYPE
- 1.10b: Feld SELF_GUID (6437c5a9) -> Control 11111111 (Semantik aus dem Frame entfernt)
- 1.10b: Feld DIALOG_TYPE (8cdad050) -> neues Control SYS_ROOT_DIALOG_TYPE
- 1.10b: Feld TAB_ELEMENTS (9c74939e) -> neues Control SYS_ROOT_TAB_ELEMENTS
- 1.10b: Verweis aa64eead auf nicht vorhandenes Control entfernt
- 1.10b: Feld TABS (b78b41ec) -> Control 11111111 (Semantik aus dem Frame entfernt)
- 1.10b: Feld TABLE (c47b969a) -> Control c47b969a (Semantik aus dem Frame entfernt)
- 1.10b: Feld SELF_NAME (c75d12c6) -> neues Control SYS_ROOT_SELF_NAME_2
- 1.10b: FIELDS 8 -> 7 Eintraege normalisiert
## Für Dialog Aufbau_ELEMENT_EDITOR (36fa5117)
- 1.10b: Feld TAB_ELEMENTS (9c74939e) -> Control edd8b26e (Semantik aus dem Frame entfernt)
- 1.10b: FIELDS 1 -> 1 Eintraege normalisiert
- 1.22: name 'Für Dialog Aufbau_ELEMENT_EDITOR' -> 'Für Dialog Aufbau_ELEMENT_EDITOR_TAB_ELEMENTS'
## Text bearbeiten (b68a5b55)
- 1.22: name 'Text bearbeiten' -> 'Text bearbeiten Frame'
## WORKFLOW_APPLY_FRAME_TEMPLATE (9b534385)
- 1.10b: Feld APPLY_ACTION (62c736b3) -> neues Control SYS_APPLY_ACTION
- 1.10b: Feld DRY_RUN_ACTION (d87d080f) -> neues Control SYS_DRY_RUN_ACTION
- 1.10b: FIELDS 2 -> 2 Eintraege normalisiert
## WORKFLOW_DIALOG_CONFIG_FRAME_TEMPLATE (56842fa2)
- 1.10b: Feld WORKFLOW_NAME (0c1f400d) -> neues Control SYS_WORKFLOW_NAME
- 1.10b: Feld DIALOG_TYPE (4677f477) -> neues Control SYS_FIELDS_DIALOG_TYPE
- 1.10b: Feld OPEN_EDIT (75c11f5f) -> neues Control SYS_FIELDS_OPEN_EDIT
- 1.10b: Feld SELECTION_MODE (eef4b4bf) -> neues Control SYS_FIELDS_SELECTION_MODE
- 1.10b: FIELDS 4 -> 4 Eintraege normalisiert
## WORKFLOW_DICTIONARY_FRAME_TEMPLATE (3a6e8cca)
- 1.10b: Feld CREATE_CONTROL_ACTION (6e5c5c95) -> neues Control SYS_CREATE_CONTROL_ACTION
- 1.10b: Feld DICTIONARY_SEARCH (7f8739fa) -> neues Control SYS_DICTIONARY_SEARCH
- 1.10b: Feld TYPE (cb7a1850) -> neues Control SYS_FIELDS_TYPE
- 1.10b: Feld CONTROL_FIELD (f12439a3) -> neues Control SYS_CONTROL_FIELD
- 1.10b: FIELDS 4 -> 4 Eintraege normalisiert
## WORKFLOW_DRAFT_BUILD_FRAME_TEMPLATE (72d54053)
- 1.10b: Feld VALIDATE_ACTION (5d53c6ce) -> neues Control SYS_VALIDATE_ACTION
- 1.10b: Feld BUILD_ACTION (6f965a0d) -> neues Control SYS_BUILD_ACTION
- 1.10b: Feld ABORT_ACTION (ac1e2692) -> neues Control SYS_ABORT_ACTION
- 1.10b: FIELDS 3 -> 3 Eintraege normalisiert
## WORKFLOW_DRAFT_CONTENT_FRAME_TEMPLATE (2ac77a9a)
- 1.10b: Feld FRAME_GUID (11ed9f64) -> neues Control SYS_FRAME_GUID
- 1.10b: Feld TAB_REF (179e8c6a) -> neues Control SYS_TAB_REF
- 1.10b: Feld VIEW_GUID (94dcd843) -> neues Control SYS_VIEW_GUID
- 1.10b: Feld EDIT_TYPE (c6ee99aa) -> neues Control SYS_FIELDS_EDIT_TYPE
- 1.10b: Feld SAVE_CONTENT_ACTION (f7fbc9b9) -> neues Control SYS_SAVE_CONTENT_ACTION
- 1.10b: FIELDS 5 -> 5 Eintraege normalisiert
## WORKFLOW_DRAFT_SETUP_FRAME_TEMPLATE (75e5262a)
- 1.10b: Feld SELF_NAME (4c1e5a97) -> neues Control SYS_FIELDS_SELF_NAME
- 1.10b: Feld HEADER (4ce4951c) -> neues Control SYS_FIELDS_HEADER
- 1.10b: Feld TABLE (b0bbfd48) -> neues Control SYS_FIELDS_TABLE_2
- 1.10b: Feld SELECTION_MODE (f9fb58c1) -> neues Control SYS_FIELDS_SELECTION_MODE_2
- 1.10b: Feld OPEN_EDIT (fd6f6857) -> neues Control SYS_FIELDS_OPEN_EDIT_2
- 1.10b: FIELDS 5 -> 5 Eintraege normalisiert
## WORKFLOW_DRAFT_TABS_FRAME_TEMPLATE (886842eb)
- 1.10b: Feld TAB_ELEMENTS (b6bd31d9) -> neues Control SYS_ROOT_TAB_ELEMENTS_3
- 1.10b: FIELDS 1 -> 1 Eintraege normalisiert
## WORKFLOW_DRAFT_VIEW_FRAME_TEMPLATE (01a520ea)
- 1.10b: Feld TABLE (61b2a091) -> neues Control SYS_FIELDS_TABLE
- 1.10b: Feld SAVE_VIEW_ACTION (75defedf) -> neues Control SYS_SAVE_VIEW_ACTION
- 1.10b: Feld NAME (9d1aae3b) -> neues Control SYS_FIELDS_NAME
- 1.10b: Feld VIEW_PROJECTION (f5eea547) -> neues Control SYS_VIEW_PROJECTION
- 1.10b: FIELDS 4 -> 4 Eintraege normalisiert
## WORKFLOW_PROPERTY_MAPPING_FRAME_TEMPLATE (c3af9a12)
- 1.10b: Feld CREATE_PROPERTY_ACTION (9a84d71a) -> neues Control SYS_CREATE_PROPERTY_ACTION
- 1.10b: Feld TABLE_PREFIX_FILTER (ccb6cb77) -> neues Control SYS_TABLE_PREFIX_FILTER
- 1.10b: Feld DICTIONARY_SEARCH (efd82195) -> neues Control SYS_FIELDS_DICTIONARY_SEARCH
- 1.10b: FIELDS 3 -> 3 Eintraege normalisiert
## WORKFLOW_SETUP_FRAME_TEMPLATE (bd919b17)
- 1.10b: Feld SOURCE_COMMIT (67a2be22) -> neues Control SYS_SOURCE_COMMIT
- 1.10b: Feld TYPE (72c58080) -> neues Control SYS_FIELDS_TYPE_2
- 1.10b: Feld TARGET_ENV (776676f6) -> neues Control SYS_TARGET_ENV
- 1.10b: Feld SOURCE_DB_ROLE (87cc7ac2) -> neues Control SYS_SOURCE_DB_ROLE
- 1.10b: Feld PACKAGE_HASH (93139920) -> neues Control SYS_PACKAGE_HASH
- 1.10b: Feld POLICY_MODE (98e377f3) -> neues Control SYS_POLICY_MODE
- 1.10b: Feld TARGET_DB_ROLE (d0dfbf3f) -> neues Control SYS_TARGET_DB_ROLE
- 1.10b: FIELDS 7 -> 7 Eintraege normalisiert
## WORKFLOW_TAB_ELEMENTS_EDITOR_FRAME (a6c4f9b6)
- 1.10b: Verweis 2527428c auf nicht vorhandenes Control entfernt
- 1.10b: Verweis 2e80a941 auf nicht vorhandenes Control entfernt
- 1.10b: Verweis 6690c5cc auf nicht vorhandenes Control entfernt
- 1.10b: Verweis 83a22531 auf nicht vorhandenes Control entfernt
- 1.10b: FIELDS 7 -> 3 Eintraege normalisiert
## sys_control_dict Frame (ebb4a327)
- 1.10b: Feld CONFIGS (e498abbe) -> neues Control SYS_CONTROL_CONFIGS
- 1.10b: FIELDS 31 -> 31 Eintraege normalisiert
## sys_control_dict Frame_ELEMENT_EDITOR (8d157d69)
- 1.10b: Feld CONTROL (33333333) -> neues Control SYS_ROOT_CONTROL
- 1.10b: FIELDS 1 -> 1 Eintraege normalisiert
- 1.22: name 'sys_control_dict Frame_ELEMENT_EDITOR' -> 'sys_control_dict Frame_ELEMENT_EDITOR_CONTROL'
## sys_dialogdaten Frame (Linear) (1f3a0e00)
- 1.10b: Feld SELF_GUID (11111111) -> neues Control SYS_ROOT_SELF_GUID
- 1.10b: Feld SELF_NAME (11111111) -> neues Control SYS_ROOT_SELF_NAME
- 1.10b: Feld TABLE (11111111) -> neues Control SYS_ROOT_TABLE
- 1.10b: Feld DIALOG_TYPE (11111111) -> neues Control SYS_DIALOG_TYPE
- 1.10b: Feld TABS (11111111) -> neues Control SYS_ROOT_TABS
- 1.10b: Feld MODULE (1f87d3eb) -> neues Control SYS_ROOT_MODULE
- 1.10b: Feld TAB_ELEMENTS (22222222) -> neues Control SYS_TAB_ELEMENTS
- 1.10b: Feld OPEN_EDIT (40b932df) -> neues Control SYS_OPEN_EDIT
- 1.10b: Feld TABLE (5c58971a) -> neues Control SYS_ROOT_TABLE_2
- 1.10b: Feld HEAD (82b20574) -> neues Control SYS_ROOT_HEAD
- 1.10b: Feld TYPE (958c6e06) -> neues Control SYS_ROOT_TYPE
- 1.10b: Feld SELECTION_MODE (a78992a9) -> neues Control SYS_SELECTION_MODE
- 1.10b: Feld GUID (b5cc762e) -> neues Control SYS_ROOT_GUID
- 1.10b: Feld TAB (facaa457) -> neues Control SYS_ROOT_TAB
- 1.10b: FIELDS 14 -> 14 Eintraege normalisiert
## sys_dialogdaten Frame (Linear)_ELEMENT_EDITOR (3dccd4cf)
- 1.10b: Feld TAB_ELEMENTS (22222222) -> neues Control SYS_ROOT_TAB_ELEMENTS_2
- 1.10b: FIELDS 1 -> 1 Eintraege normalisiert
- 1.22: name 'sys_dialogdaten Frame (Linear)_ELEMENT_EDITOR' -> 'sys_dialogdaten Frame (Linear)_ELEMENT_EDITOR_TAB_ELEMENTS'

## Dokumentierte Ausnahmen (unveraendert)
- Menüdaten Edit: Feld 'tooltip' (Kleinschreib-Datenschluessel) unveraendert
- Menüdaten Edit: Feld 'icon' (Kleinschreib-Datenschluessel) unveraendert
- Menüdaten Edit: Feld 'template_guid' (Kleinschreib-Datenschluessel) unveraendert
- Menüdaten Edit: Feld 'label' (Kleinschreib-Datenschluessel) unveraendert
- Menüdaten Edit: Feld 'enable' (Kleinschreib-Datenschluessel) unveraendert
- Menüdaten Edit: Feld 'visible' (Kleinschreib-Datenschluessel) unveraendert
- Menüdaten Edit: Feld 'command' (Kleinschreib-Datenschluessel) unveraendert

Snapshot: `C:\Users\norbe\dev\PDVM_SYSTEM_WEB\backend\reports\phase5_frames_snapshot_20261107_160241.json`

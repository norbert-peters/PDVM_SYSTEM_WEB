# Audit Systemdaten (read-only)

Pruefgrundlage: ARCHITECTURE_RULES.md. Erzeugt von `backend/tools/audit_system_data.py`.

## Bestand
- **pdvm_system**: dev_workflow_draft=21, sys_beschreibungen=4, sys_control_dict=121, sys_dialogdaten=21, sys_dropdowndaten=28, sys_ext_table=6, sys_feld_aenderungshistorie=1078, sys_framedaten=31, sys_framedaten.FIELDS=174, sys_layout=6, sys_menudaten=14, sys_systemdaten=29, sys_tooltipdaten=4, sys_viewdaten=13
- **pdvm_standard**: msy_anwendungsdaten=4, msy_error_acknowledgments=3, msy_error_log=3, msy_ext_table=3, msy_feld_aenderungshistorie=2562, msy_layout=4, msy_security=3, msy_systemdaten=15, msy_systemsteuerung=5, tst_finanzdaten=3, tst_persondaten=4
- **mandant**: msy_anwendungsdaten=4, msy_error_acknowledgments=3, msy_error_log=3, msy_ext_table=3, msy_feld_aenderungshistorie=106, msy_layout=4, msy_security=3, msy_systemdaten=15, msy_systemsteuerung=6, tst_finanzdaten=5, tst_persondaten=28

## Zusammenfassung je Regel
- pdvm_system / Regel 1.10: 14
- pdvm_system / Regel 1.10a: 3
- pdvm_system / Regel 1.10b: 2
- pdvm_system / Regel 1.12b: 118
- pdvm_system / Regel 1.21: 3
- pdvm_system / Regel 1.22: 16

## Befunde
### pdvm_system / sys_control_dict / Regel 1.10 (14)
- SYS_TEXXT_KEY (de5429ff): name 'SYS_TEXXT_KEY' != 'SYS_TEXT_KEY'
- SYS_CONFIGS_ELEMENT_KEY (b877a216): name 'SYS_CONFIGS_ELEMENT_KEY' != 'SYS_KEY'
- ASY_TAB (a6c0d956): name 'ASY_TAB' != 'SYS_TAB'
- SYS_TEST (3cefa715): FIELD 'eingeben' nicht GROSS
- SYS_TEST (3cefa715): name 'SYS_TEST' != 'SYS_EINGEBEN'
- SYS_TEST_1 (00963f4c): FIELD 'eingeben' nicht GROSS
- SYS_TEST_1 (00963f4c): name 'SYS_TEST_1' != 'SYS_EINGEBEN'
- SYS_PRENT_GUID (458b92e5): name 'SYS_PRENT_GUID' != 'SYS_PARENT_GUID'
- SYS_TEXT_22 (470ced5e): FIELD 'eingeben' nicht GROSS
- SYS_TEXT_22 (470ced5e): name 'SYS_TEXT_22' != 'SYS_EINGEBEN'
- ASY_THEME_LIGHT (ef6a4b8a): name 'ASY_THEME_LIGHT' != 'ASY_LIGHT'
- SYS_VALUE (05102810): name 'SYS_VALUE' != 'SYS_VALUES'
- ASY_PASSWORD_CHANGE (be5aa2cd): name 'ASY_PASSWORD_CHANGE' != 'ASY_LAST_PASSWORD_CHANGE'
- SYS_PROFILES (c06c632c): name 'SYS_PROFILES' != 'ASY_PROFILES'

### pdvm_system / sys_control_dict / Regel 1.10a (3)
- Eigenschaft 'FIELDS_ELEMENTS' (31x) nicht im Muttercontrol
- Eigenschaft 'CONFIGS_ELEMENTS' (31x) nicht im Muttercontrol
- Eigenschaft 'DISPLAY_ODER' (1x) nicht im Muttercontrol

### pdvm_system / sys_framedaten / Regel 1.10b (2)
- 74 FIELDS-Eintraege verweisen auf keine vorhandene sys_control_dict-UID
- FIELDS mit Kleinschreib-Legacy-Eigenschaften (Control-Semantik im Frame statt in sys_control_dict): display_order:135, tab:131, gruppe:74, label:73, feld:69, name:69, type:69, table:69, read_only:69, configs:51, source_path:46, abdatum:44

### pdvm_system / sys_control_dict / Regel 1.12b (118)
- SYS_ONLY (647a2da6): FIELD und FELD parallel (Alias-Verbot)
- SYS_SELF_GILT_BIS (620e5496): FIELD und FELD parallel (Alias-Verbot)
- SYS_TABLE (c47b969a): FIELD und FELD parallel (Alias-Verbot)
- SYS_TEXXT_KEY (de5429ff): FIELD und FELD parallel (Alias-Verbot)
- SYS_CONFIGS_ELEMENT_KEY (b877a216): FIELD und FELD parallel (Alias-Verbot)
- SYS_READ_ONLY (6f36511b): FIELD und FELD parallel (Alias-Verbot)
- SYS_REF (21abe21a): FIELD und FELD parallel (Alias-Verbot)
- ASY_NACHNAME (11e1b3b3): FIELD und FELD parallel (Alias-Verbot)
- SYS_PARENT_GUID (8e19dd43): FIELD und FELD parallel (Alias-Verbot)
- SYS_APPROVED_BY (47cff1c2): FIELD und FELD parallel (Alias-Verbot)
- SYS_SEARCH (24067406): FIELD und FELD parallel (Alias-Verbot)
- ASY_MODE (3addcaa2): FIELD und FELD parallel (Alias-Verbot)
- SYS_EN-US (149840f8): FIELD und FELD parallel (Alias-Verbot)
- SYS_EXPERT_ORDER (bb3e9f05): FIELD und FELD parallel (Alias-Verbot)
- SYS_HEAD (6bed65d9): FIELD und FELD parallel (Alias-Verbot)
- ... 103 weitere

### pdvm_system / sys_viewdaten / Regel 1.21 (3)
- WORKFLOW_DRAFT_ITEMS_VIEW_TEMPLATE (46ac9e21): keine Datengruppe neben ROOT
- RELEASE_CANDIDATE_VIEW_TEMPLATE (2160ff31): keine Datengruppe neben ROOT
- WORKFLOW_DICTIONARY_VIEW_TEMPLATE (78609ea1): keine Datengruppe neben ROOT

### pdvm_system / sys_control_dict / Regel 1.22 (11)
- SYS_TEXXT_KEY (de5429ff): SELF_NAME 'SYS_TEXT_KEY' != name 'SYS_TEXXT_KEY'
- SYS_SELF_MODIFIED_AT (743d430c): SELF_NAME 'SELF_MODIFIED_AT' != name 'SYS_SELF_MODIFIED_AT'
- SYS_PRENT_GUID (458b92e5): SELF_NAME 'SYS_PARENT_GUID' != name 'SYS_PRENT_GUID'
- SYS_VALUE (05102810): SELF_NAME 'SYS_VALUES' != name 'SYS_VALUE'
- SYS_UPPER_CASE (0a37bc7a): SELF_NAME 'SYS_UPPERCASE' != name 'SYS_UPPER_CASE'
- ASY_ANREDE (d6f90f6c): SELF_NAME 'AYS_ANREDE' != name 'ASY_ANREDE'
- ASY_PASSWORD_CHANGE (be5aa2cd): SELF_NAME 'ASY_LAST_PASSWORD_CHANGE' != name 'ASY_PASSWORD_CHANGE'
- ASY_EMAIL (c6b4fae2): SELF_NAME 'SYS_EMAIL' != name 'ASY_EMAIL'
- ASY_VORNAME (7a0d9b2f): SELF_NAME 'AYS_VORNAME' != name 'ASY_VORNAME'
- ASY_CHANGE_REQUIRED (c8f92080): SELF_NAME 'SYS_CHANGE_REQUIRED' != name 'ASY_CHANGE_REQUIRED'
- SYS_PROFILES (c06c632c): SELF_NAME 'ASY_PROFILES' != name 'SYS_PROFILES'

### pdvm_system / sys_dropdowndaten / Regel 1.22 (1)
-  (ddaa6590): SELF_NAME 'ddaa6590-6d08-461b-a061-75faec26f4ba' != name ''

### pdvm_system / sys_framedaten / Regel 1.22 (4)
- Text bearbeiten (b68a5b55): SELF_NAME 'Text bearbeiten Frame' != name 'Text bearbeiten'
- Für Dialog Aufbau_ELEMENT_EDITOR (36fa5117): SELF_NAME 'Für Dialog Aufbau_ELEMENT_EDITOR_TAB_ELEMENTS' != name 'Für Dialog Aufbau_ELEMENT_EDITOR'
- sys_control_dict Frame_ELEMENT_EDITOR (8d157d69): SELF_NAME 'sys_control_dict Frame_ELEMENT_EDITOR_CONTROL' != name 'sys_control_dict Frame_ELEMENT_EDITOR'
- sys_dialogdaten Frame (Linear)_ELEMENT_EDITOR (3dccd4cf): SELF_NAME 'sys_dialogdaten Frame (Linear)_ELEMENT_EDITOR_TAB_ELEMENTS' != name 'sys_dialogdaten Frame (Linear)_ELEMENT_EDITOR'

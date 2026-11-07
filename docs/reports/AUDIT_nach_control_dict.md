# Audit Systemdaten (read-only)

Pruefgrundlage: ARCHITECTURE_RULES.md. Erzeugt von `backend/tools/audit_system_data.py`.

## Bestand
- **pdvm_system**: dev_workflow_draft=21, sys_beschreibungen=4, sys_control_dict=116, sys_dialogdaten=21, sys_dropdowndaten=28, sys_ext_table=6, sys_feld_aenderungshistorie=1078, sys_framedaten=31, sys_framedaten.FIELDS=174, sys_layout=6, sys_menudaten=14, sys_systemdaten=29, sys_tooltipdaten=4, sys_viewdaten=13

## Zusammenfassung je Regel
- pdvm_system / Regel 1.10: 1
- pdvm_system / Regel 1.10b: 2
- pdvm_system / Regel 1.21: 3
- pdvm_system / Regel 1.22: 5

## Befunde
### pdvm_system / sys_control_dict / Regel 1.10 (1)
- SYS_PRENT_GUID (458b92e5): name 'SYS_PRENT_GUID' != 'SYS_PARENT_GUID'

### pdvm_system / sys_framedaten / Regel 1.10b (2)
- 74 FIELDS-Eintraege verweisen auf keine vorhandene sys_control_dict-UID
- FIELDS mit Kleinschreib-Legacy-Eigenschaften (Control-Semantik im Frame statt in sys_control_dict): display_order:135, tab:131, gruppe:74, label:73, feld:69, name:69, type:69, table:69, read_only:69, configs:51, source_path:46, abdatum:44

### pdvm_system / sys_viewdaten / Regel 1.21 (3)
- WORKFLOW_DRAFT_ITEMS_VIEW_TEMPLATE (46ac9e21): keine Datengruppe neben ROOT
- RELEASE_CANDIDATE_VIEW_TEMPLATE (2160ff31): keine Datengruppe neben ROOT
- WORKFLOW_DICTIONARY_VIEW_TEMPLATE (78609ea1): keine Datengruppe neben ROOT

### pdvm_system / sys_dropdowndaten / Regel 1.22 (1)
-  (ddaa6590): SELF_NAME 'ddaa6590-6d08-461b-a061-75faec26f4ba' != name ''

### pdvm_system / sys_framedaten / Regel 1.22 (4)
- Text bearbeiten (b68a5b55): SELF_NAME 'Text bearbeiten Frame' != name 'Text bearbeiten'
- Für Dialog Aufbau_ELEMENT_EDITOR (36fa5117): SELF_NAME 'Für Dialog Aufbau_ELEMENT_EDITOR_TAB_ELEMENTS' != name 'Für Dialog Aufbau_ELEMENT_EDITOR'
- sys_control_dict Frame_ELEMENT_EDITOR (8d157d69): SELF_NAME 'sys_control_dict Frame_ELEMENT_EDITOR_CONTROL' != name 'sys_control_dict Frame_ELEMENT_EDITOR'
- sys_dialogdaten Frame (Linear)_ELEMENT_EDITOR (3dccd4cf): SELF_NAME 'sys_dialogdaten Frame (Linear)_ELEMENT_EDITOR_TAB_ELEMENTS' != name 'sys_dialogdaten Frame (Linear)_ELEMENT_EDITOR'

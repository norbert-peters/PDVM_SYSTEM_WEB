# Audit Systemdaten (read-only)

Pruefgrundlage: ARCHITECTURE_RULES.md. Erzeugt von `backend/tools/audit_system_data.py`.

## Bestand
- **pdvm_system**: dev_workflow_draft=21, sys_beschreibungen=4, sys_control_dict=178, sys_dialogdaten=21, sys_dropdowndaten=28, sys_ext_table=6, sys_feld_aenderungshistorie=1078, sys_framedaten=31, sys_framedaten.FIELDS=164, sys_layout=6, sys_menudaten=14, sys_systemdaten=29, sys_tooltipdaten=4, sys_viewdaten=13

## Zusammenfassung je Regel
- pdvm_system / Regel 1.10: 35
- pdvm_system / Regel 1.10b: 2
- pdvm_system / Regel 1.21: 3
- pdvm_system / Regel 1.22: 1

## Befunde
### pdvm_system / sys_control_dict / Regel 1.10 (35)
- SYS_PRENT_GUID (458b92e5): name 'SYS_PRENT_GUID' != 'SYS_PARENT_GUID'
- SYS_FIELDS_TYPE (cb7a1850): name 'SYS_FIELDS_TYPE' != 'SYS_TYPE'
- SYS_ROOT_CONTROL (33333333): name 'SYS_ROOT_CONTROL' != 'SYS_CONTROL'
- SYS_ROOT_SELF_GUID (11111111): name 'SYS_ROOT_SELF_GUID' != 'SYS_SELF_GUID'
- SYS_ROOT_SELF_NAME (11111111): name 'SYS_ROOT_SELF_NAME' != 'SYS_SELF_NAME'
- SYS_ROOT_TABLE (11111111): name 'SYS_ROOT_TABLE' != 'SYS_TABLE'
- SYS_ROOT_TABS (11111111): name 'SYS_ROOT_TABS' != 'SYS_TABS'
- SYS_ROOT_MODULE (1f87d3eb): name 'SYS_ROOT_MODULE' != 'SYS_MODULE'
- SYS_ROOT_TABLE_2 (5c58971a): name 'SYS_ROOT_TABLE_2' != 'SYS_TABLE'
- SYS_ROOT_HEAD (82b20574): name 'SYS_ROOT_HEAD' != 'SYS_HEAD'
- SYS_ROOT_TYPE (958c6e06): name 'SYS_ROOT_TYPE' != 'SYS_TYPE'
- SYS_ROOT_GUID (b5cc762e): name 'SYS_ROOT_GUID' != 'SYS_GUID'
- SYS_ROOT_TAB (facaa457): name 'SYS_ROOT_TAB' != 'SYS_TAB'
- SYS_ROOT_DIALOG_TYPE (9bda7ab7): name 'SYS_ROOT_DIALOG_TYPE' != 'SYS_DIALOG_TYPE'
- SYS_ROOT_TAB_ELEMENTS (edd8b26e): name 'SYS_ROOT_TAB_ELEMENTS' != 'SYS_TAB_ELEMENTS'
- ... 20 weitere

### pdvm_system / sys_framedaten / Regel 1.10b (2)
- 9 FIELDS-Eintraege verweisen auf keine vorhandene sys_control_dict-UID
- FIELDS mit Kleinschreib-Legacy-Eigenschaften (Control-Semantik im Frame statt in sys_control_dict): dict_ref:8, tab:7, feld:7, name:7, type:7, label:7, table:7, gruppe:7, abdatum:7, configs:7, tooltip:7, read_only:7

### pdvm_system / sys_viewdaten / Regel 1.21 (3)
- WORKFLOW_DRAFT_ITEMS_VIEW_TEMPLATE (46ac9e21): keine Datengruppe neben ROOT
- RELEASE_CANDIDATE_VIEW_TEMPLATE (2160ff31): keine Datengruppe neben ROOT
- WORKFLOW_DICTIONARY_VIEW_TEMPLATE (78609ea1): keine Datengruppe neben ROOT

### pdvm_system / sys_dropdowndaten / Regel 1.22 (1)
-  (ddaa6590): SELF_NAME 'ddaa6590-6d08-461b-a061-75faec26f4ba' != name ''

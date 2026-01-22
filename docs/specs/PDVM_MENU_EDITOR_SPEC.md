# PDVM Menüeditor (edit_type = menu)

## Ziel
Ein spezialisierter Editor für `sys_menudaten`, der in einem Dialog über `edit_type = "menu"` verwendet wird.

- 2 Tabs:
  - Tab 1: **Grundmenü** → editiert Gruppe `GRUND`
  - Tab 2: **Vertikal Menü** → editiert Gruppe `VERTIKAL`
- Reihenfolge per Drag & Drop (MVP: innerhalb derselben Ebene / Geschwister)
- Regel: **Ein Submenü (Item mit Kindern) darf kein `command` haben**

## Dialog-Konfiguration (sys_dialogdaten)
In `sys_dialogdaten.daten.ROOT`:

- `EDIT_TYPE`: `menu`
- `MENU_GUID`: GUID eines Datensatzes in `sys_menudaten`
- Optional `SYSTEMDATEN_UID`: GUID eines Datensatzes in `sys_systemdaten` (Command-Katalog)

## Datenmodell sys_menudaten
`sys_menudaten.daten` enthält typischerweise:

- `ROOT` (Meta)
- `GRUND` (Items)
- `VERTIKAL` (Items)

Items sind als Dictionary gespeichert:

```json
{
  "GRUND": {
    "<item_uid>": {
      "type": "ITEM",
      "label": "Personen",
      "sort_order": 10,
      "parent_guid": null,
      "command": {
        "handler": "go_view",
        "params": { "view_guid": "..." }
      }
    }
  }
}
```

### Sortierung
- Sortiert wird über `sort_order`.
- Der Editor nummeriert bei Bedarf neu (10er Schritte) und speichert.

### Submenü-Regel
- Ein Item gilt als „Submenü“, sobald mindestens ein anderes Item `parent_guid = <dieses uid>` hat.
- Solche Items dürfen **kein** `command` besitzen.
- Backend entfernt `command` beim Speichern zusätzlich serverseitig.

## Command-Katalog (sys_systemdaten)
`sys_systemdaten` ist eine Systemtabelle im `pdvm_system`.

Erwartete Struktur in `daten` (Beispiel):

```json
{
  "ROOT": { "DEFAULT_LANGUAGE": "DE-DE" },
  "DE-DE": {
    "menü_command": {
      "commands": [
        {
          "handler": "go_view",
          "label": "View öffnen",
          "params": [
            { "name": "view_guid", "type": "guid", "required": true, "lookup_table": "sys_viewdaten" }
          ]
        },
        {
          "handler": "go_dialog",
          "label": "Dialog öffnen",
          "params": [
            { "name": "dialog_guid", "type": "guid", "required": true, "lookup_table": "sys_dialogdaten" },
            { "name": "dialog_table", "type": "table", "required": false }
          ]
        }
      ]
    }
  }
}
```

Hinweise:
- Feldname wird diakritik-insensitiv gelesen: `menü_command` und `menu_command` sind gleichwertig.
- Der Editor rendert Param-Felder anhand der `params`-Definition.
- Für `type = guid` + `lookup_table` bietet der Editor eine UID/Name-Auswahl.

## APIs
- `GET /api/menu-editor/{menu_guid}`
- `PUT /api/menu-editor/{menu_guid}` (speichert `daten`)
- `GET /api/systemdaten/menu-commands` (Command-Katalog)
- `GET /api/lookups/{table}` (uid/name Liste)

## MVP Einschränkungen
- Drag & Drop ist **nur innerhalb derselben Ebene** möglich (Geschwister unter gleichem `parent_guid`).
- Template-Expansion (SPACER/template_guid) wird im Editor nicht automatisch „expanded“; der Editor zeigt den Rohzustand aus `sys_menudaten`.

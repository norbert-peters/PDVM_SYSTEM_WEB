# PDVM Menüeditor (edit_type = menu)

## Ziel
Ein spezialisierter Editor für `sys_menudaten`, der in einem Dialog über `edit_type = "menu"` verwendet wird.

- 2 Tabs:
  - Tab 1: **Grundmenü** → editiert Gruppe `GRUND`
  - Tab 2: **Vertikal Menü** → editiert Gruppe `VERTIKAL`
- Struktur & Reihenfolge per Drag & Drop
  - Drop auf ein Item: sortiert innerhalb der Ebene (und kann per Parent-Wechsel auch Ebene wechseln)
  - Shift+Drop: hängt das Item als Kind ein
- Quick Actions pro Item: Einfügen, Einrücken/Ausrücken, Sortierung
- Regel: **Ein Item mit Kindern ist SUBMENU und darf kein `command` haben**

Stand (2026-01-23):
- Im Dialog gibt es zusätzlich `Refresh Edit` (lädt den Editbereich neu aus DB).
- Der aktive Menü-Edit-Tab (GRUND/VERTIKAL) wird pro Dialog persistent gespeichert und beim Öffnen wiederhergestellt.
- Es gibt eine Löschfunktion `-Item` mit Sicherheitsabfrage.

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
      "type": "BUTTON",
      "label": "Personen",
      "sort_order": 10,
      "parent_guid": null,
      "icon": null,
      "tooltip": "…",
      "enabled": true,
      "visible": true,
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
- Solche Items werden serverseitig als `type = SUBMENU` normalisiert und dürfen **kein** `command` besitzen.
- Wenn ein `SUBMENU` keine Kinder mehr hat, wird es wieder zu `type = BUTTON`.

Hinweis zu Templates:
- Menüs können Templates via `SPACER` + `template_guid` expandieren.
- Nach der Template-Expansion werden die Regeln (Parent ⇒ SUBMENU + command=null) beim Laden des Menüs serverseitig ebenfalls durchgesetzt.

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

Dialog UI-State (für `edit_type=menu`):
- `GET /api/dialogs/{dialog_guid}/ui-state`
- `PUT /api/dialogs/{dialog_guid}/ui-state`

Verwendete Keys (aktuell):
- `menu_active_tab`: `'GRUND' | 'VERTIKAL'`

## MVP Einschränkungen
- Template-Expansion (SPACER/template_guid) wird im Editor nicht automatisch „expanded“; der Editor zeigt den Rohzustand aus `sys_menudaten`.

---

## Löschen (-Item)
Beim Löschen wird immer ein Confirm-Dialog angezeigt (kein Browser-Confirm).

Sicherheitsabfrage je Fall:
1) **Template-Eintrag löschen** (Item mit `template_guid`): Hinweis, dass nur der Platzhalter gelöscht wird und das eigentliche Template nicht.
2) **Submenü löschen** (Item hat Kinder): Hinweis, dass alle untergeordneten Einträge mit gelöscht werden.
3) **Button/Separator/Spacer ohne Template**: Standardfrage „wirklich löschen?“.

Technik:
- Kinder werden rekursiv ermittelt (Descendants) und beim Löschen ebenfalls entfernt.
- Sortierung der verbleibenden Geschwister wird danach neu nummeriert.

# PDVM Dialog Edit Frame - Spec (V3)

## Ziel
Ein einheitlicher Edit-Rahmen fuer alle Dialog-Editoren.
Tabs und Kopfbereich bleiben stehen, nur der Editor-Inhalt scrollt.
Die Edit-Typen liefern Inhalte (Tabs/Felder), nicht das Layout.
Die Frame-Definition (edit_frame) beschreibt Tabs und InputControls fuer andere
Dialoge und fuer sich selbst (Selbst-Edit).
Der Dialog wird ueber sys_dialogdaten definiert und kann mehrere Module
(z.B. View, Edit, Aktionen) als Tabs enthalten.

## Grundprinzip
- Ein gemeinsamer Edit-Frame steuert das Layout.
- Edit-Typen liefern nur Daten (Tabs/FIELDS) und Inhalte.
- Keine speziellen Scroll-Loesungen pro Editor.
- Die Frame-Definition besteht aus zwei Gruppen: ROOT und FIELDS.
- Dialog-Definitionen sind egalisiert: gleiches Datenmodell fuer alle Dialogtypen.
- Module (view/edit/acti) sind an Tabs gebunden und per GUID referenziert.

## Struktur
```
EditFrame
  - Header (fixed)
  - Edit-Tabs (fixed, aus ROOT.TABS / TAB_XX)
  - Content (scroll)
```

## Datenmodell: edit_frame
Die Frame-Definition ist ein JSON-Objekt mit zwei Gruppen.

### 1) ROOT
Steuert Tabs, Edit-Typ und Anzeigename.

Beispiel:
```json
{
  "ROOT": {
    "TABS": 5,
    "TAB_01": {"HEAD": "Person", "GRUPPE": "USER"},
    "TAB_02": {"HEAD": "Einstellungen", "GRUPPE": "CONFIG/SETTINGS"},
    "TAB_03": {"HEAD": "Sicherheit & Rechte", "GRUPPE": "SECURITY/PERMISSIONS/MANDANTEN"},
    "TAB_04": {"HEAD": "Start & Apps", "GRUPPE": "MEINEAPPS"},
    "TAB_05": {"HEAD": "Passwort", "GRUPPE": "ACTIONS"},
    "EDIT_TYPE": "edit_user",
    "SELF_NAME": "Benutzer bearbeiten"
  }
}
```

Regeln:
- `TABS` ist die Anzahl der Tabs.
- `TAB_XX` (01..n) definiert den Tab-Kopf (`HEAD`) und eine oder mehrere Gruppen (`GRUPPE`).
- `GRUPPE` kann mehrere Gruppen enthalten, getrennt durch `/`.
- `EDIT_TYPE` bestimmt den Editor-Modus (z.B. `pdvm_edit`, `edit_json`).
- `SELF_NAME` ist der Name im Dialog-Header.

### 2) FIELDS
Definiert die InputControls (GUID-keyed Elemente).

Beispiel (gekuerzt):
```json
{
  "FIELDS": {
    "7a0d...": {
      "tab": 1,
      "feld": "VORNAME",
      "name": "user_vorname",
      "type": "string",
      "label": "Vorname",
      "table": "SYS_BENUTZER",
      "gruppe": "USER",
      "abdatum": false,
      "configs": {
        "help": {"key": "", "feld": "", "table": "", "gruppe": ""},
        "dropdown": {"key": "", "feld": "", "table": "", "gruppe": ""}
      },
      "tooltip": "",
      "read_only": false,
      "historical": false,
      "source_path": "root",
      "display_order": 40
    }
  }
}
```

Regeln:
- Keys in `FIELDS` sind GUIDs (stabil fuer Sortierung und Referenzen).
- `tab` verweist auf einen Tab aus ROOT.
- `gruppe` muss mit den Gruppen in ROOT kompatibel sein.
- `display_order` bestimmt die Reihenfolge im Tab.
- `type` ist der InputControl-Typ (z.B. `string`, `dropdown`, `multi_dropdown`, `true_false`, `action`, `go_select_view`).
- `configs` kann weitere Definitionen enthalten (z.B. Dropdown-Quelle).

## Standard-Renderer fuer FIELDS
- Tabs aus `ROOT.TABS` / `TAB_XX`.
- Fields nach `tab` filtern, Reihenfolge via `display_order`.
- Renderer fuer `type` bleibt generisch.
- `action`-Controls verwenden die vorhandenen Aktions-Handler.

## Edit-Frame als eigener Dialog
Der Edit-Frame wird ueber den Standard-Dialog (View + Edit) bearbeitet.
- View-Tab bleibt unveraendert (Neuanlage bleibt im View-Tab).
- Edit-Tab rendert die InputControls aus `FIELDS`.
- Keine Sonder-Layouts, nur Inhalte.

## Tabs und InputControls bearbeiten (Elemente-Listen)
Tabs und InputControls muessen hinzufuegbar und loeschbar sein.
Vorschlag: Verwaltung ueber `elemente_list` InputControl.

### Vorschlag: `elemente_list` fuer FIELDS
- `source_path`: `FIELDS`
- Jeder Eintrag ist ein komplettes InputControl-Objekt.
- Anzeige: `label` (Fallback: `name` oder `feld`).
- Bearbeitung: Popup/Modal mit allen Properties als Controls.
- Speichern erstellt/aktualisiert den GUID-Key.

Template-UIDs:
- Neue Saetze: `66666666-6666-6666-6666-666666666666`
- Element-Templates: `55555555-5555-5555-5555-555555555555` (Gruppe `ELEMENTS`)

Beispiel fuer Template (Element):
```json
{
  "ELEMENTS": {
    "INPUT_CONTROL": {
      "tab": 4,
      "feld": "START.MENU",
      "name": "meineapps_start",
      "type": "go_select_view",
      "label": "Start-Menue",
      "table": "SYS_BENUTZER",
      "gruppe": "MEINEAPPS",
      "abdatum": false,
      "configs": {
        "help": {"key": "", "feld": "", "table": "", "gruppe": ""},
        "dropdown": {"key": "", "feld": "", "table": "", "gruppe": ""}
      },
      "tooltip": "",
      "read_only": false,
      "historical": false,
      "source_path": "root",
      "display_order": 10
    }
  }
}
```

### Vorschlag: `elemente_list` fuer CONFIGS
Optional: `configs` kann ueber eine eigene `elemente_list` gepflegt werden,
z.B. fuer Dropdowns, Help-Links oder komplexe Mapping-Regeln.
Dies bleibt erweiterbar und kompatibel mit vorhandenen InputControls.

## Umsetzung in der App
- Layout in PdvmDialogPage ist zentral.
- `.pdvm-dialog__editAreaHeader` ist immer fix.
- `.pdvm-dialog__editAreaContent` ist der Scroll-Bereich.
- Import-Editor nutzt den gleichen Frame (Steps im Header, Content darunter).
- Menu-Editor nutzt den gleichen Frame (Menu-Tabs im Header, Content darunter).
- edit_json/show_json zeigen Edit-Infos im Header, Content scrollt.

## Spezial-Renderer
- `edit_json`/`show_json`: eigener Content, aber gleicher Frame.
- `pdvm_edit`: Standard-Renderer mit Tabs (Frame-gesteuert).
- `menu`: eigener Content, aber gleicher Frame.

## Vorgaben
- Editor darf keine eigenen Scroll-Container fuer Kopf/Tab erzeugen.
- Alle Edit-Typen muessen den gemeinsamen Frame nutzen.
- Dialogs nutzen keine nativen Browser-Dialoge (PdvmDialogModal).

## Architektur-Regeln (verbindlich)
- Kein direkter SQL-Zugriff in Routern (nur PdvmCentralDatabase).
- `pdvm_edit` ist der zentrale Edit-Frame fuer InputControls.
- `edit_user` nutzt denselben `pdvm_edit`-Kern und darf nur User-spezifische Add-ons liefern (z. B. Passwort/Account-Aktionen).
- `edit_frame` wird nicht mehr verwendet; Dialoge nutzen `pdvm_edit`.
- View/Edit Autonomie bleibt erhalten (Neuanlage nur im View-Tab).
- Persistenz-Scopes nutzen `(view_guid, table, edit_type)`.

## Dialog V2 (egalisiert)
Dialoge werden kuenftig in drei Typen eingeteilt und nutzen ein einheitliches
Datenmodell in `sys_dialogdaten`.

### Dialog-Typen
- `norm` (Edit Dialog): View + Edit
- `work` (Edit Workflow): View + Workflow-Tabs (Schrittfolge)
- `acti` (Aktionen): optional View, Aktionen/Workflow aus Tabs

### Aufruf
- Dialoge werden ueber `go_pdvm_dialog` aufgerufen.
- Parameter: `dialog_guid` und optional `dialog_table` (nur fuer `show_json`/`edit_json`).

### Dialog-Root (V2)
Beispiel:
```json
{
  "ROOT": {
    "DIALOG_TYPE": "norm",
    "SELF_GUID": "<dialog_guid>",
    "SELF_NAME": "Dialogname",
    "TABS": 2,
    "TAB_01": {"HEAD": "View", "MODULE": "view", "GUID": "<view_guid>", "TABLE": "sys_x"},
    "TAB_02": {"HEAD": "Edit", "MODULE": "edit", "GUID": "<frame_guid>", "EDIT_TYPE": "pdvm_edit"},
    "OPEN_EDIT": "double_click",
    "SELECTION_MODE": "single"
  }
}
```

Regeln:
- `DIALOG_TYPE` ist `norm`, `work` oder `acti`.
- Tabs sind Module: `MODULE` in {`view`, `edit`, `acti`}.
- `GUID` verweist auf `sys_viewdaten` (view) oder `sys_framedaten` (edit/acti).
- `VIEW_GUID`/`FRAME_GUID` in `ROOT` sind optional (legacy); die GUIs kommen aus den Tab-Definitionen.
- `EDIT_TYPE` wird pro Edit-Tab gesetzt (z.B. `pdvm_edit`, `edit_json`).
- `show_json` ist ein Edit-Typ und braucht immer einen Edit-Tab.
- Der Dialog ist der Manager, View und Frame bleiben autonome Module.

### Tabellen-Override (Dialog V2)
- View-Module nutzen immer `sys_viewdaten` (view_guid), Edit-Module immer `sys_framedaten` (frame_guid).
- `show_json`/`edit_json` sind tabellen-neutral und koennen fuer alle Tabellen genutzt werden.
- Ueber `go_pdvm_dialog` kann optional `dialog_table` uebergeben werden (nur fuer `show_json`/`edit_json`).
- Wenn `dialog_table` gesetzt ist, wird diese Tabelle statt der in der View-Definition hinterlegten Tabelle verwendet.
- Das Override gilt fuer View-State, View-Matrix und Dialog-CRUD (rows/record).

### Workflow-Regeln (work/acti)
- Start immer Tab 1.
- Tabs werden schrittweise freigeschaltet.
- Rueckwaerts deaktiviert Folge-Tabs wieder.
- Systemsteuerung speichert den letzten aktiven Tab.
- Ab Tab 2 ist ein Button "von vorne" vorgesehen.
- `acti` kann selektierte Menge aus View uebernehmen.

### Quickstart als Aktion
- QUICKSTART ist eine Aktion und wird als `acti`-Modul eingebunden.
- Der Tab nutzt `MODULE=acti` und verweist per `GUID` auf das Aktions-Frame in `sys_framedaten`.

## Vorteile
- Einheitliches Verhalten fuer alle Editoren.
- Weniger CSS-Sonderfaelle.
- Schnellere neue Edit-Typen.
- Stabiler UX und einfacher zu warten.

## Nachteile / Trade-offs
- Einmaliger Umbauaufwand fuer bestehende Editoren.
- Spezial-Editoren brauchen Adapter fuer den Content.
- Weniger Freiheit fuer individuelle Layouts.

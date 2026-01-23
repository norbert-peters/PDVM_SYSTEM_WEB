# PDVM Dialog (Web) – Spec v0 (MVP)

## Ziel
Ein **Dialog** ist eine eigenständige UI-Einheit, die immer mit **genau einer Root-Tabelle** arbeitet.
Im Web läuft es etwas anders als im Desktop: der Browser rendert nur – die Steuerung (Tabs/Frames/Edit-Type) kommt aus Systemtabellen.

MVP (dieser Stand):
- Mindestens **2 Tabs**
- **Tab 1 = View** (hier minimal: nur `uid` + `name`)
- **Tab 2 = Edit**
  - `EDIT_TYPE = show_json` → JSON formatiert anzeigen (read-only)
  - `EDIT_TYPE = edit_json` → JSON Editor + Speichern (JSONB `daten` wird aktualisiert)
  - `EDIT_TYPE = menu` → Menüeditor (2 interne Tabs: Grundmenü / Vertikal Menü)

---

## Systemtabellen

### 1) `sys_dialogdaten`
Dialog-Metadaten und Root-Konfiguration.

**Wichtige Felder in `daten.ROOT`:**
- `TABLE` (string): Root-Tabelle des Dialogs (z.B. `persondaten` oder `sys_dropdowndaten`)
- `TABS` (int, min 2): Anzahl Tabs (MVP nutzt mind. 2)
- `SELECTION_MODE` (string): `single` (Default) oder `multi` (vorbereitet für spätere Bereichsauswahl)
- `OPEN_EDIT` (string): `button` (Default) oder `double_click` (öffnet Edit-Tab beim Doppelklick auf Datensatz)
- `FRAME_GUID` (uuid-string, optional): Verweis auf `sys_framedaten` für den Edit-Bereich
- `EDIT_TYPE` (string): z.B. `show_json` oder `edit_json`

Für `EDIT_TYPE = menu` zusätzlich:
- `MENU_GUID` (uuid-string): GUID eines Datensatzes in `sys_menudaten`, der editiert werden soll.
- Optional `SYSTEMDATEN_UID` (uuid-string): GUID eines Datensatzes in `sys_systemdaten` für Command-Katalog.

**Optional: Tab-Definitionen in `daten` (oder alternativ in `daten.ROOT`)**

Diese Struktur enthält mindestens die Tab-Beschriftung, kann aber später erweitert werden:
```json
{
  "TAB_01": { "HEAD": "Übersicht" },
  "TAB_02": { "HEAD": "Anzeige" }
}
```

Hinweis:
- Keys sind case-insensitive (z.B. `TAB_02` oder `Tab_02`).
- `HEAD` wird im Frontend als Button-Label gerendert.

**Beispiel `sys_dialogdaten` (JSONB `daten`)**
```json
{
  "ROOT": {
    "TABLE": "persondaten",
    "TABS": 2,
    "SELECTION_MODE": "single",
    "OPEN_EDIT": "button",
    "FRAME_GUID": "11111111-1111-1111-1111-111111111111",
    "EDIT_TYPE": "edit_json"
  }
}
```

### 2) `sys_framedaten`
Definiert den Edit-Bereich eines Dialogs.

Für `EDIT_TYPE = show_json` wird im MVP **keine Feld-Definition ausgewertet** – der Frame ist dennoch als Referenz vorgesehen.

Für `EDIT_TYPE = edit_json` wird im MVP ebenfalls keine Feld-Definition ausgewertet – der Editor arbeitet direkt auf `daten`.

**Beispiel `sys_framedaten` (JSONB `daten`)**
```json
{
  "ROOT": {
    "DIALOG_GUID": "22222222-2222-2222-2222-222222222222",
    "EDIT_TYPE": "show_json"
  },
  "FIELDS": {}
}
```

### 3) `sys_menudaten`
Menü-Item ruft den Dialog über den Handler `go_dialog` auf.

**Menu-Command (Beispiel)**
```json
{
  "type": "BUTTON",
  "label": "Dialog (JSON)",
  "icon": null,
  "tooltip": "Öffnet Dialog mit JSON-Edit",
  "enabled": true,
  "visible": true,
  "sort_order": 10,
  "parent_guid": null,
  "template_guid": null,
  "command": {
    "handler": "go_dialog",
    "params": {
      "dialog_guid": "22222222-2222-2222-2222-222222222222",
      "dialog_table": "persondaten"
    }
  }
}
```

Hinweis:
- `dialog_guid` ist zwingend.
- Optional `dialog_table`: überschreibt die im Dialog konfigurierte Root-Tabelle.
- In diesem Override-Modus sind nur `EDIT_TYPE = show_json`, `EDIT_TYPE = edit_json` und `EDIT_TYPE = menu` erlaubt (sonst Fehler).

Neu (Zielbild):
- Der Dialog rendert IMMER eine View (kein Dialog-eigenes `uid+name`-Listing).
- Für Override wird die View gegen die effektive Tabelle gerendert (siehe View `table` override).

---

## API (Backend)

### `GET /api/dialogs/{dialog_guid}`
Optionaler Query-Parameter:
- `dialog_table=<tablename>`: überschreibt die Root-Tabelle.

Liefert Dialog-Definition inkl. abgeleiteter Runtime-Felder:
- `root_table`
- `edit_type`
- `frame_guid`
- optional `frame` (wenn Frame ladbar)

### `POST /api/dialogs/{dialog_guid}/rows`
Optionaler Query-Parameter:
- `dialog_table=<tablename>`: überschreibt die Root-Tabelle.

Request:
```json
{ "limit": 200, "offset": 0 }
```
Response: Rows der Root-Tabelle als `{uid, name}`.

Hinweis:
- Dieser Endpoint ist legacy (MVP) und wird perspektivisch nicht mehr benötigt, wenn Dialog ausschließlich über Views arbeitet.

### `GET /api/dialogs/{dialog_guid}/record/{uid}`
Optionaler Query-Parameter:
- `dialog_table=<tablename>`: überschreibt die Root-Tabelle.

Liefert vollen Datensatz der Root-Tabelle (`daten` JSONB) – für `show_json`.

### `PUT /api/dialogs/{dialog_guid}/record/{uid}`
Optionaler Query-Parameter:
- `dialog_table=<tablename>`: überschreibt die Root-Tabelle.

Aktualisiert das JSONB Feld `daten` des Datensatzes.

Request:
```json
{ "daten": { "ROOT": { "...": "..." } } }
```

Hinweis:
- Der Endpoint ist nur aktiv, wenn der Dialog `EDIT_TYPE = edit_json` gesetzt hat.

### `POST /api/dialogs/{dialog_guid}/record`
Optionaler Query-Parameter:
- `dialog_table=<tablename>`: überschreibt die Root-Tabelle.

Erstellt einen neuen Datensatz anhand eines Template-Records.

Request:
```json
{ "name": "Neuer Name", "template_uid": "66666666-6666-6666-6666-666666666666" }
```

Default-Verhalten (wenn `template_uid` fehlt):
- `template_uid = 66666666-6666-6666-6666-666666666666`

Beim Erstellen:
- `daten` wird aus dem Template kopiert
- `daten.ROOT.SELF_GUID` wird auf die neue UID gesetzt
- `daten.ROOT.SELF_NAME` wird auf den übergebenen Namen gesetzt
- Spalte `name` wird auf den übergebenen Namen gesetzt

Einschränkungen:
- Nur erlaubt für `EDIT_TYPE = edit_json` oder `EDIT_TYPE = menu`.
- Für `EDIT_TYPE = show_json` (read-only) wird kein neuer Satz angelegt und der Button im Dialog bleibt ausgeblendet.
- Ausnahme: `sys_benutzer` unterstützt diesen Template-Mechanismus nicht.

UI-Hinweis:
- Die Namensabfrage für „Neuer Satz“ erfolgt im Frontend über `PdvmDialogModal` (kein `window.prompt`).
- Siehe `docs/specs/PDVM_DIALOG_MODAL_SPEC.md`.

### `GET /api/systemdaten/menu-commands`
Liefert den Command-Katalog für den Menüeditor.

Query:
- `language` (optional)
- `dataset_uid` (optional)

### `GET /api/lookups/{table}`
Kleine UID/Name-Lookup-View für GUID-Auswahl.

Query:
- `limit`, `offset`
- `q` (optional, Filter auf `name` via ILIKE)

### `GET /api/menu-editor/{menu_guid}` / `PUT /api/menu-editor/{menu_guid}`
Laden/Speichern eines `sys_menudaten` Datensatzes für `edit_type=menu`.

Validierung:
- Ein Item, das Kinder hat (Submenü), darf kein `command` haben (wird beim Speichern entfernt).

### `GET /api/dialogs/{dialog_guid}/ui-state` / `PUT /api/dialogs/{dialog_guid}/ui-state`
UI-State Persistenz (pro User) in `sys_systemsteuerung` für Dialog-bezogene UI-Details.

Aktuell genutzt:
- `edit_type=menu`: Persistenz des aktiven Edit-Tabs (`menu_active_tab`: `GRUND|VERTIKAL`).

---

## Frontend Verhalten (MVP)

Route:
- `/dialog/:dialogGuid`

Tabs:
- **Tab 1**: Tabelle mit `uid` + `name` (Klick selektiert Datensatz)
- **Tab 2**: `show_json` → `<pre>` Pretty-Print von `daten`

Für `edit_json`:
- **Tab 2**: Text-Editor (monospace) + Buttons `Formatieren` und `Speichern`
- Speichern ruft `PUT /api/dialogs/{dialog_guid}/record/{uid}` auf

Für `menu`:
- Im Edit-Tab werden interne Tabs (Grundmenü/Vertikalmenü) gerendert.
- Der aktive Tab wird über `ui-state` persistiert.
- Der Dialog-Header bietet `Refresh Edit` (lädt den Editbereich neu aus DB; bei `edit_json` mit Dirty-State wird vorher bestätigt).

---

## Dialog Ablauf V1 (Linear, Zielbild)

Dieser Ablauf beschreibt das gewünschte Verhalten (einfach, linear, ohne Nebenpfade), passend zu den Architekturregeln.

### 1) Aufruf (Command)
Es gibt genau ein Command:
- `go_dialog(dialog_guid, dialog_table?)`

`dialog_table` ist optional.
- Es wirkt **nur** für `EDIT_TYPE in {show_json, edit_json}`.
- Es bestimmt die **effektive Dialog-Tabelle** (die Tabelle, deren Datensätze selektiert und editiert werden).

### 2) Definition laden
Der Dialog lädt die Definition aus `sys_dialogdaten` via `dialog_guid`.

### 3) Effektive Dialog-Tabelle bestimmen
Die effektive Tabelle wird festgelegt als:
- wenn `dialog_table` gesetzt und `EDIT_TYPE in {show_json, edit_json}`: `effective_table = dialog_table`
- sonst: `effective_table = sys_dialogdaten.ROOT.TABLE`

### 4) Last-Call Lookup
Vor dem Rendern wird anhand von `FRAME_GUID` + `effective_table` geprüft, ob ein Last-Call existiert.

Persistenzmodell:
- `sys_systemsteuerung` (pro User)
- Gruppe: bevorzugt `FRAME_GUID` (fallback: `VIEW_GUID`, fallback: `dialog_guid`)
- Feld: `LAST_CALL` (Bereich / Dict)
- Key im Dict: `effective_table` in Großbuchstaben
- Value: Datensatz-UID

Beispiel:
```json
{
  "bdcc1303-...": {
    "LAST_CALL": {
      "SYS_VIEWDATEN": "...",
      "SYS_FRAMEDATEN": "..."
    }
  }
}
```

### 5) View-Tab (Tab 1)
Tab 1 rendert eine View.

Wichtig (Zielbild):
- Die View ist ein **eigenständiges, zentrales Modul**.
- Der Dialog bindet die View nur ein und enthält **keine View-Logik-Duplikate**.
- Die View muss eine eindeutige Selektions-API/Events liefern (z.B. `selected_uids`).

### View-Definition Semantik (neu)
`sys_viewdaten.daten` nutzt standardisierte Sektionen:
- Sektion `TABLENAME` (immer uppercase, z.B. `SYS_MENUDATEN`) → Controls für fachliche Datenfelder
- Sektion `**System` → Controls für Systemspalten (`gruppe=SYSTEM`, z.B. `uid`, `name`, `created_at`, `modified_at`, ...)

`ROOT.NO_DATA=true` bedeutet:
- **Die `TABLENAME`-Sektion wird nicht ausgewertet**.
- Die View rendert trotzdem vollständig über das View-Modul (typisch: nur `**System`).

### View `table` override (für `dialog_table`)
Für Views mit `ROOT.NO_DATA=true` ist ein Table-Override erlaubt:
- `POST /api/views/{view_guid}/matrix?table=<tablename>`

Zusätzlich (Persistenz, siehe unten):
- `GET /api/views/{view_guid}/state?table=<tablename>&edit_type=<edit_type>`
- `PUT /api/views/{view_guid}/state?table=<tablename>&edit_type=<edit_type>`

Zweck:
- Ein generischer "System-View" kann beliebige Tabellen anzeigen, ohne per Tabelle eigene View-Definitionen zu benötigen.

### View-State Persistenz (WICHTIG)
Wenn eine View in unterschiedlichen Kontexten unterschiedliche Tabellen rendern kann (z.B. `dialog_table` Override), darf der persistierte View-State nicht nur an `view_guid` hängen.

Regel (Identität des States):
- Composite-Key: `(view_guid, table, edit_type)`
- Backend bildet daraus die Persistenz-Gruppe: `state_group = "{view_guid}::{table}::{edit_type}"` (normalisiert auf lower-case)

Praktische Konsequenzen:
- Gleiche `view_guid`, aber andere `table` ⇒ getrennte Filter/Sort/Spalten/Controls.
- Gleiche `view_guid` + `table`, aber anderer `edit_type` ⇒ ebenfalls getrennt (z.B. View embedded in Dialog `show_json` vs. Standalone `view`).

API-Nutzung:
- Matrix-Load muss ebenfalls konsistent gescoped sein:
  - `POST /api/views/{view_guid}/matrix?table=<tablename>&edit_type=<edit_type>`

Konventionen:
- Standalone-View nutzt `edit_type=view`.
- Embedded-View im Dialog nutzt `edit_type = sys_dialogdaten.ROOT.EDIT_TYPE`.
- `table` ist die effektive Tabelle (bei Override: `dialog_table`, ansonsten View/Dialog Root).

### 6) Edit-Tab (Tab 2)
Tab 2 rendert ein Edit-Modul abhängig von `EDIT_TYPE`.

Regel:
- Jeder `EDIT_TYPE` ist ein eigenes Modul.
- Der Dialog orchestriert nur und übergibt:
  - `effective_table`
  - `frame_guid`
  - `selected_uid(s)`

### 7) Header + Tabs
- Der Dialog hat einen konstanten Header (über allen Tabs).
- Der Titel kommt aus `sys_dialogdaten.ROOT.HEADER`.
- Wenn `SHOW_TABLE=true`, wird hinter dem Titel der Name der `effective_table` angezeigt.

UI-Regel:
- Der Button "Auswählen / Edit öffnen" entfällt.
- Tab-Wechsel ist der primäre Mechanismus.
- Wie/ob automatisch auf Tab 2 gesprungen wird, wird später klar pro `EDIT_TYPE` definiert.

---

## Auto-Select / Last Call (V1)

Ziel: Beim Öffnen des Dialogs wird – falls vorhanden – die letzte Selektion für genau diese `effective_table` wieder angeboten.

Ablauf:
- Backend liefert `meta.last_call` (aus `sys_systemsteuerung` via `FRAME_GUID` + `effective_table`).
- Frontend setzt initial `selectedUid = meta.last_call`.
- Sobald der User in der aktuellen Tabelle eine neue Auswahl trifft, wird gespeichert via:
  - `PUT /api/dialogs/{dialog_guid}/last-call?dialog_table=...` (nur relevant bei Override)

Wichtig:
- Es darf **kein** "alten" `selectedUid` in einen neuen `dialog_table`-Kontext persistiert werden.

---

## Layout & Scrolling Regeln (V1)

Grundregel: Nicht der gesamte Bildschirm scrollt.

- Horizontal-Menü und globaler Header bleiben stehen.
- Vertikales Menü scrollt, wenn zu lang.
- Content-Bereich hat immer einen eigenen Header, der stehen bleibt.

View:
- Bis zu den Spaltenüberschriften bleibt alles stehen.
- Nur die Datenliste (inkl. Gruppierungen) scrollt.

Edit:
- Scrolling/Sticky-Verhalten ist pro `EDIT_TYPE` festzulegen.

---

## Stärken / Schwächen (V1)

Stärken:
- Linearer Ablauf, klare Zuständigkeiten (Dialog orchestriert, View/Edit sind Module).
- Keine Duplikation der View-Logik im Dialog.
- Last-Call ist stabil, weil er an `FRAME_GUID` + `effective_table` gebunden ist.

Schwächen / Risiken:
- Wenn Selektionszustand aus einer embedded View kommt, muss das Event-Protokoll absolut eindeutig sein.
- Persistenz darf nicht "nebenläufig" falsche Kontexte beschreiben (Race/Carry-Over).
- `EDIT_TYPE`-Module müssen strikt ihre Input-Parameter validieren, sonst entstehen implizite Couplings.

---

## Hinweise / Next Steps
- In späteren Iterationen kann Tab 1 statt "uid+name" auch eine echte View (sys_viewdaten) rendern.
- `sys_framedaten.FIELDS` kann später für echte Edit-Controls genutzt werden (input/select/date/...)
- Filter/Sort/Group/Paging kann analog zum View-System erweitert werden.

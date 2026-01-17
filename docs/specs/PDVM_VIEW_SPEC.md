# PDVM View System (Web) – Spezifikation (V0 → Zielbild)

Diese Spezifikation beschreibt die **universelle, hoch-flexible View-Komponente** für das PDVM System Web.
Sie ist die „Single Source of Truth“ für:
- View-Definitionen aus `sys_viewdaten` (Controls/Spalten + Metadaten)
- User-spezifische Persistenz in `sys_systemsteuerung` (GCS) pro `view_guid`
- Matrix-/Pipeline-Verarbeitung (Filter → Sort → Group/Summen → Projektion)
- Recompute-Strategie (stichtagsabhängig, ohne erneuten DB-Zugriff)

## 1. Zielbild (Kurzfassung)

Eine View besteht aus:
1. **Definition** (System): kommt aus `sys_viewdaten` (ROOT + Controls)
2. **Persistierter State** (User/Mandant): kommt aus `sys_systemsteuerung` (GCS) unter Gruppe = `view_guid`
3. **Runtime-Pipeline** (UI): verarbeitet eine **Basis-Matrix** (aus DB-Rohdaten) zu einer **Projektions-Matrix** (sichtbare Spalten + Zeilenarten)

Die View ist generisch: gleiche Komponente rendert alle Tabellen/Views. Unterschiede entstehen ausschließlich über die Definition und den persistierten State.

### 1.1 Anzeige – Ausschlussregeln (global)

Für die Anzeige werden grundsätzlich Datensätze ausgeschlossen:

1. **Platzhalter-UIDs**: `0000...`, `5555...`, `6666...` (als 32-hex-UUID, Bindestriche ignoriert)
2. **Leere Zeilen**: Datensätze, die in **allen zur Anzeige möglichen Spalten** (alle Controls der View) als „leer“ gelten

3. **Ungültige Datensätze via `gilt_bis`**: Wenn `gilt_bis` **kleiner als der aktuelle Tag** ist, gilt der Satz als „gelöscht“ (logisch gelöscht).
  - Motivation: Reaktivierung möglich (durch Erhöhung von `gilt_bis`), und optional „echtes“ Löschen zu einem Datum.
  - Implementations-Hinweis: Der Vergleich ist **taggenau** im PDVM-Sinne (YYYYDDD), unabhängig vom View-`stichtag`.

Ausnahme:
- Controls mit `gruppe = SYSTEM` werden in die „leer“-Prüfung **nicht** einbezogen, da sie technische DB-Spalten abbilden und praktisch immer Werte liefern.

Hinweis: „leer“ ist **typabhängig** (siehe Tabelle unten). Mit jedem neuen Spaltentyp muss die Leer-Definition festgelegt und implementiert werden.

#### 1.1.1 Leer-Definition pro Spaltentyp

Die View verwendet folgende Leer-Regeln (Frontend):

- `string` / `text` / `base`: leer, wenn `null`/`undefined` oder leerer/whitespace String
- `dropdown`: leer, wenn `null`/`undefined` oder leerer/whitespace String
- `date` / `datetime`: leer, wenn `null`/`undefined` oder leerer String oder **PDVM-Default** `1001.0`
- `number` / `float` / `int`: leer, wenn `null`/`undefined` oder leerer String oder nicht numerisch (`NaN`/nicht parsebar)
- `boolean`: **nie leer** (auch `false` ist ein valider Wert)
- Fallback (unbekannter Typ): leer, wenn `null`/`undefined` oder leerer String oder leeres Array oder leeres Objekt

Erweiterungsregel:
- Wenn ein neuer `control.type` eingeführt wird, muss er hier dokumentiert **und** in der UI-Leerprüfung ergänzt werden.

---

## 2. Begriffe & Datenmodelle

### 2.1 ViewDefinition (`sys_viewdaten.daten`)

Eine ViewDefinition ist ein JSON-Objekt mit mindestens:
- `ROOT`: Meta-Konfiguration
- mindestens einem Control-Container (z.B. `PERSONDATEN`, `FINANZEN`, …)

Beispiel-Auszug (aus „Personen Sicht“):
```json
{
  "ROOT": {
    "TABLE": "persondaten",
    "ALLOW_FILTER": true,
    "ALLOW_SORT": true,
    "DEFAULT_SORT_COLUMN": "",
    "DEFAULT_SORT_REVERSE": false,
    "PROJECTION_MODE": "standard"
  },
  "PERSONDATEN": {
    "<control_guid>": {
      "gruppe": "PERSDATEN",
      "feld": "FAMILIENNAME",
      "label": "Familienname",
      "type": "string",
      "control_type": "base",
      "show": true,
      "display_order": 1,
      "expert_mode": true,
      "expert_order": 1,
      "searchable": true,
      "sortable": true,
      "filterType": "contains",
      "table": "persondaten"
    }
  }
}
```

**Wichtig:**
- `control_guid` ist die **stabile ID** eines Controls/Spalte.
- `gruppe` + `feld` definieren den Zugriff in der Datenstruktur (`daten[gruppe][feld]`).
- `type`/`filterType` definieren UI- & Filter-Operatoren.
- `display_order`/`expert_order` definieren Default-Sortierung der Spaltenliste.

### 2.2 Controls – `_origin` / `_source` / „effective“

Wir unterscheiden 3 Ebenen:
- **`controls_origin`**: Controls aus `sys_viewdaten` (System-Default)
- **`controls_source`**: User-spezifische, persistierte Controls (Override/Overlay)
- **`controls_effective`**: Ergebnis aus Merge(origin, source) + Mode (Standard/Expert)

Motivation:
- `controls_origin` darf durch Systemupdates wachsen/ändern (neue Spalten etc.).
- `controls_source` speichert User-Anpassungen (Show/Order/Width/Sort etc.).
- Die View muss bei Änderungen in `sys_viewdaten` **robust mergen**, ohne User-Anpassungen zu verlieren.

Wichtige Regel:
- In `sys_viewdaten` wird **niemals automatisch zurückgeschrieben**. Das sind System-Basisdaten.
- User-Anpassungen werden ausschließlich in der Systemsteuerung (`sys_systemsteuerung`) gespeichert, damit sie **user- und mandantenabhängig** sind.

### 2.3 ViewState (`sys_systemsteuerung` via GCS)

Persistiert pro User (und Mandant) unter Gruppe = `view_guid`.
Minimal (V0):
```json
{
  "controls": {
    "<control_guid>": {
      "show": true,
      "display_order": 3,
      "width": 180
    }
  }
}
```

Zielbild (erweitert):
```json
{
  "controls": { "<control_guid>": { "show": true, "width": 180, "display_order": 3 } },
  "filter": {
    "global": { "text": "lau", "mode": "contains" },
    "columns": { "<control_guid>": { "op": "contains", "value": "peter" } },
    "conditions": [
      { "logic": "AND", "control": "<control_guid>", "op": ">=", "value": 18 }
    ]
  },
  "sort": {
    "mode": "single",
    "by": [ { "control": "<control_guid>", "dir": "asc", "nulls": "last" } ]
  },
  "group": {
    "enabled": false,
    "by": ["<control_guid>"],
    "aggregates": { "<control_guid>": ["count", "sum"] }
  },
  "ui": {
    "density": "compact",
    "expert": false
  },
  "meta": {
    "view_version": "<hash-or-timestamp>",
    "last_merge": "2026-01-01T12:00:00"
  }
}
```

Hinweis zur Persistenz:
- Die Systemsteuerung ist die einzige Persistenzquelle für View-User-State.
- `sys_viewdaten` bleibt unverändert, außer durch bewusste Admin-/System-Migrationen.

---

## 3. Matrix-Modell

### 3.1 Rohdaten (DB)

Die PDVM-Tabellen enthalten:
- `uid` (UUID)
- `name` (optional)
- `daten` (JSONB)
- `historisch` (0/1)

Für stichtagsabhängige Werte gilt:
- bei `historisch = 0`: `daten[gruppe][feld] = wert`
- bei `historisch = 1`: `daten[gruppe][feld] = { "<abdatum>": wert, ... }`

**Stichtag-Regel (historisch):**
- Für `historisch = 1` wird pro Feld der **größte** Zeitstempel $t$ gewählt mit $t \le stichtag$.
- Gibt es keinen passenden Zeitstempel (alle $t > stichtag$), gilt der Wert als **leer** (`null`).

**Recompute-Regel:**
- Eine Änderung des Stichtags muss ein Neuladen der Basisdaten (BASIS) und anschließend einen kompletten Pipeline-Durchlauf (FILTER→SORT→GROUP→PROJECT) auslösen.

### 3.2 MatrixCell (3 Ebenen, Zielbild)

Pro Zelle sollen (logisch) mehrere Ebenen verfügbar sein, um **NormalMode (formatierte Anzeige)** und **ExpertMode (Rohdaten)** sauber abzubilden:

1. **`value_raw`**: Rohwert wie in der Datenbank hinterlegt (zum Stichtag ausgewählt)
2. **`value_form`**: formatierte Darstellung für UI (z.B. Dropdown-Übersetzung, Datum/Zahl formatiert)
3. **`abdatum`**: das zugehörige Änderungsdatum (PDVM-Float)
4. **`abdatum_formatiert`**: string für UI (DE/ENG/USA, via PdvmDateTime)

Das ermöglicht:
- Tooltips („gültig ab …“)
- Sortierung „nach Original“ vs „nach Anzeige“
- spätere Export-/Audit-Features

Anzeigeregel:
- **NormalMode** zeigt `value_form` (formatierte Darstellung).
- **ExpertMode** zeigt `value_raw` (Datenbank-Rohwert).

Wichtig: `value_form` ist eine Darstellungsebene, keine zweite inhaltliche Wahrheit.

### 3.3 MatrixRow

Jede Zeile enthält:
- System-Felder: `uid`, `row_type`, ggf. `group_level`, `is_selected` …
- Datenfelder: Werte nach Controls (typisch per `control_guid` oder `gruppe+feld`)

**Konvention (empfohlen):**
- Zeilenwerte werden im Matrix-Objekt unter dem `control_guid` abgelegt (stabil, unabhängig von Label).
- Für Debug/Export kann zusätzlich `gruppe`/`feld` als Metadaten im Control vorhanden bleiben.

---

## 4. Pipeline-Architektur

### 4.1 Stufen (Zielbild)

Pipeline ist deterministisch und linear:

1. **BASIS**
   - Input: DB-Rohdaten (inkl. historischer Maps)
  - Output: `matrix_base_raw` (unverändert) + `matrix_base_values(stichtag)`
  - Enthält pro Zelle mindestens `value_raw` + `abdatum`

2. **FORMAT (implizit/gekoppelt an BASIS oder PROJECT)**
  - Ziel: Aufbau von `value_form` für alle sichtbaren/später filterbaren Zellen
  - Quellen:
    - `control.type` / `control.control_type`
    - Dropdown-Configs (`configs.dropdown`)
    - Locale/Country (GCS) für Datum/Zahl
  - Hinweis: In V0 kann FORMAT zunächst minimal sein (z.B. Datum + Dropdown), später erweitert.

3. **FILTER**
   - Input: Base
   - Output: `matrix_filter`
   - Quellen: `view_state.filter` (global + columns + conditions)

4. **SORT**
   - Input: Filter
   - Output: `matrix_sort`
   - Quellen: `view_state.sort`

5. **GROUP (optional)**
   - Input: Sort
   - Output: `matrix_grouped`
   - Enthält zusätzliche Zeilen: Group-Header / Summenzeilen

6. **PROJECT**
   - Input: Sort/Group
   - Output: `matrix_project` + `visible_columns`
   - Quellen: `controls_effective` + Mode (Standard/Expert)

Anmerkung zur Projektion (Mode):
- Der Mode beeinflusst die Anzeigeebene (`value_form` vs `value_raw`), nicht die Spaltenreihenfolge.
- Wenn wir ohne Duplikate arbeiten (ein Control repräsentiert genau eine Spalte), kann `expert_order` entfallen.
- Dann gilt: **`display_order` ist die einzige Reihenfolge** (auch im ExpertMode).

### 4.2 Recompute-Regeln

- **Stichtag geändert** (`pdvm:stichtag-changed`):
  - **kein DB-Reload** notwendig, solange `matrix_base_raw` die Historie enthält
  - recompute: `BASIS(values)` → `FILTER` → `SORT` → `GROUP` → `PROJECT`

- **Filter geändert**: recompute ab `FILTER`
- **Sort geändert**: recompute ab `SORT`
- **Spalten/Projection geändert** (show/order/width/expert toggle): recompute ab `PROJECT`
- **DB-Reload** nur wenn:
  - der User aktiv „Refresh from DB“ auslöst, oder
  - die View ein „Live“-Flag bekommt (später), oder
  - Mandant/User gewechselt wird

---

## 5. Merge-Strategie: `sys_viewdaten` ↔ User-State

Beim Laden der View wird:
1. `controls_origin` aus `sys_viewdaten` gelesen
2. `controls_source` aus GCS (`get_view_controls(view_guid)`) geladen
3. Merge durchgeführt und anschließend (optional) normalisiert zurückgeschrieben

### 5.1 Merge-Regeln (empfohlen)

Für jedes `control_guid`:
- Wenn Control nur in origin existiert → **neu hinzufügen** (mit origin defaults)
- Wenn Control nur in source existiert → **behalten**, aber als „veraltet“ markieren (optional)
- Wenn Control in beiden existiert →
  - systemkritische Keys (z.B. `gruppe`, `feld`, `type`, `table`) kommen aus origin
  - userkritische Keys (`show`, `display_order`, `width`, `sortDirection`, `filterType`-Overrides) kommen aus source, wenn vorhanden

Wichtig:
- Merge/Normalisierung darf `controls_source` aktualisieren (z.B. neue Controls ergänzen),
  aber es darf **nie** nach `sys_viewdaten` zurückgeschrieben werden.

### 5.2 Normalisierung

Nach Merge:
- `display_order` und `expert_order` in eindeutige Reihenfolge bringen (keine Duplikate)
- Fallback: wenn keine sichtbaren Spalten → setze minimal 1 Standardspalte sichtbar

---

## 6. UI/UX: Features (Zielbild)

### 6.1 Spaltensteuerung
- Standard/Expert Toggle (global, aus GCS Expert Mode ableitbar)
- Show/Hide pro Spalte
- Reihenfolge via Drag&Drop
- Breite (resize), optional „Auto-fit“

Anzeigemodus:
- **Standard (NormalMode)**: formatierte Inhalte (`value_form`)
- **Expert**: Rohwerte (`value_raw`) + optional zusätzliche technische Infos (z.B. `abdatum` als Tooltip)

### 6.2 Sortierung
- V0: Single Sort (eine Spalte, asc/desc)
- Ziel: Multi Sort + "nulls first/last" + sortByOriginal (z.B. Date/Number)
- Ziel: Group-Sort (Gruppierung + Sort innerhalb Gruppe)

### 6.3 Filter
- Global Search (über `searchable` Controls)
- Column Filter (op abhängig von `filterType`)
- Conditions Builder (AND/OR, Klammern optional später)

### 6.4 Selektion
- Row Selection (single/multi)
- Range Selection (Shift-Click, optional Drag)
- Events nach außen:
  - `pdvm:view-selection-changed` (payload: view_guid, selected_uids)

---

## 7. Backend API (Vorschlag)

Hinweis: Gemäß Architekturregeln: **keine SQL direkt in Routern**.

### 7.1 View Definition
- `GET /api/views/{view_guid}` → liefert `sys_viewdaten` (ROOT + Controls)

### 7.2 View State (Persistenz)
- `GET /api/views/{view_guid}/state` → liefert persisted state aus `sys_systemsteuerung`
- `PUT /api/views/{view_guid}/state` → schreibt state (oder Teile) zurück

Minimal kompatibel zu vorhandener GCS-API:
- intern wird `PdvmCentralSystemsteuerung.get_view_controls(view_guid)` / `set_view_controls(view_guid, controls)` genutzt.

### 7.3 View Data (optional, Phase später)
Variante A (UI-Pipeline):
- UI lädt Base-Rohdaten z.B. über bestehende Table-Endpunkte (`/api/tables/{table}`)

Variante B (Server-Pipeline, später):

- `POST /api/views/{view_guid}/matrix` (body enthält state + paging) → liefert project-matrix
  - Request:
    - `controls_source?`, `table_state_source?`
    - `include_historisch?: boolean`
    - `offset?: number`, `limit?: number`
  - Response:
    - `rows`: `kind=group|data`
    - `totals`: aktuell **global-scope** (über alle Treffer)
    - `meta`: u.a. `total_after_filter`, `has_more`, `returned_data`, `returned_rows`, `cache_hit`, `table_truncated`

---

## 8. Frontend-Architektur (Vorschlag)

### 8.1 Komponenten
- `PdvmView` (Container)
- `ViewToolbar` (Search, Expert Toggle, Filter/Sort Buttons)
- `ViewColumnManager` (Show/Hide, Order, Width)
- `ViewTable` (Render + Virtualisierung)

### 8.4 Start & Einbettung (Routing/Parent)

Die View soll von Beginn an so gebaut werden, dass sie in zwei Kontexten funktioniert:

1) **"Voller Content" als Seite** (Navigation über Menüeintrag)
- Menüaktion: `go_view(<view_guid>)`
- Route: z.B. `/view/:viewGuid`
- Der Page-Wrapper rendert `PdvmView` als Hauptinhalt.

2) **Einbettung in andere Parents** (z.B. Dialog, Split-View, Tab)
- `PdvmView` ist ein reiner UI-Container ohne harte Annahmen über Page-Layout.
- Ein Parent kann `PdvmView` in beliebige Container einhängen und Größe/Toolbar-Optionen steuern.

Konsequenzen:
- `PdvmView` bekommt Props für Layout-Optionen (z.B. `variant: 'page' | 'embedded'`, `showToolbar?: boolean`).
- Navigation/Router ist außerhalb von `PdvmView` (z.B. in `ViewPage`).

### 8.2 Hooks
- `useViewDefinition(viewGuid)`
- `useViewState(viewGuid)`
- `useViewPipeline(definition, state, baseRaw, stichtag)`

### 8.3 Integration Stichtag
- `StichtagsBar` feuert `pdvm:stichtag-changed`
- `PdvmView` subscribed und triggert Pipeline-Recompute

---

## 9. Implementations-Phasen (empfohlen)

### Phase 0 (MVP – Daten anzeigen)
- ViewDefinition laden (sys_viewdaten)
- Base-Rohdaten laden (z.B. table endpoint)
- Spalten rendern nach `show` + `display_order`
- Standard/Expert Toggle (nur Projektion)

Erweiterung Phase 0 (Anzeige):
- NormalMode zeigt `value_form` (mindestens Datum/Zahl), ExpertMode zeigt `value_raw`.

### Phase 1 (Persistenz + Merge)
- State laden/speichern (`controls`)
- Merge origin/source stabil implementieren

### Phase 2 (Filter + Sort V0)
- Global Search + Single Sort
- Persistenz für `filter.global` und `sort.by[0]`

### Phase 3 (Selection)
- Row + Range
- Selection-Events

### Phase 4 (Group + Summen)
- Group rows + aggregates (count/sum/avg)
- Render row_type + group indentation

---

## 10. Referenzdaten

Für reproduzierbares Testing existiert ein Test-Datensatz in `sys_viewdaten`:
- Name: `Personen Sicht`
- UID: `a7cc4cd1-7d34-46ca-a371-011c9bf608ea`

Dieser Datensatz soll als primäre Smoke-Test-View für die Implementationsphasen genutzt werden.

# PDVM System Web - Architekturregeln

Dieses Dokument definiert die verbindlichen Architektur-Regeln für die Weiterentwicklung des PDVM Systems. Ziel ist die Stabilität und Wartbarkeit bei wachsender Komplexität.

## 1. Backend Architektur

### 1.1 Das "Central Database" Gesetz
**Regel:** Es gibt keinen direkten Datenbank-Zugriff in den API-Endpunkten (Routers).

*   ❌ **VERBOTEN:** SQL-Queries (`SELECT...`) oder direkter Zugriff auf JSON-Strukturen (`row['daten']['GRUND']`) im Router.
*   ✅ **PFLICHT:** Nutzung der Business-Logic Klasse `PdvmCentralDatabase`.

```python
# Richtig:
menu = await PdvmCentralDatabase.load("sys_menudaten", guid, system_pool)
items = menu.get_value_by_group("GRUND")

# Falsch:
row = await db.fetch_row(query)
items = row["daten"]["GRUND"]  # Umgeht Historisierung und Logik!
```

### 1.2 Single Source of Configuration
**Regel:** Es gibt keine hardcodierten Verbindungsdaten für Mandanten- oder System-Datenbanken (`config.py`).

*   Die einzige statisch bekannte Datenbank ist die **AUTH-DB**.
*   Alle anderen Verbindungen (System, Mandant) **MÜSSEN** dynamisch über den `ConnectionManager` und die Tabelle `sys_mandanten` bezogen werden.
*   **Warum?** Mandanten können auf verschiedenen Servern liegen. Hardcoded URLs in `config.py` (wie `DATABASE_URL_MANDANT`) sind veraltet und dürfen nicht genutzt werden.

### 1.3 Factory Pattern für Datensätze
**Regel:** Instanzierung von Business-Objekten immer über die asynchrone Factory-Methode `.load()`.

*   ❌ `obj = PdvmCentralDatabase(...)` (Lädt keine Daten, fehleranfällig)
*   ✅ `obj = await PdvmCentralDatabase.load(...)` (Erzeugt Instanz UND lädt Daten korrekt)

### 1.4 Persistenz-Scopes (View-State)
**Regel:** Persistierter View-State darf nicht nur an `view_guid` hängen, wenn eine View in unterschiedlichen Kontexten unterschiedliche Tabellen oder Modi (Edit-Type) rendern kann.

*   ✅ **PFLICHT:** State-Identität ist der Composite-Key `(view_guid, table, edit_type)`.
*   ✅ **PFLICHT:** Backend persistiert unter einer Gruppe `state_group = "{view_guid}::{table}::{edit_type}"` (normalisiert, z.B. lower-case).
*   ✅ **PFLICHT:** Frontend scoped React-Query Keys und API-Calls identisch (immer `table` + `edit_type` mitsenden).
*   Konvention: Standalone-View nutzt `edit_type=view`; Embedded-View im Dialog nutzt `edit_type = sys_dialogdaten.ROOT.EDIT_TYPE`.

---

## 2. Frontend Architektur (React)

### 2.1 Context over Props
**Regel:** Globale Zustände (Auth, Mandant, Theme) gehören in React Context Provider.

*   ❌ **VERBOTEN:** "Prop-Drilling" von `token` oder `mandantId` durch mehr als 2 Ebenen.
*   ✅ **PFLICHT:** Nutzung von `useAuth()` für Benutzerkontext und `useMenu()` für App-Steuerung.

### 2.2 Strikte Menü-Struktur
**Regel:** Das UI-Layout akzeptiert nur definierte Menü-Gruppen.

*   **GRUND:** Horizontale Menüleiste oben (App-Umschaltung, Tools).
*   **VERTIKAL:** Sidebar links (Navigation innerhalb der App).
*   ❌ **VERBOTEN:** Erfindung neuer Gruppen (z.B. "ZUSATZ", "FOOTER") ohne Anpassung des `MenuRenderer`.
*   Das Frontend ist "dumm" und rendert generisch, was die API liefert, aber nur in diesen zwei Containern.

### 2.3 API-Layer Separierung
**Regel:** Keine direkten HTTP-Calls (`fetch`, `axios`) in Komponenten.

*   Alle Netzwerk-Anfragen müssen in `src/api/client.ts` oder entsprechenden API-Modulen definiert sein.
*   Dies sichert konsistentes Error-Handling (z.B. 401 Redirects) und Token-Injection.

### 2.4 UI Dialoge/Modals
**Regel:** Keine nativen Browser-Dialoge (`window.alert/confirm/prompt`) in der App.

*   ❌ **VERBOTEN:** `window.alert(...)`, `window.confirm(...)`, `window.prompt(...)`
*   ✅ **PFLICHT:** Nutzung von `PdvmDialogModal` für Info/Confirm/Form-Dialoge.
*   **Warum?** Einheitliches Theming, Busy-Zustände (Async), Validierung, konsistente UX.

Siehe Spezifikation: `docs/specs/PDVM_DIALOG_MODAL_SPEC.md`.

---

## 3. Legacy Code
Code, der als `DEPRECATED` markiert ist (insb. in `config.py`), darf nicht für neue Features verwendet werden. Bei Berührung mit solchem Code ist Refactoring (Anpassung an neue Regeln) vorzuziehen.

---

## 4. Spezifikations-Konformität (Domain Specs)

Bei der Implementierung von Kern-Funktionalitäten ist die Einhaltung der dedizierten Spezifikationen verpflichtend. Diese Dokumente sind die "Single Source of Truth" für das jeweilige Subsystem.

### 4.1 PDVM DateTime (`docs/specs/PDVM_DATETIME_SPEC.md`)
**Regel:** Keine native `datetime`-Nutzung für Business-Logik.
*   Das System verwendet eine **3-Ebenen-Matrix** für zeitbezogene Werte (Original, AB-Datum, Formatierung).
*   Alle Zeitstempel müssen als `float` (PDVM-Format) gespeichert und verarbeitet werden.
*   Jedes Widget, das Zeitdaten darstellt oder manipuliert (z.B. `PdvmDateTimePicker`), muss diese Spezifikation implementieren.

### 4.2 Theming System V2 (`docs/specs/THEMING_SYSTEM.md`)
**Regel:** Keine hardcodierten Farben oder Styles in CSS/Komponenten.
*   Styling erfolgt ausschließlich über **Style Blocks** (z.B. `block_header_std`, `block_input_std`).
*   Verwendung von `--block-*` CSS-Variablen ist Pflicht für konfigurierbare Komponenten.
*   Die Fallback-Kette (Block -> Variable -> Default) muss eingehalten werden.

### 4.3 Menu System (`docs/specs/MENU_SYSTEM.md`)
**Regel:** Menü-Struktur folgt strikter Hierarchie und Berechtigung.
*   Dynamischer Aufbau basierend auf `sys_menudaten` und User-Rechten.
*   Trennung von Navigation (Sidebar) und App-Steuerung (Header).
*   Keine manuelle Manipulation der Menü-Struktur im Frontend Code.

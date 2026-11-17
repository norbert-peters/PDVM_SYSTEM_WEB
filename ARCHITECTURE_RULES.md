# PDVM System Web - Architekturregeln

Dieses Dokument definiert die verbindlichen Architektur-Regeln für die Weiterentwicklung des PDVM Systems. Ziel ist die Stabilität und Wartbarkeit bei wachsender Komplexität.

Es enthält ausschließlich Regeln (Soll-Zustand). Beschreibungen des Ist-Stands stehen in [backend/SERVICE_ARCHITECTURE.md](./backend/SERVICE_ARCHITECTURE.md), Detailspezifikationen in `docs/specs/` (siehe Abschnitt 4), Arbeitspläne und Status in `docs/`. Bei Widerspruch gilt dieses Dokument. Die Regelnummern sind stabil und werden in anderen Dokumenten und Werkzeugen referenziert.

## 1. Backend Architektur

### 1.1 Das "Central Database" Gesetz
**Regel:** Es gibt keinen direkten Datenbank-Zugriff in den API-Endpunkten (Routers).

*   ❌ **VERBOTEN:** SQL-Queries (`SELECT...`), direkter asyncpg-Zugriff oder direkter Zugriff auf JSON-Strukturen (`row['daten']['GRUND']`) im Router.
*   ✅ **PFLICHT (Lesen):** Datenzugriff über `PdvmDatabase` (`app.core.pdvm_datenbank`, mit den Pools der GCS-Session). Fachlogik auf Datensatzebene (Defaults, Historie, Stichtag) über die Business-Klasse `PdvmCentralDatabase`.
*   ✅ **PFLICHT (Schreiben):** ausschließlich über den Gateway `app.core.central_write_service`.

**Erweiterung (Dialoge / edit_user):**
- `EDIT_TYPE=edit_user` MUSS Daten ausschließlich über `PdvmCentralDatabase.get_value()` / `set_value()` pflegen.
- Keine direkten JSON-Patches im Frontend/Router für edit_user.
- Hintergrund: Historisierung, Defaults, Datenhaltung bleiben nur so konsistent.

```python
# Richtig:
menu = await PdvmCentralDatabase.load("sys_menudaten", guid, system_pool)
items = menu.get_value_by_group("GRUND")

# Falsch:
row = await db.fetch_row(query)
items = row["daten"]["GRUND"]  # Umgeht Historisierung und Logik!
```

**Write-Pfad:**
- Alle Schreiboperationen (`create`, `update`, `delete`) laufen über `app.core.central_write_service`.
- Direkte Aufrufe wie `await db.update(...)`, `await db.create(...)` oder `await db.delete(...)` im Router sind verboten.
- Actor-Kontext wird primär aus der GCS-Session ermittelt (`user_guid`, `actor_ip`); explizite Actor-Parameter sind nur als kontrollierter Override für Sonderfälle erlaubt.
- `PdvmCentralDatabase.save_all_values`, die GCS-Initialanlage (`msy_systemsteuerung`, `msy_anwendungsdaten`, `msy_layout`) und der Control-Dictionary-Service schreiben ebenfalls über den Gateway.

**Dokumentierte Ausnahmen (Direktzugriff erlaubt):**
- Draft-Container (`workflow_draft_service`, `dev_workflow_draft`)
- Release-Tabellen (`release_service`)
- Mandanten-DB-Wartung (`mandant_db_maintenance`)
- `asy_benutzer`-Sonderpfad (`user_manager`, `pdvm_central_benutzer`, siehe 1.13)
- Feldänderungshistorie

**Weitere Pflichten:**
- Tabellennamen aus Requests müssen einfache Bezeichner sein (`^[a-z_][a-z0-9_]*$`); `PdvmDatabase` lehnt andere Namen ab (400).
- Datenbankfehler "Tabelle existiert nicht" werden zentral als HTTP 404 ausgegeben (`app/core/error_handlers.py`), nicht als 500.
- Wer einen Router ändert, der noch nicht dem Write-Gateway folgt, stellt ihn dabei um.
- Geteilte Pools laufen über `app.core.pool_registry.PoolRegistry`; neue Datenbankverbindungen pro Request sind zu vermeiden (Verbindungsaufbau ca. 150 ms). GCS-Sessions teilen Pools und schließen sie beim Logout nicht.
- Die Einhaltung wird durch Tests erzwungen (siehe Abschnitt 5).

### 1.2 Single Source of Configuration
**Regel:** Es gibt keine hardcodierten Verbindungsdaten für Mandanten- oder System-Datenbanken (`config.py`).

*   Die einzige statisch bekannte Datenbank ist die **AUTH-DB** (`DATABASE_URL_AUTH`).
*   Alle anderen Verbindungen (System, Mandant) **MÜSSEN** dynamisch über den `ConnectionManager` und die Tabelle `asy_mandanten` bezogen werden. System-DB und Mandanten-DB dürfen auf verschiedenen Instanzen liegen.
*   Zugangsdaten gehören in `backend/.env` bzw. den Credential-Store (`PDVM_DB_CREDENTIALS`), nicht in den Quellcode und nicht in `asy_mandanten`. Mandantensätze enthalten nur Adressen und den Verweis `CREDENTIAL`/`SYSTEM_CREDENTIAL`. Die AUTH-Zugangsdaten gelten nur für die AUTH-Instanz und werden nie an andere Server gesendet (`docs/specs/PDVM_DB_VERBINDUNGEN_UND_ZUGANGSDATEN_SPEC_V1.md`).
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

### 1.4a View-Pipeline Source of Truth (Controls)
**Regel:** Sichtbare Controls in der View werden primär aus dem aktuellen Matrix-Response der Server-Pipeline aufgebaut.

*   ✅ **PFLICHT:** Frontend nutzt `POST /api/views/{view_guid}/matrix -> controls_effective` als Laufzeit-Quelle fuer Spalten/Labels/Typen.
*   ✅ **PFLICHT:** Bei Umschalten von Gruppierung/Filter/Sortierung wird die Anzeige immer aus dem aktuellen Matrix-Stand neu aufgebaut (kein statischer Cache als Hauptquelle).
*   ✅ **PFLICHT:** Lokale Draft-Werte (`show`, `display_order`, `width`) duerfen nur als Overlay auf den Matrix-Stand wirken.
*   ✅ **PFLICHT:** Ein deaktiviertes Grouping darf keine Row-Collapse-Informationen mehr anwenden.
*   ❌ **VERBOTEN:** Controls dauerhaft nur aus einem veralteten State-Objekt zu rendern, wenn ein aktuelles Matrix-Resultat vorliegt.

Begruendung:
- Die lineare Pipeline (BASIS -> FILTER -> SORT -> GROUP -> PROJECT) ist die fachliche Quelle.
- Nur so bleiben Header, Typen (z. B. `dropdown`) und Zellauflösung (z. B. Uebersetzungen wie `Anrede`) beim Wechsel zwischen GROUP on/off konsistent.

### 1.5 SYSTEM-Gruppe = Tabellen-Spalten
**Regel:** Controls mit `gruppe=SYSTEM` sind **Spaltenfelder** der Tabelle.

- Speicherung erfolgt **direkt über `PdvmDatabase`** (nicht in `daten` JSONB), Schreiben wie immer über den Gateway (1.1).
- Für `asy_benutzer` gelten Sonder-Spalten: `benutzer`, `passwort`.
- `USER.EMAIL` bleibt **JSONB** (Gruppe USER) und darf **nicht** als SYSTEM-Spalte behandelt werden.

### 1.6 Dialog LAST_CALL (vereinfachte Pflichtlogik)
**Regel:** `LAST_CALL` ist ausschließlich an **`view_guid + root_table`** gekoppelt.

**Vorgabe:**
1. `LAST_CALL` wird nur unter der Gruppe `view_guid` gespeichert.
2. Feldname ist `TABLE` (UPPERCASE), der Wert ist ein Objekt `{"LAST_CALL": <uid|null>}`.
3. Keine Fallbacks auf `frame_guid` oder `dialog_guid`, keine Auto-Korrektur, keine zusätzliche Validierung.
4. Dialog-Start:
	- Für `view_guid + table` **muss** der Feld‑Key existieren; fehlt er, wird `{ "LAST_CALL": null }` erstellt und persistiert.
	- Vorhandene Auswahl → direkt Tab2 (Edit)
	- Keine Auswahl → Tab1 (View)
5. View-Auswahl aktualisiert `{ "LAST_CALL": <uid> }`.

**Begründung:**
Mehrere Dialoge können unterschiedliche Frames haben, aber dieselbe `view_guid + table` teilen.
Dann sollen alle Dialoge auf den zuletzt ausgewählten Datensatz springen.

### 1.7 Tabellen-Routing (zentral über PdvmDatabase)
**Regel:** Datenbank‑Routing erfolgt ausschließlich über `PdvmDatabase` anhand des Tabellennamens.

- Keine manuelle DB‑Auswahl in Callern.
- Sonderfälle (z.B. `asy_benutzer`) dürfen Zusatzfunktionen haben, müssen aber **primär**
	`PdvmDatabase` nutzen und nur für Spezialspalten auf Auth‑Queries ausweichen.

### 1.7a Verbindliche Praefix-Routing-Regeln
**Regel:** Der Datenbanktyp wird ausschließlich aus dem Tabellenpraefix bis zum ersten `_` ermittelt.

- `asy_*` -> AUTH-DB
- `sys_*` -> System-DB (`pdvm_system`)
- `dev_*` -> System-DB (`pdvm_system`) als explizite Entwicklungs-Ausnahme
- `msy_*` -> Mandanten-DB (systemnahe Mandanten-Tabellen)
- `<app>_*` -> Mandanten-DB (applikationsspezifische Tabellen, z. B. `crm_*`, `pps_*`)

Pflicht:
- Tabellen **ohne** `_` (also ohne Praefix) sind ungueltig.
- Auf AUTH-DB sind nur `asy_*`-Tabellen zulaessig.
- Auf System-DB sind nur `sys_*`-Tabellen zulaessig.

### 1.8 Session Idle Timeout (Mandant ROOT)
**Regel:** Idle‑Timeout wird zentral über Mandant‑Daten gesteuert.

- `ROOT.IDLE_TIMEOUT` und `ROOT.IDLE_WARNING` sind **Sekunden**.
- Backend aktualisiert Session‑Aktivität bei jeder Anfrage (Sliding Session).
- Frontend sendet `POST /api/auth/keep-alive` bei Benutzer‑Aktivität und zeigt Warnung via `PdvmDialogModal`.
- Bei Inaktivität wird die Session serverseitig beendet (GCS‑Session schließt Pools).

### 1.9 Zeitwerte im Pdvm-Format (JSONB)
**Regel:** Zeitwerte in JSONB-Daten werden im Pdvm-Format gespeichert.

- Gilt fuer `daten` in allen PDVM-Tabellen.
- Ausnahme: systemeigene Spalten wie `created_at`/`modified_at`/`gilt_bis` bleiben SQL-Timestamps (siehe 1.14).

Verbindliche Definition (PdvmDateTime):
- Format ist immer `YYYYDDD.FRACTION`.
- `YYYY`: Jahr, `DDD`: Tag im Jahr (1-366), `FRACTION`: Bruchteil des Tages (`0.5 = 12:00:00`).
- Es gibt kein alternatives Zeitkodierungsformat im Nachkommateil.

Verbindliche Umwandlung:
- Umwandlung zwischen Python/JS Datum und PDVM erfolgt ausschliesslich ueber `pdvm_datetime.py` bzw. deren abgeleitete, formatgleiche Hilfsfunktionen.
- Direkte Eigenimplementierungen mit abweichender Mathematik sind verboten.
- Wenn neue Hilfsfunktionen benoetigt werden, werden sie als neue Funktionssammlung hinzugefuegt, muessen aber dieselbe Formatdefinition einhalten.

### 1.10 sys_control_dict Struktur (linear, ohne Fallback)
**Regel:** Datensaetze in `sys_control_dict.daten` haben exakt die Gruppen `ROOT` und `CONTROL`.

- Keine flachen Legacy-Top-Level-Properties in `daten`.
- `CONTROL.FIELD` ist verpflichtend in GROSSBUCHSTABEN. `CONTROL.FELD` ist ein Alias und unzulaessig (Alias-Verbot, siehe 1.12b); `FIELD` ist die einzige kanonische Schreibweise.
- `name`/`SELF_NAME` folgen immer `<TABELLENPREFIX>_<FIELD>` in GROSSBUCHSTABEN (z. B. `SYS_LABEL`). Gibt es dasselbe `FIELD` mit abweichender Semantik (Gruppe, Label, Typ) mehrfach, lautet der Name `<TABELLENPREFIX>_<GRUPPE>_<FIELD>` (Punkte in der Gruppe als `_`), bei weiterer Kollision mit Zaehler `_2`, `_3`.
- Neuanlage erfolgt ausschliesslich ueber den regulären Neuanlage-Flow (keine Template-Direktkopien als Fachdaten).

### 1.10a Muttercontrol-Regel fuer `sys_control_dict` (starr)
**Regel:** `sys_control_dict` mit UID `66666666-6666-6666-6666-666666666666` ist das verbindliche Muttercontrol unter `daten.CONTROL`.

- `daten.CONTROL` des 666-Satzes ist die einzige kanonische Quelle fuer erlaubte Control-Eigenschaften.
- Eigenschaftsvergleiche fuer Freigabe/Validierung erfolgen **case-insensitive**.
- Freigegebene Eigenschaft `IMMUTABLE` (Boolean, Standard `false`, 2026-11-13): Feld darf nach der Anlage nicht mehr geaendert werden (Set-Once), siehe 2.15.
- Freigegebene Eigenschaft `IMMUTABLE_AFTER` (String, Pfad `GRUPPE.FELD`, Standard leer, 2026-11-16): macht die Sperre von `IMMUTABLE` bedingt, sie gilt erst, wenn dieses Feld im gespeicherten Satz einen Wert hat (Mandanten: `ROOT.DB_CREATED_AT`), siehe 2.15.
- Freigegebener Control-Typ `password` (2026-11-14) mit `CONFIGS.password.name_prefix` (Praefix fuer neu erzeugte Credential-Namen): write-only, siehe 2.15.
- Freigegebener Control-Typ `password_input` (2026-11-16): Passwort-Eingabe ohne Speicherung (Anmeldung), nur in Frames mit `ROOT.FRAME_TYPE = "public_form"`; `CONFIGS.input {name, autocomplete}` (auch fuer `string`) und `CONFIGS.password_input {reveal, min_length, confirm_with}`, siehe 2.15 und `PDVM_LOGIN_FRAME_SPEC_V1.md`.
- Freigegebener Control-Typ `text_popup` und Konfiguration `CONFIGS.text` (`rows`, `expand`, `title`, `mono`, `html_preview`) fuer Langtexte (2026-11-14): Der Typ `text` erhaelt eine Vergroessern-Schaltflaeche, beide oeffnen dasselbe Textfenster, siehe PDVM_FRAME_INPUT_RENDERING_SPEC_V1.md Abschnitt 10.
- Freigegebene Control-Typen `action` (Button) und `info` (Hinweis) mit `CONFIGS.action` (`id`, `placement`, `modes`, `confirm`, `params`, `visible_when`, `enabled_when`, `when_denied`) und `CONFIGS.info` (`text`, `value_path`, `format`, `severity`, `placement`, `modes`, `state`, `visible_when`) (2026-11-15), siehe 2.17.
- Die kanonische Schreibweise im Muttercontrol ist **GROSSBUCHSTABEN**.
- Eigenschaften, die in `sys_framedaten` (`daten.FIELDS.*`) oder `sys_viewdaten` (`daten.SYSTEM.*`) genutzt werden, duerfen nur dann als Control-Eigenschaft gelten, wenn sie im Muttercontrol aufgenommen und freigegeben wurden.
- Neue Eigenschaften werden zuerst im Muttercontrol dokumentiert und erst danach in Runtime-/Migrationslogik verwendet.
- Erweiterungen in `CONTROL.CONFIGS` folgen demselben Freigabeprozess (keine stillen Ad-hoc-Keys in Produktionsdaten).
- Zusammenspiel mit 1.12a/1.13: Der 666-Satz fuehrt dieselbe Struktur zusaetzlich als Neuanlage-Vorlage unter `daten.TEMPLATES.CONTROL`. `daten.CONTROL` (Pruefquelle) und `daten.TEMPLATES.CONTROL` (Vorlage) muessen inhaltlich identisch sein; Seeder und Audit pruefen die Synchronitaet.

### 1.10b Frame-Layout-Override auf FIELDS (TAB/DISPLAY_ORDER)
**Regel:** In `sys_framedaten.daten.FIELDS` bleibt `sys_control_dict` die fachliche Quelle fuer Controls; reine Layout-Attribute duerfen pro Frame uebersteuert werden.

- ✅ **PFLICHT:** Control-Semantik (`TYPE`, `LABEL`, `GRUPPE`, `FELD`, `CONFIGS`, usw.) kommt aus `sys_control_dict`.
- ✅ **PFLICHT:** Frame darf Layout-Parameter je Feld setzen, insbesondere `TAB` und `DISPLAY_ORDER` (sowie `SOURCE_PATH`/`SAVE_PATH` wenn benoetigt).
- ✅ **PFLICHT:** Frame darf bei generischen Controls die Kontextbindung `GRUPPE` und `TABLE` (GROSS geschrieben) uebersteuern. Ein Eintrag traegt nur diese Schluessel; eingebettete Control-Kopien (`ROOT`/`CONTROL` im Feld) und Kleinschreib-Eigenschaften sind unzulaessig.
- ✅ **PFLICHT:** Runtime-Merge muss diese Layout-Parameter erhalten, damit mehrtabbige Frames stabil gerendert werden.
- ❌ **VERBOTEN:** Unbekannte freie Zusatz-Properties in `FIELDS.*` als fachliche Overrides zu akzeptieren.

Dokumentierte Ausnahmen (nicht als Control zu fuehren):
- Benannte Struktur-Eintraege in `element_list`-Frames (z. B. `FIELDS.CONTROL.element`, `FIELDS.CONFIGS.*`).
- Felder mit Kleinschreib-Datenschluessel (`sys_menudaten.MENU`: `label`, `tooltip`, `icon`, `command`, ...), solange das Menuedatenmodell Kleinschreibung nutzt.

Begruendung:
- Frames brauchen eine eigene visuelle Ordnung, ohne die zentrale Control-Definition zu duplizieren.
- Ohne erlaubtes `TAB`-Override landen Felder implizit in Tab 1 und die Frame-Darstellung wird inkonsistent.

### 1.10c pdvm_edit Control-Autonomie und Expert-Debug-Konsistenz (verbindlich)
**Regel:** Fuer `EDIT_TYPE=pdvm_edit` gilt ein einheitlicher Laufzeitvertrag ohne bereichsspezifische Sonderpfade. `edit_user` und `pdvm_edit` nutzen denselben `PdvmInputControl`-Contract und dieselbe Control-Resolution (siehe 2.14).

Pflichten:
- Jedes InputControl wird immer ueber denselben Datenzugriffsvertrag aufgeloest: `SOURCE_PATH` + `GRUPPE` + `FELD`.
- `FRAME_TYPE` beschreibt nur den Host-/Containerkontext (z. B. workspace, popup, element-editor) und darf den Datenzugriffsweg nicht aendern.
- Auch Child-Frames in `element_list` werden als normale InputControls mit voller Runtime-Hydration gerendert.
- Die Control-Rohansicht (`{}`) bleibt **ausschliesslich Expert-Mode** vorbehalten. Wenn Expert-Mode aktiv ist, muss die Rohansicht fuer alle InputControls im selben Renderkontext konsistent verfuegbar sein (keine Mischform).

Nicht zulaessig:
- Kontextabhaengige Speziallogik, bei der einzelne InputControls im selben Expert-Mode keine Rohansicht erhalten.
- Datenzugriffslogik, die alternativ Parent-/Dialogpfade nutzt, obwohl `SOURCE_PATH` + `GRUPPE` + `FELD` fuer das Control vorliegen.

### 1.10d Lineare Frame-Control-Pipeline (verbindlich)
**Regel:** Frame-basierte Controls folgen einem strikt linearen End-to-End-Pfad ohne Kontext-Sonderlogik (Ergänzung zu 1.10c).

Pflichten:
- Es gibt genau ein Runtime-Control-Modell pro Feld (Single Runtime Model).
- Lesen erfolgt ausschliesslich ueber `SOURCE_PATH + GRUPPE + FELD`.
- Schreiben erfolgt ausschliesslich ueber `SOURCE_PATH + SAVE_PATH`.
- Config-Aufloesung erfolgt genau einmal zentral vor dem Rendering.

Nicht zulaessig:
- Doppelte Resolver-Logik je Renderkontext (z. B. Haupteditor vs. Element-Modal).
- Stilles Leerlaufen bei fehlender Pflichtkonfiguration.
- Mehrere parallele Config-Quellen im Renderer (Legacy nur einmal am Eingang mappen).

Pflicht fuer `go_select_view`:
- Die `lookup_table` wird zentral aus `resolved_configs.go_select_view.table` bestimmt.
- Fehlt die Tabelle, muss ein qualifizierter Fehler angezeigt werden.

Verweis: `docs/specs/PDVM_LINEAR_FRAME_CONTROL_PIPELINE_SPEC_V1.md`

### 1.11 Schutz von Basis-/Template-GUIDs (maschinenfest)
**Regel:** Reservierte Basis-/Template-Datensaetze duerfen durch Migrationen nicht geaendert werden.

- Gilt insbesondere fuer GUID-Serien mit den Praefixen `5...`, `6...` und `0...` (z. B. `5555...`, `6666...`, `0000...`).
- Diese Saetze bilden die tabellenweiten Basiseinstellungen und werden manuell gepflegt.
- Migrationsskripte fuer `sys_control_dict` muessen diese GUIDs explizit vom Update ausschliessen.
- Automatische Umbenennung/Normalisierung (auch UID-Neuvergabe durch Mandanten-Wartung) dieser reservierten Saetze ist verboten.
- Pruefung der Basissaetze: `backend/tools/seed_base_records.py --check`.

### 1.12 Verbindliche Tabellen-Basissaetze 000/555/666
**Regel:** Jede fachliche PDVM-Tabelle hat drei fixe reservierte UIDs mit klarer Bedeutung.

- `00000000-0000-0000-0000-000000000000`
	Enthält Tabellen-Metadaten (informativ, keine feste fachliche Payloadstruktur).
- `55555555-5555-5555-5555-555555555555`
	Enthält die Basisstruktur eines neuen Satzes in den Gruppen `ROOT` und weiteren Gruppen (Ausgangspunkt der Neuanlage, siehe 1.13) sowie Erweiterungs-/Element-Templates.
- `66666666-6666-6666-6666-666666666666`
	Enthält die Vorlagen (`daten.TEMPLATES`) fuer Gruppen, die in der 555-Basis leer sind (siehe 1.12a, 1.13).

Pflicht:
- Diese drei UIDs sind reserviert und dürfen nicht als normale Fachdaten verwendet werden.
- Seeder/Migrationen müssen Existenz und Struktur dieser Basissätze prüfen.

### 1.12a 666 Template-Gruppenregel (TEMPLATES)
**Regel:** Template-Definitionen im 666-Satz liegen unter der Gruppe `TEMPLATES`.

Verbindliche Struktur:
- `daten.ROOT` enthaelt die ROOT-Vorlage fuer Neuanlagen.
- `daten.TEMPLATES` enthaelt Template-Container/Varianten.
- Wenn `TABLE_INFO` als Template-Metadaten genutzt wird, dann ausschliesslich unter `daten.TEMPLATES.TABLE_INFO`.
- `daten.TABLE_INFO` im 666-Satz ist ungueltig.

Verboten:
- `TABLE_INFO` als fachliches Feld in normalen Datensaetzen (nicht reservierte UIDs).
- Gemischte Ablagepfade pro Tabelle ohne dokumentierte Ausnahme.

### 1.12b ROOT/TABLE_INFO Vereinheitlichung (verbindlich)
**Regel:** Die Datenstruktur bleibt flach und einheitlich; ROOT und TABLE_INFO haben strikt getrennte Verantwortlichkeiten.

Kanonische ROOT-Kernfelder (tabellenweit):
- `SELF_GUID`
- `SELF_NAME`
- `SELF_LINK_UID`
- `SELF_CREATED_AT`
- `SELF_MODIFIED_AT`
- `SELF_GILT_BIS`
- `TABLE`

Kanonische TABLE_INFO-Felder (Template-Metadaten):
- `version`
- `description`
- `created_at`
- `created_by`
- `schema_migrated`

Abgrenzung:
- ROOT enthaelt Datensatzidentitaet und Laufzeit/Fachzustand.
- TABLE_INFO enthaelt Tabellen-/Template-Metadaten.
- ROOT-Felder werden nicht nach TABLE_INFO verschoben.

Namenskonflikte/Alias-Verbot:
- Doppelte Semantik mit unterschiedlichen Feldnamen ist unzulaessig.
- Bei Konflikten ist genau ein kanonischer Feldname festzulegen und zu verwenden.

### 1.12c Pflichtgrad und Fehlerbehandlung (verbindlich)
**Regel:** TABLE_INFO ist als Template-Gruppe in der 666 verpflichtend, nicht als Pflichtgruppe in jedem Fachdaten-Satz.

Pflichten:
- Jede fachliche Tabelle mit 666-Basissatz fuehrt `daten.TEMPLATES.TABLE_INFO`.
- Nicht-reservierte Datensaetze enthalten mindestens ROOT; TABLE_INFO in Fachdaten ist optional und standardmaessig nicht vorgesehen.

Fehlerklassifikation (bei Audit-Abweichungen):
- **Datenfix:** Bestehende Datensaetze weichen von 666-Struktur oder kanonischen Feldnamen ab.
- **Programmfix:** Create/Update/Clone/Import-Logik erzeugt erneut Abweichungen oder schreibt ungueltige Pfade.
- Bei jeder Abweichung sind beide Ebenen zu pruefen; Datenfix ohne Programmfix gilt als unvollstaendig.

### 1.13 Einheitlicher Neuanlage-Algorithmus (tabellenweit)
**Regel:** Neuanlage erfolgt linear und zentral in genau einem Algorithmus.

Ausnahme:
- `asy_benutzer` behaelt den bestehenden Sonderpfad.

Verbindlicher Ablauf:
1. Name ermitteln/abfragen (Pflicht).
2. Neue GUID erzeugen.
3. Daten aus UID `555...` derselben Tabelle als Basis laden und tief kopieren.
4. `ROOT`-Eigenschaften des neuen Satzes setzen (`SELF_GUID`, `SELF_NAME`, `TABLE`, optionale Create-Context-Werte).
5. Fuer jede leere Gruppe der 555-Basis gleichnamige Vorlage in `666...(TEMPLATE|TEMPLATES)` suchen und uebernehmen.
6. Wenn eine leere 555-Gruppe keine gleichnamige Vorlage in `666...(TEMPLATE|TEMPLATES)` hat: Fehler.
7. Datensatz speichern (direkt oder innerhalb eines Draft-Containers).

Verboten:
- Tabellen-/Feature-spezifische Sonder-Neuanlagen ausser der expliziten Ausnahme `asy_benutzer`.
- Parallele zweite Neuanlage-Logik mit abweichender Basiserzeugung.

Der Ablauf im Dialog (Draft-Flow) steht in 2.5a.

### 1.14 UID-, LINK_UID- und ROOT-SYSTEM-Felder
**Regel:** `uid` bleibt der technische Primärschlüssel; `link_uid` bildet die fachliche Datensatz-Linie.

Pflicht:
- `uid` ist immer eindeutig pro Zeile (Primary Key) und darf sich nie ändern. Sie ist eine reine technische Row-ID ohne fachliche Verlinkungsbedeutung.
- `link_uid` ist für neue Datensätze zu setzen; Standardfall: `link_uid = uid`. Fachliche Identität und exakte Adressierung laufen über `link_uid`.
- Bei historisierten Folgezeilen oder Feld-Audits zeigt `link_uid` auf den fachlichen Ursprungssatz.
- Die Systemspalten werden in `daten.ROOT` gespiegelt (`SELF_LINK_UID`, `SELF_CREATED_AT`, `SELF_MODIFIED_AT`, `SELF_GILT_BIS`, siehe 1.12b) und dort im PDVM-Format geführt (1.9).
- Die SQL-Spalten `created_at`, `modified_at`, `gilt_bis` sind in **allen** Tabellen, auch in den `asy_*`-Tabellen, native PostgreSQL `TIMESTAMP`.

Fuer GCS gilt speziell:
- `msy_systemsteuerung` wird über `link_uid = user_guid` gelesen/geschrieben.
- `msy_anwendungsdaten` wird über `link_uid = mandant_guid` gelesen/geschrieben.
- Bei Migrationen dürfen für diese Tabellen neue `uid`-Werte vergeben werden; `link_uid` bleibt stabil.
- Ausnahmen müssen explizit dokumentiert werden und dürfen diese GCS-Link-UID-Regel nicht verletzen.

### 1.15 Semantik historisch und gilt_bis (verbindlich)
**Regel:** `historisch` und `gilt_bis` haben unterschiedliche, nicht austauschbare Bedeutung.

Verbindliche Definition:
- `historisch` kennzeichnet, ob Daten/Felder historisch gefuehrt werden (0 = nein, 1 = ja).
- `historisch` ist **nicht** die zentrale Steuerung fuer Archivierung oder Loeschung im operativen Laufzeitmodell.

Verbindliche Archivierungs-/Loeschregel:
- Archivierungen und Loeschungen laufen ueber `gilt_bis`.
- Ein aktiver Datensatz hat den offenen Wert `9999-12-31 23:59:59` (PDVM `9999365.99999`, siehe 1.23).
- Das Beenden/Archivieren eines Datensatzes erfolgt durch Setzen eines passenden `gilt_bis`-Zeitpunkts.

Konsequenz fuer neue Tabellen/Tools:
- Monitoring-, Batch- und Job-Tabellen duerfen fuer Aufbewahrung/Abschluss nicht auf `historisch` umdeuten.
- Wenn ein Lebenszyklus benoetigt wird, ist dieser ueber `gilt_bis` (und optional ROOT-Statusfelder) abzubilden.

### 1.16 I18N Default- und Supported-Languages (verbindlich)
**Regel:** DEFAULT_LANGUAGE und SUPPORTED_LANGUAGES werden zentral ueber die I18N-Policy definiert.

- Verbindliche Quelle: `backend/config/i18n_policy_v1.json` (dort stehen Default und unterstuetzte Sprachen).
- Sprach-Normalisierung erfolgt zentral in `backend/app/core/i18n_policy.py`.
- Services mit Sprachauflösung (z. B. Dropdown/Systemdaten) muessen diese Normalisierung verwenden.
- Historische/abweichende Codes (z. B. `US-EN`, `DEU`) werden per Alias auf kanonische Codes abgebildet.

Die folgenden Regeln 1.17 bis 1.19 haben ebenfalls je eine JSON-Datei in `backend/config/` als einzige Quelle der Werte. Werte werden nicht in diesem Dokument dupliziert.

### 1.17 I18N Pflicht-Uebersetzungsumfang je Inhaltstyp (verbindlich)
**Regel:** Der Pflichtumfang je Inhaltstyp (`dropdown`, `label`, `hilfe`, `text`) wird zentral als Matrix gepflegt und fuer Qualitaetschecks verwendet.

- Verbindliche Quelle: `backend/config/i18n_required_translation_scope_v1.json`
- Validierungs- und Reporting-Tools muessen diese Matrix verwenden; Sprach-Normalisierung ueber die zentrale I18N-Policy (1.16).
- Neue Inhalte duerfen nicht als produktionsreif gelten, wenn required-Sprachen fuer den jeweiligen Inhaltstyp fehlen.

### 1.18 I18N Uebersetzungsmodus je Tabelle (verbindlich)
**Regel:** Jede betroffene infos-Tabelle hat einen verbindlichen Uebersetzungsmodus (`MANUAL` oder `MACHINE_ASSISTED`) inklusive Review-Regel.

- Verbindliche Quelle: `backend/config/i18n_translation_mode_per_table_v1.json`
- Unabhaengig vom Modus ist vor produktiver Nutzung eine fachliche Freigabe erforderlich; maschinelle Vorbelegungen ohne Freigabe sind nicht produktiv gueltig.
- Validierungs-/Reporting-Tools muessen Modus, Review-Regel und Entscheidungs-Lock je In-Scope-Tabelle ausweisen. Offene Entscheidungen (`decision_locked = false`) sind fuer produktive Freigaben nicht zulaessig.

### 1.19 I18N Freigabemodell je Sprache (verbindlich)
**Regel:** Sprachbezogene Inhalte verwenden ein einheitliches Freigabemodell fuer produktive Nutzung.

- Verbindliche Quelle: `backend/config/i18n_language_release_model_v1.json`
- Pflichtfelder je Spracheintrag: `version` (Pattern `^v[0-9]+\.[0-9]+\.[0-9]+$`), `status`, `approved_by`, `approved_at`.
- Statuswerte: `new`, `machine`, `review`, `approved`. Nur `status=approved` gilt als produktiv freigegeben; dann sind `approved_by` (nicht leer) und `approved_at` (ISO8601) verpflichtend.

### 1.20 Mandanten-DB Updates: Updatearten und Versionierungsachsen (verbindlich)
**Regel:** Wiederkehrende Datenbank-Migrationen werden mandantenbezogen ueber ein standardisiertes Updateverfahren gefahren.

- Verbindliche Spezifikation: `docs/specs/PDVM_MANDANT_DB_UPDATE_VERSIONIERUNG_SPEC_V1.md`
- Updatearten: `SOURCE_UPDATE` (Quellstand/Release-Kontext), `DATABASE_UPDATE` (Schema/Struktur), `DATA_UPDATE` (Inhaltsmigration).
- Versionsachsen je Mandant: `SOURCE_VERSION`, `DB_SCHEMA_VERSION`, `DATA_MODEL_VERSION`.
- Wiederkehrende Update-Ziele sind Mandanten-DBs. AUTH-DB und SYSTEM-DB sind keine regulaere Update-Pipeline.

### 1.21 ViewDefinition Datengruppen-Validierung (verbindlich)
**Regel:** In `sys_viewdaten.daten` gilt fuer Datengruppen neben `ROOT` eine strikt lineare Validierung.

Verbindliche Gruppen:
- Erlaubt sind nur:
	- `<ROOT.TABLE in UPPERCASE>`
	- `**SYSTEM` (technische Gruppe)
	- `SYSTEM` (Legacy-Variante)

Verbindliche Fehlerfaelle:
- Fehler nur, wenn neben `ROOT` keine Datengruppe vorhanden ist.
- Fehler nur, wenn mindestens eine Datengruppe nicht zu den erlaubten Gruppen gehoert.

Verbindliche Nicht-Fehlerfaelle:
- `**SYSTEM` oder `SYSTEM` alleine ist zulaessig.
- `<ROOT.TABLE in UPPERCASE>` zusammen mit `**SYSTEM`/`SYSTEM` ist zulaessig.
- Das Fehlen der Tabellen-Gruppe alleine ist kein Fehler, solange eine erlaubte Datengruppe vorhanden ist.

### 1.22 Name/SELF_NAME Schreib-Lese-Vertrag (verbindlich)
**Regel:** `ROOT.SELF_NAME` ist die fachliche Schreibquelle fuer den Datensatznamen, die Spalte `name` ist die technische Lesebasis.

- **Beim Schreiben (create/update):**
	- Wenn `ROOT.SELF_NAME` vorhanden und nicht leer ist, wird der Wert in die Spalte `name` uebernommen.
	- Wenn `ROOT.SELF_NAME` fehlt oder leer ist, bleibt das vorhandene Namensverhalten erhalten.
- **Beim Lesen:**
	- `name` wird aus der Spalte `name` gelesen.
	- `ROOT.SELF_NAME` muss mit der Spalte `name` synchron sein.

### 1.23 GILT_BIS / SELF_GILT_BIS Vertrag (verbindlich)
**Regel:** `ROOT.SELF_GILT_BIS` ist die fachliche Schreibquelle fuer Gueltigkeit, die Spalte `gilt_bis` ist die technische Wahrheit beim Lesen.

- **Beim Schreiben (create/update):**
	- Wenn `ROOT.SELF_GILT_BIS` vorhanden und nicht leer ist, wird der Wert in die Spalte `gilt_bis` uebernommen.
	- Bei Neuanlage wird ohne expliziten Wert immer `offen` gesetzt (`9999365.99999` = `31.12.9999 23:59:59`).
	- Nach dem Write werden `ROOT.SELF_GILT_BIS` und weitere `SELF_*` aus den Spaltenwerten in `daten.ROOT` synchronisiert.
- **Beim Lesen (View-Sicht):**
	- Datensaetze mit `gilt_bis <= stichtag` sind in Views ausgeschlossen (nicht sichtbar).
	- Datensaetze mit offenem Sentinel (`9999365.99999`) bleiben sichtbar.
- Spezifikation: `docs/specs/PDVM_GILT_BIS_SPEC_V1.md`

### 1.24 Textvorlagen (verbindlich)
**Regel:** Texte für Nachrichten (E-Mail u. a.) stehen nicht im Quellcode, sondern als sprachbezogene Vorlagen in `sys_textvorlagen` (System) und `msy_textvorlagen` (Mandant). Spezifikation: `docs/specs/PDVM_TEXTVORLAGEN_SPEC_V1.md`.

- Der Code sucht nach dem stabilen `ROOT.TEMPLATE_KEY`, nie nach UID oder Name. Auflösung: aktive Mandantenvorlage (`ROOT.ACTIVE`) → Systemvorlage (ohne Mandanten-DB direkt die Systemvorlage); gewählt wird die erste **freigegebene** Sprache der Kette.
- Freigabe je Sprache nach 1.19 (`STATUS`): Textänderungen setzen `review`, versendet wird nur `approved`. Pflege und Freigabe nur mit Rolle (`vorlagen` für `sys_textvorlagen`; `admin`/`man_admin`/`vorlagen` für `msy_textvorlagen`, jeweils auch `superadmin`), durchgesetzt in `text_template_service.guard_write` über `central_write_service`. Schreibpfade müssen die Session (`gcs`) an den Gateway durchreichen.
- Systemvorlagen werden einmalig in den Mandanten kopiert (neue UID, `SOURCE_UID`, `SOURCE_HASH`); Mandanten ändern nur ihre Kopien, nie die Systemvorlagen. Wird die Systemvorlage später geändert, zeigt der Mandanten-Dialog „Systemvorlage ist neuer“ (Vergleich `SOURCE_HASH`); die neue Fassung wird nur als **neue, inaktive Kopie** übernommen, nie durch Überschreiben. Nachträglich neue Systemvorlagen und Basissätze liefert `mandant_textvorlagen_update_v1.py` (DATA_UPDATE, 1.20) in bestehende Mandanten-DBs.
- Platzhalter `{{name}}` nur als Ersetzung; Variablen sind deklariert (`VARIABLES`, `REQUIRED_VARIABLES`) und werden beim Speichern geprüft. Gerenderte Texte mit Geheimnissen (OTP) werden nicht geloggt.
- Sprache: Empfänger → `CONFIG.DEFAULT_LANGUAGE` des Mandanten (Dropdown im Mandanten-Frame, Quelle `Sprachen::sprache`) → `DEFAULT_LANGUAGE` der I18N-Policy (1.16).

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
*   Menüeinträge können optional `roles` (Liste) tragen: ohne `roles` für alle sichtbar, sonst nur für Benutzer mit einer dieser Rollen (`superadmin` sieht alle). Gefiltert wird serverseitig in `GET /api/menu/start` und `/api/menu/app/{name}` (`menu.filter_menu_group_by_roles`); die Endpunkte prüfen ihre Rollen weiterhin selbst. Menü-Handler sind eine feste Allowlist in `menuHandlers.ts` (z. B. `go_mandant_create` mit fester Route), keine freien Pfade aus Menüdaten.
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

### 2.5 Dialog View/Edit Autonomie
**Regel:** View- und Edit-Tab sind **autonom** und dürfen **nicht** voneinander abhängig sein.

- **Neuanlage** ist eine **Dialog-/Tabellenfunktion**, nicht Edit-Type abhängig.
- „Neuer Satz“ gehört in den **View-Tab** (Anzeige der Tabelle), **nicht** in den Edit-Tab.
- Der Edit-Tab zeigt **nur** Speichern/Änderungen (keine Neuanlage).
- Der neue Datensatz entsteht über den Neuanlage-Algorithmus (1.13, Ablauf in 2.5a) und ist danach in der View sichtbar.
- View/Tabellenanzeige und Edit-Formular bleiben unabhängig (keine Vermischung von Zuständigkeiten).

### 2.5a Linearer Draft-Flow bei Neuanlage
**Regel:** "Neuer Satz" läuft generisch und linear über Drafts, tabellenübergreifend.

Der einzige fachlich zulässige Neuanlage-Flow ist:
`POST /api/dialogs/{dialog_guid}/draft/start` → Edit auf Draft → `POST /api/dialogs/{dialog_guid}/draft/{draft_id}/commit`.

- Edit arbeitet auf Draft-Daten; das Backend liefert Validierungsfehler mit Zielpfad (`group`, `field`).
- Persistenz erfolgt erst beim Commit.
- Kein erzwungener Sonderpfad mit `428` als Steuermechanismus für Standard-Neuanlage.
- Direkte Neuanlage über `POST /api/dialogs/{dialog_guid}/record` ist nur Kompatibilität und muss intern denselben Ablauf nutzen.
- Neue Features dürfen keinen zweiten Neuanlage-Mechanismus einführen; direkte Neuanlage-Aufrufe im Source sind auf den Draft-Flow umzustellen.

### 2.6 Einheitlicher Edit-Frame (Dialoge)
**Regel:** Alle Editoren verwenden denselben Edit-Rahmen.

- Kopfbereich (Header + Edit-Tabs) ist fix.
- Nur der Editor-Inhalt scrollt.
- Edit-Typen liefern Inhalte, nicht das Layout.
- Keine individuellen Scroll-Container pro Editor.

Siehe Spezifikation: `docs/specs/PDVM_DIALOG_EDIT_FRAME_SPEC.md`.

### 2.7 Dialog V2 (egalisiert)
**Regel:** Dialoge nutzen ein einheitliches Datenmodell in `sys_dialogdaten`.

- `DIALOG_TYPE`: `norm`, `work`, `acti`.
- Tabs definieren Module (`view`, `edit`, `acti`) mit `GUID` pro Tab.
- `VIEW_GUID`/`FRAME_GUID` in `ROOT` sind optional (legacy); die GUIs kommen aus den Tab-Definitionen.
- Aufruf erfolgt immer ueber `go_pdvm_dialog` (dialog_guid + optional dialog_table fuer `show_json`/`edit_json`).
- `pdvm_edit` ist der Standard-Edit-Typ (Frame-gesteuert). `edit_json`/`show_json` bleiben erhalten.
- `show_json` ist ein Edit-Typ und benoetigt immer einen Edit-Tab.
- `dialog_table` ueberschreibt die Tabelle der View-Definition bei `show_json`/`edit_json` (View-State, Matrix, Dialog-CRUD).

Siehe Spezifikation: `docs/specs/PDVM_DIALOG_EDIT_FRAME_SPEC.md`.

### 2.8 Dialog/View/Frame Refaktoring
**Regel:** Normalisierung und Refaktorisierung von Dialogen, Views und Frames folgen der Arbeitsgrundlage `docs/specs/PDVM_DIALOG_VIEW_FRAME_REFAKTORING_ENTWICKLUNGSPHASE.md` (Fokus, Vorgehen und Entscheidungsbedarf stehen dort).

- Es gilt klare Trennung `DIALOG_TYPE=edit` vs `DIALOG_TYPE=work`.
- InputControls-First mit dokumentierten Ausnahmen.

### 2.9 Single-Tab Dialogdarstellung (verbindlich)
**Regel:** Wenn in `sys_dialogdaten` effektiv genau ein Tab konfiguriert ist, wird kein Tab-Header gerendert.

- Diese Regel gilt global fuer alle Dialogtypen.
- Die interne Tab-Logik bleibt erhalten; nur die visuelle Tab-Navigation wird ausgeblendet.

### 2.10 Workflow-Endtab (verbindlich)
**Regel:** Bei `DIALOG_TYPE=work` muss der letzte Tab `MODULE=acti` besitzen.

- Ohne `acti`-Endtab ist die Dialogkonfiguration ungueltig.
- Validierungs- und Analyse-Tools muessen diese Regel explizit pruefen.

### 2.11 JSON/Edit Sonderpfade und Menue-Security (verbindlich)
**Regel:** `show_json` und `edit_json` sind dokumentierte Sonderpfade und nur fuer Entwicklerrollen freizugeben.

- Sie duerfen nicht als allgemeiner Standard-Editor fuer Endanwender ausgerollt werden.

### 2.12 Guardrails fuer Prefix-Multi-Table Dropdown-Views (verbindlich)
**Regel:** Prefix-basierte Multi-Table-Dropdowns duerfen nur unter klaren technischen Guardrails betrieben werden.

Pflicht-Guardrails:
- Prefix-Whitelist
- Max-Result Limit
- Timeout-Grenze
- Caching-Strategie
- Nachvollziehbares Logging

### 2.13 Einheitliche Gruppen und Labels
**Regel:** Gruppen- und Feldnamen sind egalisiert.

Gruppen (Ausnahme: sys_layout):
- `ROOT`
- `SYSTEM`
- `>TABELLE<` (Grossbuchstaben)
- `GRUND` (nur sys_menudaten)
- `VERTIKAL` (nur sys_menudaten)
- `>SPRACHKENNUNG<` (Grossbuchstaben)
- `DATAS` (sys_ext_table, msy_ext_table)
- `CONFIG`
- `>GUID<` (msy_systemsteuerung, msy_anwendungsdaten)

Label-Regel:
- Bei GUID-keyed Listen/Auswahlen ist `label` Pflicht.
- Nur wenn `label` fehlt, darf die GUID als Kurzform (8 Zeichen) angezeigt werden.

Templates:
- `element_list` Templates liegen unter UID `5555...` in Gruppe `ELEMENTS`.

### 2.14 Einheitlicher InputControl-Contract (edit_user + pdvm_edit)
**Regel:** `edit_user` und `pdvm_edit` nutzen denselben `PdvmInputControl`-Contract und dieselbe Control-Resolution (Laufzeitvertrag in 1.10c/1.10d).

- Control-Metadaten kommen aus `sys_control_dict` (inkl. Template `5555...`) fuer **beide** Edit-Typen.
- Es gibt keine separaten Sonderpfade fuer Expert-Mode/Control-Debug pro Edit-Typ.
- Es gibt keine Fallback-Renderer oder Edit-Type-spezifische Ersatz-Payloads fuer Control-Infos.
- Unterschiedlich bleibt nur die Feldquelle (z. B. Frame-Definition), nicht die InputControl-Logik.

Verbindliche Ableitung fuer Dialog-Editoren:
- `pdvm_edit` ist das zentrale Edit-Frame mit kompletter Control-Steuerung.
- `edit_user` ist technisch ein `pdvm_edit`-Ablauf plus User-spezifische Add-ons. Die Passwort-/Account-Aktionen und -Anzeigen sind seit 2026-11-15 keine Add-ons im Code mehr, sondern Frame-Controls vom Typ `action`/`info` (2.17).
- `edit_frame` wird nicht mehr verwendet; bestehende Einsaetze sind auf `pdvm_edit` umzustellen.

Erweiterung `multi_dropdown` (verbindlich):
- Auswahl erfolgt generisch im `PdvmInputControl` ueber einen einheitlichen Add/Remove-Mechanismus.
- Mehrfachauswahlen muessen sichtbar als einzelne ausgewaehlte Eintraege dargestellt werden; Eintraege koennen einzeln hinzugefuegt und entfernt werden.
- Keine edit_type-spezifischen Multi-Select-Implementierungen.

### 2.15 Frame-gesteuerte Eingabe (InputControls-First, verbindlich)
**Regel:** Eingaben erfolgen ausschließlich über `PdvmInputControl`; welche Controls eine Maske zeigt, steht im Frame (`sys_framedaten`), nicht im Komponentencode. Spezifikation: `docs/specs/PDVM_FRAME_INPUT_RENDERING_SPEC_V1.md`.

- ✅ **PFLICHT:** Properties eines Feldes (Typ, Label, Konfiguration, Standardwert, `READ_ONLY`) liegen im `sys_control_dict` (1.10, 1.10a); der Frame liefert nur Layout und Kontextbindung (1.10b).
- ✅ **PFLICHT:** Die Anzeige erfolgt über die Frame-UID. Frame und Controls werden als ein Runtime-Modell geladen (`GET /api/frames/{uid}/runtime` oder Dialog-API); Lesen und Schreiben folgen 1.10d.
- ✅ **PFLICHT:** Ein Feld aus einer Maske zu entfernen oder hinzuzufügen ist eine Datenänderung am Frame, keine Codeänderung.
- ✅ **PFLICHT:** Passwörter, Tokens und Schlüssel stehen nie in Datensätzen, Vorlagen (555/666) oder Frames, sondern im Credential-Store; im Datensatz steht nur der Verweis (`CREDENTIAL`). Das Backend lehnt solche Felder beim Speichern ab. Geändert werden sie über den write-only Control-Typ `password` (Speicher: verschlüsselt in `asy_credentials`, Schlüssel `PDVM_SECRET_KEY` in der `.env`; Spec Abschnitt 9). Das Passwort wird nie angezeigt, zurückgegeben oder geloggt.
- ✅ **PFLICHT:** Pflichtfelder prüft das Backend und liefert Fehler mit Zielpfad (`group`, `field`, `message`); der Renderer markiert das Feld.
- ✅ **PFLICHT:** Nach der Anlage unveränderliche Felder sind im Control als `IMMUTABLE=true` gekennzeichnet (Muttercontrol, 1.10a). Der Host liefert den Modus (`create`/`edit`), der Renderer setzt im Modus `edit` readOnly, und der zentrale Schreibpfad lehnt Änderungen ab (Set-Once). Ein Frame für beide Aufgaben genügt. Optional macht `IMMUTABLE_AFTER=GRUPPE.FELD` die Sperre bedingt: das Feld bleibt änderbar, bis das Bedingungsfeld im gespeicherten Satz gefüllt ist (Mandanten-Verbindungsfelder bis `ROOT.DB_CREATED_AT`, also bis die Datenbank eingerichtet ist). Die Bedingung prüfen Renderer und Schreibpfad gleich.
- ✅ **PFLICHT:** Jede Frame-Auslieferung läuft durch die zentrale Zugriffsprüfung (`frame_runtime_service.ensure_frame_access`); Security außerhalb der Menüpunkte wird dort ergänzt.
- ✅ **PFLICHT:** Die Anmeldemasken (Anmeldung, Passwort vergessen, Passwort ändern) sind Frames mit `FRAME_TYPE = "public_form"` und werden ohne Token über `GET /api/public/login-frames` geliefert (feste UID-Allowlist, feste Typmenge `string`/`password_input`, keine Aktionen, Dropdowns oder Tabellenbezüge, Begrenzung je IP; `public_frame_service`). Der Typ `password_input` ist nur in solchen Frames erlaubt; das Passwort steht nur im Formularzustand bis zum Absenden. `Login.tsx` hat einen Notfall-Rückfall (eingebaute Felder), damit ein beschädigter Frame niemanden aussperrt. Weitere öffentliche Frames brauchen eine eigene Freigabe.
- ✅ **PFLICHT (Anmeldung):** Fehlermeldungen von Anmeldung und „Passwort vergessen“ verraten nicht, ob ein Konto existiert (einheitliche Antwort, Begrenzung je IP); ein Token mit ausstehendem Passwortwechsel (Claim `pwc`) erlaubt nur `/auth/password-change` und `/auth/logout`.
- ✅ **PFLICHT (Performance):** Frame und Controls in einer Antwort (Bulk), serverseitiger Cache mit Invalidierung bei Schreibzugriffen, clientseitiges Caching der Runtime, kein Request je Feld, gemeinsame Pools (`PoolRegistry`).
- ✅ **PFLICHT:** Nicht darstellbare Typen oder fehlende Controls erzeugen einen qualifizierten Fehler am Feld, keinen stillen Fallback.
- ❌ **VERBOTEN:** Neue Masken mit eigenen `<input>`/`<select>`/`<textarea>` für Fachdaten, Feldlisten im Komponentencode oder eigener Typ→Markup-Zuordnung.
- Buttons und Zusatzangaben in Frames sind in 2.17 geregelt (Typen `action` und `info`). Bestehende Masken werden nach der Umstellungsliste in der Spezifikation (Abschnitt 6) migriert.

### 2.17 Frame-Aktionen und Hinweise (verbindlich)
**Regel:** Schaltflaechen (Aktionen) und Statusanzeigen (Hinweise) in Masken sind Controls (`action`, `info`) im `sys_control_dict` und werden ueber den Frame platziert (2.15). Das Control verweist nur auf eine **Aktions-ID**; was die Aktion tut und wer sie ausfuehren darf, steht ausschliesslich im Backend-Register `backend/app/core/frame_action_service.py`. Spezifikation: `docs/specs/PDVM_FRAME_ACTIONS_SPEC_V1.md`.

- ✅ **PFLICHT:** Neue Aktionen werden im Register angelegt (ID, Tabellen mit Rollen, Handler, Parameter, optional Zustand) und im Control nur per `CONFIGS.action.id` referenziert. Der Handler ruft vorhandene Services; geschrieben wird ueber den zentralen Gateway (1.1).
- ✅ **PFLICHT:** Ausgefuehrt wird ueber `POST /api/frame-actions/{id}/run`; die zentrale Pruefung (bekannte ID, Tabelle, Rolle der Sitzung, UID, Parameter, Vorbedingung wie Mandantenbezug) liegt in `frame_action_service.run_action`. Rechte und Zustaende fuer einen Satz liefert gebuendelt `POST /api/frame-actions/state` (die Frame-Runtime ist nicht benutzerbezogen gecacht).
- ✅ **PFLICHT:** Nicht erlaubte Aktionen werden ausgeblendet (`when_denied` kann auf `disable` stehen). Bei ungespeicherten Aenderungen erscheint vor der Ausfuehrung ein Hinweis mit Abbruchmoeglichkeit.
- ✅ **PFLICHT:** Texte (Label, Tooltip, Bestaetigung, Parameter, Hinweistext) stehen im Control, feste Renderertexte in `frontend/src/i18n/uiTexts.ts`; Handler liefern `message_key` plus Klartext (spaeteres Woerterbuch, Rendering-Spec Abschnitt 7, Nr. 8).
- ❌ **VERBOTEN:** Endpunkte, Funktionen oder Skripte in Control- oder Framedaten; Schaltflaechen mit Fachlogik oder Tabellennamen im Komponentencode; Aktionsendpunkte ausserhalb des Registers ohne Rollenpruefung.
- ✅ **PFLICHT:** Aktionen, die der Dialog selbst ausfuehrt (z. B. Workflow-Draft-Builder, `executor = "host"`, IDs `workflow.*`), stehen ebenfalls im Register; es liefert nur Rechte und Sichtbarkeit, `run` lehnt sie ab. Die Controls tragen die ID explizit; eine Zuordnung per Textsuche im Label ist verboten. Endpunkte, die solche Aktionen ausloesen, pruefen die Rolle selbst.
- ✅ **PFLICHT:** Mandanten anlegen (`/api/mandanten/template|create`) und die Datenbank aufbauen (Aktion `mandant.setup`) darf nur `superadmin`; der Live-Commit eines Workflow-Entwurfs (`commit-live`, `dry_run=false`) nur Admin. Der generische Dialog legt keine Mandanten an („Neuer Satz“ ausgeblendet über `meta.create_blocked_reason`, Backend 403); der Anleger erhält den Mandanten in `MANDANTEN.LIST`. Die Mandantenwahl (`/api/mandanten/select`) und die Listen-Endpunkte richten sich nach `MANDANTEN.LIST` des Benutzers (`mandant_access`).
- Offen: `PdvmFrameForm` stellt `action`/`info` nicht dar (zurueckgestellt).

### 2.16 Dropdown-Quellen (verbindlich, Entwurf 2026-11-14)
**Regel:** Die Optionen jedes Dropdowns stehen ausschließlich in `sys_dropdowndaten` (Datensatz mit `ROOT` und `OPTIONS.<Schlüssel>.<Sprache>`); das Control verweist per `CONFIGS.dropdown.key` (UID) und `CONFIGS.dropdown.table = sys_dropdowndaten` darauf. Spezifikation: `docs/specs/PDVM_FRAME_INPUT_RENDERING_SPEC_V1.md`, Abschnitt 11.

- ✅ **PFLICHT:** Neue Dropdowns (`dropdown`, `multi_dropdown`) werden als Datensatz in `sys_dropdowndaten` angelegt und per Seed-Tool ausgeliefert (Muster: `seed_mandant_language_v1.py`).
- ✅ **PFLICHT:** Der Frame-Runtime-Service liefert die Optionen mit (`fields[].options`, Sprache über `?language=`, sonst `DEFAULT_LANGUAGE` der I18N-Policy). Das funktioniert auch ohne Session, weil nur die System-DB gelesen wird. Sprachauswahlen zeigen jede Sprache in ihrer Eigenbezeichnung (`CONFIGS.dropdown.label_language = "own"`).
- ❌ **VERBOTEN:** Optionslisten im Komponentencode, in Frame- oder Controldaten oder in Fachtabellen für neue Dropdowns.
- Offen: Die generelle Umstellung bestehender Dropdowns (andere Quellen, feste Listen im Code) steht in der Aufgabenliste (Spec Abschnitt 7).

---

## 3. Legacy Code
Code, der als `DEPRECATED` markiert ist (im gesamten Backend und Frontend), darf nicht für neue Features verwendet werden. Bei Berührung mit solchem Code ist Refactoring (Anpassung an neue Regeln) vorzuziehen.

---

## 4. Spezifikations-Konformität (Domain Specs)

Bei der Implementierung von Kern-Funktionalitäten ist die Einhaltung der dedizierten Spezifikationen verpflichtend. Diese Dokumente sind die "Single Source of Truth" für das jeweilige Subsystem.

### 4.1 PDVM DateTime (`docs/specs/PDVM_DATETIME_SPEC.md`)
**Regel:** Keine native `datetime`-Nutzung für Business-Logik.
*   Das System verwendet eine **3-Ebenen-Matrix** für zeitbezogene Werte (Original, AB-Datum, Formatierung).
*   Alle Zeitstempel müssen als `float` (PDVM-Format) gespeichert und verarbeitet werden.
*   Jedes Widget, das Zeitdaten darstellt oder manipuliert (z.B. `PdvmDateTimePicker`), muss diese Spezifikation implementieren.
*   Verbindliches Zeitformat: `YYYYDDD.FRACTION` mit Bruchteil des Tages.
*   Normative Referenz fuer Konvertierung und Formatlogik ist `backend/app/core/pdvm_datetime.py`.
*   Technische Weiterentwicklungen werden gesammelt in: `docs/specs/PDVM_DATETIME_FUNCTION_COLLECTION.md`.

### 4.2 Theming System V2 (`docs/specs/THEMING_SYSTEM.md`)
**Regel:** Keine hardcodierten Farben oder Styles in CSS/Komponenten.
*   Styling erfolgt ausschließlich über **Style Blocks** (z.B. `block_header_std`, `block_input_std`).
*   Verwendung von `--block-*` CSS-Variablen ist Pflicht für konfigurierbare Komponenten.
*   Die Fallback-Kette (Block -> Variable -> Default) muss eingehalten werden.
*   Das aktive Theme wird serverseitig aus Paket, Mandanten- und Benutzer-Overlay aufgelöst (`GET /api/layout/resolved`, Details in `THEMING_SYSTEM.md` Abschnitt 6); das Token-Schema liegt in `backend/app/core/theme_schema.py`.
*   Farbliterale (`#hex`, `rgb()`, `hsl()`, benannte Farben) stehen nur in `frontend/src/styles/base/variables.css`; `backend/test_frontend_theme_guard.py` erzwingt das (Ausnahme nur mit Zeilenmarker `guard-allow-color`).
*   Neue `--block-*`-Variablen müssen im Token-Schema existieren; neue Strukturvarianten brauchen Katalogeintrag (`layout_schema.py`) und CSS (`styles/layouts/variants.css`).
*   Schreibzugriffe auf Overlays und Theme-Einstellungen laufen über `central_write_service` (Rolle `overlay`, Router ohne SQL, Regel 1.1); Overlays und Einstellungen werden strikt validiert.
*   Kontrast: Pflichtpaare unter WCAG AA (4,5:1) dürfen nicht gespeichert werden (`theme_service.contrast_errors`); neue Pakete mit `backend/tools/fix_theme_contrast_v1.py` prüfen (siehe `THEMING_SYSTEM.md` Abschnitt 9).

### 4.3 Menu System (`docs/specs/MENU_SYSTEM.md`)
**Regel:** Menü-Struktur folgt strikter Hierarchie und Berechtigung.
*   Dynamischer Aufbau basierend auf `sys_menudaten` und User-Rechten.
*   Trennung von Navigation (Sidebar) und App-Steuerung (Header).
*   Keine manuelle Manipulation der Menü-Struktur im Frontend Code.

### 4.4 Passwortverwaltung (`docs/specs/PASSWORD_MANAGEMENT_SPEC.md`)
**Regel:** Passwort-Reset, OTP und Account-Sperrung folgen der Spezifikation.
*   `SEND_EMAIL` Konfiguration liegt in `asy_mandanten`; das SMTP-Passwort steht nicht im Satz, sondern im Credential-Store (`SEND_EMAIL.CREDENTIAL`, Regel 2.15).
*   OTP-Logik und `PASSWORD_CHANGE_REQUIRED` werden strikt umgesetzt.

### 4.5 Lineares SOLL-Schema (`docs/specs/PDVM_LINEAR_SCHEMA_V1.md`)
**Regel:** Die Datenstrukturen fuer Dialog/View/Frame/Control folgen der verbindlichen SOLL-Definition.
*   `ROOT`/`CONTROL`/`TEMPLATES` werden strukturell einheitlich gefuehrt.
*   Property-Keys sind in der Zielsicht grossgeschrieben.
*   Neuanlage basiert auf den Template-Saetzen `555...` und `666...` (1.13).

---

## 5. Durchsetzung

Diese Tests prüfen Regeln automatisch; sie laufen aus `backend/` mit `..\.venv\Scripts\python.exe -m pytest`.

| Test | Regel |
|---|---|
| `backend/test_architecture_guard.py` | 1.1: Router ohne SQL und ohne asyncpg, keine Legacy-CRUD-Klasse, Schreiben nur über den Gateway |
| `backend/test_frontend_theme_guard.py` | 4.2: keine Farbliterale außerhalb von `variables.css` |
| `backend/test_frame_runtime.py` | 2.15: Runtime-Modell, Cache-Invalidierung, Vorlage und Neuanlage ohne Geheimnisse, SMTP über Credential-Store, Dropdown-Optionen (2.16), Aktions-Verweise (2.17) |
| `backend/test_frame_actions.py` | 2.17: Aktionsregister (Rolle, Tabelle, Parameter, UID, Mandantenbezug), Zustände, Host-Aktionen, `mandant.setup`, HTTP-Statuscodes |
| `backend/test_mandant_access.py` | 2.17: Mandanten-Endpunkte nur Superadmin, Mandantenwahl und Listen nach `MANDANTEN.LIST`, Anlegen (Satz vor Datenbank, Teilfehler), alte Setup-Endpunkte entfernt, Live-Commit nur Admin |
| `backend/test_menu_roles.py` | 2.2: Rollen an Menüeinträgen (Filter, Zweige, `superadmin`) |
| `backend/test_public_frames.py` | 2.15: öffentliche Login-Frames (Allowlist, Typmenge, Fehler, Cache-Header, Begrenzung) |
| `backend/test_auth_hardening.py` | 2.15: einheitliche Anmeldefehler, Sperre nur für den Kontoinhaber sichtbar, IP-Begrenzung, „Passwort vergessen“ immer gleich, Token mit `pwc` eingeschränkt |
| `backend/test_immutable_fields.py` | 2.15/1.10a: `IMMUTABLE` und `IMMUTABLE_AFTER` (Set-Once-Prüfung, bedingte Sperre, Durchsetzung im Schreibpfad, Weitergabe ins Runtime-Modell) |
| `backend/test_credential_service.py`, `backend/test_send_email_config.py` | 2.15: Zugangsdaten nur verschlüsselt (`asy_credentials`), `.env` hat Vorrang, SMTP-Konfiguration wird frisch gelesen |
| `backend/test_text_templates.py` | 1.24: Auswahl (aktiv → Mandant → System, nur freigegebene Sprachen), Freigabe-/Rollen-Guard, Platzhalter-Prüfung, Hash, Cache-Invalidierung, Session-Durchreichung im Dialog-Pfad |

Werkzeuge zur Prüfung der Daten: `backend/tools/audit_system_data.py` (Systemdaten gegen diese Regeln) und `backend/tools/seed_base_records.py --check` (Basissätze 000/555/666), siehe [backend/tools/README.md](./backend/tools/README.md).

# PDVM System Web - Architekturregeln

Dieses Dokument definiert die verbindlichen Architektur-Regeln für die Weiterentwicklung des PDVM Systems. Ziel ist die Stabilität und Wartbarkeit bei wachsender Komplexität.

## 1. Backend Architektur

### 1.1 Das "Central Database" Gesetz
**Regel:** Es gibt keinen direkten Datenbank-Zugriff in den API-Endpunkten (Routers).

*   ❌ **VERBOTEN:** SQL-Queries (`SELECT...`) oder direkter Zugriff auf JSON-Strukturen (`row['daten']['GRUND']`) im Router.
*   ✅ **PFLICHT:** Nutzung der Business-Logic Klasse `PdvmCentralDatabase`.

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

**Write-Pfad (verbindlich fuer neue/geaenderte Router-Pfade):**
- Alle Schreiboperationen (`create`, `update`, `delete`) laufen über den zentralen Gateway
	`app.core.central_write_service`.
- Direkte Aufrufe wie `await db.update(...)`, `await db.create(...)` oder `await db.delete(...)`
	im Router sind verboten.
- Actor-Kontext wird primär aus der GCS-Session ermittelt (`user_guid`, `actor_ip`);
	explizite Actor-Parameter sind nur als kontrollierter Override für Sonderfälle erlaubt.

Hinweis zur Migration:
- Bestehende Legacy-Router werden schrittweise umgestellt.
- Bei Änderungen an einem Legacy-Router ist die Umstellung auf den zentralen Write-Gateway Pflicht.

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

- Speicherung erfolgt **direkt über `PdvmDatabase`** (nicht in `daten` JSONB).
- Für `sys_benutzer` gelten Sonder-Spalten: `benutzer`, `passwort`.
- `USER.EMAIL` bleibt **JSONB** (Gruppe USER) und darf **nicht** als SYSTEM-Spalte behandelt werden.

### 1.6 Dialog LAST_CALL (vereinfachte Pflichtlogik)
**Regel:** `LAST_CALL` ist ausschließlich an **`view_guid + root_table`** gekoppelt.

**Vorgabe:**
1. `LAST_CALL` wird nur unter der Gruppe `view_guid` gespeichert.
2. Feldname ist `TABLE` (UPPERCASE), der Wert ist ein Objekt `{"LAST_CALL": <uid|null>}`.
3. Keine Fallbacks auf `frame_guid` oder `dialog_guid`.
4. Dialog-Start:
	- Für `view_guid + table` **muss** der Feld‑Key existieren.
	- Wenn keine Auswahl existiert: `{ "LAST_CALL": null }` (Key bleibt bestehen).
	- Vorhandene Auswahl → direkt Tab2 (Edit)
	- Keine Auswahl → Tab1 (View)
5. View-Auswahl aktualisiert `{ "LAST_CALL": <uid> }`.

**Implementierung (verbindlich):**
- Backend: [backend/app/api/dialogs.py](backend/app/api/dialogs.py) verwaltet `last_call` linear.
- Lesen: `group=view_guid`, `field=TABLE (UPPERCASE)` → `{"LAST_CALL": <uid|null>}`.
- Fehlt der Feld-Key, wird `{ "LAST_CALL": null }` erstellt und persistiert.
- Keine Fallbacks, keine Auto-Korrektur, keine zusätzliche Validierung.

**Begründung:**
Mehrere Dialoge können unterschiedliche Frames haben, aber dieselbe `view_guid + table` teilen.
Dann sollen alle Dialoge auf den zuletzt ausgewählten Datensatz springen.

### 1.7 Tabellen-Routing (zentral über PdvmDatabase)
**Regel:** Datenbank‑Routing erfolgt ausschließlich über `PdvmDatabase` anhand des Tabellennamens.

- Keine manuelle DB‑Auswahl in Callern.
- Sonderfälle (z.B. `sys_benutzer`) dürfen Zusatzfunktionen haben, müssen aber **primär**
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
- Ausnahme: systemeigene Spalten wie `created_at`/`modified_at` bleiben SQL-Timestamps.

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
- `CONTROL.FIELD`/`CONTROL.FELD` sind verpflichtend in GROSSBUCHSTABEN.
- `name`/`SELF_NAME` folgen immer `<TABELLENPREFIX>_<FIELD>` in GROSSBUCHSTABEN (z. B. `SYS_LABEL`).
- Neuanlage erfolgt ausschliesslich ueber den regulären Neuanlage-Flow (keine Template-Direktkopien als Fachdaten).

### 1.10a Muttercontrol-Regel fuer `sys_control_dict` (starr)
**Regel:** `sys_control_dict` mit UID `66666666-6666-6666-6666-666666666666` ist das verbindliche Muttercontrol unter `daten.CONTROL`.

- `daten.CONTROL` des 666-Satzes ist die einzige kanonische Quelle fuer erlaubte Control-Eigenschaften.
- Eigenschaftsvergleiche fuer Freigabe/Validierung erfolgen **case-insensitive**.
- Die kanonische Schreibweise im Muttercontrol ist **GROSSBUCHSTABEN**.
- Eigenschaften, die in `sys_framedaten` (`daten.FIELDS.*`) oder `sys_viewdaten` (`daten.SYSTEM.*`) genutzt werden, duerfen nur dann als Control-Eigenschaft gelten, wenn sie im Muttercontrol aufgenommen und freigegeben wurden.
- Neue Eigenschaften werden zuerst im Muttercontrol dokumentiert und erst danach in Runtime-/Migrationslogik verwendet.
- Erweiterungen in `CONTROL.CONFIGS` folgen demselben Freigabeprozess (keine stillen Ad-hoc-Keys in Produktionsdaten).

### 1.10b Frame-Layout-Override auf FIELDS (TAB/DISPLAY_ORDER)
**Regel:** In `sys_framedaten.daten.FIELDS` bleibt `sys_control_dict` die fachliche Quelle fuer Controls; reine Layout-Attribute duerfen pro Frame uebersteuert werden.

- ✅ **PFLICHT:** Control-Semantik (`TYPE`, `LABEL`, `GRUPPE`, `FELD`, `CONFIGS`, usw.) kommt aus `sys_control_dict`.
- ✅ **PFLICHT:** Frame darf Layout-Parameter je Feld setzen, insbesondere `TAB` und `DISPLAY_ORDER` (sowie `SOURCE_PATH` wenn benoetigt).
- ✅ **PFLICHT:** Runtime-Merge muss diese Layout-Parameter erhalten, damit mehrtabbige Frames stabil gerendert werden.
- ❌ **VERBOTEN:** Unbekannte freie Zusatz-Properties in `FIELDS.*` als fachliche Overrides zu akzeptieren.

Begruendung:
- Frames brauchen eine eigene visuelle Ordnung, ohne die zentrale Control-Definition zu duplizieren.
- Ohne erlaubtes `TAB`-Override landen Felder implizit in Tab 1 und die Frame-Darstellung wird inkonsistent.

### 1.11 Schutz von Basis-/Template-GUIDs (maschinenfest)
**Regel:** Reservierte Basis-/Template-Datensaetze duerfen durch Migrationen nicht geaendert werden.

- Gilt insbesondere fuer GUID-Serien mit den Praefixen `5...`, `6...` und `0...` (z. B. `5555...`, `6666...`, `0000...`).
- Diese Saetze bilden die tabellenweiten Basiseinstellungen und werden manuell gepflegt.
- Migrationsskripte fuer `sys_control_dict` muessen diese GUIDs explizit vom Update ausschliessen.
- Automatische Umbenennung/Normalisierung dieser reservierten Saetze ist verboten.

### 1.12 Verbindliche Tabellen-Basissaetze 000/555/666
**Regel:** Jede fachliche PDVM-Tabelle hat drei fixe reservierte UIDs mit klarer Bedeutung.

- `00000000-0000-0000-0000-000000000000`
	Enthält Tabellen-Metadaten (informativ, keine feste fachliche Payloadstruktur).
- `55555555-5555-5555-5555-555555555555`
	Enthält Templates der Tabelle in den Gruppen `ROOT` und `TEMPLATES`.
- `66666666-6666-6666-6666-666666666666`
	Enthält den Basissatz fuer Neuanlagen.

Pflicht:
- Diese drei UIDs sind reserviert und dürfen nicht als normale Fachdaten verwendet werden.
- Seeder/Migrationen müssen Existenz und Struktur dieser Basissätze prüfen.

### 1.12a 666 Template-Gruppenregel (TEMPLATES)
**Regel:** Template-Definitionen im 666-Satz liegen unter der Gruppe `TEMPLATES`.

Verbindliche Struktur:
- `daten.ROOT` enthaelt den Basissatz fuer Neuanlagen.
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

### 1.14 UID-, LINK_UID- und ROOT-SYSTEM-Felder
**Regel:** `uid` bleibt der technische Primärschlüssel; `link_uid` bildet die fachliche Datensatz-Linie.

Pflicht:
- `uid` ist immer eindeutig pro Zeile (Primary Key) und darf sich nie ändern.
- `link_uid` ist für neue Datensätze zu setzen; Standardfall: `link_uid = uid`.
- Bei historisierten Folgezeilen oder Feld-Audits zeigt `link_uid` auf den fachlichen Ursprungssatz.
- Systemspalten werden in `daten.ROOT` gespiegelt:
	- `ROOT.SELF_LINK_UID`
	- `ROOT.SELF_CREATED_AT`
	- `ROOT.SELF_MODIFIED_AT`
	- `ROOT.SELF_GILT_BIS`

Zeitformat-Regel (verbindlich):
- SQL-Spalten `created_at`, `modified_at`, `gilt_bis` bleiben native PostgreSQL `TIMESTAMP`.
- In `daten` werden Datums-/Zeitwerte im PDVM-Format gespeichert (z. B. `YYYYDDD.00000`).
- Damit sind `ROOT.SELF_CREATED_AT`, `ROOT.SELF_MODIFIED_AT`, `ROOT.SELF_GILT_BIS` im `daten`-JSON immer PDVM-formatiert.

UID-/LINK_UID-Regel (verbindlich):
- `uid` ist in allen Tabellen eine reine technische Row-ID (keine fachliche Verlinkungsbedeutung).
- Fachliche Identität und exakte Adressierung laufen über `link_uid`.
- Für GCS gilt speziell:
	- `sys_systemsteuerung` wird über `link_uid = user_guid` gelesen/geschrieben.
	- `sys_anwendungsdaten` wird über `link_uid = mandant_guid` gelesen/geschrieben.
- Bei Migrationen dürfen für diese Tabellen neue `uid`-Werte vergeben werden; `link_uid` bleibt stabil.

- Ausnahmen müssen explizit dokumentiert werden und dürfen die obige GCS-Link-UID-Regel nicht verletzen.

### 1.15 Semantik historisch und gilt_bis (verbindlich)
**Regel:** `historisch` und `gilt_bis` haben unterschiedliche, nicht austauschbare Bedeutung.

Verbindliche Definition:
- `historisch` kennzeichnet, ob Daten/Felder historisch gefuehrt werden (0 = nein, 1 = ja).
- `historisch` ist **nicht** die zentrale Steuerung fuer Archivierung oder Loeschung im operativen Laufzeitmodell.

Verbindliche Archivierungs-/Loeschregel:
- Archivierungen und Loeschungen laufen ueber `gilt_bis`.
- Ein aktiver Datensatz hat den Defaultwert fuer `gilt_bis` (z. B. 1001 bzw. tabellenspezifischer Default).
- Das Beenden/Archivieren eines Datensatzes erfolgt durch Setzen eines passenden `gilt_bis`-Zeitpunkts.

Konsequenz fuer neue Tabellen/Tools:
- Monitoring-, Batch- und Job-Tabellen duerfen fuer Aufbewahrung/Abschluss nicht auf `historisch` umdeuten.
- Wenn ein Lebenszyklus benoetigt wird, ist dieser ueber `gilt_bis` (und optional ROOT-Statusfelder) abzubilden.

### 1.16 I18N Default- und Supported-Languages (verbindlich)
**Regel:** DEFAULT_LANGUAGE und SUPPORTED_LANGUAGES werden zentral ueber die I18N-Policy definiert.

Verbindliche Quelle:
- `backend/config/i18n_policy_v1.json`

Verbindliche V1-Werte:
- `DEFAULT_LANGUAGE = DE-DE`
- `SUPPORTED_LANGUAGES = [DE-DE, EN-US, IT-IT]`

Verbindliche Umsetzung:
- Sprach-Normalisierung erfolgt zentral in `backend/app/core/i18n_policy.py`.
- Services mit Sprachauflösung (z. B. Dropdown/Systemdaten) muessen diese Normalisierung verwenden.
- Historische/abweichende Codes (z. B. `US-EN`, `DEU`) werden per Alias auf kanonische Codes abgebildet.

### 1.17 I18N Pflicht-Uebersetzungsumfang je Inhaltstyp (verbindlich)
**Regel:** Der Pflichtumfang je Inhaltstyp wird zentral als Matrix gepflegt und fuer Qualitaetschecks verwendet.

Verbindliche Quelle:
- `backend/config/i18n_required_translation_scope_v1.json`

V1-Pflichtmatrix:
- `dropdown`: required `DE-DE`, `EN-US`; optional `IT-IT`
- `label`: required `DE-DE`, `EN-US`; optional `IT-IT`
- `hilfe`: required `DE-DE`; optional `EN-US`, `IT-IT`
- `text`: required `DE-DE`; optional `EN-US`, `IT-IT`

Verbindliche Umsetzung:
- Validierungs- und Reporting-Tools muessen diese Matrix verwenden.
- Alias- und Sprach-Normalisierung erfolgt ueber die zentrale I18N-Policy.
- Neue Inhalte duerfen nicht als produktionsreif gelten, wenn required-Sprachen fuer den jeweiligen Inhaltstyp fehlen.

### 1.18 I18N Uebersetzungsmodus je Tabelle (verbindlich)
**Regel:** Jede betroffene infos-Tabelle hat einen verbindlichen Uebersetzungsmodus inklusive Review-Regel.

Verbindliche Quelle:
- `backend/config/i18n_translation_mode_per_table_v1.json`

V1-Entscheidung:
- `sys_dropdowndaten` -> `MANUAL`
- `sys_beschreibungen` -> `MACHINE_ASSISTED`

Verbindliche Review-Pflicht:
- Unabhaengig vom Modus ist vor produktiver Nutzung eine fachliche Freigabe erforderlich.
- Bei `MACHINE_ASSISTED` sind maschinelle Vorbelegungen ohne Freigabe nicht produktiv gueltig.

Verbindliche Nachweisfuehrung:
- Validierungs-/Reporting-Tools muessen Modus, Review-Regel und Entscheidungs-Lock je In-Scope-Tabelle ausweisen.
- Offene Entscheidungen (`decision_locked = false`) sind fuer produktive Freigaben nicht zulaessig.

### 1.19 I18N Freigabemodell je Sprache (verbindlich)
**Regel:** Sprachbezogene Inhalte verwenden ein einheitliches Freigabemodell fuer produktive Nutzung.

Verbindliche Quelle:
- `backend/config/i18n_language_release_model_v1.json`

Pflichtfelder je Spracheintrag:
- `version`
- `status`
- `approved_by`
- `approved_at`

Verbindliche Statuswerte:
- `new`
- `machine`
- `review`
- `approved`

Produktivregel:
- Nur `status=approved` gilt als produktiv freigegeben.
- Bei `approved` sind `approved_by` (nicht leer) und `approved_at` (ISO8601) verpflichtend.

Versionsregel:
- `version` ist Pflichtfeld und muss dem Pattern `^v[0-9]+\.[0-9]+\.[0-9]+$` entsprechen.

Governance:
- Das Modell ist verbindlich definiert; fehlende Laufzeit-Metadaten im Bestand sind als Migrations-/Einfuehrungsaufgabe zu behandeln.

### 1.20 Mandanten-DB Updates: Updatearten und Versionierungsachsen (verbindlich)
**Regel:** Wiederkehrende Datenbank-Migrationen werden mandantenbezogen ueber ein standardisiertes Updateverfahren gefahren.

Verbindliche Spezifikation:
- `docs/specs/PDVM_MANDANT_DB_UPDATE_VERSIONIERUNG_SPEC_V1.md`

Verbindliche Updatearten:
- `SOURCE_UPDATE` (Quellstand/Release-Kontext)
- `DATABASE_UPDATE` (Schema/Struktur)
- `DATA_UPDATE` (Inhaltsmigration)

Verbindliche Versionsachsen je Mandant:
- `SOURCE_VERSION`
- `DB_SCHEMA_VERSION`
- `DATA_MODEL_VERSION`

Scope-Regel V1:
- Wiederkehrende Update-Ziele sind Mandanten-DBs.
- AUTH-DB und SYSTEM-DB gelten in diesem Zyklus als initial bereitgestellt und nicht als regulaere Update-Pipeline.

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

### 2.5 Dialog View/Edit Autonomie
**Regel:** View- und Edit-Tab sind **autonom** und dürfen **nicht** voneinander abhängig sein.

- **Neuanlage** ist eine **Dialog-/Tabellenfunktion**, nicht Edit-Type abhängig.
- „Neuer Satz“ gehört in den **View-Tab** (Anzeige der Tabelle), **nicht** in den Edit-Tab.
- Der Edit-Tab zeigt **nur** Speichern/Änderungen (keine Neuanlage).
- Der neue Datensatz wird ueber den zentralen linearen Algorithmus erstellt (555-Basis + Auffuellen aus 666 TEMPLATE/TEMPLATES), danach in der View sichtbar.
- View/Tabellenanzeige und Edit-Formular bleiben unabhängig (keine Vermischung von Zuständigkeiten).

### 2.5a Linearer Draft-Flow bei Neuanlage
**Regel:** "Neuer Satz" läuft generisch und linear über Drafts.

- `Neuer Satz` startet mit `POST /api/dialogs/{dialog_guid}/draft/start`.
- Edit arbeitet auf Draft-Daten; Backend liefert Validierungsfehler mit Zielpfad (`group`, `field`).
- Persistenz erfolgt erst bei `POST /api/dialogs/{dialog_guid}/draft/{draft_id}/commit`.
- Kein erzwungener Sonderpfad mit `428` als Steuermechanismus für Standard-Neuanlage.
- Gilt tabellenübergreifend (nicht nur `sys_control_dict`).

Verbindlich (einziger Ablauf):
- Der einzige fachlich zulässige Neuanlage-Flow ist:
	`POST /api/dialogs/{dialog_guid}/draft/start` → Edit auf Draft → `POST /api/dialogs/{dialog_guid}/draft/{draft_id}/commit`.
- Direkte Neuanlage über `POST /api/dialogs/{dialog_guid}/record` ist nur Kompatibilität und muss intern denselben Ablauf nutzen.
- Neue Features dürfen keinen zweiten Neuanlage-Mechanismus einführen.
- Bestehende direkte Neuanlage-Aufrufe im Source sind auf den Draft-Flow umzustellen.

### 2.6 Einheitlicher Edit-Frame (Dialoge)
**Regel:** Alle Editoren verwenden denselben Edit-Rahmen.

- Kopfbereich (Header + Edit-Tabs) ist fix.
- Nur der Editor-Inhalt scrollt.
- Edit-Typen liefern Inhalte, nicht das Layout.
- Keine individuellen Scroll-Container pro Editor.

Siehe Spezifikation: `docs/specs/PDVM_DIALOG_EDIT_FRAME_SPEC.md`.

### 2.7 Dialog V2 (egalisiert)
**Regel:** Dialoge nutzen ein einheitliches Datenmodell in `sys_dialogdaten`.

### 2.8 Dialog/View/Frame Refaktoring (Entwicklungsphase)
**Regel:** Die laufende Refaktorisierung von Dialogen, Views und Frames erfolgt in der Entwicklungsphase ohne zusaetzliche DB-Versionierungsachse fuer diesen Teilbereich.

Verbindliche Arbeitsgrundlage:
- `docs/specs/PDVM_DIALOG_VIEW_FRAME_REFAKTORING_ENTWICKLUNGSPHASE.md`

Verbindlicher Fokus:
- Normalisierung von `sys_dialogdaten`, `sys_viewdaten`, `sys_framedaten`, `sys_control_dict`
- klare Trennung `DIALOG_TYPE=edit` vs `DIALOG_TYPE=work`
- InputControls-First mit dokumentierten Ausnahmen
- Analyse von Schwachstellen, Architektur-Differenzen und Entscheidungsbedarf vor finaler Verhaertung

### 2.9 Single-Tab Dialogdarstellung (verbindlich)
**Regel:** Wenn in `sys_dialogdaten` effektiv genau ein Tab konfiguriert ist, wird kein Tab-Header gerendert.

- Diese Regel gilt global fuer alle Dialogtypen.
- Die interne Tab-Logik bleibt erhalten; nur die visuelle Tab-Navigation wird ausgeblendet.

### 2.10 Workflow-Endtab (verbindlich)
**Regel:** Bei `DIALOG_TYPE=work` muss der letzte Tab `MODULE=acti` besitzen.

- Ohne `acti`-Endtab ist die Dialogkonfiguration ungueltig.
- Validierungs- und Analyse-Tools muessen diese Regel explizit pruefen.

### 2.11 JSON/Edit Sonderpfade und Menue-Security (verbindlich)
**Regel:** `show_json` und `edit_json` sind dokumentierte Uebergangs-Sonderpfade.

- Mit Einfuehrung der Menue-Security sind diese Pfade nur fuer Entwicklerrollen freizugeben.
- Bis zur Security-Einfuehrung duerfen diese Pfade nicht als allgemeiner Standard-Editor fuer Endanwender ausgerollt werden.

### 2.12 Guardrails fuer Prefix-Multi-Table Dropdown-Views (verbindlich)
**Regel:** Prefix-basierte Multi-Table-Dropdowns duerfen nur unter klaren technischen Guardrails betrieben werden.

Pflicht-Guardrails:
- Prefix-Whitelist
- Max-Result Limit
- Timeout-Grenze
- Caching-Strategie
- Nachvollziehbares Logging

- `DIALOG_TYPE`: `norm`, `work`, `acti`.
- Tabs definieren Module (`view`, `edit`, `acti`) mit `GUID` pro Tab.
- `VIEW_GUID`/`FRAME_GUID` in `ROOT` sind optional (legacy); die GUIs kommen aus den Tab-Definitionen.
- Aufruf erfolgt immer ueber `go_pdvm_dialog` (dialog_guid + optional dialog_table fuer `show_json`/`edit_json`).
- `pdvm_edit` ist der Standard-Edit-Typ (Frame-gesteuert). `edit_json`/`show_json` bleiben erhalten.
- `show_json` ist ein Edit-Typ und benoetigt immer einen Edit-Tab.
- `dialog_table` ueberschreibt die Tabelle der View-Definition bei `show_json`/`edit_json` (View-State, Matrix, Dialog-CRUD).

Siehe Spezifikation: `docs/specs/PDVM_DIALOG_EDIT_FRAME_SPEC.md`.

### 2.8 Einheitliche Gruppen und Labels
**Regel:** Gruppen- und Feldnamen sind egalisiert.

Gruppen (Ausnahme: sys_layout):
- `ROOT`
- `SYSTEM`
- `>TABELLE<` (Grossbuchstaben)
- `GRUND` (nur sys_menudaten)
- `VERTIKAL` (nur sys_menudaten)
- `>SPRACHKENNUNG<` (Grossbuchstaben)
- `DATAS` (sys_ext_table, sys_ext_table_man)
- `CONFIG`
- `>GUID<` (sys_systemsteuerung, sys_anwendungsdaten)

Label-Regel:
- Bei GUID-keyed Listen/Auswahlen ist `label` Pflicht.
- Nur wenn `label` fehlt, darf die GUID als Kurzform (8 Zeichen) angezeigt werden.

Templates:
- `element_list` Templates liegen unter UID `5555...` in Gruppe `ELEMENTS`.

### 2.9 Einheitlicher InputControl-Contract (edit_user + pdvm_edit)
**Regel:** `edit_user` und `pdvm_edit` nutzen denselben `PdvmInputControl`-Contract und dieselbe Control-Resolution.

- Control-Metadaten kommen aus `sys_control_dict` (inkl. Template `5555...`) fuer **beide** Edit-Typen.
- Es gibt keine separaten Sonderpfade fuer Expert-Mode/Control-Debug pro Edit-Typ.
- Es gibt keine Fallback-Renderer oder Edit-Type-spezifische Ersatz-Payloads fuer Control-Infos.
- Unterschiedlich bleibt nur die Feldquelle (z. B. Frame-Definition), nicht die InputControl-Logik.

Verbindliche Ableitung fuer Dialog-Editoren:
- `pdvm_edit` ist das zentrale Edit-Frame mit kompletter Control-Steuerung.
- `edit_user` ist technisch ein `pdvm_edit`-Ablauf plus User-spezifische Add-ons (z. B. Passwort/Account-Aktionen).
- `edit_frame` wird nicht mehr verwendet; bestehende Einsaetze sind auf `pdvm_edit` umzustellen.

Erweiterung `multi_dropdown` (verbindlich):
- Auswahl erfolgt generisch im `PdvmInputControl` ueber einen einheitlichen Add/Remove-Mechanismus.
- Mehrfachauswahlen muessen sichtbar als einzelne ausgewaehlte Eintraege dargestellt werden.
- Eintraege koennen einzeln hinzugefuegt und einzeln entfernt werden.
- Keine edit_type-spezifischen Multi-Select-Implementierungen.

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
*   Verbindliches Zeitformat: `YYYYDDD.FRACTION` mit Bruchteil des Tages.
*   Normative Referenz fuer Konvertierung und Formatlogik ist `backend/app/core/pdvm_datetime.py`.
*   Technische Weiterentwicklungen werden gesammelt in: `docs/specs/PDVM_DATETIME_FUNCTION_COLLECTION.md`.

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

### 4.4 Passwortverwaltung (`docs/specs/PASSWORD_MANAGEMENT_SPEC.md`)
**Regel:** Passwort-Reset, OTP und Account-Sperrung folgen der Spezifikation.
*   `SEND_EMAIL` Konfiguration liegt in `sys_mandanten`.
*   OTP-Logik und `PASSWORD_CHANGE_REQUIRED` werden strikt umgesetzt.

### 4.5 Lineares SOLL-Schema (`docs/specs/PDVM_LINEAR_SCHEMA_V1.md`)
**Regel:** Die Datenstrukturen fuer Dialog/View/Frame/Control folgen der verbindlichen SOLL-Definition.
*   `ROOT`/`CONTROL`/`TEMPLATES` werden strukturell einheitlich gefuehrt.
*   Property-Keys sind in der Zielsicht grossgeschrieben.
*   Neuanlage basiert auf den Template-Saetzen `666...` und `555...`.

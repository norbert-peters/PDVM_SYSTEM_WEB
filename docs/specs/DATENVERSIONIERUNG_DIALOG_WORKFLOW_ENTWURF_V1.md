# Datenversionierung Dialog-Workflow Entwurf V1

Status: Entwurf

## Klarstellung Dialog Builder Ablauf (praxisnah)

Diese Klarstellung beschreibt den Soll-Standard fuer DIALOG_TYPE=work.

1. Overview ist ausserhalb des eigentlichen Bearbeitungsworkflows.
2. Overview zeigt eine normale View auf dev_workflow_draft.
3. In Overview gibt es zwei Standardaktionen:
- Doppelklick auf bestehenden Draft: oeffnet den Draft und setzt auf den zuletzt bearbeiteten Tab.
- Neuer Satz: legt einen neuen Datensatz in dev_workflow_draft an (nur Name als Pflichtfeld, TABLE wird aus Create-Dialog gesetzt).
4. Standard-Template 6666 fuer dev_workflow_draft ist verpflichtend und muss automatisch verfuegbar sein.

Hinweis Umsetzung:
- Der 6666-Template-Pfad fuer dev_workflow_draft/dev_workflow_draft_item wird automatisch im Backend-Service abgesichert.

Hinweis Umsetzung:
- Phase A ist gestartet und dokumentiert in DATENVERSIONIERUNG_PHASE_A_UMSETZUNG.md
- Phase B Rollenmodell (admin+develop) ist dokumentiert in DATENVERSIONIERUNG_PHASE_B_ROLLENMODELL.md
- Phase C UI-Sichtbarkeit und Action-Gating ist dokumentiert in DATENVERSIONIERUNG_PHASE_C_UI_SICHTBARKEIT.md
- Einheitliches Dialog-Datenmodell ist dokumentiert in DIALOG_WORKFLOW_DATENMODELL_V1.md
- Draft-Container Architektur ist dokumentiert in DATENVERSIONIERUNG_WORKFLOW_DRAFT_CONTAINER_V1.md

## 1. Ausgangslage

- Entwicklungsdatenbank liegt auf Windows (Quellsystem).
- Zieldatenbank liegt auf Ubuntu (Zielsystem).
- Die technische Datenversionierung (Release-Check, Apply, Import) ist im Backend bereits vorhanden.
- Vor weiterer App-Entwicklung muss die datengetriebene Dialog-Integration fertiggestellt und testbar sein.

## 2. Zielbild

Ein standardisierter, datengetriebener Workflow-Dialog zur Verwaltung von Datenreleases und Datenpatches, der:

1. nur fuer Rollen admin und develop sichtbar ist,
2. ueber Menueeintrag gestartet wird,
3. Dialog/View/Frame aus sys_dialogdaten, sys_viewdaten, sys_framedaten verwendet,
4. ueber Templates automatisch (weitgehend maschinell) erzeugt wird,
5. in allen Applikationen identisch wiederverwendbar ist.

## 3. Rollen- und Sichtbarkeitsmodell

### 3.1 Sichtbarkeit im Menue

- Menueeintrag DATA_RELEASE_WORKFLOW wird nur bei Rolle admin oder develop geliefert.
- Empfehlung Datenmodell (User):
  - SECURITY.ROLE = admin | develop | ...
  - alternativ PERMISSIONS.ROLES = ["admin", "develop", ...]

### 3.2 Backend-Guards

- Apply/Import Endpunkte bleiben schreibend nur fuer admin.
- Read-only Endpunkte (Preview, Validation, Katalog, Diff) koennen admin + develop erlauben.
- Vorschlag neue zentrale Guard-Varianten:
  - require_admin_user() -> admin
  - require_admin_or_develop_user() -> admin, develop

## 4. Standard-Dialog fuer Release/Patch Verwaltung

### 4.1 Dialog-Typ

- DIALOG_TYPE = work (schrittweiser Workflow)
- Aufruf per go_pdvm_dialog aus sys_menudaten

### 4.2 Standard-Tabs (entspricht deinem Ablauf)

TAB_01: Setup
- Name festlegen
- Type waehlen (release | patch)
- Ziel-App waehlen

TAB_02: Dialogdaten
- Rootdaten und Tab-Verbindungen
- Open/Edit Regeln

TAB_03: View
- View-Definition fuer Quell-/Ziel-Daten, Filter, Sort, Projektion

TAB_04: Properties Dictionary
- Control-Auswahl via Prefix-Filter + Suche
- Bei Bedarf neue Property ueber Dictionary anlegen

TAB_05: Build/Validate/Apply
- Paket bauen (Manifest + Items + Data)
- Dry-run
- Apply (admin)
- Status/Logs anzeigen

Regel:
- Pro `edit`/`acti`-Tab genau ein eigenes Frame (`sys_framedaten`).
- `view`-Tab referenziert immer `sys_viewdaten`.

## 4.3 Tab-Funktionen fuer dialog_builder (verbindlich)

1. Overview
- Nur Auswahl/Anlage von Drafts (dev_workflow_draft).
- Nicht Teil der fachlichen Bearbeitungsschritte.

2. Setup
- Frame-basierte Inputcontrols.
- Struktur orientiert sich fachlich an sys_dialogdaten.
- Persistenz erfolgt als Draft-Item in dev_workflow_draft_item (nicht direkt in sys_dialogdaten).
- Weiter zu TABS erst nach plausiblen Daten (formale Pruefungen koennen spaeter datengetrieben erweitert werden).

3. TABS
- Standard-Inputcontrol fuer Hinzufuegen/Entfernen von Tabs.
- Struktur orientiert sich fachlich an sys_dialogdaten (TAB_ELEMENTS).
- Persistenz erfolgt im Draft-Container.
- Mindestens ein Tab ist Pflicht; ein erster Tab wird als Muster vorbelegt.

4. Content
- Struktur orientiert sich fachlich an sys_framedaten.
- Standard-Inputcontrol fuer Tab-bezogene Content-Bloecke (hinzufuegen/aendern/entfernen).
- Mindestens ein Content-Block ist Pflicht.
- Bei genau einem Tab darf intern ohne expliziten Tab-Key gespeichert werden; ab >1 Tabs tab-spezifisch speichern.
- Empfehlung: pro Dialog-Tab eigener Frame-Datensatz (einfache Zuordnung, klare Verantwortlichkeit).

5. Build
- Enthält Aktionen fuer pruefen, erzeugen, abbrechen.
- Aktionen sollen als Inputcontrols im Frame definiert werden (Typ action/button-Rendering).
- Vorteil: Label, Tooltip, Hilfe, Rollensteuerung und Texte sind voll datengetrieben.
- Erweiterung: Show/Preview-Aktion fuer Popup-Testlauf mit leerem oder Musterdatensatz vor Erzeugung.

## 5. Datengetriebene Standard-Definitionen

### 5.1 sys_dialogdaten (Standard-Record)

- ROOT.SELF_NAME = Datenversionierung Workflow
- ROOT.DIALOG_TYPE = work
- ROOT.TAB_ELEMENTS als einzige fuehrende Tab-Quelle
- Je Tab MODULE + GUID (view/edit/acti)

### 5.2 sys_viewdaten (Standard-Views)

Mindestens drei Views:

1. release_candidates_view
- Datenquelle: dev_release
- Filter: APP_ID, STATUS, VERSION

2. release_items_view
- Datenquelle: dev_release_item
- Filter: RELEASE_ID, TABLE_NAME, OPERATION

3. release_state_target_view
- Datenquelle: sys_release_state
- Filter: APP_ID, STATUS, APPLIED_AT

### 5.3 sys_framedaten (Standard-Frames)

Mindestens vier Frames (ein Frame je `edit`/`acti`-Tab):

1. workflow_setup_frame
- Felder fuer Name, Type, App, Version, Policy

2. dialog_config_frame
- Felder fuer DIALOG_TYPE, TAB_ELEMENTS, MODULE/GUID Mapping

3. property_mapping_frame
- element_list fuer Dictionary Properties
- Prefix-Filter + Suchfeld + Neuanlage-Action

4. workflow_apply_frame
- Dry-run/Apply Controls, Status und technische Aktionen

Verbindliche Strukturregel fuer Workflow-Frames:

1. Alle Workflow-Controls liegen in `daten.FIELDS`.
2. Jedes Feld in `daten.FIELDS` muss `gruppe = FIELDS` verwenden.
3. Workflow-Inputcontrols duerfen nicht aus `gruppe = ROOT` bezogen werden.
4. Seeder und Health-Check muessen diese Regel aktiv durchsetzen.

### 5.4 Dialog-spezifische Create-Parameter (CREATE_FRAME_GUID)

Ziel:
- Jeder Dialog kann seinen "Neuer Satz"-Ablauf datengetrieben definieren.
- Create-Dialoge sind nicht mehr hart codiert, sondern kommen aus einem dedizierten Frame.

Verbindliche ROOT-Konfiguration in sys_dialogdaten:

1. ROOT.CREATE_FRAME_GUID
- GUID auf ein Frame in sys_framedaten.
- Das Frame definiert die Eingabefelder fuer den Create-Modal.

2. ROOT.CREATE_MODE (optional)
- Beispielwerte: simple | frame
- Wenn nicht gesetzt: implizit frame bei gueltigem CREATE_FRAME_GUID, sonst simple.

3. ROOT.CREATE_DEFAULTS (optional)
- JSON-Objekt mit Defaultwerten fuer Create-Felder.
- Prioritaet im UI: CREATE_DEFAULTS ueberschreibt Frame-Feld-Defaults.

4. ROOT.CREATE_REQUIRED (optional)
- Array mit Pflichtfeldern fuer serverseitige Validierung.
- Akzeptiert auch CSV-String (z. B. "TABLE,VIEW_GUID").

Create-Flow (linear):

1. Frontend liest ROOT.CREATE_FRAME_GUID aus Dialogdefinition.
2. Frontend laedt Frame per /api/dialogs/frame/{frame_guid}.
3. Frontend rendert Create-Modal aus frame.daten.FIELDS.
4. Frontend sendet die eingegebenen Werte als create_context an /api/dialogs/{dialog_guid}/draft/start.
5. Backend mappt create_context auf ROOT-Patch des neuen Drafts (inkl. TABLE-Alias auf ROOT.TABLE).
6. Draft wird mit den Create-Parametern erzeugt und anschliessend normal bearbeitet/committed.

Servervalidierung bei /draft/start:

1. CREATE_REQUIRED wird gegen create_context geprueft.
2. Leere Strings gelten als fehlend.
3. Bei fehlenden Pflichtfeldern liefert das Backend HTTP 422 mit `missing_fields`.

Alias-Regel fuer Tabellenfeld in create_context:
- TABLE hat Prioritaet.
- Falls TABLE leer ist, werden ROOT_TABLE, TARGET_TABLE, DIALOG_TABLE in dieser Reihenfolge auf TABLE gemappt.

Wichtig:
- Dadurch kann ROOT.TABLE pro neuem Dialogdatensatz bereits beim Draft-Start korrekt gesetzt werden.
- Fehlerklasse "Dialog ROOT.TABLE ist leer" wird fuer diesen Create-Pfad vermieden.

### 5.5 Praktische Umsetzung fuer DIALOG_TYPE=work

Ziel:
- Nach Klick auf Anlegen sollen die Grunddaten nicht nur im UI-Draft stehen, sondern sofort als persistente Workflow-Draft-Daten vorhanden sein.

Aktueller Soll-Ablauf (schrittweise):

1. Neuer Satz Popup (Pflicht):
- NAME
- keine weiteren Pflichtfelder fuer die Neuanlage
- kein separates WORKFLOW_TYPE-Feld erforderlich
- DIALOG_TYPE=work steuert den Ablauf
- DRAFT_TABLE und DRAFT_ITEM_TABLE steuern die physischen Draft-Zieltabellen dynamisch je Work-Dialog
- Damit sind getrennte Workflows (z. B. Buchungslauf, Personalabrechnung, Kostenstellenverteilung) in separaten Draft-Tabellen moeglich

2. Draft-Start in Dialog-API:
- erzeugt weiterhin den Dialog-Draft fuer die Bearbeitung,
- erkennt DIALOG_TYPE=work,
- bootstrapped zusaetzlich einen persistenten Datensatz in ROOT.DRAFT_TABLE,
- legt in ROOT.DRAFT_ITEM_TABLE einen zentralen work-Container an (Standard aus UID 666),
- referenziert diesen Container in ROOT.DRAFT_TABLE.ROOT (WORK_ITEM_UID, WORK_ITEM_TYPE, WORK_ITEM_KEY),
- erzeugt dabei noch keine fachlichen Zielsaetze in den Buckets,
- verwaltet darin die Zielstrukturen tabellenweise unter Gruppen (initial leer):
  - sys_dialogdaten
  - sys_viewdaten
  - sys_framedaten

2a. Weiter-Logik (lineares Standardvorgehen):
- Beim Klick auf Weiter wird fuer den naechsten Workflow-Schritt geprueft, ob fuer die Tab-Tabelle bereits ein Standardsatz im work-Container existiert.
- Falls nicht vorhanden, wird er aus Template UID 666 der jeweiligen Tabelle erzeugt und in dev_workflow_draft_item gespeichert.
- Die Speicherung erfolgt immer in der durch DRAFT_ITEM_TABLE definierten Work-Item-Tabelle.
- Regel:
  1. Modul=view/acti: keine tabellenbezogene Neuanlage
  2. Modul=edit: Standardsatz fuer TAB.TABLE anlegen (falls noch nicht vorhanden)
- Der Name dieser Standardsaetze ist immer der Name der ersten Neuanlage (ROOT.TITLE des dev_workflow_draft).

3. Rueckgabe in den Edit-Draft:
- ROOT.WORKFLOW_DRAFT_GUID
- ROOT.DIALOG_TYPE
- ROOT.TARGET_TABLE
- ROOT.WORKFLOW_NAME
- ROOT.DIALOG_UID
- ROOT.WORK_ITEM_UID

Nutzen:
- Ein Draft ist sofort in dev_workflow_draft/dev_workflow_draft_item vorhanden und spaeter wieder aufnehmbar.
- Setup startet mit den bereits eingegebenen Grundwerten.
- Alle zu erzeugenden Tabellenstrukturen liegen konsistent in einem Containerdatensatz.

Hinweis zu TARGET_TABLE:
- TARGET_TABLE steuert die fachliche Zieltabelle des spaeteren Build-Schritts.
- Fuer dialog_builder ist der sinnvolle Default sys_dialogdaten.
- ROOT.TABLE bleibt davon getrennt: ROOT.TABLE ist die technische Tabelle des aktuell bearbeiteten Dialogdatensatzes.

### 5.5a Work-Tab-Reihenfolge (verbindlich)

Fuer den Workflow-Builder ist folgende Reihenfolge verbindlich:

1. Overview (view auf dev_workflow_draft)
2. Setup (edit)
3. Tabs (edit)
4. View (edit fuer View-Controls)
5. Content (edit)
6. Build (acti)

Wichtig:
- Der View-Tab liegt vor Content.
- Tab 1 bleibt eine normale View.
- Die weiteren Bearbeitungsdaten werden im work-Container aus dev_workflow_draft_item gepflegt.

## 5.6 Standard-Workflow-Ansatz (Optimierung, Risiken, Vorteile)

Zielbild:
- dialog_builder soll mit Standardmitteln eines normalen Workflows abbildbar sein.
- Ablauflogik kommt primär aus Datenbank-Definitionen (Dialog/View/Frame/Controls), nicht aus Spezialcode.

Vorteile:
1. Einheitlicher Ablauf ueber alle Apps.
2. Weniger Sondercode im Frontend/Backend.
3. Aenderungen an Labels/Hilfen/Tab-Struktur ohne Deploy moeglich.
4. Bessere Revisionsfaehigkeit und Testbarkeit von Workflow-Definitionen.

Risiken:
1. Fehlkonfiguration in DB kann Laufzeitfehler verursachen.
2. Komplexe Validierungslogik wird schwieriger zu debuggen, wenn rein datengetrieben.
3. Ohne klare Mindeststandards koennen inkompatible Workflows entstehen.

Gegenmassnahmen:
1. Verbindliche Mindestpruefungen im Backend (z. B. Setup vorhanden, mindestens 1 Tab, mindestens 1 Content-Block).
2. Versionierte Standard-Templates (6666 Basis + dokumentierte Blueprint-UIDs).
3. Preview/Show-Lauf vor Build als Pflichtschritt fuer Freigabe.

## 6. Automatisierung: Dialog Factory Workflow

## 6.1 Ziel

Ein maschineller Generator erzeugt in einem Lauf:

- Dialog-Record in sys_dialogdaten
- benoetigte View-Records in sys_viewdaten
- benoetigte Frame-Records in sys_framedaten
- optional Menueeintrag in sys_menudaten

## 6.2 Eingaben

- app_id
- workflow_name
- workflow_type (release/patch)
- target_tables (sys_*)
- role_visibility (admin, develop)
- optional menu_parent_guid

## 6.3 Ausgabe

- dialog_guid
- view_guids[]
- frame_guids[]
- menu_item_guid
- Erzeugungsprotokoll (created/updated/skipped)

## 6.4 Regeln

- idempotent: gleicher Input erzeugt kein Duplikat
- deterministische Naming-Konventionen
- Vollvalidierung vor Persist
- rollback bei Teilfehlern

## 7. Fehlende Templates (Gap-Liste)

Die nachfolgenden Templates sind fuer einen robusten, app-uebergreifenden Workflow notwendig und sollten als Standard in die Datenbank aufgenommen werden.

### 7.1 Fehlende Dialog-Templates

1. WORKFLOW_DIALOG_BASE_TEMPLATE
- fuer sys_dialogdaten
- enthaelt ROOT.DIALOG_TYPE=work + TAB_ELEMENTS Grundstruktur

2. WORKFLOW_DIALOG_RELEASE_TEMPLATE
- spezialisiert fuer release

3. WORKFLOW_DIALOG_PATCH_TEMPLATE
- spezialisiert fuer patch

### 7.2 Fehlende View-Templates

1. RELEASE_CANDIDATE_VIEW_TEMPLATE
2. RELEASE_ITEMS_VIEW_TEMPLATE
3. TARGET_STATE_VIEW_TEMPLATE
4. CHANGE_LOG_VIEW_TEMPLATE

### 7.3 Fehlende Frame-Templates

1. WORKFLOW_SETUP_FRAME_TEMPLATE
2. WORKFLOW_DIALOG_CONFIG_FRAME_TEMPLATE
3. WORKFLOW_VIEW_CONFIG_FRAME_TEMPLATE
4. WORKFLOW_PROPERTY_MAPPING_FRAME_TEMPLATE
5. WORKFLOW_APPLY_FRAME_TEMPLATE

### 7.4 Fehlende Control-Dictionary Templates (sys_control_dict)

Zusatz-Controls fuer den Workflow:

1. SYS_RELEASE_TYPE (dropdown: release|patch)
2. SYS_TARGET_ENV (dropdown: dev|test|prod)
3. SYS_SOURCE_DB_ROLE (dropdown: development)
4. SYS_TARGET_DB_ROLE (dropdown: system)
5. SYS_POLICY_MODE (manual|auto|deferred)
6. SYS_PACKAGE_HASH
7. SYS_SOURCE_COMMIT
8. SYS_TABLE_PREFIX_FILTER
9. SYS_DICTIONARY_SEARCH
10. SYS_CREATE_PROPERTY_ACTION
11. SYS_DRY_RUN_ACTION
12. SYS_APPLY_ACTION

Hinweis:
- Diese Controls sollten auf dem bestehenden 555.../666... Prinzip aufsetzen.
- Fuer element_list Pflege sind TAB_ELEMENTS, FIELDS_ELEMENTS, CONFIGS_ELEMENTS als Standard abzubilden.

## 8. Optimierungspotential

1. Rollenmodell vereinheitlichen
- ROLE und/oder PERMISSIONS.ROLES auf einen verbindlichen Standard festlegen.
- develop-Rolle systemweit in Guards, Menuefilter und Dialogaktionen konsistent nutzen.

2. Generator statt Einzelpflege
- Dialog/View/Frame nicht manuell einzeln pflegen.
- Ein Factory-Service erzeugt alle Records in einem transaktionalen Ablauf.

3. Prefix-basierte Property-Auswahl beschleunigen
- Dictionary-View mit serverseitigem Prefix-Filter und Suchindex.
- Quick-Create fuer fehlende Property mit Ruecksprung in laufenden Workflow.

4. Dry-run zuerst erzwingen
- Bei develop immer Pflicht-Dry-run vor Apply.
- Apply nur nach erfolgreicher Validierung freischalten.

5. Standardisierte Namenskonventionen
- dialog_name, view_name, frame_name strikt aus app_id + workflow_name + type ableiten.
- Verbesserte Diff- und Wiederholbarkeit.

6. Environment-Trennung sichtbar machen
- Im Workflow immer Quell- und Zielsystem anzeigen (Windows Dev, Ubuntu Target).
- Verwechslungen beim Apply vermeiden.

## 9. Konkreter Umsetzungsfahrplan (naechster Schritt)

Phase A: Templates vervollstaendigen
1. fehlende Dialog/View/Frame/Control Templates als Seed bereitstellen
2. Template-Health-Check bauen (Pflichtgruppen, Pflichtfelder, GUID-Referenzen)

Phase B: Factory-Service
1. Workflow-Generator API erstellen (create/update)
2. idempotente Erzeugung von dialog/view/frame/menu
3. Dry-run/Preview Response

Phase C: UI-Integration
1. Menueeintrag fuer admin/develop
2. Standarddialog starten und End-to-End testen
3. Testprotokoll: Dev->Target Release und Patch

## 10. Akzeptanzkriterien

1. admin und develop sehen den Workflow-Dialog im Menue, andere Rollen nicht.
2. Ein Workflow kann ohne manuelle Einzelpflege aus Templates erzeugt werden.
3. Dialog/View/Frame sind vollstaendig ueber DB-Daten definiert.
4. Property-Auswahl ueber Prefix + Suche funktioniert und erlaubt Neuanlage.
5. Ein Release/Patch kann per Dry-run geprueft und danach angewendet werden.
6. Der Ablauf ist app-uebergreifend wiederverwendbar.

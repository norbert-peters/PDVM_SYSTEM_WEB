# PDVM Work Zielarchitektur - Einheitlicher Speicherweg V1

Status: Architektur-Spezifikation zur fachlichen Abnahme vor Umsetzung

Implementierungsstand 30.05.2026 (verbindliche Runtime-Regeln):

1. View-Auswahl in Work setzt den aktiven `draft_guid` fuer alle Folgetabs.
2. Work-Tabs sind linear: Navigation ausschliesslich ueber `Zurueck`/`Weiter`/`Von vorne`.
3. Enter-Pipeline je Tab:
1. `ensure-step` fuer den Zieltab ausfuehren
2. Tab-Record aus `DRAFT_DB.<TABLE>.<UID>` lesen
3. Falls nicht vorhanden: nach 555/666-Regeln anlegen und direkt in DRAFT_DB persistieren
4. Leave-Pipeline je Tab:
1. Aktuellen Tab-Datensatz ueber den einheitlichen Draft-Write-Weg persistieren
2. Workflow-State (`ACTIVE_TAB`, `MAX_TAB`) in Draft-State schreiben
5. In-Tab-Speicherbutton ist fuer Work deaktiviert; expliziter fachlicher Abschluss erfolgt im `acti`-Tab.
6. `storage_scope=draft` ist die Default-Semantik fuer Work-Laufzeit; `storage_scope=live` wird erst im `acti`-Commit genutzt.
7. Einheitlicher Aufrufvertrag ist systemweit aktiviert: jeder CRUD-Read/Write-Aufruf akzeptiert `storage_scope` und `draft_guid`.
8. `draft_guid` wird immer mitgefuehrt (bei `live` leer/null erlaubt), bei `draft` verpflichtend.

Scope:

1. Work-Dialoge (`DIALOG_TYPE=work`)
2. Einheitliche Speicherlogik fuer `edit` und `work`
3. Speicherziel-Scope `live` vs `draft`

Nicht-Scope:

1. UI-Design oder kosmetische Frontend-Anpassungen
2. Vollstaendige Datenmigration historischer Draft-Bestaende

---

## 1. Zielbild

Work ist kein eigener Speicheralgorithmus.

Work ist derselbe fachliche Ablauf wie Edit, mit genau drei Unterschieden:

1. Tabsteuerung (Workflow-Navigation)
2. Speicher-Scope ist `draft` statt `live`
3. Ein `acti`-Tab uebertraegt Daten von `draft` nach `live`

Konsequenz:

1. Gleicher CRUD-Weg fuer beide Modi
2. Gleiche table/uid-Semantik
3. Kein Sonder-JSON-Pfad je Tab

---

## 2. Verbindliche Leitprinzipien

### 2.1 Ein Aufrufweg fuer alle Schreibvorgaenge

Verbindlich:

1. Jeder Save (Button, Weiter, Auto-Save) verwendet denselben zentralen Write-Pfad.
2. Der Aufrufer kennt nur `table`, `uid`, `daten`, `storage_scope`.
3. Keine tab-spezifischen Sonderrouten fuer fachliche Daten.

### 2.2 Table/UID bleibt die fachliche Adresse

Verbindlich:

1. Fachliche Datensaetze werden immer ueber `table + uid` adressiert.
2. Der Unterschied zwischen Edit und Work ist nur der Speicher-Scope.

### 2.3 Scope statt Sondername im Tabellennamen

Verbindlich:

1. Kein semantischer Hack wie `DRAFT_DB#table` als Pflichtmodell.
2. Bevorzugt: separates Routingfeld `storage_scope` (`live|draft`) und `draft_guid`.

Begruendung:

1. Stabiler als String-Parsing
2. Klarere API-Vertraege
3. Geringeres Risiko fuer Fehler bei Validierung/Normalisierung

---

## 3. Ziel-Datenmodell fuer Work

## 3.1 Draft-Container

`dev_workflow_draft` bleibt Workflow-Container.

`DRAFT_DB` enthaelt ausschliesslich tabellenfoermige Buckets:

1. `DRAFT_DB.<TABLE_NAME_UPPER>.<UID> = Datensatz`
2. Datensatzstruktur entspricht der echten Tabelle (inkl. 555/666-Regeln)

`_META` enthaelt nur technische Workflow-Engine-Daten:

1. Navigation (`ACTIVE_TAB`, `MAX_TAB`)
2. Status (`STATUS`)
3. technische Prozessmetadaten (optional)

Nicht erlaubt in `_META`:

1. fachliche Datensatzinhalte, die in Tabellenrecords gehoeren

## 3.2 Setup als normaler Tabellenrecord

Verbindlich:

1. Setup-Daten liegen in einem Tabellenrecord (table/uid), nicht als eigene fachliche Quelle in `_META.SETUP`.
2. `_META.SETUP` darf maximal als technische UI-Hilfe existieren und ist nicht Source of Truth.

---

## 4. Einheitliche CRUD-Vertraege

## 4.1 Abstrakter Vertrag

Eingabe:

1. `table`
2. `uid`
3. `daten`
4. `storage_scope` (`live` oder `draft`)
5. `draft_guid` (immer als Feld vorhanden; bei `live` leer/null erlaubt, bei `draft` Pflicht)

Validierung (verbindlich):

1. `storage_scope=live` -> `draft_guid` darf leer/null sein.
2. `storage_scope=draft` -> `draft_guid` muss gueltige UUID sein.
3. Ungueltige Kombinationen liefern sofort `400` (kein stilles Fallback).

Operationen:

1. `create`
2. `read`
3. `update`
4. `list`
5. `delete` (optional, wenn fachlich noetig)

## 4.2 Routingregel

1. `storage_scope=live` -> normaler DB-Weg
2. `storage_scope=draft` -> Speicherung unter `dev_workflow_draft[uid=draft_guid].DRAFT_DB.<TABLE>.<UID>`

Wichtig:

1. Der Aufrufer sieht nur den Scope, nicht die interne Persistenzmechanik.

## 4.3 Legacy-Endpoints und Migration

Status:

1. Legacy-Record-Endpunkte in `workflow_drafts` wurden entfernt.
2. Der Draft-CRUD-Zugriff erfolgt ausschliesslich ueber den Tabellen-Standardpfad mit Scope-Vertrag.

Standard-Endpunkte (verbindlich fuer Neuentwicklung):

1. `GET /tables/{table_name}?storage_scope=draft&draft_guid=<uuid>`
2. `GET /tables/{table_name}/{uid}?storage_scope=draft&draft_guid=<uuid>`
3. `POST /tables/{table_name}?storage_scope=draft&draft_guid=<uuid>`
4. `PUT /tables/{table_name}/{uid}?storage_scope=draft&draft_guid=<uuid>`
5. `DELETE /tables/{table_name}/{uid}?storage_scope=draft&draft_guid=<uuid>`

Hinweis:

1. `POST /workflow-drafts/{draft_guid}/commit-live` bleibt als fachlicher Orchestrierungsendpunkt bestehen.

---

## 5. Tabregeln fuer Work

## 5.1 Tab-erzeugte Tabellen

Verbindlich:

1. Ein Tab, der direkt einen Datensatz erzeugt/editiert, hat genau einen aktiven Datensatz.
2. Speicherung ersetzt den Tabellenbucket fuer diesen Tab-Kontext deterministisch (kein Akkumulieren alter Eintraege).

## 5.2 Mehrsatztabellen (z. B. sys_framedaten)

Verbindlich:

1. Mehrsatzfaelle werden nicht ueber den Tab selbst erzeugt.
2. Mehrsaetze entstehen ueber Element-List/Picker-Mechanismen.
3. Auswahl liefert explizit `uid`, und Save geht exakt auf diese `uid`.

---

## 6. Neuanlage- und Template-Regeln (555/666)

Verbindlich:

1. Neuanlage (ausser `asy_benutzer`) immer linear aus 555 derselben Tabelle
2. ROOT-Eigenschaften des neuen Satzes zentral setzen
3. Leere Gruppen aus 555 mit gleichnamiger Struktur aus 666.(TEMPLATE|TEMPLATES) auffuellen; fehlt diese, ist es ein Fehler
4. Nur definierte Felder werden uebernommen
5. Keine impliziten Zusatzfelder

Gilt gleich fuer:

1. `live`
2. `draft`

---

## 7. Acti-Tab (Draft -> Live)

Verbindlich:

1. Acti liest die betroffenen Tabellenrecords aus `DRAFT_DB`.
2. Jede Uebertragung nutzt denselben zentralen Write-Weg mit `storage_scope=live`.
3. Kein Spezial-SQL im Router.
4. Ergebnisbericht pro Tabelle/uid (created/updated/skipped/error).

Optional (empfohlen):

1. Commit als transaktionale Job-Einheit mit Report-Datensatz.

---

## 8. Risiken und Gegenmassnahmen

## 8.1 Risiko: Doppelte Wahrheiten (ROOT/_META/Tabelle)

Folge:

1. Drift, scheinbar leere Felder, unvorhersehbares Verhalten

Gegenmassnahme:

1. Genau eine fachliche Quelle: Tabellenrecord
2. `_META` nur technisch

## 8.2 Risiko: Scope-Leak nach live

Folge:

1. Draft-Daten landen unbeabsichtigt produktiv

Gegenmassnahme:

1. Harte Scope-Validierung im zentralen Write-Pfad
2. Audit-Logging fuer jeden Scope-Wechsel

## 8.3 Risiko: Parallelitaet im selben Draft

Folge:

1. Lost updates

Gegenmassnahme:

1. Revision/ETag-Pruefung pro Datensatz
2. deterministische Last-Write-Regeln nur mit Konfliktmeldung

## 8.4 Risiko: Buckets wachsen unkontrolliert

Folge:

1. Unklare Datenlage, Performanceverlust

Gegenmassnahme:

1. Tab-erzeugte Tabellen im Ein-Satz-Modus
2. Mehrsatz nur ueber expliziten Picker-Flow

---

## 9. Alternativen fuer Draft-Persistenz

## 9.1 Alternative A - DRAFT_DB im dev_workflow_draft (Container-JSON)

Vorteile:

1. Ein Objekt pro Workflow
2. einfacher Snapshot/Export
3. wenig DB-Schema-Aenderung

Nachteile:

1. grosse JSONB-Strukturen
2. Konfliktbehandlung komplexer
3. Querying/Indexing begrenzt

Bewertung:

1. Kurz-/Mittelfristig praktikabel, wenn einheitlicher Zugriff strikt erzwungen wird.

## 9.2 Alternative B - Eigene Draft-Tabellen je Fach-Tabelle

Vorteile:

1. Relationale Klarheit
2. bessere Indizierung/Abfragen
3. natuerlicher table/uid-Zugriff

Nachteile:

1. hoeherer Migrationsaufwand
2. mehr Betriebsobjekte

Bewertung:

1. Langfristig technisch sauberste Loesung bei wachsendem Volumen.

## 9.3 Alternative C - Temporaere Datensaetze in echten Tabellen (`temp`-Spalte)

Vorteile:

1. ein physischer Tabellenraum
2. wenig Adapterlogik

Nachteile:

1. hohes Risiko fuer Vermischung von produktiv und draft
2. komplizierte Berechtigungs- und Sichtbarkeitsregeln
3. historisierungstechnisch fehleranfaellig

Bewertung:

1. Fuer PDVM nicht empfohlen.

---

## 10. Kompatibilitaet mit ARCHITECTURE_RULES

Diese Zielarchitektur ist konform mit:

1. Central-DB-Gesetz (kein Router-SQL)
2. Tabellenrouting zentral
3. einheitlicher Neuanlagealgorithmus (666)
4. 555/666-Strukturregeln
5. Trennung fachlicher Daten und technischer Metadaten

Sinnvolle, regelkonforme Erweiterung:

1. Zentrales Scope-Routing (`live|draft`) als offizieller Teil des DB-Zugriffsvertrags.

---

## 11. Abnahmekriterien (vor Umsetzung)

Ein Architekturentwurf ist freigegeben, wenn folgende Aussagen akzeptiert sind:

1. Work und Edit nutzen denselben CRUD-Vertrag.
2. Unterschiede liegen nur in Tabsteuerung, Scope, Acti-Transfer.
3. Setup ist fachlich ein Tabellenrecord, nicht Sonderquelle.
4. `_META` ist rein technisch.
5. Tab-erzeugte Tabellen sind deterministisch Ein-Satz.
6. Mehrsatzfaelle laufen nur ueber explizite Picker-/Element-List-Flows.
7. Acti verwendet denselben zentralen Write-Weg fuer Live-Commit.

---

## 12. Entscheidungsprotokoll (verbindlich festgelegt)

Vom Auftraggeber festgelegt:

1. Scope-Modell: separates Feld `storage_scope` ist verbindlich.
2. Mittelfristige Persistenzstrategie:
	- aktuell Container-JSON (`dev_workflow_draft.DRAFT_DB`),
	- Wechsel auf relationale Draft-Tabellen nur bei nachgewiesenen Groessen-/Performanceproblemen.
3. Rueckwaertskompatibilitaet fuer bestehende Draft-Daten:
	- aktuell nicht erforderlich,
	- alte Draft-Daten werden vor Testzyklen geloescht.

Konsequenz fuer Umsetzung:

1. Keine Implementierung von Legacy-Migrationspfaden fuer alte Draft-Schemata in dieser Phase.
2. Fokus liegt auf sauberem Zielmodell und deterministischem Verhalten im aktuellen Scope.

---

## 13. Verbindliche Regeln aus ARCHITECTURE_RULES fuer diese Umsetzung

Fuer die Implementierung dieser Zielarchitektur sind folgende Regeln zwingend:

1. Kein Router-SQL, keine Router-JSON-Manipulation ausser orchestrierender Aufruflogik.
2. Schreibpfade laufen ueber zentrale Business-/Write-Services.
3. Tabellenrouting bleibt zentral und wird nicht in Frontend oder Routern dupliziert.
4. Neuanlage fuer Fachdatensaetze folgt weiterhin dem 666-Algorithmus.
5. 555/666-Strukturregeln (inkl. TABLE_INFO unter 666.TEMPLATES) bleiben unveraendert gueltig.
6. Work-spezifische Erweiterungen sind als Scope-Parameter umzusetzen, nicht als Parallelarchitektur.
7. Neue Sonderfelder in ROOT oder DRAFT_DB sind nur zulaessig, wenn sie in der Spezifikation explizit beschrieben sind.

Pragmatische, regelkonforme Abweichungen in dieser Phase:

1. Interne technische Metadaten in `_META` bleiben vorerst erlaubt, bis Setup vollstaendig als Tabellenrecord gefuehrt wird.
2. Bestehende API-Vertraege duerfen in einer Uebergangsphase parallel bereitstehen, wenn der zentrale Pfad bereits aktiv ist.

---

## 14. Rollenquelle und Tabellenrechte (verbindlich)

Fuer rollenbasierte Entscheidungen (Dropdown, API-Guards, UI-State) gilt verbindlich:

1. Die normalisierte Rollenquelle ist `asy_benutzer.PERMISSIONS.ROLES`.
2. Rollen werden immer kleingeschrieben und als Set ausgewertet.
3. `developer` (bzw. Legacy `develop`) hat im Tabellenkatalog-Dropdown immer Vollzugriff.
4. Mandantenbezogene Tabellenrechte fuer alle anderen Rollen werden aus `msy_security` gelesen.
5. Der Tabellenkatalog selbst kommt aus `TABLE_META`/`TEMPLATE_META` in `asy_systemdaten` und optional `msy_systemdaten`.

---

## 15. TAB_ELEMENTS Optimierungen (umgesetzt 01.06.2026)

### 15.1 Erweiterte Template-Felder fuer Dialog-Tabs

Verbindlich:

1. `sys_dialogdaten` UID `66666666-6666-6666-6666-666666666666` fuehrt in `daten.TEMPLATES.TAB_ELEMENTS` je Tab-Eintrag mindestens:
	- `TAB`, `GUID`, `HEAD`, `TABLE`, `MODULE`, `EDIT_TYPE`, `OPEN_EDIT`, `SELECTION_MODE`
2. Die Felder `OPEN_EDIT` und `SELECTION_MODE` sind damit Bestandteil der element_list-Definition und werden im Workflow-Tab-Editor direkt gepflegt.

### 15.2 Frame-Setup fuer Work-Tabeditor

Verbindlich:

1. `sys_framedaten` UID `886842eb-f62b-56d8-80cf-7d071264307b` verwendet fuer den Tabs-Tab ein einzelnes `element_list`-Control auf `gruppe=ROOT`, `feld=TAB_ELEMENTS`.
2. `configs.element_template` und `configs.element_fields` des Controls werden aus `sys_dialogdaten(666...).TEMPLATES.TAB_ELEMENTS` abgeleitet.
3. Das Control schreibt in `ROOT.TAB_ELEMENTS` (kanonische Tab-Quelle).

Lineare Auswertungsregel (verbindlich):

1. In `ROOT.TAB_ELEMENTS.TAB_XX` ist `GUID` die alleinige Modul-Referenz.
2. Bei `MODULE=view` referenziert `GUID` auf `sys_viewdaten`.
3. Bei `MODULE=edit|show|acti` referenziert `GUID` auf `sys_framedaten`.
4. Eine separate Property `VIEW_GUID` ist nicht mehr Bestandteil des Zielbilds.
5. `TABLE` ist ausschliesslich die fachliche Datentabelle fuer Read/Write (z. B. `sys_dialogdaten`) und keine Frame-/View-Tabelle.
6. Damit sind Routing und Rendering getrennt, aber linear: `MODULE+GUID -> View/Frame`, `TABLE -> Datensatzspeicherweg`.
7. Eine Property `TAB_GUID` innerhalb von `TAB_ELEMENTS` ist unzulaessig und wird nicht verwendet.

### 15.3 Serverseitige Kanonisierung beim Save

Umgesetzt in der zentralen JSON-Speicherlogik (`update_dialog_record_json`):

1. Beim Speichern von `sys_dialogdaten` wird `ROOT.TAB_ELEMENTS` serverseitig normalisiert.
2. Zulässig sind Eingaben als `dict` oder `list`; gespeichert wird immer als `dict` mit Schluesseln `TAB_01..TAB_NN`.
3. `TAB` wird fortlaufend numerisch gesetzt.
4. Fehlende Werte fuer `TABLE`, `EDIT_TYPE`, `OPEN_EDIT`, `SELECTION_MODE` werden aus `ROOT` geerbt.
5. Legacy-Root-Bloecke `TAB_01..TAB_20` werden entfernt, `ROOT.TABS` wird auf die Anzahl der normalisierten Eintraege synchronisiert.

Nutzen:

1. Keine driftenden Tab-Schluessel mehr (deterministische `TAB_XX`-Struktur).
2. Stabilere Runtime-Auswertung in Backend/Frontend.
3. Vermeidung von Inkonsistenzen zwischen UI-Editor und Persistenzformat.

### 15.4 UI/Save/Dropdown Nachschaerfung (umgesetzt 01.06.2026)

Verbindlich:

1. Listendarstellung im `element_list` priorisiert `HEAD` als sichtbares Label; Tooltip zeigt primär `GUID` (statt Voll-JSON).
2. Add/Edit/Delete innerhalb `ROOT.TAB_ELEMENTS` ist ein direkter Speichervorgang.
3. Die Persistierung erfolgt sofort ueber den bestehenden linearen Speicherweg:
	- Workflow-Kontext: Draft-Snapshot in der aktiven Modul-Tabelle.
	- Nicht-Workflow-Kontext: reguläres `updateRecord`/`commitDraft`.
4. Default-Dropdown-Definitionen fuer TAB-Element-Felder werden zentral in `sys_control_dict` gepflegt und bei Bedarf pro Frame (`configs.element_fields`) ueberschrieben.
5. Dropdown- und Auswahlfelder werden ausschliesslich ueber `configs.dropdown` aufgeloest (keine Inline-`options` als Laufzeitquelle).
6. Die Datenquelle fuer diese Dropdowns ist `sys_dropdowndaten` mit `dataset_uid` (`key`) + `feld` (`FIELD_KEY`).
7. Element-Editor-Felder ohne aufloesbare `configs.dropdown`-Referenz zeigen keine Fallback-Options an.
8. `sys_dropdowndaten.daten.OPTIONS` ist linear aufgebaut: `OPTIONS.<option_key>.<language> = label`.
9. Doppelte Strukturen `OPTIONS.<x>.key` und `OPTIONS.<x>.values` sind unzulaessig und werden nicht mehr gelesen.
10. Bei Schemaabweichungen (`ROOT`/`OPTIONS`/`FIELD_KEY` fehlt oder angefordertes Feld nicht vorhanden) wird ein harter Runtimefehler ausgelost (`HTTP 400`, `DROPDOWN_DATA_INVALID...`).

Dropdown-Datenmodell (verbindlich, linear):

```json
{
	"ROOT": {
		"TABLE": "sys_dropdowndaten",
		"FIELD_KEY": "anrede",
		"DEFAULT_LANGUAGE": "DE-DE",
		"SUPPORTED_LANGUAGES": ["DE-DE", "EN-US"]
	},
	"OPTIONS": {
		"w": { "DE-DE": "Frau", "EN-US": "Woman" },
		"m": { "DE-DE": "Herr", "EN-US": "Man" },
		"d": { "DE-DE": "Frau oder Herr", "EN-US": "Woman or Man" }
	}
}
```

Angelegte Default-Controls in `sys_control_dict`:

1. `TAB` (`d0e1e2ef-0603-504a-b0c2-bba74153e204`)
2. `GUID` (`cd815af8-b1db-5866-98d5-d4478d202126`)
3. `HEAD` (`6bed65d9-564b-59ce-b8d4-d73436d171c2`)
4. `TABLE` (`4d6d7a7e-df2e-5b90-b52a-aa78c83347cd`)
5. `MODULE` (`3c2d1955-70a7-5e87-80a9-80e696b6db92`)
6. `EDIT_TYPE` (`0ba01c4e-e755-59a0-b65a-dbaa58b7e295`)
7. `OPEN_EDIT` (`fc74a25f-601e-5bda-9ed1-286466409be7`)
8. `SELECTION_MODE` (`8d642af6-9b14-5f09-ac4b-6ca80183ce74`)

Dropdown-Verlinkung (verbindlich, Stand 01.06.2026):

1. `MODULE` -> `sys_dropdowndaten`, `key=f2e7f8a1-f7ad-4f6a-b1f9-f1abec9f21a1`, `feld=module`
2. `EDIT_TYPE` -> `sys_dropdowndaten`, `key=e3dc4eb9-2b79-45f5-a169-9f9e0c7fd322`, `feld=edit_type`
3. `OPEN_EDIT` -> `sys_dropdowndaten`, `key=8f3f8f45-4f3d-4ea3-9efe-8c4bf1305b12`, `feld=open_edit`
4. `SELECTION_MODE` -> `sys_dropdowndaten`, `key=b73633dd-4734-48ab-a9f9-63bf2f4c1db7`, `feld=selection_mode`

Workflow-Speicherkorrektur (verbindlich, Stand 01.06.2026):

1. Speichern in Work-Dialogen ist nicht mehr von `selectedUid` abhaengig.
2. Bei fehlender Modul-Tabellenzuordnung nutzt der Save-Pfad einen linearen Fallback:
	- `activeModule.table` -> `source.ROOT.TABLE` -> `effectiveDialogTableForDataOps` -> `effectiveDialogTable` -> `sys_dialogdaten`.
3. Damit werden auch Element-Aenderungen in Tab02 deterministisch in `DRAFT_DB.sys_dialogdaten` persistiert.

## 16. Zielbild fuer Element-Editor ohne Sonderstruktur (Vorschlag 01.06.2026)

Ausgangslage:

1. Aktuell wird fuer `element_list` in `configs` mit `element_fields`, `element_template`, `target_save_path`, `source_template_path` gearbeitet.
2. Diese Sonderstruktur fuehrt zu eigener Render- und Mapping-Logik und weicht vom sonstigen linearen Control/Frame-Modell ab.

Zielbild:

1. `configs` bleibt schlank und einheitlich, analog zu `dropdown` und `help`.
2. Fuer Element-Editing wird nur noch eine Referenz auf einen Element-Frame verwendet:
	- `configs.element.key`
	- `configs.element.feld`
	- `configs.element.table`
	- `configs.element.gruppe`
3. Der referenzierte Datensatz in `sys_framedaten` beschreibt die Edit-Felder als normale Inputcontrols aus `sys_control_dict`.
4. Kein separates "Element-Sonderrendering" mehr; die Element-Bearbeitung nutzt denselben linearen Frame-Renderpfad wie andere Edit-Masken.

### 16.1 Optimierungen

1. Weniger Sonderlogik im Frontend:
	- Wegfall von `element_fields`-spezifischen Hydratoren/Normalizern.
2. Einheitliche Konfigurationssemantik:
	- `configs.dropdown`, `configs.help`, `configs.element` folgen derselben Referenzform.
3. Bessere Wartbarkeit:
	- Felddefinitionen liegen zentral in `sys_control_dict`, Layout in `sys_framedaten`.
4. Konsistente Rechte- und Lookup-Mechanik:
	- Dropdowns/Help laufen ueber vorhandene Resolver statt Inline-Daten.
5. Klare Verantwortlichkeiten:
	- `sys_control_dict` fuer Feldverhalten,
	- `sys_framedaten` fuer Maskenaufbau,
	- `sys_dialogdaten` fuer fachliche Werte.

### 16.2 Risiken

1. Migrationsrisiko bestehender Frames:
	- Alte `configs.element_fields` muessen deterministisch in referenzierte Element-Frames ueberfuehrt werden.
2. Rueckwaertskompatibilitaet waehrend Uebergang:
	- Mischbetrieb alt/neu kann zu inkonsistentem Verhalten fuehren, wenn keine klare Prioritaetsregel existiert.
3. Datenqualitaet in `sys_control_dict`:
	- Flache Altformate oder unvollstaendige CONTROL-Payloads koennen Feldauflösung stoeren.
4. Save-Pfad-Grenzen:
	- Wenn Element-Frame Felder nicht korrekt auf `SAVE_PATH` und Zielgruppe gemappt sind, bleibt die Speicherung scheinbar ohne Effekt.
5. Betriebsrisiko durch stille Fallbacks:
	- Verborgene Fallbacks verschleiern Konfigurationsfehler und erschweren Debugging.

### 16.3 Guardrails fuer die Umstellung

1. Harte Prioritaet neu vor alt:
	- Wenn `configs.element` gesetzt ist, wird `configs.element_fields` ignoriert.
2. Keine stillen Dropdown-Fallbacks:
	- Ohne aufloesbare `configs.dropdown`-Referenz keine Optionserzeugung aus Inline-Daten.
3. Pflichtvalidierung beim Laden:
	- Element-Frame muss aufloesbar sein,
	- Referenzierter Frame muss gueltige FIELDS enthalten,
	- Feldtypen muessen in `sys_control_dict` existieren.
4. Pflichtvalidierung beim Speichern:
	- Zielpfad muss explizit und gueltig sein,
	- Fehler werden sichtbar gemeldet statt still geschluckt.

### 16.4 Migrationspfad mit wenig Besonderheiten

1. Phase A: Bestandsaufnahme
	- Alle Frames mit `configs.element_fields` identifizieren.
2. Phase B: Frame-Generierung
	- Pro Element-Definition einen echten Element-Frame in `sys_framedaten` erzeugen.
3. Phase C: Referenzumschaltung
	- `configs.element_fields` durch `configs.element` ersetzen.
4. Phase D: Kompatibilitaetsfenster kurz halten
	- Altformat nur temporaer lesen, nicht mehr schreiben.
5. Phase E: Cleanup
	- Altlogik entfernen und in `ARCHITECTURE_RULES.md` als verbindlich festschreiben.

Umsetzungsstand 01.06.2026 (abgeschlossen fuer aktive `sys_framedaten`-Faelle):

1. Alle aktiven Legacy-Bloecke `configs.element_fields` / `element_template` / `target_save_path` / `source_template_path` wurden entfernt.
2. Alle betroffenen `element_list`-Controls wurden auf `configs.element` (Frame-Referenz) umgestellt.
3. Migrationsergebnis fuer vormals aktive Legacy-Frames:
	- `886842eb-f62b-56d8-80cf-7d071264307b` -> `configs.element.key = a6c4f9b6-7b52-4f4c-8f59-3d9a4bd7a901`
	- `9f06711e-4ad8-4ea4-9837-2f40f3a6f103` -> `configs.element.key = 8d157d69-544e-5a6f-8350-68f2c9854cef`
	- `20de7493-d648-41e2-87a0-7894de95af35` -> `configs.element.key = 36fa5117-35da-578f-8d4d-94f2b1f46b8e`
	- `1f3a0e00-48bb-4a08-9cb8-7a7d52f23003` -> `configs.element.key = 3dccd4cf-58c8-506b-9e30-58b485e20491`
4. Verifikation: Es existieren keine aktiven `sys_framedaten`-Eintraege mehr mit den Legacy-Config-Schluesseln.

### 16.5 Entscheidungsregel

1. Ziel ist "so wenig Sondertechnik wie moeglich".
2. Sonderstrukturen in `configs` sind nur zulaessig, wenn sie als generische Referenz (`key`, `feld`, `table`, `gruppe`) modelliert sind.
3. Inline-Definitionsbloecke fuer komplexe Editorlogik gelten als Legacy und werden auslaufend behandelt.

### 16.6 CONFIGS-Normalform und Nicht-Zulaessigkeiten (Stand 04.06.2026)

Bestandsaufnahme (aktive Daten):

1. `sys_framedaten`: keine aktiven Treffer fuer `configs.element.key_mode`, `key_prefix`/`key_praefix`, `key_padding`.
2. `sys_control_dict`: genau ein aktiver Ausreisser gefunden:
	- Control `SYS_TABLE` (`uid=2e80a941-4444-5e08-97ed-5f544343b227`)
	- `CONTROL.CONFIGS.dropdown = {"source": "table_catalog", "limit": 500, "include_inactive": false}`

Bestandsaufnahme (nur effektiv verwendete Controls aus Frame/View-Quellen):

1. Referenzierte Control-GUIDs (auflosbar in `sys_control_dict`): 47.
2. Davon mit nicht-normalisierten `configs.*`: genau 1 (`SYS_TABLE`).
3. Aktive Verwendung des Ausreissers:
	- `sys_framedaten` Frame `WORKFLOW_TAB_ELEMENTS_EDITOR_FRAME` (`uid=a6c4f9b6-7b52-4f4c-8f59-3d9a4bd7a901`), Feld-GUID `2e80a941-4444-5e08-97ed-5f544343b227`.
4. Hinweis zur Datenlage:
	- Viele `FIELDS`-Keys in `sys_framedaten` sind technische Feld-UIDs ohne `sys_control_dict`-Datensatz; relevant fuer diese Regel sind nur effektiv aufloesbare Control-Referenzen.

Verbindliche Normalform (ab sofort):

1. Fuer `configs.element`, `configs.dropdown`, `configs.help` sind nur folgende Referenzschluessel zulaessig:
	- `key`
	- `feld`
	- `table`
	- `gruppe`
2. Diese Struktur ist fuer alle Bereiche gleich (kein bereichsspezifischer Sonderschluessel).
3. Dynamische Quellen werden separat in `configs.dropdown_source` modelliert (nicht in `configs.dropdown`).

Vertrag fuer `configs.dropdown_source`:

1. `type`: `static` | `view` | `prefix_multi_table` | `table_catalog`
2. `params`: optionale source-spezifische Parameter (`limit`, `include_inactive`, `prefix`, `table_prefix`, ...)
3. Legacy-kompatibel sind optional `source`/`source_type`, wenn `type` nicht gesetzt ist.
4. Sprachaufloesung fuer Dropdown-Texte erfolgt case-insensitive und alias-normalisiert (z. B. `de`, `DEU`, `de-de` -> `DE-DE`).
5. Dropdown-Mappings nutzen eine Parser-/Schema-Version im Cache; bei Parser-Aenderungen werden alte Cache-Eintraege automatisch verworfen und neu aufgebaut.

Nicht zulaessig (explizit):

1. `key_mode`
2. `key_prefix` / `key_praefix`
3. `key_padding`
4. In `configs.dropdown`: `source`, `limit`, `include_inactive`, `prefix`, `table_prefix`
5. In `configs.element`: bereichsspezifische GUID-Generierungsregeln statt stabiler Referenz (`key/feld/table/gruppe`)

Begruendung:

1. `configs.dropdown` bleibt eine stabile Referenzstruktur; Laufzeit-/Resolverlogik wird in `configs.dropdown_source` gekapselt.
2. `key_mode`/`key_prefix`/`key_padding` erzeugen implizite GUID-Generierungsregeln statt deterministischer Referenzierung.
3. Erlaubt bleiben nur stabile fachliche Referenzen (`key`, `feld`, `table`, `gruppe`).
4. Laufzeit-Resolver duerfen `configs.dropdown_source` transportseitig in einen effektiven Request-Config-Block ueberfuehren; persistiert bleibt die Trennung (`dropdown` vs. `dropdown_source`) verbindlich.

Uebergangsregel (kurzes Kompatibilitaetsfenster):

1. Bestehende Legacy-Eintraege duerfen zur Laufzeit noch gelesen werden.
2. Neue Schreibvorgaenge duerfen Legacy-Schluessel in `configs.dropdown` nicht mehr erzeugen.
3. Nach erfolgter Migration wird die Runtime-Validierung fuer Legacy-Schluessel auf "hart fehlerhaft" umgestellt.

Migrationsvorschlag fuer Schritt 1 (klein, risikoarm):

1. `SYS_TABLE` bleibt funktional bei Rollen-/ACL-gesteuertem Tabellenkatalog (kein Verhaltensverlust).
2. Legacy-Schluessel aus `CONTROL.CONFIGS.dropdown` nach `CONTROL.CONFIGS.dropdown_source` verschieben:
	- `source` -> `dropdown_source.type`
	- `limit`, `include_inactive` -> `dropdown_source.params.*`
3. `CONTROL.CONFIGS.dropdown` bleibt als Referenzobjekt erhalten (nur `key`, `feld`, `table`, `gruppe`; bei `table_catalog` optional leer).
4. Validieren, dass Dropdown-Aufloesung fuer `SYS_TABLE` unveraendert funktioniert.

Akzeptanzkriterium Schritt 1:

1. In aktiven `sys_framedaten` und `sys_control_dict` existieren keine `configs.element`-Sonderschluessel (`key_mode`, `key_prefix`/`key_praefix`, `key_padding`).
2. In aktiven Controls existieren keine neuen `configs.dropdown.source`/`limit`-Eintraege; dynamische Parameter stehen unter `configs.dropdown_source`.

### 16.7 Muttercontrol 666 fuer `sys_control_dict` (starr, Stand 04.06.2026)

Verbindliche Regel:

1. `sys_control_dict` UID `66666666-6666-6666-6666-666666666666` unter `daten.CONTROL` ist das Muttercontrol.
2. Dieses Muttercontrol definiert die vollstaendige, erlaubte Eigenschaftsmenge fuer Controls.
3. Eigenschaftsvergleiche fuer Pruefung/Freigabe erfolgen case-insensitive.
4. Die kanonische Schreibweise im Muttercontrol ist GROSSBUCHSTABEN.
5. Eigenschaften aus `sys_framedaten` (`daten.FIELDS.*`) und `sys_viewdaten` (`daten.SYSTEM.*`) gelten erst dann als erlaubt, wenn sie explizit im Muttercontrol aufgenommen wurden.
6. Erweiterungen in `CONTROL.CONFIGS` sind verpflichtend im Muttercontrol zu dokumentieren, bevor sie produktiv genutzt werden.

Ist-Befund (Snapshot: `database/backups/pdvm_system_snapshot_20260512_181120.jsonl`):

1. Muttercontrol (`666...`, `daten.CONTROL`) ist aktuell leer.
2. Damit fehlen aktuell alle in Frame/View verwendeten Eigenschaftsschluessel im Muttercontrol.

Gefundene Eigenschaftsschluessel aus `sys_framedaten` (`daten.FIELDS.*`, normalisiert auf GROSSBUCHSTABEN):

1. `ABDATUM`
2. `CONFIGS`
3. `CONTROL` (Struktur-/Altlastkandidat)
4. `DICT_REF`
5. `DISPLAY_ORDER`
6. `FELD`
7. `FIELD`
8. `GRUPPE`
9. `HISTORICAL`
10. `LABEL`
11. `NAME`
12. `READ_ONLY`
13. `ROOT` (Struktur-/Altlastkandidat)
14. `SELF_NAME` (Struktur-/Altlastkandidat)
15. `SOURCE_PATH`
16. `TAB`
17. `TABLE`
18. `TOOLTIP`
19. `TYPE`

Gefundene Eigenschaftsschluessel aus `sys_viewdaten` (`daten.SYSTEM.*`, normalisiert auf GROSSBUCHSTABEN):

1. `CONTROL_TYPE`
2. `DEFAULT`
3. `DISPLAY_ORDER`
4. `DROPDOWN`
5. `EXPERT_MODE`
6. `EXPERT_ORDER`
7. `FELD`
8. `FILTERTYPE`
9. `GRUPPE`
10. `LABEL`
11. `SEARCHABLE`
12. `SHOW`
13. `SORTABLE`
14. `SORTBYORIGINAL`
15. `SORTDIRECTION`
16. `TABLE`
17. `TYPE`

Kombinierte fehlende Schluessel im Muttercontrol (case-insensitive, kanonisch GROSSBUCHSTABEN):

1. `ABDATUM`
2. `CONFIGS`
3. `CONTROL`
4. `CONTROL_TYPE`
5. `DEFAULT`
6. `DICT_REF`
7. `DISPLAY_ORDER`
8. `DROPDOWN`
9. `EXPERT_MODE`
10. `EXPERT_ORDER`
11. `FELD`
12. `FIELD`
13. `FILTERTYPE`
14. `GRUPPE`
15. `HISTORICAL`
16. `LABEL`
17. `NAME`
18. `READ_ONLY`
19. `ROOT`
20. `SEARCHABLE`
21. `SELF_NAME`
22. `SHOW`
23. `SORTABLE`
24. `SORTBYORIGINAL`
25. `SORTDIRECTION`
26. `SOURCE_PATH`
27. `TAB`
28. `TABLE`
29. `TOOLTIP`
30. `TYPE`

Offene Freigabeentscheidung (naechster Schritt):

1. Es werden ausschliesslich Eigenschaften einzeln freigegeben, die im **aktuellen** Muttercontrol fehlen.
2. Bereits vorhandene Eigenschaften im Muttercontrol gelten als gesetzt und werden nicht erneut abgefragt.
3. Jede fehlende Eigenschaft wird einzeln freigegeben (`aufnehmen`/`nicht aufnehmen`).
4. Danach wird das Muttercontrol (`666...`) entsprechend erweitert.
5. Abschliessend erfolgt die Pruefung der bestehenden Dialoge auf Funktionsfaehigkeit und Bereinigung.

### 16.8 Tooltip-Referenzmodell + View-Key-Hardmigration (Stand 04.06.2026)

Verbindliche Umsetzung:

1. `sys_tooltipdaten` ist neue zentrale Tooltip-Tabelle (analog `sys_beschreibungen`/`sys_dropdowndaten`).
2. Tabelle wird inkl. Basissaetzen `000`/`555`/`666` angelegt.
3. Tooltip-Texte aus `sys_framedaten.daten.FIELDS.*.tooltip` werden nach `sys_tooltipdaten` migriert.
4. In `sys_framedaten` wird `tooltip` auf Referenzobjekt umgestellt (`table`, `key`, `feld`, `gruppe`), und in `configs.tooltips` gespiegelt.
5. Laufzeitauflosung in Dialogen liest Referenz und liefert wieder Tooltip-Text an die UI.

Viewdaten-Hardmigration (ohne Alias/Fallback):

1. `CONTROL_TYPE`/`control_type`/`type` -> `TYPE`
2. `FILTERTYPE`/`filterType` -> `FILTER_TYPE`
3. `SHOW`/`show` -> `DISPLAY_SHOW`
4. `SORTBYORIGINAL`/`sortByOriginal` -> `SORT_BY_ORIGINAL`
5. `SORTDIRECTION`/`sortDirection` -> `SORT_DIRECTION`

Wichtig:

1. Die Legacy-Keys werden aus den Daten entfernt.
2. Source-Lesewege verwenden keine Legacy-Namen mehr.
3. Migration wird ueber `backend/tools/migrate_tooltips_and_view_keys_v1.py` ausgefuehrt.

### 16.9 Harte Normalisierung `sys_control_dict` (Stand 05.06.2026)

Verbindliche Regeln:

1. `ROOT.SELF_NAME` ist case-insensitive eindeutig (keine Dubletten erlaubt).
2. `ROOT.SELF_NAME` beginnt mit Tabellenpraefix aus `CONTROL.TABLE`:
	- bei `sys_*` -> `SYS_*`
	- bei fehlender/neutraler Tabelle -> `XXX_*`
3. Jeder Datensatz in `sys_control_dict` hat unter `daten.CONTROL` exakt die Mutterstruktur.
4. Mutterstruktur wird aus dem reservierten 666er-Template uebernommen (UID `66666666-6666-6666-6666-666666666666`, Quelle: `daten.TEMPLATES.CONTROL`).
5. Bei Strukturangleichung gilt fuer Inhalte:
	- Zielwert bleibt erhalten, wenn belegt.
	- Mutterwert wird nur uebernommen, wenn Zielwert leer ist.
6. Inhalte, die durch Strukturangleichung entfallen, werden in `backup_daten.control_removed_keys` abgelegt.
7. Dubletten werden hart aufgeloest:
	- Ein Keep-UID je kanonischem `SELF_NAME`.
	- Referenzen in `sys_framedaten` und `sys_viewdaten` werden auf Keep-UID umgeschrieben.
	- Zu loeschende Controls werden mit `DEL_` markiert und danach physisch geloescht.

Umsetzungsskript:

1. `backend/tools/hard_migrate_sys_control_dict_v1.py`
2. Modi:
	- `--dry-run` (Rollback, nur Report)
	- `--apply` (persistiert Aenderungen)

Ausfuehrungsnachweis (Apply, 05.06.2026):

1. `controls_total=190`
2. `duplicate_groups=41`
3. `duplicate_retire_candidates=94`
4. `references_rows_changed=4` (+1 gezielter Follow-up-Cleanup fuer eingebettete `SELF_GUID`)
5. `controls_deleted=94`
6. `controls_structure_synced=186`
7. `controls_backup_written=60`

Validierung nach Apply:

1. `controls_active=96`
2. `duplicate_self_names=0`
3. `prefix_bad_count=0`
4. `structure_mismatch_non_template=0`
5. `rows_with_deleted_uid_refs=0` in `sys_framedaten`/`sys_viewdaten`

Reportdateien:

1. `backend/reports/hard_migrate_sys_control_dict_v1_dry_run.json`
2. `backend/reports/hard_migrate_sys_control_dict_v1_apply.json`

### 16.10 Harte Strukturregel ROOT/CONTROL + 555-ROOT (Stand 05.06.2026)

Verbindliche Regeln fuer Controls mit `CONTROL.TABLE = sys_control_dict`:

1. Top-Level in `daten` enthaelt ausschliesslich Gruppen `ROOT` und `CONTROL`.
2. Andere Gruppen (z. B. `TEMPLATES`) werden hart entfernt.
3. Entfernte nicht-leere Gruppen werden in `backup_daten.removed_top_groups` abgelegt.
4. `CONTROL` hat exakt den Keyraum des Muttercontrols (strukturelle Vollstaendigkeit).
5. Mutter `CONTROL` kommt verbindlich aus dem 666er-Template (UID `66666666-6666-6666-6666-666666666666`, Quelle: `daten.TEMPLATES.CONTROL`).
6. Befuellungsregel bleibt strikt:
	- Zielwert bleibt, wenn belegt.
	- Mutterwert wird nur gesetzt, wenn Zielwert leer ist.
7. `ROOT` wird aus dem 555er-Mutterroot abgeleitet (UID `55555555-5555-5555-5555-555555555555`).
8. `ROOT`-Keyraum ist fuer alle betroffenen Saetze identisch zum 555er-ROOT.

Umsetzung (Script-Update):

1. `backend/tools/hard_migrate_sys_control_dict_v1.py`
2. Neue Option: `--target-table sys_control_dict`

Ausfuehrungsnachweis (05.06.2026, 555-Fix Apply):

1. `root_mother_uid=55555555-5555-5555-5555-555555555555`
2. `mother_uid=66666666-6666-6666-6666-666666666666`
3. `duplicate_retire_candidates=0`
4. `controls_deleted=0`
5. `controls_structure_synced=0` (idempotenter Final-Lauf)
6. `controls_other_groups_removed=0`
7. `controls_root_synced=50`

Validierung nach Apply (`CONTROL.TABLE = sys_control_dict`, ohne Template-UIDs):

1. `scoped_rows=50`
2. `bad_groups_only_root_control=0`
3. `bad_control_keys_vs_mother=0`
4. `bad_root_keys_vs_555=0`

Reportdateien:

1. `backend/reports/hard_migrate_sys_control_dict_v1_dry_run_table_scope_555fix.json`
2. `backend/reports/hard_migrate_sys_control_dict_v1_apply_table_scope_555fix.json`

### 16.11 View-Sektionen und NO_DATA-Semantik (Stand 06.06.2026)

Verbindliche Struktur fuer `sys_viewdaten.daten`:

1. `ROOT` enthaelt View-Metadaten.
2. `**SYSTEM` enthaelt technische Spalten (z. B. `uid`, `name`).
3. `<ROOT.TABLE in UPPERCASE>` enthaelt fachliche Spalten der Root-Tabelle (z. B. `ASY_BENUTZER`).

Verbindliche NO_DATA-Regel (vereinfacht):

1. `NO_DATA=true`, wenn `ROOT.NO_DATA` explizit true ist.
2. Sonst gilt effektiv `NO_DATA=true`, wenn neben SYSTEM-Sektionen keine fachlichen Spalten angeboten werden.
3. Fachliche Spalten sind alle Control-Sektionen ausser `ROOT`, `SYSTEM` und `**SYSTEM`.

Projektionsregel:

1. Matrix-Projektion bleibt linear.
2. SYSTEM-Spalten duerfen technisch mitlaufen, zaehlen aber nicht als fachliche Datenbasis.
3. Bei effektivem `NO_DATA=true` wird die Root-Tabellen-Sektion nicht in die Controls-Origin uebernommen.
4. Table-Override-Guard nutzt den effektiven NO_DATA-Wert (nicht nur das rohe ROOT-Flag).

Implementierungsstatus:

1. Runtime umgesetzt in `backend/app/core/view_state_service.py` (`derive_effective_no_data`).
2. Verwendet in `backend/app/core/view_matrix_service.py` und `backend/app/api/views.py`.

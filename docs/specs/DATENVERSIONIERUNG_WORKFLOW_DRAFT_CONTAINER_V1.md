# Datenversionierung Workflow Draft-Container V1

Status: Vorschlag zur Umsetzung (Optimierung Ziffer 2)

## 1. Ziel

Diese Spezifikation definiert die persistente Ablage laufender, nicht abgeschlossener Workflows in dedizierten Draft-Containern.

Ziele:

1. Laufende Workflows robust und transaktionssicher persistieren.
2. Resume/Weiterarbeit ueber Sessions hinweg ermoeglichen.
3. Finaldaten strikt von Draftdaten trennen.
4. Build-Schritt als einzige Stelle fuer produktive Schreibvorgaenge etablieren.

## 2. Leitentscheidung

Draft-Nutzdaten werden nicht primaer in `sys_systemsteuerung` gespeichert.

Stattdessen:

1. Dedizierte Draft-Tabellen halten komplette Workflow-Daten.
2. `sys_systemsteuerung` speichert nur leichte Session-Metadaten (Pointer, last_opened, UI-State).

Begruendung:

1. Bessere Skalierung bei groesseren JSON-Strukturen.
2. Klare Trennung von Runtime-State und finalen Artefakten.
3. Einfachere Validierung, Versionierung und Bereinigung.
4. Sauberes Resume mehrerer paralleler Workflows pro Benutzer.

## 3. Tabellenmodell (pdvm_system)

### 3.1 dev_workflow_draft

Ein Datensatz je Workflow-Instanz.

Pflichtfelder in `daten.ROOT`:

1. `DRAFT_GUID` (uuid)
2. `WORKFLOW_TYPE` (`dialog_builder` | `release_patch`)
3. `STATUS` (`draft` | `in_review` | `validated` | `approved` | `built` | `archived`)
4. `OWNER_USER_GUID`
5. `MANDANT_GUID`
6. `CREATED_AT`, `UPDATED_AT`
7. `TITLE`

Optionale Felder:

1. `LOCKED_BY`, `LOCKED_AT`
2. `LAST_EDITOR_USER_GUID`
3. `REVISION` (optimistic locking)

### 3.2 dev_workflow_draft_item

Sub-Strukturen je Draft (append/update pro Bereich).

Pflichtfelder in `daten.ROOT`:

1. `DRAFT_GUID`
2. `ITEM_TYPE` (`setup` | `tabs` | `dialogdata` | `framedata` | `viewdata` | `dictionary_selection` | `release_assignment` | `snapshot`)
3. `ITEM_KEY` (z. B. `TAB_01`, `dialog_guid`, `view_guid`)
4. `PAYLOAD` (JSON)
5. `UPDATED_AT`

Hinweis:

1. Mehrere Items pro Draft sind erlaubt.
2. `ITEM_TYPE + ITEM_KEY` ist innerhalb einer Draft eindeutig.

### 3.3 sys_systemsteuerung (nur Pointer)

Verwendung fuer leichte User-Metadaten:

1. `WORKFLOW_LAST_OPENED_DRAFT_GUID`
2. `WORKFLOW_RECENT_DRAFTS` (kleine Liste)
3. `WORKFLOW_UI_STATE` (Tab, Schritt, Filter)

Keine vollstaendigen Draft-Nutzdaten in `sys_systemsteuerung`.

## 4. Workflow-Typen

### 4.1 dialog_builder

Inhalte:

1. Setup (Name, Dialog-Typ, Zieltable)
2. Tab-Definition (hinzufuegen, aendern, loeschen)
3. Tab-Inhalte:
   1. `view` -> View-Definition
   2. `edit`/`acti` -> Frame-Definition
4. Dictionary-Auswahl als separater Pflegebereich
5. Build -> validieren und final schreiben

### 4.2 release_patch

Inhalte:

1. Setup (Release/Patch, Titel, Beschreibung)
2. Zuordnung von Dialogen
3. Snapshot-Fixierung je freigegebenem Dialogzustand
4. Build -> finales Paket + optional `gilt_bis`

## 5. Zustandsmaschine

Verbindliche Statuswerte:

1. `draft`
2. `in_review`
3. `validated`
4. `approved`
5. `built`
6. `archived`

Uebergaenge:

1. `draft -> in_review -> validated -> approved -> built`
2. Rueckspruenge zu `draft` sind vor `built` erlaubt.
3. `built` ist fachlich abgeschlossen (nur archivieren, nicht frei editieren).

## 6. Build-Strategie (Write Gate)

Finale Writes erfolgen ausschliesslich im Build-Schritt.

Build-Ablauf:

1. Draft laden (Header + Items).
2. Konsistenzpruefung ausfuehren:
   1. GUID-Referenzen
   2. Modul/GUID-Konsistenz je Tab
   3. Frame- und View-Strukturregeln
   4. Dictionary-Aufloesung
3. Bei Erfolg: transaktional in `sys_dialogdaten`, `sys_viewdaten`, `sys_framedaten` schreiben.
4. Draft auf `built` setzen und Build-Metadaten protokollieren.

Fehlschlag:

1. Keine Teilwrites.
2. Draft bleibt in bearbeitbarem Status.
3. Validierungsfehler strukturiert rueckmelden.

## 7. Resume und Start-View

Beim Menueaufruf fuer Workflow-Builder wird zuerst eine Uebersicht offener Drafts angezeigt.

Start-View Mindestfunktionen:

1. Eigene offene Drafts listen.
2. Entwurf neu anlegen.
3. Entwurf fortsetzen.
4. Optional: archivierte Drafts anzeigen.

## 8. Abschluss und Aufraeumen

Nach erfolgreichem Build:

1. Draft bleibt auditierbar erhalten (Status `built`).
2. Pointer in `sys_systemsteuerung` werden bereinigt/aktualisiert.
3. Optional zeitgesteuerte Archivierung oder Retention-Regel.

## 9. API-Rahmen (Service-Layer)

Erforderliche Service-Funktionen:

1. `create_draft(workflow_type, owner, mandant, title)`
2. `update_draft_item(draft_guid, item_type, item_key, payload)`
3. `get_draft(draft_guid)`
4. `list_open_drafts(owner, mandant)`
5. `validate_draft(draft_guid)`
6. `build_draft(draft_guid)`
7. `archive_draft(draft_guid)`

Regeln:

1. Keine SQL-Logik in Routern.
2. Alle Build-Schreibvorgaenge in einer Transaktion.
3. Berechtigungen zentral ueber Security-Layer.

## 10. Architekturkonformitaet

Diese Spezifikation ist kompatibel zu den bestehenden ArchitectureRules:

1. Service-Layer statt Router-SQL.
2. Deterministische, validierbare Datenstrukturen.
3. Klare Trennung von Entwurfsdaten und Finaldaten.
4. Build als kontrollierter, transaktionaler Commit.

## 11. Migrationspfad

Empfohlene Einfuehrung in 3 Schritten:

1. Tabellen + Service-Basis einfuehren (ohne UI-Umbruch).
2. Workflow-UI auf Draft-Container umstellen, `sys_systemsteuerung` nur noch als Pointer.
3. Build-Gate voll aktivieren und alte direkte Zwischenwrites abschalten.

## 12. Akzeptanzkriterien

1. Laufende Workflows sind nach Session-Ende vollständig fortsetzbar.
2. Vor Build werden keine Finaltabellen geschrieben.
3. Build schreibt finale Dialog/View/Frame-Daten transaktional.
4. Nicht abgeschlossene Workflows sind in einer Start-Uebersicht auswählbar.
5. Architekturregeln (kein Router-SQL, zentrale Guards) bleiben eingehalten.

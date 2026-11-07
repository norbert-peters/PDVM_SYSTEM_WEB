# PDVM Plan: Optimierung und Systemdaten (V1)

Status: Phase 0/1/2/3/4/5 abgeschlossen. Das System ist noch nicht produktiv, es gibt keine Zeitvorgaben.
Verbindliche Grundlage: [ARCHITECTURE_RULES.md](../ARCHITECTURE_RULES.md).

## Entscheidungen
- Reihenfolge: erst Code optimieren, dann Systemdaten erstellen.
- DB-Zugriff: lokale DB per Skript/API (Zugangsdaten aus `.env`), immer mit Backup und Dry-Run.
- Reservierte Sätze (UID-Serien `0...`, `5...`, `6...`) werden nicht ohne ausdrückliche Freigabe geändert.
- Neuanlagen ausschließlich über den Draft-Flow (Regel 2.5a).

## Stand Phase 0/1 (06.11.2026)
- Repo wurde nach `C:\Users\norbe\dev\PDVM_SYSTEM_WEB` verschoben (außerhalb OneDrive; `C:\dev` war ohne Adminrechte nicht anlegbar). Git funktioniert dort (`git status`, `git fsck` ok, 7 offene Änderungen aus früherer Arbeit sind erhalten). `.venv` neu erstellt mit identischen Paketversionen, `node_modules` kopiert, Tests und `tsc --noEmit` liefern die gleichen Ergebnisse wie vorher.
- Verifikation der Backend-Befunde: Auth-Verbindung pro Aufruf, Dropdown-N+1, Python-seitige View-Matrix und Router-DB-Zugriffe bestätigt (siehe Bericht unten). Die Vermutung "fehlende link_uid-Indizes" war falsch: auf den System-Tabellen existieren Indizes auf `link_uid`, `name`, `modified_at`, `historisch`, `sec_id` und `daten` (GIN).
- Systemdaten-Audit (read-only, wiederholbar): `backend/tools/audit_system_data.py`, Ergebnis in [reports/AUDIT_SYSTEMDATEN_2026-11-06.md](reports/AUDIT_SYSTEMDATEN_2026-11-06.md).
- Laufzeitmessung (lokal, Mandant "Filiale Test 1", Skript `backend/tools/measure_runtime.py`, Zugangsdaten nur per Umgebungsvariablen `PDVM_USER`/`PDVM_PASSWORD`):
  - Login 2,9 s, Mandantenwahl 2,0 s (kalt, einmalig je Sitzung) - Kandidaten für Phase 4 (Auth-Pool).
  - Warm: Startmenü 13 ms, App-Menü 22 ms, Dialog-Definition 16 ms (erster Aufruf 2,3 s), Dialog-Zeilen 38 ms, View-Matrix 32 ms (max. 118 Zeilen). Die Laufzeit ist bei diesem Datenumfang unkritisch; der Gewinn aus Phase 4 liegt vor allem im Kaltstart und in der Skalierung.
  - 43 Dialog-Einstiege in den App-Menüs: 11 Aufrufe von `/rows` liefern HTTP 500 (`UndefinedTableError`), weil Menüeinträge auf nicht existierende Tabellen zeigen (`sys_security`, `sys_systemsteuerung`, `sys_error_log`, `sys_ext_table_man`, `sys_anwendungsdaten`, `sys_benutzer`). Zwei Defekte: falsche Tabellennamen in den Menüdaten, und ein fehlender Fehlerabfang im Router (muss 4xx statt 500 liefern).
  - 2 View-Matrix-Aufrufe liefern HTTP 400 `VIEW_DATA_INVALID` (Audit Regel 1.21: Views ohne Datengruppe neben ROOT). Draft-Dialoge liefern ohne `draft_guid` erwartungsgemäß 400.
- Entscheidungen (06.11.2026), Umsetzung in Phase 2/3/5:
  - Muttercontrol: Daten nach `daten.CONTROL` verschieben, Code anpassen (Regel 1.10a bleibt gültig).
  - `FIELD`/`FELD`: `FELD` entfernen, `FIELD` ist die Wahrheit (Regel 1.12b).
  - `TABLE_INFO` aus Fachdatensätzen entfernen, nur in 666 führen (Regel 1.12c).
  - Menüeinträge mit nicht existierenden Tabellen: Menüdaten korrigieren (`msy_*`/`asy_*` bzw. vorhandene Tabellen); zusätzlich Router-Fehlerabfang (4xx statt 500).
  - Alle Datenänderungen nur mit Backup, Dry-Run und Protokoll (reservierte UID-Serien nicht ohne Freigabe).
- Phase 1 ist damit abgeschlossen.

## Stand Phase 2 (06.11.2026)
1. Regeldokument bereinigt: Doppelte Nummern aufgelöst. Name/SELF_NAME ist jetzt Regel 1.22, GILT_BIS/SELF_GILT_BIS ist Regel 1.23 (am Ende von Kapitel 1). Die Regeln 1.11 (Schutz Basis-GUIDs) und 1.12 (Basissätze) behalten ihre Nummern, weil 1.12a-c daran hängen. Die zweiten 2.8/2.9 sind jetzt 2.13/2.14. Der verirrte Dialog-V2-Text am Ende von 2.12 steht wieder in 2.7.
   - 1.10: `CONTROL.FELD` ist Alias und unzulässig, `FIELD` kanonisch.
   - 1.10a (Entscheidung Variante A): Muttercontrol liegt in `daten.CONTROL` (Prüfquelle) und identisch in `daten.TEMPLATES.CONTROL` (Neuanlage-Vorlage, 1.13). Seeder und Audit prüfen die Synchronität.
   - Audit-Tool nutzt die neuen Nummern 1.22/1.23.
   - Schema-Quelle der Wahrheit: `ARCHITECTURE_RULES.md` > `docs/specs/PDVM_LINEAR_SCHEMA_V1.md` (FIELD ist dort bereits kanonisch) > Spezialspezifikationen.
2. Seeder und Prüfung für Basissätze: `backend/tools/seed_base_records.py` (Dry-Run als Standard, `--check`, `--apply --confirm-backup`, Aenderungen an vorhandenen 000/555/666-Sätzen nur mit `--allow-reserved-changes`, Snapshot vor dem Schreiben, eine Transaktion je DB). Unit-Tests: `backend/test_seed_base_records.py` (7 Tests). Praxistest `--apply` auf einer Wegwerf-Kopie von `pdvm_standard`: 16 Änderungen, danach Seeder `--check` und Audit ohne Befund. Die Kopie ist wieder gelöscht, die echten DBs sind unverändert. Dry-Run auf den echten DBs: [reports/SEED_BASISSAETZE_DRYRUN_2026-11-06.md](reports/SEED_BASISSAETZE_DRYRUN_2026-11-06.md) (53 Änderungen; Ausführung in Phase 5 Schritt 1 nach Backup und Freigabe).
   - Ursache der Basissätze mit falscher UID (`msy_anwendungsdaten`, `msy_systemsteuerung`): ältere Anlage-/Migrationslogik (Programmfix in Phase 3 prüfen).
3. Skripte: 45 Einmal-Skripte aus `backend/` und dem Repo-Root nach `backend/_archive_scripts/` verschoben, Doku-Verweise ergänzt, `pytest.ini` bereinigt (Baseline unverändert: 4 bekannte Fehlschläge). `backend/tools/README.md` beschreibt aktive Werkzeuge. Die historischen `phase*`/`migrate_*` in `backend/tools` bleiben vorerst, bis die Verweise in `docs/specs/` angepasst sind.

## Frühere Stände (05.11.2026)
- Backups aller 7 DBs (auth, pdvm_system, pdvm_standard, mandant, filale_test_1, filiale_test_2, ganz_neu1) liegen in `C:\Users\norbe\PDVM_BACKUPS\2026-11-05_phase0` (außerhalb des Repos).
- `backend/pytest.ini` angelegt. Baseline: 26 passed, 3 skipped, 4 failed (Details unten).
- Git: `.git` liegt in OneDrive und hat Reparse-Point-Attribute; `git` erkennt das Repo nicht. Empfehlung: Repo aus OneDrive herauslösen.
- Systemdaten `pdvm_system`: 13 Tabellen, ca. 280 Sätze; jede fachliche Tabelle hat 000/555/666. Es fehlen die Basissätze in `msy_anwendungsdaten`, `msy_systemdaten`, `msy_systemsteuerung`.
- AUTH-DB enthält neben `asy_*` noch Legacy-Tabellen `sys_benutzer`, `sys_mandanten`, `sys_feld_aenderungshistorie` (Regel 1.7a: nur `asy_*` zulässig).

## Phase 0: Absicherung
1. Backup AUTH-, System- und Mandanten-DB; Export-Verfahren für Systemdaten.
2. Test-Baseline: pytest-Konfiguration, vorhandene Tests ausführen.
3. Git-Status klären (`.git` vorhanden, `git` meldet "not a git repository").

## Phase 1: Analyse vertiefen (nur lesend)
1. Befunde aus der Erstanalyse gegen den Code verifizieren und mit Messwerten belegen.
2. Messung: Login, Menüaufbau, Dialog öffnen, View-Matrix, Dropdowns.
3. Ist-Inventar der Systemdaten je Tabelle inkl. Regelprüfung (000/555/666, Muttercontrol, ROOT/SELF_*, gilt_bis, I18N, Dialog/Frame/View-Validierung).

## Phase 2: Fundament
1. Regeldokument bereinigen (doppelte Nummern 1.10-1.12 und 2.8/2.9), Schema-Dateien zu einer Quelle der Wahrheit vereinheitlichen.
2. Seeder und Prüfung für Basissätze 000/555/666.
3. Skripte aufräumen: einmalige Skripte ins Archiv, `backend/tools` als einzige Werkzeugablage.

## Phase 3: Architekturkonformität im Code (umgesetzt 06.11.2026)
Plan: Schreibzugriffe über `central_write_service`, Router-SQL in Services, alte CRUD-Schicht stilllegen. Ergebnis:
1. Schreibzugriffe: `PdvmCentralDatabase.save_all_values`, die GCS-Initialanlage (`msy_systemsteuerung`/`msy_anwendungsdaten`/`msy_layout`) und `ControlDictService` (Neuanlage und MODUL-Wechsel, vorher Roh-SQL ohne Historie) schreiben über `central_write_service`. Das tote Modul `pdvm_central_mandanten.py` (Roh-SQL, nirgends verwendet) liegt jetzt in `backend/_archive_scripts/`. Bewusst direkt bleiben: Draft-Container, Release-Tabellen, Mandanten-DB-Wartung, `asy_benutzer`-Sonderpfad, Änderungshistorie (in `ARCHITECTURE_RULES.md` 1.1 dokumentiert).
2. Router-SQL in Services: `admin.py` -> `db_admin_service.py`, `mandanten.py` -> `mandant_db_provisioning_service.py`, `dialogs.py` -> `WorkflowDraftService.update_draft_root_fields` und `dialog_service.list_public_table_names`. Test: `test_router_sql_free.py` (32 Tests), `test_architecture_guard.py`.
3. Alte CRUD-Schicht stillgelegt: `PdvmDatabase` in `core/database.py` entfernt (`DatabasePool` und URL-Helfer bleiben). `api/tables.py` liest jetzt über die zentrale `PdvmDatabase` mit den GCS-Pools (vorher nur für `asy_*` lauffähig, sonst 500).
4. Fehlerbehandlung und Härtung: Fehler "Tabelle existiert nicht" -> HTTP 404 (`error_handlers.py`, 11 vorherige 500er verschwunden). Tabellennamen werden als einfache Bezeichner validiert (400 statt SQL-Fragment aus der URL). `tables.py` mappt `ValueError` auf 400.
5. Programmfix 1.12c: Die Neuanlage entfernt `TABLE_INFO` aus der kopierten 555-Basis. Der Seeder entfernt `TABLE_INFO` auch aus vorhandenen 555-Sätzen (Dry-Run: siehe aktualisierten Bericht).
6. Verifikation: Tests 71 bestanden, dieselben 4 bekannten Fehlschläge wie in der Baseline. Live-Smoke mit Testbenutzer: Login, Menü, 43 Dialog-Einstiege, View-Matrix, `/api/tables/*` (sys/msy/asy lesen, ungültige Namen 400, unbekannte Tabelle 404), `/api/admin/*`, `/api/mandanten/list` ok.
7. Offen für Phase 5 (Daten und Code gemeinsam): `FELD`-Alias wird noch von `ControlTemplateService.create_new_control` und `ControlDictService.update_control` mitgeschrieben (Regel 1.12b). Das Entfernen erfolgt zusammen mit der Datenbereinigung von `sys_control_dict`. Die Lese-Fallbacks bleiben bis dahin.


## Phase 4: Performance (umgesetzt 07.11.2026)
Plan: Auth-Pool, Request-Cache für Definitionen, gebündelte Dropdowns, DB-seitige Matrix-Pipeline, Indizes, große Dateien aufteilen. Ergebnis:
Messgrundlage: `backend/tools/measure_runtime.py`, `profile_cold_path.py` (zählt Verbindungsaufbauten je Aufrufer). Befund: Ein neuer DB-Verbindungsaufbau kostet hier ca. 150 ms (Postgres unter Windows); die Zeiten kamen fast vollständig aus Verbindungsaufbau und Einzelabfragen, nicht aus Python-Rechenzeit.

| Messung | vorher | nachher |
|---|---|---|
| Mandantenwahl (kalt, erster Login im Prozess) | 2,0-2,4 s | ca. 0,9 s |
| Mandantenwahl (jeder weitere Login) | 2,0-2,4 s | 22-70 ms |
| Dialog-Definition "Dictionary pflegen" (31 Controls) | 137 ms, 64 Abfragen | 25 ms, 3 Abfragen |
| Login | 2,9 s | 0,4 s (bcrypt ca. 330 ms ist gewollt) |

Der Login-Wert von 2,9 s war überwiegend ein Messartefakt: `localhost` kostet unter Windows je neuer TCP-Verbindung ca. 0,2 s (httpx bis 2 s, IPv6-Fallback). Mit `127.0.0.1` sind es 0,4 s. Vite-Proxy und Messskript nutzen deshalb `127.0.0.1`.

1. Pools: Neues `app/core/pool_registry.py` (ein gemeinsamer Pool je URL und Prozess, Schließen beim App-Shutdown). GCS-Sessions teilen System- und Mandanten-Pool (vorher je Login 2 neue Pools mit je 2 Verbindungen, beim Logout geschlossen). `PdvmDatabaseService` (Mandanten-/Layout-Zugriffe, vorher eine Verbindung je Aufruf) und `ConnectionManager.get_mandant_config` nutzen Pool statt Einzelverbindung. Existenzprüfung der Mandanten-DB und Wartung nutzen die gemeinsamen Pools.
2. Mandanten-Wartung (`run_mandant_maintenance`): Wird bei unveränderter Mandanten-CONFIG (u. a. FEATURES) für 15 Minuten übersprungen, eine geänderte CONFIG löst sofort einen neuen Lauf aus; Läufe mit Fehlern werden nicht gemerkt.
3. Definitionen laden (N+1 beseitigt): `PdvmDatabase.load_control_definitions` lädt alle Controls eines Frames/einer View mit einer Abfrage (`dialog_service`-Frame-Auflösung und `resolve_view_control_references`). Die reservierten Control-Templates 555/666 werden 30 s gecacht und bei jedem Schreibzugriff auf `sys_control_dict` sofort verworfen. Auf einen eigenen Cache mit `modified_at`-Prüfung habe ich verzichtet: Die Prüfung kostet eine Abfrage und spart damit gegenüber dem Laden nichts; die verbleibenden Dialogdefinitionen laufen warm in 10-25 ms.
4. Dropdowns/View-Matrix: Die Controls der Matrix kommen jetzt über den Bulk-Pfad. Dropdowns werden je Dropdown-Control (nicht je Zeile) aufgelöst und sind bereits gecacht (Test `test_dropdown_source_guardrails`).
5. Filter/Sort/Group der View-Matrix bleiben in Python: Mit 20 000 synthetischen Zeilen kosten Filter 80 ms, Sortierung 110 ms, Leer-Prüfung 60 ms. Größte Tabelle heute: 28 Fachsätze (Historientabellen ca. 2,5 k). Eine DB-seitige Verlagerung lohnt erst bei Tabellen über ca. 50 000 Zeilen.
6. Indizes: `gilt_bis` zu den Standard-Indizes ergänzt (neue Tabellen und beim Wartungslauf für bestehende). `link_uid`, `name`, `modified_at`, `historisch`, `sec_id` und `daten` (GIN) sind bereits vorhanden.
7. Große Dateien (reine Verschiebungen, Namen bleiben aus den Ursprungsmodulen importierbar): `dialogs.py` 2042 -> 1258 Zeilen (`dialogs_models.py`, `dialog_api_helpers.py`, `dialog_create_helpers.py`), `dialog_service.py` 2051 -> 1244 (`dialog_frame_helpers.py`, `dialog_runtime_config.py`), `pdvm_datenbank.py` 1393 -> 1258 (`pdvm_mandant_provisioning.py`).
8. Tests: 84 bestanden, dieselben 4 bekannten Fehlschläge; neu `test_pool_registry.py`, `test_performance_caches.py`.

## Phase 5: Systemdaten erstellen (umgesetzt 07.11.2026)
Freigabe für Änderungen an reservierten Sätzen (UID-Serien 0…/5…/6…) durch den Nutzer erteilt (System noch nicht produktiv).

Ergebnis:
- Backup aller 7 DBs (pg_dump) in `C:\Users\norbe\PDVM_BACKUPS\2026-11-07_phase5\`; Snapshots je Schritt in `backend/reports/`.
- Basissätze 000/555/666: Seeder auf allen 6 DBs angewandt, `--check` = 0 Änderungen. Seeder-Fehler bei Float-`gilt_bis` und Tabellen mit eigenem Layout behoben; Nicht-Standard-Tabellen (z. B. `msy_update_history`) werden übersprungen.
- `sys_control_dict`: `FELD` entfernt, Namen nach Regel 1.10 (`<PREFIX>_<FIELD>`, bei Kollision `<PREFIX>_<GRUPPE>_<FIELD>`, dann `_N`) korrigiert, 120 Sätze normalisiert, 5 Dubletten gelöscht. `FELD`-Writer in `ControlTemplateService`/`ControlDictService` entfernt (Lese-Fallbacks bleiben).
- Frames: 62 neue Controls für inline definierte Felder, 21 Frames migriert, Layout-Keys GROSS. Absicherung per Golden-Master: verbleibende Abweichungen nur `read_only` (jetzt aus dem Control, erwünscht) und `gruppe ''` → `root`.
- Menüs auf vorhandene Tabellen korrigiert (`sys_security` → `msy_security`, `sys_benutzer` → `asy_benutzer` usw.), Views erhalten `**SYSTEM`, 3 leere Test-Dialoge gelöscht, 2 Dialoge korrigiert, Release-Tabellen über `ReleaseService.ensure_release_tables` angelegt.
- Ursache der Basissätze mit falscher UID: Die Mandanten-Wartung `_rekey_row_uids_for_link_tables` schlüsselte 000/555/666 in `msy_anwendungsdaten`/`msy_systemsteuerung` auf Zufalls-UIDs um. Behoben (reservierte UIDs ausgeschlossen), Test `test_maintenance_rekey.py`. Verifiziert: Mandantenwahl auf `filale_test_1` lässt den Seeder-`--check` bei 0.
- Dokumentierte Ausnahmen (Regeln 1.10/1.10b): benannte Struktureinträge in `element_list`-Frames, Kleinschreib-Datenschlüssel `sys_menudaten.MENU`, EDIT_TYPE `menu`/`edit_control`/`import_data` als Sondertypen.
- Abschluss-Audit: 0 Befunde ([reports/AUDIT_SYSTEMDATEN_2026-11-07_final.md](reports/AUDIT_SYSTEMDATEN_2026-11-07_final.md)). Validatoren `validate_linear_schema_v1`, `validate_edit_type_contracts_v1`, `dialog_view_frame_consistency_analyzer_v1` bestanden. Tests: 95 bestanden, 2 übersprungen, dieselben 4 bekannten Fehlschläge; `tsc --noEmit` im Frontend fehlerfrei.
- Offen: `/api/admin/tables/<unbekannte DB>` liefert 500 (nicht angefasst); I18N/Tooltips/Layout/Themes wurden nur auf Regelkonformität geprüft, nicht inhaltlich neu erstellt.

Ursprüngliche Reihenfolge (nach Abhängigkeiten):
1. Tabellen-Basissätze 000/555/666
2. `sys_systemdaten`
3. `sys_control_dict` (Muttercontrol als Basis)
4. I18N, Dropdowns, Tooltips, Beschreibungen
5. `sys_viewdaten`
6. `sys_framedaten`
7. `sys_dialogdaten`
8. `sys_menudaten`
9. Layout und Themes
10. Mandanten-Einstellungen (Anwendungsdaten, `msy_*`)
11. Abschließender Gesamt-Audit

## Arbeitsweise
Datenänderungen als reproduzierbare Skripte mit Dry-Run, Backup, Validierung und Protokoll.

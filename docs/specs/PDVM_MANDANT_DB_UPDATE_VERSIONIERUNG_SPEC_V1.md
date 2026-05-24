# PDVM Mandant-DB Update + Versionierung V1

Status: Ziel-Spezifikation mit initialer Umsetzung
Datum: 2026-05-20
Scope: Wiederholbare Migration/Updates von bestehenden Mandanten-Datenbanken auf neue Release-Staende.

## 1. Ausgangspunkt

1. AUTH-DB und SYSTEM-DB gelten im aktuellen Zielbild als initial einmalig bereitgestellt.
2. Der operative Update-Bedarf liegt primaer in Mandanten-Datenbanken.
3. Nach der grossen Strukturmigration ist der naechste Schritt ein standardisiertes Updateverfahren,
   das Schema + Datenanpassungen kontrolliert in eine Ziel-Mandanten-DB uebertraegt.

## 2. Ziel

1. Ein einheitliches DB-Updateverfahren fuer Mandanten schaffen.
2. Updates in drei Arten trennen: Source, Datenbank, Daten.
3. Mandantenstand jederzeit ueber Versionen und Run-Historie nachvollziehbar machen.
4. Updates idempotent, dry-run-faehig und mit klaren Abbruchkriterien ausfuehrbar machen.

## 3. Updatearten (verbindliche Taxonomie)

## 3.1 SOURCE_UPDATE

Definition:
1. Aenderung am ausliefernden Quellstand (Backend/Frontend/Tools/Specs),
   die potentielle Auswirkungen auf Mandanten-DB-Updatepfade hat.

Pflicht-Metadaten:
1. source_version (z. B. git tag oder release id)
2. source_commit
3. source_hash (optional verdichtete Artefakt-Signatur)

Hinweis:
1. SOURCE_UPDATE ist Trigger-/Kontextebene, nicht direkt die fachliche DB-Transformation.

## 3.2 DATABASE_UPDATE

Definition:
1. Strukturbezogene Aenderungen an Mandanten-DBs (DDL, Tabellenstruktur, Indizes,
   technische Pflichtfelder, systematische Strukturangleichung wie 555/666-Regeln).

Beispiele:
1. neue Tabelle anlegen
2. Spalte/Index hinzufuegen
3. technische ROOT-Felder angleichen
4. STRUCT_VERSION_APPLIED synchronisieren

## 3.3 DATA_UPDATE

Definition:
1. Inhaltsbezogene Datenmigrationen innerhalb bestehender Struktur.

Beispiele:
1. Werte umschluesseln
2. Daten in neue Gruppen verschieben
3. Sprachwerte normalisieren
4. backup_daten.MIGRATION_BACKUP bei Feldentfall befuellen

## 4. Versionierungsmodell (Mandantenbezogen)

Jeder Mandant fuehrt drei Versionsachsen:
1. SOURCE_VERSION
2. DB_SCHEMA_VERSION
3. DATA_MODEL_VERSION

## 4.1 Versionformat

Empfehlung V1:
1. semver-nah fuer SOURCE_VERSION (z. B. v2.1.0)
2. monotoner Zielstand fuer DB_SCHEMA_VERSION (z. B. db.2026.05.20.01)
3. monotoner Zielstand fuer DATA_MODEL_VERSION (z. B. data.2026.05.20.01)

## 4.2 Zustandsobjekt je Mandant

Minimale Felder:
1. mandant_guid
2. source_version_current
3. db_schema_version_current
4. data_model_version_current
5. updated_at_utc
6. last_successful_run_id

## 5. Laufmodell (Update-Run)

## 5.1 Standardphasen

1. PRECHECK
   - Verbindungscheck, Rechtecheck, erwartete Tabellen vorhanden.
2. PLAN
   - Delta-Ermittlung zwischen Ist-Version und Ziel-Version.
3. DRYRUN (optional, standardmaessig empfohlen)
   - keine persistente Aenderung, nur Impact-Report.
4. APPLY
   - DATABASE_UPDATE und/oder DATA_UPDATE ausfuehren.
5. VALIDATE
   - Integritaets-/Regelchecks, z. B. keine offenen Pflichtverletzungen.
6. FINALIZE
   - Versionsfelder aktualisieren, Run abschliessen.

## 5.2 Abbruchkriterien (V1)

1. max_db_errors > 0 erreicht
2. Pflichttabellen fehlen
3. nicht aufloesbare Referenzverletzung
4. Validierung fehlgeschlagen

## 5.3 Idempotenz

Regeln:
1. Jeder Schritt muss bei Wiederholung deterministisch sein.
2. Bereits erfolgreich angewendete Einzelschritte duerfen keinen erneuten Seiteneffekt erzeugen.
3. Resume ab letztem stabilen Checkpoint muss moeglich sein.

## 6. Persistenz fuer Steuerung und Historie

## 6.1 Update-State Tabelle (Mandanten-DB)

Empfohlener Name:
1. msy_update_state

Minimalfelder:
1. mandant_guid
2. source_version_current
3. db_schema_version_current
4. data_model_version_current
5. last_successful_run_id
6. modified_at

## 6.2 Update-History Tabelle (Mandanten-DB)

Empfohlener Name:
1. msy_update_history

Minimalfelder:
1. run_id
2. mandant_guid
3. source_version_target
4. db_schema_version_target
5. data_model_version_target
6. run_status (running/success/failed/aborted)
7. started_at_utc
8. ended_at_utc
9. step_name
10. error_count
11. warning_count
12. report_json

Hinweis:
1. Bestehendes Monitoring (z. B. msy_batch_job_monitoring) kann angebunden werden,
   ersetzt aber nicht den mandantenspezifischen Versionszustand.

## 7. Sicherheit und Datenintegritaet

1. Keine destruktiven Updates ohne Backup-/Recovery-Strategie.
2. Bei Feldentfall gilt additive Sicherung in backup_daten.MIGRATION_BACKUP.
3. AUTH-DB und SYSTEM-DB werden in diesem Zyklus nicht als wiederkehrende Update-Ziele behandelt.
4. Mandanten-Updates laufen transaktional, soweit der jeweilige Schritt dies erlaubt.

## 8. Tooling-Rahmen (V1)

Geplante Tool-Bausteine:
1. backend/tools/mandant_update_plan_v1.py
2. backend/tools/mandant_update_apply_v1.py
3. backend/tools/mandant_update_validate_v1.py
4. backend/tools/mandant_update_report_v1.py

Gemeinsame CLI-Parameter (Mindeststandard):
1. --mandant-guid
2. --source-version-target
3. --db-schema-version-target
4. --data-model-version-target
5. --dry-run
6. --max-db-errors
7. --max-batches
8. --output

## 9. Akzeptanzkriterien fuer V1

1. Ein Ziel-Mandant kann von Ist-Stand auf Zielstand aktualisiert werden.
2. Nach Run ist Versionszustand je Mandant konsistent und nachvollziehbar.
3. Run-Historie ist mit Ergebnis und Fehlern dokumentiert.
4. Wiederholter Run ohne neue Deltas erzeugt keine Seiteneffekte.
5. Fehlgeschlagene Runs brechen kontrolliert ab und sind reproduzierbar analysierbar.

## 10. Abgrenzung zu Infos-Punkt 10

1. Das infos_translation Overlay ist bewusst vertagt.
2. Prioritaet liegt auf dem Mandanten-DB-Updatepfad (Versionierung + Datenanpassung).
3. Overlay-Entscheidung wird nach Stabilisierung des Updatepfads erneut aufgenommen.

## 11. Naechste konkrete Umsetzungsschritte

1. [x] V1 SQL/DDL fuer msy_update_state und msy_update_history definieren.
2. [x] Plan-Tool fuer Delta-Ermittlung gegen Zielversionen implementieren.
3. [x] Apply-Tool fuer DATABASE_UPDATE/DATA_UPDATE mit Dry-Run und Resume erstellen.
4. [x] Validierungs-Tool und standardisierten JSON-Report verankern.
5. [x] Pilotlauf auf einer ausgewaehlten Ziel-Mandanten-DB durchfuehren.

## 12. Umsetzungsstand 2026-05-21

Technisch umgesetzt:
1. SQL/DDL-Artefakt erstellt:
   backend/reports/mandant_update_basis_v1.sql
2. Basis-Setup Tool erstellt:
   backend/tools/mandant_update_define_basis_v1.py
3. Runtime-Defaults erstellt:
   backend/config/mandant_update_runtime_defaults_v1.json
4. Delta-Plan Tool erstellt:
   backend/tools/mandant_update_plan_v1.py
5. Apply-Tool erstellt:
   backend/tools/mandant_update_apply_v1.py
6. Validate-Tool erstellt:
   backend/tools/mandant_update_validate_v1.py

Nachweise:
1. backend/reports/mandant_update_define_basis_dryrun_v1.json
   - db_available=true, errors=0, ddl_executed_count=0
2. backend/reports/mandant_update_define_basis_apply_v1.json
   - db_available=true, state_table_exists_after=true, history_table_exists_after=true,
     ddl_statement_count=8, ddl_executed_count=8, errors=0
3. backend/reports/mandant_update_plan_v1.json
   - plan_status=ready, delta_count=3, state_table_exists=true, state_row_exists=false, errors=0
4. backend/reports/mandant_update_apply_dryrun_v1.json
   - apply_status=dry_run_ready, delta_count=3, applied_writes=0, errors=0
5. backend/reports/mandant_update_apply_apply_v1.json
   - apply_status=applied, delta_count=3, applied_writes=2,
     state_row_exists_before=false, state_row_exists_after=true, errors=0
6. backend/reports/mandant_update_plan_v2_after_apply.json
   - plan_status=no_change, delta_count=0, state_table_exists=true, state_row_exists=true, errors=0
7. backend/reports/mandant_update_validate_v1.json
   - validation_status=passed, checks_total=9, checks_passed=9, checks_failed=0, errors=0
8. backend/reports/mandant_update_pilot_standard_plan_before_v1.json
   - plan_status=no_change, delta_count=0
9. backend/reports/mandant_update_pilot_standard_apply_v1.json
   - apply_status=no_change, delta_count=0, applied_writes=0
10. backend/reports/mandant_update_pilot_standard_validate_v1.json
   - validation_status=passed, checks_total=9, checks_passed=9, checks_failed=0, errors=0
11. backend/reports/mandant_update_pilot_standard_plan_after_v1.json
   - plan_status=no_change, delta_count=0
12. backend/reports/mandant_update_pilot_standard_summary_v1.json
   - pilot_status=passed, idempotence_confirmed=true, consistency_confirmed=true
13. backend/reports/mandant_update_report_v1.json
      - overall_status=passed, checks_total=8, checks_passed=8,
         checks_failed=0, idempotence_confirmed=true

Interpretation:
1. Die technische Basis fuer Mandanten-DB-Versionierung ist in der Ziel-Mandanten-DB angelegt.
2. Der Planer erkennt erwartungsgemaess drei Deltas (Source/Schema/Data), solange noch kein
   initialer State-Satz geschrieben wurde.
3. Nach dem ersten Apply ist der State-Satz gesetzt und der Folge-Plan meldet erwartungsgemaess
   no_change (delta_count=0).
4. Die Validierung bestaetigt Basis-, State-, History- und Zielversionskonsistenz ohne offene Fehler.
5. Der Pilotlauf auf dem Standard-Mandanten (`Filiale Test 1 Mandant`,
   `e51a8688-2cca-4a16-855d-52a69677fb50`) bestaetigt stabilen no_change-Betrieb.
6. Der konsolidierte Abschlussreport fasst Plan/Apply/Validate/Pilotsequenz
   maschinenlesbar zusammen und bestaetigt den Gesamtstatus `passed`.

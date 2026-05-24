# PDVM Monitoring Batch Job Basis V1

Status: Entscheidungs- und Umsetzungs-Spezifikation
Datum: 2026-05-20
Scope: Mandantenweite Monitoring-Basis fuer Batch/Job-Ablaufe

## 1. Entscheidung

1. Tabellenname: msy_batch_job_monitoring
2. Datenbank: main_mandant (Mandanten-DB)
3. Ziel: generische, wiederverwendbare Monitoring-Basis fuer Migration, Abrechnung, Buchung, Verteilung, Imports.

## 2. Tabellenstruktur

Pflichtspalten:
1. uid UUID PRIMARY KEY
2. link_uid UUID NULL
3. name TEXT NOT NULL
4. daten JSONB NOT NULL
5. backup_daten JSONB NOT NULL
6. daten_backup JSONB NOT NULL
7. historisch INTEGER NOT NULL DEFAULT 0
8. source_hash TEXT NOT NULL DEFAULT ''
9. sec_id TEXT NOT NULL DEFAULT ''
10. gilt_bis DOUBLE PRECISION NOT NULL DEFAULT 1001
11. created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
12. modified_at TIMESTAMPTZ NOT NULL DEFAULT NOW()

Indizes:
1. historisch
2. created_at
3. modified_at
4. (daten->ROOT->>JOB_NAME)
5. (daten->ROOT->>RUN_STATUS)

## 3. Datenmodell in daten (ROOT)

Pflichtfelder in ROOT:
1. JOB_NAME
2. JOB_TYPE
3. RUN_STATUS (planned|running|success|failed|cancelled)
4. RUN_MODE (dry_run|apply)
5. STARTED_AT_UTC
6. FINISHED_AT_UTC
7. DURATION_MS
8. BATCH_SIZE
9. TOTAL_ITEMS
10. PROCESSED_ITEMS
11. UPDATED_ITEMS
12. ERROR_COUNT
13. SOURCE_TOOL
14. RUN_ID

Optionale Felder:
1. CONTEXT_DB_LABEL
2. CONTEXT_TABLE
3. CHECKPOINT_PATH
4. REPORT_PATH
5. NOTE

## 4. Write-Strategie

1. Job-Start:
- Insert mit RUN_STATUS=running, STARTED_AT_UTC, RUN_ID, Source-Kontext.

2. Laufendes Update:
- Regelmaessiges Update von PROCESSED_ITEMS, UPDATED_ITEMS, ERROR_COUNT, modified_at.

3. Job-Ende:
- Update FINISHED_AT_UTC, DURATION_MS, RUN_STATUS.

4. Fehlerfall:
- RUN_STATUS=failed, ERROR_COUNT>0, Fehlerdetails als Text in NOTE oder strukturierte Fehlersammlung in backup_daten.

5. Aufbewahrung:
- historisch wird nicht als Laufzeit-Archivierungssteuerung verwendet.
- Archivierung/Loeschlogik erfolgt ueber gilt_bis (PDVM-Standard).
- Ein Monitoring-Eintrag gilt als aktiv, solange gilt_bis auf dem Defaultwert (9999-12-31 23:59:59) steht.
- Beendete/archivierte Eintraege werden ueber gilt_bis abgeschnitten (Zeitpunktregel), nicht ueber historisch-Flip.

## 5. Technische Umsetzung V1

Tool:
1. backend/tools/phaseC_define_monitoring_basis.py

Reports:
1. backend/reports/phaseC_define_monitoring_basis_dryrun_v1.json
2. backend/reports/phaseC_define_monitoring_basis_apply_v1.json

## 6. Abgrenzung

1. Diese V1 definiert die Basis-Tabelle und Write-Strategie.
2. Konkrete Betriebswerte (batch_size, Laufintervalle, Delta-Fenster) werden in Punkt 5 der Master-Checkliste festgelegt.
3. Die semantische Definition von historisch/gilt_bis ist verbindlich in ARCHITECTURE_RULES.md geregelt.

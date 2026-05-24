# PDVM Batch Runtime Betriebswerte V1

Status: Entscheidungs-Spezifikation
Datum: 2026-05-20
Scope: Initiale Betriebswerte fuer Strukturmigrations-Batchlaeufe

## 1. Startwerte V1

1. batch_size: 100
2. Laufintervall: 15 Minuten
3. Delta-Rerun-Fenster: 24 Stunden
4. max_batches_per_table: 500
5. Abbruchkriterium db_errors: 0 erlaubt
6. Abbruchkriterium completion: volle Tabellenabdeckung erforderlich

## 2. Begründung

1. 100er Batches begrenzen Lock-Dauer und halten Laufzeit stabil.
2. 15 Minuten erlaubt zeitnahe Nachführung ohne Dauerlast.
3. 24h Delta-Fenster deckt Tagesbetrieb inkl. Nachläufer ab.
4. 500 Batches pro Tabelle ist Schutz gegen Endlosschleifen/Fehlkonfiguration.
5. db_errors > 0 ist in V1 ein harter Fehlzustand fuer Migrationsläufe.

## 3. Technische Verankerung

1. Runtime-Profil Datei:
- backend/config/phaseC_batch_runtime_defaults_v1.json

2. Runner mit Profilnutzung und Abbruchlogik:
- backend/tools/phaseC_batch_reconcile_struct_version.py

3. Wichtige Parameter:
- --defaults
- --batch-size
- --max-batches
- --delta-window-hours
- --max-db-errors
- --allow-partial-completion

## 4. Operativer Standardlauf

1. Standard:
- Dry-Run zyklisch mit Defaults

2. Apply:
- bei geplanter Migration oder nach Freigabe

3. Delta-Lauf:
- wenn --changed-since nicht gesetzt ist, wird automatisch now - delta_rerun_window_hours verwendet.

## 5. Nachweis

1. Report fuer Punkt 5:
- backend/reports/phaseC_batch_reconcile_struct_version_runtime_v1.json

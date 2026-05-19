# PDVM Template 555/666 Phase B Status V1

Status: gestartet, Schritt 1, 1b, 2, 3 und 4 umgesetzt  
Datum: 2026-05-18

## 1. Umgesetzter Schritt

Persistierung von Tabellenklassifizierung und Strukturzielversion in den jeweiligen *systemdaten*-Tabellen fuer:
1. System-DB
2. Auth-DB
3. Hauptmandant-DB

Erweiterung (Schritt 1b):
1. Persistierung von TABLE_TYPE je Tabelle.
2. Explizite Zuordnung fuer infos-Typen (z. B. sys_dropdowndaten, sys_beschreibungen) plus Heuristik fuer restliche Tabellen.

Erweiterung (Schritt 2):
1. Big-Bang Migration von Dropdown-Strukturen aus sys_systemdaten nach sys_dropdowndaten.
2. Pro Dropdown ein eigener Datensatz in sys_dropdowndaten.
3. RECORD_TYPE wird gesetzt:
- sys_dropdowndaten Zielsaetze: dropdown_definition
- verbleibende sys_systemdaten Quelle: mixed_system_config
4. Harte Referenzpolitik: verbleibende Dropdown-Verweise auf sys_systemdaten gelten als Fehler.

Erweiterung (Schritt 3):
1. Runtime-Hard-Guard aktiv: Dropdown-Aufloesung mit table=sys_systemdaten wirft expliziten Fehler.
2. Integritaets-Validator fuer Legacy-Dropdown-Referenzen eingefuehrt.
3. Strict-Validierung nach Migration erfolgreich (0 Legacy-Referenzen).

Erweiterung (Schritt 4):
1. Finale Verhaertung der infos-Tabellen sys_dropdowndaten und sys_beschreibungen.
2. Template-Verhaertung: 555 strikt ROOT+leere Gruppen, 666 strikt ROOT+TEMPLATES.
3. Datensatz-Verhaertung: RECORD_TYPE/TABLE/DEFAULT_LANGUAGE konsistent gesetzt.
4. Nachlauf-Validierung erneut strict auf Legacy-Dropdown-Referenzen.

Tool:
1. backend/tools/phaseB_persist_template_modes.py
2. backend/tools/phaseB_migrate_sys_systemdaten_dropdowns.py
3. backend/tools/phaseB_validate_dropdown_reference_integrity.py
4. backend/tools/phaseC_harden_infos_tables.py

Report:
1. backend/reports/phaseB_persist_template_modes_apply_v1.json
2. backend/reports/phaseB_persist_template_modes_apply_v2.json
3. backend/reports/phaseB_migrate_sys_systemdaten_dropdowns_dryrun_v4.json
4. backend/reports/phaseB_migrate_sys_systemdaten_dropdowns_apply_v1.json
5. backend/reports/phaseB_validate_dropdown_reference_integrity_v1.json
6. backend/reports/phaseC_harden_infos_tables_dryrun_v1.json
7. backend/reports/phaseC_harden_infos_tables_apply_v1.json
8. backend/reports/phaseB_validate_dropdown_reference_integrity_v2.json

## 2. Ergebnis

Summary aus Apply V1:
1. db_count: 3
2. db_errors: 0
3. tables_total: 30
4. meta_rows_planned: 30
5. meta_rows_inserted: 30
6. meta_rows_updated: 0
7. meta_rows_skipped_blocked: 0

Summary aus Apply V2:
1. db_count: 3
2. db_errors: 0
3. tables_total: 30
4. meta_rows_planned: 30
5. meta_rows_inserted: 0
6. meta_rows_updated: 30
7. meta_rows_skipped_blocked: 0
8. table_type_counts:
- process: 2
- infos_text: 2
- config: 9
- infos_dropdown: 1
- audit_history: 5
- master_data: 11

Summary aus B.2 Dry-Run V4:
1. db_count: 3
2. db_skipped: 2
3. db_errors: 0
4. dropdown_records_planned: 3
5. system_rows_touched: 1
6. hard_ref_errors: 0

Summary aus B.2 Apply V1:
1. db_count: 3
2. db_skipped: 2
3. db_errors: 0
4. dropdown_records_planned: 3
5. dropdown_records_inserted: 3
6. dropdown_records_updated: 0
7. system_rows_touched: 1
8. hard_ref_errors: 0

Summary aus B.3 Validator V1 (strict):
1. db_count: 3
2. db_errors: 0
3. tables_scanned: 30
4. rows_scanned: 379
5. legacy_ref_count: 0
6. strict_exit_code: 0

Summary aus C.1 Harden Infos Dry-Run V1:
1. tables_total: 2
2. rows_scanned: 10
3. rows_changed: 7
4. template_rows_changed: 4
5. db_errors: 0

Summary aus C.2 Harden Infos Apply V1:
1. tables_total: 2
2. rows_scanned: 10
3. rows_changed: 7
4. template_rows_changed: 4
5. db_errors: 0

Summary aus B.3 Validator V2 (strict):
1. db_count: 3
2. db_errors: 0
3. tables_scanned: 30
4. rows_scanned: 379
5. legacy_ref_count: 0
6. strict_exit_code: 0

## 3. Persistierte Felder (pro Tabelle)

Jeder Metadata-Satz enthaelt unter TEMPLATE_META:
1. TARGET_TABLE
2. TEMPLATE_MODE
3. TABLE_TYPE
4. TABLE_TYPE_SOURCE
5. STRUCT_VERSION_TARGET
6. SOURCE_DB_LABEL
7. UPDATED_AT_UTC
8. SOURCE

## 4. Naechste Schritte in Phase B

1. Werte bei wiederholtem Lauf aktualisieren (idempotenter Updatepfad ist bereits enthalten).
2. Ausnahmekatalog final je Tabelle pruefen und ggf. manuell nachsteuern.
3. Monitoring-Tabelle fuer Batch-Prozesse in Mandanten-DB spezifizieren.
4. Optional: STRUCT_VERSION_APPLIED je Satz in den Nutzdaten als Folgephase einfuehren.
5. Folgephase abgeschlossen: sys_beschreibungen/sys_dropdowndaten Strukturregeln final verhaertet und strict validiert.
6. Naechster Fokus: infos_translation Overlay-Struktur und Review-Workflow spezifizieren/implementieren.

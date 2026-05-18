# PDVM Template 555/666 Phase B Status V1

Status: gestartet und Schritt 1 umgesetzt  
Datum: 2026-05-18

## 1. Umgesetzter Schritt

Persistierung von Tabellenklassifizierung und Strukturzielversion in den jeweiligen *systemdaten*-Tabellen fuer:
1. System-DB
2. Auth-DB
3. Hauptmandant-DB

Tool:
1. backend/tools/phaseB_persist_template_modes.py

Report:
1. backend/reports/phaseB_persist_template_modes_apply_v1.json

## 2. Ergebnis

Summary aus Apply V1:
1. db_count: 3
2. db_errors: 0
3. tables_total: 30
4. meta_rows_planned: 30
5. meta_rows_inserted: 30
6. meta_rows_updated: 0
7. meta_rows_skipped_blocked: 0

## 3. Persistierte Felder (pro Tabelle)

Jeder Metadata-Satz enthaelt unter TEMPLATE_META:
1. TARGET_TABLE
2. TEMPLATE_MODE
3. STRUCT_VERSION_TARGET
4. SOURCE_DB_LABEL
5. UPDATED_AT_UTC
6. SOURCE

## 4. Naechste Schritte in Phase B

1. Werte bei wiederholtem Lauf aktualisieren (idempotenter Updatepfad ist bereits enthalten).
2. Ausnahmekatalog final je Tabelle pruefen und ggf. manuell nachsteuern.
3. Monitoring-Tabelle fuer Batch-Prozesse in Mandanten-DB spezifizieren.
4. Optional: STRUCT_VERSION_APPLIED je Satz in den Nutzdaten als Folgephase einfuehren.

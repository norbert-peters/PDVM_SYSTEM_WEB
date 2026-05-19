# PDVM Template 555/666 Normalisierung A.0 Status V1

Status: umgesetzt (Apply V1)  
Datum: 2026-05-18

## 1. Anlass

Die 555/666-Saetze waren tabellenweise uneinheitlich und mussten vor Projektfortsetzung je Tabelle aus den vorhandenen Datensaetzen normalisiert werden.

## 2. Verbindliche Normalisierungsregeln

1. 555 besteht aus ROOT + leeren Gruppenobjekten fuer alle fachlichen Gruppen.
2. 666 besteht aus ROOT + TEMPLATES.
3. ROOT-Struktur von 555 und 666 ist identisch (Werte SELF_GUID/SELF_NAME template-spezifisch).
4. TEMPLATES-Inhalte werden aus aktiven Datensaetzen der jeweiligen Tabelle hergeleitet.
5. Ablauf erfolgt linear pro Tabelle.

## 3. Tooling

Neues Tool:
1. backend/tools/phaseA0_normalize_templates_from_data.py

Ausfuehrung:
1. Apply V1 Report: backend/reports/phaseA0_normalize_templates_from_data_apply_v1.json

## 4. Ergebnis Apply V1

1. db_count: 3
2. db_errors: 0
3. tables_total: 30
4. tables_considered: 30
5. tables_normalized: 18
6. rows_inserted: 0
7. rows_updated: 34
8. rows_skipped_blocked: 1

## 5. Interpretation

1. Die Normalisierung wurde ueber alle drei Ziel-DBs ausgefuehrt.
2. Ein grosser Teil der Tabellen wurde tatsaechlich angepasst (18 Tabellen, 34 Template-Updates).
3. Der eine Skip ist ein technisch erwartbarer Blocker bei Tabellen mit zusaetzlichen Pflichtspalten ohne sichere Blind-Insert-Strategie.

## 6. Naechste Schritte

1. Einzelanalyse des verbliebenen Skip-Falls und definierter Sonderpfad.
2. Optionaler Verifikationslauf (dry-run) zur Differenzkontrolle nach Apply.
3. Danach Freigabe fuer weitere Projektphasen.

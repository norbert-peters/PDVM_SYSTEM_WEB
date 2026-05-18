# PDVM Template 555/666 Phase A Analyse V1

Status: erweitert auf Multi-DB (System + Auth + Hauptmandant), Rest-Fix-Lauf abgeschlossen  
Datum: 2026-05-18

## 1. Zweck

Dieser Report startet Phase A formal und liefert die initiale Befundlage fuer:
1. A.0 Template-Roundmaking (555/666 korrigieren),
2. Ausnahmekatalog je Tabelle,
3. Vorbereitung der nachgelagerten Strukturmigration.

Scope-Update:
1. System-DB (pdvm_system)
2. Auth-DB (auth)
3. Mandanten-DB (Hauptmandant: Filiale Test 1 Mandant, DB: filale_test_1)

## 2. Durchgefuehrte Checks

1. Linear-Schema-Validator
- Tool: backend/tools/validate_linear_schema_v1.py
- Ergebnis: 207 gepruefte Zeilen, 3 Fehler, 8 Warnungen.
- Auffaellig: sys_contr_dict_man nicht gefunden; in sys_dialogdaten mindestens ein TAB_ELEMENTS-Eintrag ohne TABLE.

2. Control-Consistency-Report
- Tool: backend/tools/phase7_control_dict_consistency_report.py
- Ergebnis: 157 aktive Controls, 7 Duplicate ref_names, 0 fehlende Referenzen.
- Report: backend/reports/phase7_control_dict_consistency_report.json

3. Neuer Phase-A-Template-Health-Check
- Tool: backend/tools/phaseA_555_666_template_health_check.py
- Ergebnis:
  - tables_scanned: 13
  - tables_with_555_or_666: 12
  - tables_with_findings: 12
  - tables_ok: 0
  - error_count: 22
- Report: backend/reports/phaseA_555_666_template_health_check.json

4. Multi-DB Analyse + Roundmaking
- Tool: backend/tools/phaseA_multidb_template_roundmaking.py
- Dry-Run Report: backend/reports/phaseA_multidb_template_roundmaking_dryrun_v2.json
- Apply Reports: 
  - backend/reports/phaseA_multidb_template_roundmaking_apply_v3.json
  - backend/reports/phaseA_multidb_template_roundmaking_apply_v4.json
  - backend/reports/phaseA_multidb_template_roundmaking_apply_v5.json
- Globales finales Ergebnis (Apply V5):
  - db_count: 3
  - tables_total: 30
  - tables_scope_uid_daten: 30
  - mode_voll: 22
  - mode_teil: 2
  - mode_ausgenommen: 6
  - health_error_count: 0
  - roundmaking_actions: 1
  - db_errors: 0

DB-spezifische finale Werte (Apply V5):
1. system: tables_total 13, health_error_count 0
2. auth: tables_total 7, health_error_count 0
3. mandant_main: tables_total 10, health_error_count 0

## 3. Kernaussage

Die Annahme ist bestaetigt: 555/666 sind aktuell nicht migrationstauglich gepflegt.

Vor jeder Bestandsdatenmigration ist ein verpflichtender A.0-Schritt notwendig:
1. ROOT-Identitaet 555/666 je Tabelle herstellen.
2. 666.TEMPLATES je Tabelle formal vorhanden und verwendbar machen.
3. Tabellen klassifizieren (voll/teil/ausgenommen) und in sys_systemdaten markieren.

Zusatz nach Multi-DB-Lauf:
1. Die Klassifizierung wurde fuer alle Tabellen in allen drei Ziel-DBs ausgefuehrt.
2. Roundmaking ist technisch durchgelaufen und hat keine DB-Abbrueche mehr (db_errors = 0).
3. Rest-Fix-Lauf wurde abgeschlossen; Health-Fehler sind im finalen Lauf auf 0 reduziert.

## 4. Befundcluster aus dem Health-Check

1. 666.TEMPLATES fehlt in nahezu allen geprueften Tabellen.
2. ROOT-Strukturen zwischen 555 und 666 sind vielfach ungleich.
3. Technische/history-nahe Tabellen haben teils keine 555/666 und sind Kandidaten fuer "ausgenommen".
4. Teiltemplatefaehige Tabellen mit zusaetzlichen Pflichtspalten (z. B. asy_benutzer: benutzer/passwort) koennen 555 nicht blind per Insert erhalten und brauchen Sonderpfad.

Beobachtete konkrete Kandidaten:
1. dev_workflow_draft: Root-Drift + fehlende TEMPLATES (bekannte Ausnahmetabelle).
2. dev_workflow_draft_item: Root-Drift + fehlende TEMPLATES (bekannte Ausnahmetabelle).
3. sys_feld_aenderungshistorie: weder 555 noch 666 vorhanden (technische Historie, vermutlich ausgenommen).

## 5. Initiale Klassifizierung (Arbeitsstand)

1. ausgenommen:
- dev_workflow_draft
- dev_workflow_draft_item
- sys_feld_aenderungshistorie

2. teiltemplatefaehig:
- asy_benutzer (fachliche Sonderregeln fuer passwort/benutzer, daten-Bereich grundsaetzlich templatefaehig)

3. ausgenommen (aktuell aus Multi-DB-Lauf):
- dev_workflow_draft
- dev_workflow_draft_item
- sys_feld_aenderungshistorie
- asy_feld_aenderungshistorie
- msy_feld_aenderungshistorie
- msy_error_acknowledgments

4. zu validieren (voraussichtlich voll templatefaehig nach A.0):
- sys_control_dict
- sys_dialogdaten
- sys_viewdaten
- sys_framedaten
- sys_layout
- sys_systemdaten
- sys_menudaten
- sys_dropdowndaten
- sys_ext_table
- sys_beschreibungen
- asy_mandanten
- asy_systemdaten
- msy_anwendungsdaten
- msy_systemdaten
- msy_systemsteuerung
- tst_finanzdaten
- tst_persondaten

## 6. A.0 Aufgabenpaket (vor Phase-B/C)

1. Strukturversion und Klassifizierung vorbereiten
- In sys_systemdaten je Tabelle ablegen:
  - STRUCT_VERSION_TARGET
  - TEMPLATE_MODE (voll_templatefaehig | teiltemplatefaehig | ausgenommen)

2. 555 normalisieren
- ROOT auf kanonische Struktur je Tabelle bringen.
- Leere Pflichtgruppen in 555 sicherstellen.

3. 666 normalisieren
- ROOT exakt wie 555 erzwingen.
- TEMPLATES pro Gruppe anlegen und minimal valide befuellen.

4. Technische Konsistenz pruefen
- Health-Check erneut laufen lassen.
- Ziel fuer A.0-Freigabe: keine Errors fuer Tabellenmodus voll/teil.

5. Delta-Lauf vorbereiten
- Migrationslauf muss start_ts/end_ts und Delta-Rerun ueber modified_at unterstuetzen.

## 7. Umsetzung bereits gestartet

Neu angelegt:
1. backend/tools/phaseA_555_666_template_health_check.py
2. backend/tools/phaseA_multidb_template_roundmaking.py

Zweck:
1. Tabellenscan mit uid/daten.
2. 555/666-Existenz pruefen.
3. ROOT-Identitaet pruefen.
4. 666.TEMPLATES-Pruefung.
5. JSON-Report fuer A.0-Steuerung.
6. Multi-DB Tabellenklassifizierung + Roundmaking (Dry-Run/Apply) inklusive Hauptmandant-Selektion.

## 8. Naechste konkrete Schritte (Phase A Fortsetzung)

1. Rest-Fehler aus Apply-V3 je Tabelle bereinigen (fokus: 666.TEMPLATES konsistent fuellen).

2. Klassifizierung in sys_systemdaten persistieren (TEMPLATE_MODE + STRUCT_VERSION_TARGET pro Tabelle).

3. Sonderpfad fuer teiltemplatefaehige Tabellen finalisieren (asy_benutzer ohne Blind-Insert).

4. Monitoring-Grundlage spezifizieren:
- neue mandantenweite Monitoring-Tabelle fuer Batchprozesse (inkl. Migration).

5. Ausnahmekatalog in sys_systemdaten finalisieren.

6. Optional: konsolidierten Abschlussreport erzeugen (nur finale Artefakte, V5 als Referenz).

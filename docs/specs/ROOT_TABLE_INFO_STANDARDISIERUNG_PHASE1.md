# ROOT/TABLE_INFO Standardisierung Phase 1

Stand: 2026-05-27
Scope Phase 1:
- dev_workflow_draft
- sys_dialogdaten (inkl. Dialog UID 14b932e7-451c-5509-b4b4-aac3199e2936)

Quelle:
- backend/reports/root_table_info_unification_audit_2026_05_27.json

## 1) Entscheidungen zu den offenen Fragen

1. ROOT-Vereinheitlichung:
- Wir verwenden tabellenweit die ROOT-Kernfelder aus den Architekturregeln.
- Doppelte Bedeutung mit verschiedenen Feldnamen ist unzulaessig.

2. TABLE_INFO-Vereinheitlichung:
- TABLE_INFO ist Template-Metadaten.
- Gueltiger Pfad ist nur 666.TEMPLATES.TABLE_INFO.
- ROOT-Felder werden nicht in TABLE_INFO verschoben.

3. Pflichtgrad TABLE_INFO:
- TABLE_INFO ist verpflichtend im 666-Template (unter TEMPLATES).
- TABLE_INFO ist nicht verpflichtend in nicht-reservierten Fachdatensaetzen.

4. Flach und einheitlich:
- 666 hat nur ROOT und TEMPLATES als Gruppen.
- Abweichungen werden als Fehler behandelt.
- Pro Fehler wird Datenfix und Programmfix getrennt bewertet.

5. Sichtbarkeit in Architekturregeln:
- Festlegungen sind in ARCHITECTURE_RULES dokumentiert (1.12a, 1.12b, 1.12c).

## 2) Audit-Kurzlage (Phase 1 relevant)

- 13 Tabellen geprueft.
- 7 Tabellen mit TABLE_INFO in 666 (korrekt unter TEMPLATES).
- 0 Tabellen mit ungueltiger 666-Gruppenstruktur.
- 0 Tabellen mit ungueltigem direktem Pfad 666.TABLE_INFO.

## 3) Tabelle fuer Tabelle

### 3.1 dev_workflow_draft

Soll in 666.ROOT vorhanden:
- IS_TEMPLATE
- REVISION
- SELF_CREATED_AT
- SELF_GILT_BIS
- SELF_GUID
- SELF_LINK_UID
- SELF_MODIFIED_AT
- SELF_NAME
- STATUS
- TITLE
- WORKFLOW_TYPE

Ist-Abweichung:
- 3 nicht-reservierte Saetze mit fehlenden ROOT-Feldern.
- Beispiel: fehlend IS_TEMPLATE, SELF_NAME, STATUS, TITLE, WORKFLOW_TYPE.

Fehlerentscheidung:
- Datenfix: Ja.
  - Bestehende Datensaetze auf 666-ROOT angleichen.
- Programmfix: Ja.
  - Erzeugungs-/Updatepfade muessen fehlende ROOT-Pflichtfelder automatisch setzen.

### 3.2 sys_dialogdaten (Dialog-Fokus)

Dialog UID 14b932e7-451c-5509-b4b4-aac3199e2936:
- ROOT passt gegen 555/666 (keine missing vs 555/666).
- Zusatzfeld im Dialogdatensatz: ROOT.TABLE_INFO (extra vs 666).

Interpretation:
- Der Zieldialog ist funktional konsistent zu 555/666-ROOT.
- ROOT.TABLE_INFO im Fachdaten-Satz ist ein Struktur-Delta gegen das 666-ROOT-Soll.

Fehlerentscheidung:
- Datenfix: Ja (gezielt pro Datensatz pruefen/bereinigen).
- Programmfix: Ja (Write-Pfade verhindern, dass ROOT.TABLE_INFO in Fachdaten landet).

## 4) Nächste Umsetzungsschritte (Phase 2)

1. Datenfix-Migration dev_workflow_draft:
- Fehlende ROOT-Felder nach 666 ergaenzen.
- Keine fachlichen Felder umbenennen ohne Alias-Migrationsplan.

2. Programmfix in Workflow-Draft-Service:
- Beim Create/Save von draft und draft_item ROOT-Minimum hart erzwingen.
- Guard gegen ungueltige Gruppen/Pfade (insb. ROOT.TABLE_INFO in Fachdaten).

3. sys_dialogdaten Bereinigung:
- Datensaetze mit ROOT.TABLE_INFO identifizieren.
- Nur behalten, wenn explizite Ausnahme dokumentiert ist; sonst entfernen.

4. Audit als Gate verwenden:
- Release-relevante Pipelines brechen bei:
  - invalid_666_group_structure > 0
  - invalid_666_direct_table_info > 0
  - nicht dokumentierten Alias-Feldern

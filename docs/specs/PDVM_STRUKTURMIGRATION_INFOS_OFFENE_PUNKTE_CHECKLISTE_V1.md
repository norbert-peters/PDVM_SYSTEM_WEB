# PDVM Strukturmigration + Infos Uebersetzungsstrategie Offene Punkte V1

Status: Arbeits-Checkliste
Datum: 2026-05-20
Scope: Offene Punkte aus 555/666-Strukturmigration und infos_typ_uebersetzungsstrategie

## 1. Arbeitsmodus

Diese Liste wird Punkt fuer Punkt in Reihenfolge bearbeitet.
Pro Punkt gilt genau ein Ergebnis:
1. Entscheidung getroffen
2. Technisch umgesetzt
3. Explizit vertagt mit Begruendung

## 2. Strukturmigration (offen)

- [x] 1) Ausnahmekatalog final entscheiden (6 offene Entscheidungen)
  Ergebnis erwartet:
  finaler Zielmodus und Lock je Tabelle fuer
  system.dev_workflow_draft,
  system.sys_feld_aenderungshistorie,
  auth.asy_benutzer,
  auth.asy_feld_aenderungshistorie,
  mandant_main.msy_feld_aenderungshistorie.
  Nachweis:
  backend/reports/phaseB_exception_catalog_v1.json
  Erledigt am:
  2026-05-20 (Finalentscheidungen per backend/config/phaseB_exception_decisions_v1.json, open_decisions_count=0).

- [x] 2) Abnahmekriterium "backup_daten bei Entfall" mit Nachweislauf absichern
  Ergebnis erwartet:
  reproduzierbarer Dry-Run/Apply-Nachweis fuer Feldentfall mit MIGRATION_BACKUP.
  Bezug:
  PDVM_TEMPLATE_555_666_STRUKTURMIGRATION_SPEC_V1.md Abschnitt 5.2 und 11.
  Nachweis:
  backend/reports/phaseC_prove_backup_removed_fields_dryrun_v1.json
  backend/reports/phaseC_prove_backup_removed_fields_apply_v1.json
  backend/reports/phaseC_prove_backup_removed_fields_dryrun_v2.json
  Erledigt am:
  2026-05-20 (Dry-Run V1: rows_with_removed_fields=1, removed_field_count=2; Apply V1: rows_updated=1; Dry-Run V2: rows_with_removed_fields=0).

- [x] 3) Abnahmekriterium "kein regressiver Einfluss Save/View" formal belegen
  Ergebnis erwartet:
  Testprotokoll fuer Save, Reload, View-Pfade auf in-scope Tabellen (mind. system/auth/mandant_main Stichprobe).
  Bezug:
  PDVM_TEMPLATE_555_666_STRUKTURMIGRATION_SPEC_V1.md Abschnitt 11.
  Nachweis:
  backend/reports/phaseC_validate_no_regression_save_view_v1.json
  Erledigt am:
  2026-05-20 (targets_total=6, targets_passed=6, targets_failed=0, targets_skipped=0).

- [x] 4) Monitoring-Basis fuer Batch/Jobs entscheiden und spezifizieren
  Ergebnis erwartet:
  Name/Schema/Write-Strategie fuer mandantenweite Monitoring-Tabelle inkl. Mindestfeldern.
  Bezug:
  PDVM_TEMPLATE_555_666_STRUKTURMIGRATION_SPEC_V1.md Abschnitt 8.5.
  Nachweis:
  docs/specs/PDVM_MONITORING_BATCH_JOB_BASIS_SPEC_V1.md
  backend/reports/phaseC_define_monitoring_basis_dryrun_v1.json
  backend/reports/phaseC_define_monitoring_basis_apply_v1.json
  Erledigt am:
  2026-05-20 (db_available=true, table_exists_after=true, ddl_executed_count=6, errors=0).

- [x] 5) Initiale Betriebswerte fuer Batch-Runs festlegen
  Ergebnis erwartet:
  Startwerte fuer batch_size, Laufintervall, Delta-Rerun-Fenster und Abbruchkriterien.
  Bezug:
  PDVM_TEMPLATE_555_666_STRUKTURMIGRATION_SPEC_V1.md Abschnitt 9.4.
  Nachweis:
  docs/specs/PDVM_BATCH_RUNTIME_BETRIEBSWERTE_V1.md
  backend/config/phaseC_batch_runtime_defaults_v1.json
  backend/reports/phaseC_batch_reconcile_struct_version_runtime_v1.json
  Erledigt am:
  2026-05-20 (batch_size=100, run_interval_minutes=15, delta_window_hours=24, max_batches=500, max_db_errors=0, operational_status=ok).

## 3. Infos Uebersetzungsstrategie (offen)

- [x] 6) SUPPORTED_LANGUAGES und DEFAULT_LANGUAGE finalisieren
  Ergebnis erwartet:
  verbindliche Sprachliste V1 und Default-Definition.
  Bezug:
  PDVM_INFOS_TYP_UEBERSETZUNGSSTRATEGIE_SPEC_V1.md Abschnitt 6.
  Nachweis:
  backend/config/i18n_policy_v1.json
  backend/reports/phaseC_finalize_supported_languages_v1.json
  Erledigt am:
  2026-05-20 (DEFAULT_LANGUAGE=DE-DE, SUPPORTED_LANGUAGES=[DE-DE, EN-US, IT-IT], unsupported_observed_count=0).

- [x] 7) Pflicht-Uebersetzungsumfang festlegen
  Ergebnis erwartet:
  Matrix je Inhaltstyp (label, hilfe, dropdown, text): Pflicht/Optional je Sprache.
  Bezug:
  PDVM_INFOS_TYP_UEBERSETZUNGSSTRATEGIE_SPEC_V1.md Abschnitt 6.
  Nachweis:
  backend/config/i18n_required_translation_scope_v1.json
  backend/reports/phaseC_define_required_translation_scope_v1.json
  Erledigt am:
  2026-05-20 (items_total=58, items_with_missing_required=0, required_scope_fully_covered=true).

- [x] 8) Uebersetzungsmodus je Tabelle festlegen
  Ergebnis erwartet:
  MANUAL oder MACHINE_ASSISTED je betroffener Tabelle inkl. Review-Regel.
  Bezug:
  PDVM_INFOS_TYP_UEBERSETZUNGSSTRATEGIE_SPEC_V1.md Abschnitt 5 und 6.
  Nachweis:
  backend/config/i18n_translation_mode_per_table_v1.json
  backend/reports/phaseC_define_translation_mode_per_table_v1.json
  Erledigt am:
  2026-05-20 (in_scope_tables_count=2, assignments_count=2, invalid_mode_count=0, open_decisions_count=0, decision_set_complete=true).

- [x] 9) Freigabeversion je Sprache definieren
  Ergebnis erwartet:
  minimales Freigabemodell (Version, approved_by, approved_at, status) fuer produktive Verwendung.
  Bezug:
  PDVM_INFOS_TYP_UEBERSETZUNGSSTRATEGIE_SPEC_V1.md Abschnitt 6,
  PDVM_TABELLENTYPEN_UND_I18N_STRUKTUR_SPEC_V1.md Abschnitt 3.3.
  Nachweis:
  backend/config/i18n_language_release_model_v1.json
  backend/reports/phaseC_define_language_release_model_v1.json
  Erledigt am:
  2026-05-20 (model_definition_complete=true; items_total=58; items_with_release_fields=0; runtime_release_metadata_coverage=false).

- [x] 10) infos_translation Overlay einfuehren oder bewusst vertagen
  Ergebnis erwartet:
  klare Entscheidung inkl. Zieltermin/No-Go-Begruendung.
  Bezug:
  PDVM_TABELLENTYPEN_UND_I18N_STRUKTUR_SPEC_V1.md Abschnitt 3.3 und 8.
  Entscheidung:
  bewusst vertagt auf spaeteren Entwicklungszeitpunkt.
  Begruendung:
  Prioritaet liegt nach der grossen Migration auf einem wiederholbaren Mandanten-DB-Updateverfahren
  (Versionierung + Datenanpassung) fuer Ziel-Mandanten.
  Folge-Spezifikation:
  docs/specs/PDVM_MANDANT_DB_UPDATE_VERSIONIERUNG_SPEC_V1.md
  Erledigt am:
  2026-05-20 (explizit vertagt, kein Overlay-Start in diesem Zyklus).

- [ ] 11) Resolver/API fuer sprachbezogene UI-Inhalte vereinheitlichen
  Ergebnis erwartet:
  einheitliche Aufloesungsreihenfolge requested -> default -> fallback ueber alle relevanten Endpunkte.
  Bezug:
  PDVM_TABELLENTYPEN_UND_I18N_STRUKTUR_SPEC_V1.md Abschnitt 5 und 8.

## 4. Reihenfolge (verbindlich)

1. Punkt 1
2. Punkt 2
3. Punkt 3
4. Punkt 4
5. Punkt 5
6. Punkt 6
7. Punkt 7
8. Punkt 8
9. Punkt 9
10. Punkt 10
11. Punkt 11

## 5. Aktueller Stand

1. Technische Kernmigration ist umgesetzt (Phase D/E, STRUCT_VERSION_APPLIED, Batch-Resume).
2. Die restlichen Punkte sind Governance-, Abnahme- und Betriebsfestlegungen plus API-Harmonisierung.

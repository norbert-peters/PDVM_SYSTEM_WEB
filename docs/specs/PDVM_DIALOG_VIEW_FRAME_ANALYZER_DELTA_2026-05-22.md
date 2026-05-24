# PDVM Dialog/View/Frame Analyzer Delta Report (2026-05-22)

Status: Delta-Vergleich abgeschlossen
Scope: Vergleich zwischen Baseline-Simulation (ohne Ausnahmen/ohne edit_control-Contract) und aktuellem Policy-Stand.

## 1. Vergleichsquellen

1. Baseline-Simulation:
   - `backend/config/dialog_view_frame_analyzer_policy_baseline_simulated_v1.json`
   - `backend/reports/dialog_view_frame_consistency_report_baseline_simulated_v1.json`
2. Aktueller Stand:
   - `backend/config/dialog_view_frame_analyzer_policy_v1.json`
   - `backend/reports/dialog_view_frame_consistency_report_v1.json`

## 2. Summary Delta

| Kennzahl | Baseline-Simulation | Aktueller Stand | Delta |
|---|---:|---:|---:|
| overall_status | failed | passed | verbessert |
| checks_total | 6 | 6 | 0 |
| checks_passed | 6 | 6 | 0 |
| checks_failed | 0 | 0 | 0 |
| violations_error | 2 | 0 | -2 |
| violations_warning | 2 | 2 | 0 |

## 3. Violation-Code Delta

### 3.1 Baseline-Simulation

1. `dialog_tabs_missing`: 2
2. `unknown_edit_type`: 2

### 3.2 Aktueller Stand

1. `dialog_tabs_missing_allowed_exception`: 2

### 3.3 Interpretation

1. Harte Architekturfehler wurden auf 0 reduziert.
2. `unknown_edit_type` wurde durch formalen Contract fuer `edit_control` aufgeloest.
3. Tab-lose Spezialdialoge sind nicht mehr ungesteuerte Fehler, sondern kontrollierte Policy-Warnungen.

## 4. Policy-Lifecycle Status

1. Analyzer-Policy enthaelt nun `metadata`.
2. Jede tab-lose Ausnahme enthaelt `owner` und `expires_at`.
3. Analyzer prueft fehlende oder abgelaufene Ausnahme-Metadaten und meldet diese als Warnungen.
4. Analyzer besitzt eine Ablauf-Vorwarnung (T-Threshold):
   - Warncode: `dialog_tabs_exception_expiring_soon`
   - Regel: `days_left <= expires_soon_days` (Policy-Metadaten)
   - Aktuell konfiguriert: `expires_soon_days = 14`
5. Laufstand 2026-05-22:
   - Kein `expiring_soon` Treffer, da `expires_at=2026-12-31` fuer alle aktiven Ausnahmen.

## 5. Empfehlung fuer naechsten Zyklus

1. Vor Ablaufdatum (`expires_at`) Review durchfuehren und Entscheidung dokumentieren:
   - Ausnahme verlaengern, oder
   - Dialog auf explizites Tab-Layout migrieren.
2. Delta-Report nach jeder Policy-Aenderung erneut erzeugen.

## 6. Update 2026-05-23 (Backend Contract Hardening)

1. Harte Backend-Validierung fuer Edit-Type-Contracts ist aktiv (policy-basiert in Dialog-API).
2. Datenseitige Rest-Inkonsistenz (`MODULE=edit` + `EDIT_TYPE=show_json`) wurde auf `edit_json` normalisiert.
3. Validation-Report `backend/reports/edit_type_contract_validation_report_v1.json` steht auf `overall_status=passed`.
4. Konsistenz-Analyzer `backend/reports/dialog_view_frame_consistency_report_v1.json` bleibt `passed` mit `violations_error=0` und `violations_warning=0`.

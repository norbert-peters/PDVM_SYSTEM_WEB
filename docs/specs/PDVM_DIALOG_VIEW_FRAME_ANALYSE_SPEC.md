# PDVM Dialog/View/Frame Konsistenzanalyse Spec V1

Status: Analyse-Spezifikation
Datum: 2026-05-21
Scope: Automatisierte Pruefung von Dialog-, View-, Frame-, Edit-Type- und Dropdown-Konsistenz.

## 1. Ziel

Das Analyse-Tool liefert einen standardisierten JSON-Report fuer die Refaktoring-Phasen A/B und fuer Abschlusspruefungen.

## 2. Datenquellen

1. Dialogdefinitionen (`sys_dialogdaten`)
2. Framedefinitionen (`sys_framedaten`)
3. Viewdefinitionen (`sys_viewdaten`)
4. Dropdown-Stammdaten (`sys_dropdowndaten`)

## 3. Pflichtpruefungen V1

### 3.1 Dialogstruktur

1. `DIALOG_TYPE` vorhanden und in `edit|work|acti|norm`.
2. Tabs sind auswertbar (`ROOT.TAB_ELEMENTS` oder `ROOT.TAB_XX`).
3. `MODULE` je Tab nur in `view|show|edit|acti`.
4. Bei `DIALOG_TYPE=work`: letzter Tab muss `MODULE=acti` sein.
5. Bei genau einem Tab: Flag fuer Single-Tab-Rendering ohne Header.
6. Tab-lose Dialoge sind standardmaessig Fehler, ausser sie sind in einer kontrollierten
	Ausnahme-Policy explizit freigegeben.

### 3.2 GUID-Referenzen

1. `MODULE=view` muss auf existierende View-GUID verweisen.
2. `MODULE=edit|acti` muss auf existierende Frame-GUID verweisen.
3. Fehlende Referenzen als harte Inkonsistenz markieren.

### 3.3 Edit-Type Inventar

1. Verwendete Edit-Typen aggregieren.
2. Edit-Typen werden gegen formale Contracts geprueft (Policy-basiert, inkl. `edit_control`).
3. Edit-Typen ausserhalb der Contract-Liste separat reporten.
4. Modulbindung wird geprueft (z. B. `show_json` nur in Modul `show`).

### 3.4 Dropdown-Source-Guardrails (B.4)

1. Dropdown-Configs werden in Dialog/View/Frame-Daten rekursiv gefunden (`*.dropdown`).
2. Zulassige `source`-Werte sind policy-gesteuert (`static|view|prefix_multi_table`).
3. Wenn `require_explicit_source=true`, ist fehlender `source` ein harter Fehler.
4. Legacy-Referenzen auf `table=sys_systemdaten` sind harte Fehler.
5. Source-spezifische Pflichtfelder:
	- `static`: `key` und `field|feld`
	- `view`: `key` und `table`
	- `prefix_multi_table`: `prefix|table_prefix`, optional `limit`
6. Prefix-Source wird gegen die Policy-Whitelist geprueft.
7. Optionales `limit` muss numerisch und im Bereich `1..max_result_limit` liegen.

### 3.6 Analyzer-Policy

1. Analyzer liest `backend/config/dialog_view_frame_analyzer_policy_v1.json`.
2. Policy steuert:
	- kontrollierte tab-lose Dialog-Ausnahmen (UID-basiert),
	- bekannte Edit-Type-Contracts,
	- Dropdown-Source-Guardrails (Allowed Sources, Prefix-Whitelist, Limit-Cap).
3. Policy-Ausnahmen duerfen keine stillen Fehler maskieren; jede Ausnahme muss mit Begruendung vorliegen.
4. Fuer jede tab-lose Ausnahme sind Lifecycle-Felder verpflichtend:
	- `owner`
	- `expires_at` (ISO Datum, `YYYY-MM-DD`)
5. Fehlende oder abgelaufene Lifecycle-Felder werden als Warnungen reportet.
6. Zusaetzliche Vorwarnung vor Ablauf ist verpflichtend:
	- Warnung bei `days_left <= expires_soon_days` (Default: 14 Tage).
	- `expires_soon_days` wird ueber Policy-Metadaten gesteuert.

### 3.5 Dropdown-Sprachkonvention

1. Statische Dropdowns werden auf Sprachkeys in `OPTIONS.*.values` geprueft.
2. Zielvorgabe: DE-DE + EN-US (ohne Alias-Alternativen).
3. Fehlende zweisprachige Pflege wird als Warnung reportet.

## 4. Reportformat (Mindeststruktur)

1. `summary` mit Total/Pass/Fail/Warnung.
2. `checks` als Liste einzelner Pruefungen.
3. `inventory` fuer Dialogtypen, Edit-Typen, Module.
4. `violations` mit Schweregrad (`error|warning`).
5. `recommendations` mit priorisierten Folgemassnahmen.

## 5. Einsatzpunkte

1. Vor Normalisierungs-Massnahmen (Baseline).
2. Nach jeder Refaktoring-Iteration.
3. Vor Abschlussentscheidungen zu Architektur-Differenzen.

## 6. Abnahmekriterien fuer V1-Analyzer

1. Tool laeuft ohne interaktive Eingaben.
2. Report ist maschinenlesbar (JSON, stabiler Aufbau).
3. Kernregeln 3.1 bis 3.5 werden nachvollziehbar geprueft.
4. Der Report ist als Entscheidungsgrundlage fuer D1-D6 geeignet.

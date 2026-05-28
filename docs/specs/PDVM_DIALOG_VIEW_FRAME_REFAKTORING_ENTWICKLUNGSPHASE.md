# PDVM Dialog/View/Frame Refaktoring (Entwicklungsphase)

Status: Analyse- und Ziel-Spezifikation
Datum: 2026-05-21
Scope: Dialoge, Views, Frames, Edit-Typen, InputControls, Dropdown-Quellen
Hinweis: In dieser Entwicklungsphase erfolgt Refaktoring ohne zusaetzliche DB-Versionachsen fuer diesen Teilbereich.

## 1. Zielbild (kompakt)

1. Jeder Menuepunkt startet einen Dialog.
2. Dialoge werden ausschliesslich ueber `sys_dialogdaten` konfiguriert.
3. Tabs sind die zentrale Steuerungseinheit (`MODULE`, `EDIT_TYPE`, `GUID`, optional `TABLE`).
4. `DIALOG_TYPE=edit` und `DIALOG_TYPE=work` bleiben, mit klar getrennten Laufmodellen.
5. UI-Darstellung erfolgt grundsaetzlich ueber `pdvm_inputcontrols` und Frame-Definitionen in `sys_framedaten`.
6. Control-Basis liegt zentral in `sys_control_dict`; tab-spezifische Abweichungen liegen im Frame.
7. Keine Sonderdarstellungen ausser explizit dokumentierten Uebergangs-Ausnahmen.

## 2. Ist-Bild und Leitregeln

Bereits verbindlich (Auszug):
1. Dialog/View/Edit Autonomie und Draft-Flow (ARCHITECTURE_RULES 2.5, 2.5a).
2. Einheitlicher Edit-Frame (ARCHITECTURE_RULES 2.6, PDVM_DIALOG_EDIT_FRAME_SPEC).
3. Dialog V2 mit Modul-Tabs (`view|edit|acti`) (PDVM_DIALOG_EDIT_FRAME_SPEC, DIALOG_WORKFLOW_DATENMODELL_V1).
4. View-State Scope muss `(view_guid, table, edit_type)` sein (ARCHITECTURE_RULES 1.4).
5. `edit_user` darf nur ueber `PdvmCentralDatabase.get_value/set_value` schreiben (ARCHITECTURE_RULES 1.1).

## 3. Fachliche Festlegungen aus diesem Refaktoring

### 3.1 Dialogstart und Tab-Logik

1. Jeder Menuepunkt startet genau einen Dialog (`go_pdvm_dialog`).
2. Tabs werden aus `sys_dialogdaten` gelesen.
3. Wenn genau ein Tab konfiguriert ist, wird kein visueller Tab-Header dargestellt.
4. Die Tab-Reihenfolge ist linear und stabil (kein implizites Umordnen im Frontend).
5. Modulmenge ist verbindlich: `view|show|edit|acti`.

### 3.2 Dialog-Typen

1. `edit`:
   - klassische Tabs,
   - direkte Arbeit auf Zieldaten (unter Einhaltung Central-Write/Draft-Regeln).
2. `work`:
   - Tabs als Workflow-Sequenz,
   - Zwischenspeicherung nur in `dev_workflow_draft`,
   - `ROOT.TABLE` in `sys_dialogdaten` ist fuer `work` optional,
   - Runtime-Zieltabelle ist hart `dev_workflow_draft` (kein Tabellenwechsel ueber Dialog-Config),
   - letzter Tab muss `MODULE=acti` besitzen, erst dort wird die Abschlussaktion ausgefuehrt.

### 3.3 Edit-Typen (zu spezifizieren und zu haerten)

Verwendete/zu fuehrende Edit-Typen in diesem Paket:
1. `view` (Platzhalter / View-Modul)
2. `pdvm_edit`
3. `show_json`
4. `edit_json`
5. `import_data`
6. `menu`
7. `edit_user`

Regel:
1. Jeder Edit-Typ bekommt einen klaren Contract: Eingaben, erlaubte Writes, Renderpfad, Persistenzpfad, Validierung.
2. Keine impliziten Seiteneffekte ausserhalb des definierten Contracts.
3. `show_json` wird ausschliesslich im Modul `show` verwendet (nicht im Modul `edit`).
4. `MODULE=show` wird im Frontend als edit-aehnlicher Tab behandelt (Renderpfad wie Edit-Bereich),
   damit `show_json`-Dialoge den Bearbeiten-Tab konsistent laden.

### 3.4 InputControls-First

1. Darstellungen erfolgen standardmaessig ueber `pdvm_inputcontrols`.
2. `sys_framedaten` ist die konkrete Renderbeschreibung je Tab.
3. `sys_control_dict` ist der zentrale Control-Standard.
4. Frame-Werte duerfen Control-Defaults ueberschreiben; Rueckschreiben in `sys_control_dict` nur explizit.

Uebergangs-Ausnahmen (bewusst):
1. `show_json` und `edit_json` bleiben als Rohdatenpfad zulaessig.
2. Diese Ausnahmen sind dokumentiert und duerfen nicht unkontrolliert wachsen.

### 3.5 Dropdown-Quellen

Dropdowns werden in drei Modi unterstuetzt:
1. Statisch ueber Datensaetze in `sys_dropdowndaten`.
2. View auf eine Tabelle (optional mit Suche/Filter).
3. View ueber mehrere Tabellen via Prefix-Filter (ein oder mehrere Prefixe).

Regel:
1. Fuer jeden Dropdown-Control muss die Quelle explizit konfiguriert sein.
2. Fallbacks ohne explizite Quelle sind nicht zulaessig.

Hinweis zur Sprachpflege (verbindliche Linearitaet):
1. Statische Dropdown-Quellen in `sys_dropdowndaten` werden grundsaetzlich zweisprachig gepflegt:
   `DE-DE` und `EN-US`.
2. Abweichende Sprach-Aliase sind in diesem Kontext nicht zulaessig.

### 3.6 Views

1. Bestehende View-Funktionalitaet bleibt nutzbar.
2. Gleichzeitig wird Optimierungspotenzial systematisch bewertet (Filterkosten, Recompute, Projektion, State-Merge).
3. View-Verhalten muss konsistent mit Dialogkontext (table/edit_type) bleiben.

Verbindlicher Laufablauf fuer Dialog-Tab mit `MODULE=view`:
1. Dialog liefert `TAB_n`-Konfiguration (`GUID`, optional `TABLE`, optional `EDIT_TYPE`).
2. Frontend oeffnet die View immer ueber `view_guid=TAB_n.GUID`.
3. Table-Aufloesung erfolgt strikt in dieser Reihenfolge:
   - expliziter Aufrufparameter `dialog_table` (wenn gesetzt),
   - danach `TAB_n.TABLE` (wenn gesetzt),
   - sonst kein Override; Backend nutzt `sys_viewdaten.ROOT.TABLE` als Fallback.
4. Fuer den View-Tab ist `edit_type=view` der Standardpfad.
5. View-State/Persistenz bleibt auf `(view_guid, table, edit_type)` gescoped.

Verbindliche Runtime-Policy fuer Tabellen-Override (Dialog):
1. Wenn der Dialog mit `dialog_table` gestartet wird, gilt diese Tabelle als aktive Dialogtabelle.
2. Das Runtime-Merkmal `force_table_override` erzwingt dann dieselbe Tabelle in View- und Edit-Datenpfaden.
3. Diese Erzwungene-Aufloesung gilt fuer alle `edit_type` (inkl. `show_json`, `edit_json`, `pdvm_edit`,
   `import_data`, `menu`, `edit_user`).
4. Ohne `dialog_table` bleibt das bestehende Fallback-Verhalten aktiv (TAB.TABLE -> ROOT.TABLE).
5. Ausnahme `DIALOG_TYPE=work`: Runtime-Tabelle ist immer `dev_workflow_draft`; `dialog_table` und
   `ROOT.TABLE` werden dafuer nicht als Zieltable verwendet.

Konsequenz:
1. Wenn eine Dialog-Root-Table blind als View-Override verwendet wird, kann TAB_01 trotz korrekter
   `sys_viewdaten`-Definition auf der falschen Tabelle laufen.
2. Dieser Fehler zeigt sich typischerweise als "Overview funktioniert nicht", obwohl View-UID,
   View-ROOT und Tabellenstruktur korrekt sind.

### 3.7 Datum/Uhrzeit

1. Intern wird der PDVM-Datepfad verwendet (`pdvm_datetime`/Pdvm-Datepicker-Logik).
2. Keine parallelen Zeitformate fuer dieselbe fachliche Bedeutung.

### 3.8 Normalisierung ohne Ausnahmen

1. Einheitliches Verhalten hat Vorrang vor einzelfallgetriebenen Sonderpfaden.
2. Jede verbleibende Ausnahme muss explizit dokumentiert, begruendet und terminiert sein.

## 4. Schwachstellenanalyse (Ist-Risiken)

1. Edit-Type Contracts sind teilweise implizit statt formal.
2. Dialogtyp `work` ist konzeptionell stark, aber nicht ueberall gleich strikt erzwungen.
3. Tab-Sichtbarkeit bei `TABS=1` ist nicht zentral als verbindliche UI-Regel dokumentiert.
4. InputControls-First ist Zielbild, aber JSON/Edit-Sonderpfade koennen ausufern.
5. Dropdown-Quellen sind flexibel, jedoch potenziell uneinheitlich konfiguriert.
6. Prefix-basierte Multi-Table-Views brauchen klare Performance- und Sicherheitsgrenzen.
7. View-Optimierungen sind verteilt dokumentiert, nicht als einheitliches Benchmark-Ziel.
8. Doppelte Logik in Dialog/View/Frame-Konfigurationen kann zu Divergenz fuehren.
9. Unterschiede zwischen `edit` und `work` sind funktional klar, aber technisch noch nicht ueberall hart validiert.
10. Fehlende zentrale Quality-Gates fuer neue Edit-Typen erhoehen Inkonsistenzrisiko.

Verbindliche Abschlussregel fuer die Umsetzung:
1. Alle hier gelisteten Schwachstellen muessen bis zum Abschluss der Refaktoring-Roadmap explizit
   auf Beseitigung geprueft werden.
2. Offene Restpunkte sind mit Begruendung, Risikoeinschaetzung und Zieltermin zu dokumentieren.

## 5. Differenzen zu Architekturregeln (Mapping)

### 5.1 Bereits kompatibel

1. Dialogstart ueber Menue + DB-Konfiguration ist kompatibel.
2. View/Edit-Autonomie ist kompatibel.
3. Composite View-State Scope ist kompatibel.
4. Einheitlicher Edit-Frame ist kompatibel.
5. `edit_user`-Sonderregel ueber PdvmCentralDatabase ist kompatibel.

### 5.2 Als Regel festgelegt (verbindlich)

1. Single-Tab-Darstellung ohne Tab-Header ist harte Architekturregel.
2. Bei `DIALOG_TYPE=work` muss der letzte Tab `MODULE=acti` sein (harte Regel).
3. JSON/Edit-Sonderpfade (`show_json`, `edit_json`) bleiben Uebergangsausnahme; mit Einfuehrung
   der Menue-Security werden diese Pfade nur fuer Entwickler freigegeben.
4. Fuer Prefix-basierte Multi-Table-Dropdown-Views gelten verbindliche Guardrails
   (Prefix-Whitelist, Max-Result, Timeout, Caching, Logging).

## 6. Entscheidungen (festgelegt)

D1. `TABS=1` wird global ohne Tab-Header erzwungen.
1. Entscheidung: Ja.

D2. Bei `DIALOG_TYPE=work` ist der letzte Tab zwingend `MODULE=acti`.
1. Entscheidung: Ja.

D3. Neue Edit-Typen werden nur mit formalem Contract aufgenommen.
1. Entscheidung: Ja.

D4. `show_json/edit_json` bleiben dokumentierte Entwicklungs-Ausnahme.
1. Entscheidung: Ja.

D5. Dropdown Prefix-Multi-Table wird in der ersten Runde limitiert.
1. Entscheidung: Ja.

D6. Ein zentraler Analyzer fuer Dialog/View/Frame-Konsistenz wird eingefuehrt.
1. Entscheidung: Ja.

## 7. Refaktoring-Roadmap (ohne neue Versionierungsachse)

Phase A: Analyse und Inventar
1. Vollstaendiges Inventar aller Dialoge mit `DIALOG_TYPE`, Tabs, `MODULE`, `EDIT_TYPE`, GUID-Referenzen.
2. Vollstaendiges Inventar aller Frames mit FIELDS/Overrides.
3. Vollstaendiges Inventar aller Views inkl. State-Scope-Verwendung.
4. Inventar aller Dropdown-Quellen inkl. Typ (static/table/prefix).

Phase B: Normalisierung
1. Dialog-Schema haerten (Tabs, Module, Single-Tab-Rendering-Regel).
2. Workflow-Regeln fuer `work` technisch erzwingen.
3. Edit-Type Contracts dokumentieren und im Backend validieren.
4. Dropdown-Quellen standardisieren und Guardrails einfuehren.

Fortschritt 2026-05-23:
1. B1 abgeschlossen: tab-lose Ausnahmen entfernt und Dialoge auf explizite TAB-Struktur migriert.
2. B3 abgeschlossen: harte Backend-Validierung der Edit-Type-Contracts aktiv (policy-basiert).
3. Aktueller Analyzer-Stand: keine offenen Violations (error=0, warning=0).

Phase C: Optimierung
1. View-Recompute und Filterpfade benchmarken und vereinheitlichen.
2. Frame/Control Merge konsolidieren (keine stillen Fallbacks).
3. Legacy-Sonderpfade auf dokumentierte Ausnahmen reduzieren.

Phase D: Abschluss
1. Konsistenzreport Dialog/View/Frame erstellen.
2. Architektur-Differenzen final entscheiden.
3. Fehlende Regeln in `ARCHITECTURE_RULES.md` uebernehmen.

## 8. Mindest-Akzeptanzkriterien

1. Jeder Menueeintrag startet reproduzierbar genau einen Dialog aus `sys_dialogdaten`.
2. Single-Tab-Dialoge rendern ohne Tab-Header.
3. `work`-Dialoge laufen deterministisch ueber Draft-Tabkette und enden in `acti`.
4. Jeder Edit-Typ besitzt einen dokumentierten Contract.
5. InputControls sind der Standardweg; Ausnahmen sind explizit dokumentiert.
6. Dropdown-Quellen sind je Control eindeutig und validiert.
7. View-State ist konsistent auf `(view_guid, table, edit_type)` gescoped.
8. Konsistenzanalyse weist keine kritischen Architekturabweichungen mehr aus.

## 9. Direkt naechste Arbeitspakete

1. Analyzer-Spezifikation erstellen: `PDVM_DIALOG_VIEW_FRAME_ANALYSE_SPEC.md`.
2. Analyzer-Tooling definieren (Reports fuer Dialog/Frame/View/EditType/Dropdown).
3. Entscheidungsrunde D1-D6 mit finalen Architektur-Entscheidungen vorbereiten.

# Datenversionierung Phase A - Umsetzung und Betriebsregeln

Status: aktiv

## 1. Ziel von Phase A

Phase A stellt die Template-Governance fuer den datengetriebenen Workflow sicher:

1. fehlende Workflow-Templates standardisiert definieren,
2. Vollstaendigkeit und Struktur automatisch pruefen,
3. Seed-Prozess idempotent und reproduzierbar ausfuehren.

Damit wird die Grundlage fuer die praktische Dialog-Integration der Datenversionierung gelegt.

## 2. Umgesetzte Artefakte

### 2.1 Template-Registry

Datei:
- backend/tools/release_workflow_template_registry.py

Inhalt:
- zentrale Definition der benoetigten Templates fuer
  - sys_dialogdaten
  - sys_viewdaten
  - sys_framedaten
  - sys_control_dict
- deterministische GUID-Erzeugung per Namespace + key
- SELF_GUID/SELF_NAME Aufloesung fuer Seed/Checks

### 2.2 Health-Check Tool

Datei:
- backend/tools/release_workflow_template_health_check.py

Prueft:
- Existenz aller Pflicht-Templates
- Mindeststruktur je Kategorie
  - dialog: ROOT.DIALOG_TYPE=work, ROOT.TAB_ELEMENTS
  - view: ROOT.TABLE
  - frame: ROOT.TAB_ELEMENTS, FIELDS
  - control: ROOT + CONTROL, CONTROL.FIELD/FELD in GROSS

### 2.3 Seed Tool

Datei:
- backend/tools/seed_release_workflow_templates.py

Eigenschaften:
- default dry-run
- apply nur mit --apply
- idempotent
- optionales --force-update fuer vorhandene UID-Saetze
- Name-Konflikte werden nicht blind ueberschrieben (sicheres Verhalten)

## 3. Betriebsablauf (verbindlich)

1. Vor jeder Aenderung: Health-Check ausfuehren.
2. Seeder zuerst im dry-run pruefen.
3. Seeder mit --apply nur bei validiertem Ergebnis.
4. Danach erneut Health-Check als Abschlusskontrolle.

## 4. Kommandos

Im Ordner backend ausfuehren:

```powershell
python tools/release_workflow_template_health_check.py
python tools/seed_release_workflow_templates.py
python tools/seed_release_workflow_templates.py --apply
python tools/release_workflow_template_health_check.py --json
```

Optional explizite DB:

```powershell
python tools/release_workflow_template_health_check.py --db-url "postgresql://..."
python tools/seed_release_workflow_templates.py --db-url "postgresql://..." --apply
```

## 5. Architekturregeln fuer die Zukunft

Diese Punkte sind fuer alle Folgearbeiten verbindlich:

1. Kein SQL in Routern
- Alle Datenlogik bleibt im Service-Layer oder in dedizierten Tools.

2. Single Source fuer Verbindungen
- Tools nutzen dieselbe Connection-Aufloesung wie das System (ConnectionManager/System-Config).

3. Template-Aenderungen nur ueber Registry + Seeder
- Keine ad-hoc Einzelmanipulation produktiver Template-Saetze.

4. Nicht-destruktiver Standard
- Dry-run ist Standard.
- Ueberschreiben bestehender UID-Saetze nur explizit mit --force-update.

5. Deterministische GUIDs
- Workflow-Template-GUIDs werden aus Namespace + key abgeleitet.
- Keine zufaelligen GUIDs fuer Standard-Templates.

6. Namenskonventionen beibehalten
- Controls in sys_control_dict folgen der Tabellenpraefix-Regel (SYS_<FIELD>).
- CONTROL.FIELD und CONTROL.FELD sind GROSS.

7. JSONB-Schreibregel fuer Seeder/Tools
- Bei asyncpg-Schreibzugriffen mit $n::jsonb wird die Nutzlast als JSON-String uebergeben (json.dumps), nicht als Python-Dict.
- Diese Regel verhindert Typfehler beim Insert/Update in daten/jsonb-Spalten.

## 6. Offene Punkte fuer naechste Phase

1. Rollenfreigabe fuer Sichtbarkeit/Anwendung admin + develop im Workflow-Dialog.
2. Factory-Service, der dialog/view/frame/menu aus den Templates erzeugt.
3. UI-seitige Prefix-Suche + Quick-Create fuer Dictionary-Properties.

## 7. Update Stand 2026-05-08

Die Template-Registry wurde auf das vereinbarte Dialog-Modell angepasst:

1. 5-Tab Mapping im Workflow-Dialog:
- Setup (edit -> frame)
- Dialog (edit -> frame)
- View (view -> sys_viewdaten)
- Dictionary (edit -> frame)
- Build (acti -> frame)

2. Deterministische GUID-Referenzen in `TAB_ELEMENTS`:
- Dialog-Templates referenzieren View/Frame-Templates direkt per stabiler GUID.

3. Workflow-Frames enthalten jetzt konkrete `FIELDS` (nicht mehr leer):
- Setup-Frame: Basisparameter (Release Type, Target Env, Policy, Hash, Commit, ...)
- Dialog-Frame: Workflow/Dialog-Metadaten
- Dictionary-Frame: Suche + Prefix + Create-Action
- Build-Frame: Dry-Run + Apply-Action

4. Health-Check erweitert:
- prueft Dialog-Module (`view`/`acti`) und GUID-Gueltigkeit je Tab
- prueft Mindestfelder in den Workflow-Frames

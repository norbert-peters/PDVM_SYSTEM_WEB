# Dialog Linear Redesign Analyse (19.02.2026)

## Ausgangslage
Die bisherige Dialogstruktur ist funktional, aber in der Pflege zu komplex, weil:
- Tabs mehrfach modelliert werden (`TAB_01/02` + `VIEW_GUID/FRAME_GUID` Duplikate)
- lineare Bearbeitung von Tab-Definitionen in `pdvm_edit` nicht sauber als ein Feld abbildbar ist
- `ROOT`-Pfad und Gruppenpflege nicht durchgaengig als strukturierte Listen gedacht sind

## Zielbild (vereinheitlicht)
Alle Dialoge nutzen `ROOT.TAB_ELEMENTS` als zentrale Tab-Liste:

```json
{
  "ROOT": {
    "SELF_GUID": "...",
    "SELF_NAME": "...",
    "TABLE": "...",
    "DIALOG_TYPE": "norm",
    "TABS": 2,
    "EDIT_TYPE": "pdvm_edit",
    "TAB_ELEMENTS": {
      "TAB_01": {
        "GUID": "...",
        "HEAD": "Liste",
        "TABLE": "...",
        "MODULE": "view",
        "EDIT_TYPE": "pdvm_edit",
        "OPEN_EDIT": "double_click",
        "SELECTION_MODE": "single"
      },
      "TAB_02": {
        "GUID": "...",
        "HEAD": "Bearbeiten",
        "TABLE": "...",
        "MODULE": "edit",
        "EDIT_TYPE": "pdvm_edit",
        "OPEN_EDIT": "double_click",
        "SELECTION_MODE": "single"
      }
    }
  }
}
```

## Was implementiert wurde
1. Runtime-Unterstuetzung fuer `TAB_ELEMENTS` in `extract_dialog_runtime_config`
   - Datei: [backend/app/core/dialog_service.py](backend/app/core/dialog_service.py)
   - Wirkung:
     - liest Tabs aus `ROOT.TAB_ELEMENTS` (dict oder list)
     - fallback auf Legacy `TAB_01/TAB_02/...`
     - leitet `view_guid` und `frame_guid` aus `MODULE=view/edit` + `GUID` ab
     - dadurch sind `VIEW_GUID`/`FRAME_GUID` nicht mehr zwingend

2. Seed-Dialog fuer `sys_control_dict` auf `TAB_ELEMENTS` umgestellt
   - Datei: [backend/tools/create_sys_control_dict_dialog.py](backend/tools/create_sys_control_dict_dialog.py)

3. Setup-Skript fuer `pdvm_edit` auf `sys_dialogdaten`
   - Datei: [backend/tools/setup_pdvm_edit_dialog_for_sys_dialogdaten.py](backend/tools/setup_pdvm_edit_dialog_for_sys_dialogdaten.py)
   - erzeugt:
     - fehlende `sys_control_dict` Controls (`SYS_*`) fuer Dialog-ROOT
     - View (`sys_viewdaten`) fuer `sys_dialogdaten`
     - Frame (`sys_framedaten`) inkl. `TAB_ELEMENTS` als `element_list`
     - Dialog (`sys_dialogdaten`) mit neuer `TAB_ELEMENTS` Struktur

4. Migrationsskript fuer bestehende Dialogsaetze
   - Datei: [backend/tools/migrate_dialogs_to_tab_elements.py](backend/tools/migrate_dialogs_to_tab_elements.py)
   - migriert Legacy `TAB_XX` nach `TAB_ELEMENTS`
   - setzt `SELF_GUID` / `SELF_NAME`
   - entfernt `VIEW_GUID` / `FRAME_GUID` Duplikate in ROOT

## Offene/zu pruefende Punkte (Analyse)
1. `TAB_ELEMENTS` als dict vs list:
   - Runtime unterstuetzt beides.
   - Empfehlung: persistiert als dict mit `TAB_01..` fuer Lesbarkeit und stabile Diffs.

2. `ROOT` als `element_list`:
   - fachlich sinnvoll fuer spaetere Gruppenverwaltung.
   - aktuell ist `TAB_ELEMENTS` bereits als `element_list` im Frame umgesetzt.
   - naechster Schritt: Root-Gruppeneditor als eigene `element_list` standardisieren.

3. sys_ Tabellen-Ausnahmen:
   - muessen pro Tabelle explizit beschrieben werden.
   - Kernmechanik bleibt gleich (Dialog -> View/Frame via `TAB_ELEMENTS`).

4. Kontrolle der vorhandenen 666/555 Templates in `sys_control_dict`:
   - Setup nutzt diese als Defaults fuer neue Controls.
   - falls in einer Umgebung nicht vorhanden/inkonsistent: Templates zuerst harmonisieren.

## Update 01.03.2026 (Frame-Tab Harmonisierung)
- `sys_framedaten` wurde fuer die Schluessel-Datensaetze (666..., 555..., Testframe) auf `ROOT.TAB_ELEMENTS` harmonisiert.
- Legacy `ROOT.TAB_01`/`ROOT.TAB_02` wurde im Testframe entfernt, damit nur noch eine Tab-Quelle aktiv ist.
- Frontend (`PdvmDialogPage`) liest Frame-Tabs jetzt ebenfalls zuerst aus `ROOT.TAB_ELEMENTS` und nutzt `TABS_DEF`/`TAB_XX` nur noch als Fallback.
- Ergebnis: Dialog- und Frame-Tabmechanik sind technisch gleichgezogen und kompatibel zu bestehender Legacy-Struktur.

## Ausfuehrungsempfehlung (Reihenfolge)
1. Setup neuer Dialogdaten-Editor:
```powershell
python backend/tools/setup_pdvm_edit_dialog_for_sys_dialogdaten.py
```

2. Migration zuerst als Analyse:
```powershell
python backend/tools/migrate_dialogs_to_tab_elements.py --dry-run
```

3. Migration anwenden:
```powershell
python backend/tools/migrate_dialogs_to_tab_elements.py
```

4. Smoke-Tests:
- `GET /api/dialogs/{dialog_guid}`
- `POST /api/dialogs/{dialog_guid}/draft/start`
- `PUT /api/dialogs/{dialog_guid}/draft/{draft_id}`
- `POST /api/dialogs/{dialog_guid}/draft/{draft_id}/commit`

## Architektur-Regeln
Die Umsetzung bleibt konform zu [ARCHITECTURE_RULES.md](ARCHITECTURE_RULES.md):
- keine SQL im Router
- lineare Draft-Neuanlage bleibt erhalten
- Dialog/View/Edit bleiben logisch getrennt

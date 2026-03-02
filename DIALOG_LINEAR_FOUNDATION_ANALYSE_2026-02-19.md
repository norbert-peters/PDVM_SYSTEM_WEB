# Dialog Linear Foundation Analyse (19.02.2026)

## Ziel
Aufbau einer linearen, tabellenunabhaengigen Dialog-Basis mit:
- fester 6666-Template-Struktur fuer Neuanlage
- 5555-Template-Struktur fuer Element-/Feldvorlagen
- Controls in `sys_control_dict` nach Konvention `SYS_<CONTROLNAME>`
- erster Dialogsatz im Format `ROOT.TAB_ELEMENTS`

## Umgesetzt
Ausgefuehrt mit:
- [backend/tools/setup_linear_dialog_foundation.py](backend/tools/setup_linear_dialog_foundation.py)

Ergebnis:
- Templates gesetzt:
  - `sys_control_dict` UID `666...` + `555...`
  - `sys_dialogdaten` UID `666...` + `555...`
- Controls upserted in `sys_control_dict`: **25**
- Dialogsatz upserted: `1f3a0e00-48bb-4a08-9cb8-7a7d52f23001`

## Eingestellte Template-Inhalte
### `sys_control_dict` – UID `666...`
```json
{
  "ROOT": { "SELF_GUID": "", "SELF_NAME": "" },
  "CONTROL": {}
}
```

### `sys_control_dict` – UID `555...`
```json
{
  "TEMPLATES": {
    "CONTROL": {
      "NAME": "", "TYPE": "", "FIELD": "", "LABEL": "", "TABLE": "", "GRUPPE": "",
      "ABDATUM": false, "DEFAULT": "", "SORTABLE": true, "READ_ONLY": false,
      "HISTORICAL": false, "SEARCHABLE": true, "EXPERT_MODE": true, "FILTER_TYPE": "contains",
      "PARENT_GUID": null, "SOURCE_PATH": "root", "DISPLAY_SHOW": true,
      "EXPERT_ORDER": 0, "DISPLAY_ORDER": 0, "SORT_DIRECTION": "asc", "SORT_BY_ORIGINAL": false,
      "FIELDS_ELEMENTS": {}, "CONFIGS_ELEMENTS": {}
    },
    "CONFIGS_ELEMENTS": {"KEY": "", "FIELD": "", "TABLE": "", "GRUPPE": "", "ELM_TYPE": ""},
    "FIELDS_ELEMENTS": {"BY_FRAME_GUID": true}
  }
}
```

### `sys_dialogdaten` – UID `666...`
```json
{
  "ROOT": {
    "TABS": 0,
    "TABLE": "",
    "SELF_GUID": "",
    "SELF_NAME": "",
    "DIALOG_TYPE": "norm",
    "TAB_ELEMENTS": {}
  }
}
```

### `sys_dialogdaten` – UID `555...`
```json
{
  "TEMPLATES": {
    "TAB_ELEMENTS": {
      "TAB_GUID": {
        "TAB": 0, "GUID": "", "HEAD": "", "TABLE": "", "MODULE": "",
        "EDIT_TYPE": "", "OPEN_EDIT": "", "SELECTION_MODE": ""
      }
    }
  }
}
```

## Analyse: Geht die Struktur so?
Ja, mit aktuellem Backend-Stand ist das tragfaehig:
1. Runtime liest `TAB_ELEMENTS` bereits direkt und bleibt abwaertskompatibel.
2. `VIEW_GUID`/`FRAME_GUID` sind nicht mehr zwingend, da aus `TAB_ELEMENTS` + `MODULE` ableitbar.
3. Neuanlage ueber 666-Template bleibt linear (Draft-Flow) und tabellenuebergreifend einsetzbar.

## Coverage-Pruefung der 666/555-Templates
Die Pruefung gegen vorhandene Controls ergab:
- beobachtete Uppercase-Keys: **28**
- in `TEMPLATES.CONTROL` hinterlegte Keys: **23**
- fehlend im Template: **3**
  - `ROOT`
  - `CONTROL`
  - `TABLE_INFO`

### Bewertung der fehlenden Keys
- `ROOT` und `CONTROL` sind strukturelle Container (keine Feld-Properties) und koennen bewusst ausserhalb von `TEMPLATES.CONTROL` bleiben.
- `TABLE_INFO` ist fachlicher Zusatzkey aus Bestandsdaten; falls er kuenftig standardisiert werden soll, kann er als optionaler CONTROL-Key ins 555-Template aufgenommen werden.

## Naechster sinnvoller Schritt
Wie von dir vorgegeben: Framedaten gezielt anpassen, damit die neuen element_list-Definitionen (`ROOT`, `CONTROL`, `TAB_ELEMENTS`, `FIELDS_ELEMENTS`, `CONFIGS_ELEMENTS`) im `pdvm_edit` vollstaendig linear pflegbar sind.

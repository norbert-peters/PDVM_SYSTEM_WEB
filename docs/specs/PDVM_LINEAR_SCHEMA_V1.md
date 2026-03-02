# PDVM Linear Schema V1 (Verbindliche SOLL-Definition)

Stand: 2026-02-21  
Status: **verbindlich für Neuanlage und Migration**

## 1. Ziel
Dieses Dokument definiert die einheitliche Datenstruktur für die lineare, datenbankgetriebene Pflege im PDVM System Web.

Leitsatz:
- Source führt aus.
- Struktur/Regeln liegen in der Datenbank.
- Keine verdeckte Fachlogik außerhalb der definierten Datenmodelle.

## 2. Geltungsbereich
Diese Spezifikation gilt mindestens für:
- `sys_control_dict` (System-Control-Dictionary)
- `sys_contr_dict_man` (Mandanten-Control-Dictionary)
- `sys_dialogdaten`
- `sys_viewdaten`
- `sys_framedaten`

Bestehende `ARCHITECTURE_RULES.md` bleiben voll gültig und werden durch dieses Dokument konkretisiert.

## 3. Schreibweisen (verbindlich)

### 3.1 Tabellen
- Tabellenname immer **klein**: z. B. `sys_control_dict`
- Präfix (erste 3 Zeichen) kennzeichnet Domäne/App: z. B. `sys_`

### 3.2 Gruppen
- Gruppennamen in JSON immer **GROSS**: `ROOT`, `CONTROL`, `TEMPLATES`, `SYSTEM`, `DATAS`, usw.

### 3.3 Property-Keys
- Fachliche Property-Keys in `ROOT`/`CONTROL`/`TEMPLATES` immer **GROSS**
  - Beispiele: `SELF_GUID`, `SELF_NAME`, `TABLE`, `TYPE`, `DISPLAY_ORDER`

### 3.4 Runtime-Kompatibilität
- Für Altbestände sind temporäre Fallbacks (case-insensitive Lesen) erlaubt.
- Zielbild ist jedoch **vollständig normalisierte Großschreibung** gemäß diesem Dokument.

## 4. Globale Datensatz-Basis
Jeder Datensatz in `daten` enthält mindestens:

```json
{
  "ROOT": {
    "SELF_GUID": "<uid aus Spalte uid>",
    "SELF_NAME": "<logischer Name>"
  }
}
```

Pflichtregeln:
- `ROOT.SELF_GUID` muss dem Tabellenfeld `uid` entsprechen.
- `ROOT.SELF_NAME` muss mit Tabellenfeld `name` synchronisiert werden.
- Ohne diese Basis ist ein Datensatz ungültig.

## 5. Fiktive Template-Sätze (Pflicht)
Für jede pflegbare Tabelle müssen vorhanden sein:
- `66666666-6666-6666-6666-666666666666` (Basis-Template)
- `55555555-5555-5555-5555-555555555555` (Erweiterungs-/Element-Templates)

Wenn einer fehlt:
- Neuanlage abbrechen
- eindeutige Fehlermeldung ausgeben

## 6. Neuanlage (linear, handler=go_dialog)
1. Tabelle aus `sys_dialogdaten.ROOT.TABLE` bestimmen.
2. Prüfen: `ROOT.GO_NEW_SET == true` für den Dialog.
3. Name erfassen und Präfix-Regel prüfen.
4. Basis aus `666...` übernehmen.
5. `SELF_GUID`/`SELF_NAME` setzen.
6. Für leere Eigenschaften vom Typ `element_list` passende Template-Struktur aus `555...` (`TEMPLATES`) einfügen.
7. Speichern.
8. Datensatz direkt im Edit anbieten.

## 7. Dialogmodell (`sys_dialogdaten`)

### 7.1 Minimalstruktur
```json
{
  "ROOT": {
    "SELF_GUID": "...",
    "SELF_NAME": "...",
    "TABLE": "sys_control_dict",
    "DIALOG_TYPE": "norm",
    "TABS": 2,
    "GO_NEW_SET": true,
    "TAB_ELEMENTS": {
      "<guid>": {
        "TAB": 1,
        "HEAD": "Liste",
        "MODULE": "view",
        "TABLE": "sys_viewdaten",
        "GUID": "<view_guid>",
        "OPEN_EDIT": "double_click",
        "EDIT_TAB": 2,
        "SELECTION_MODE": "single",
        "EDIT_TYPE": ""
      }
    }
  }
}
```

### 7.2 Regeln
- `TAB_ELEMENTS` ist die **einzige** führende Tab-Definition.
- `TAB_ELEMENTS` ist ein `element_list`.
- Je Tab gilt: `TABLE` + `GUID` bestimmen die Moduldefinition.
- Dialog-ROOT enthält keine redundanten Modul-GUID-Duplikate als Pflicht.

## 8. Control Dictionary (`sys_control_dict` / `sys_contr_dict_man`)

### 8.1 Ziel
Zentrale, eindeutige Control-Definition mit Override-Möglichkeit in View/Frame.

### 8.2 Struktur
```json
{
  "ROOT": {
    "SELF_GUID": "...",
    "SELF_NAME": "..."
  },
  "CONTROL": {
    "NAME": "NAME",
    "TYPE": "string",
    "FIELD": "NAME",
    "LABEL": "Name",
    "TABLE": "sys_control_dict",
    "GRUPPE": "ROOT",
    "UPPER_CASE": false,
    "SORTABLE": true,
    "READ_ONLY": false,
    "HISTORICAL": false,
    "SEARCHABLE": true,
    "EXPERT_MODE": true,
    "FILTER_TYPE": "contains",
    "PARENT_GUID": null,
    "SOURCE_PATH": "ROOT",
    "DISPLAY_SHOW": true,
    "DISPLAY_ORDER": 0,
    "EXPERT_ORDER": 0,
    "SORT_DIRECTION": "asc",
    "SORT_BY_ORIGINAL": false,
    "FIELDS_ELEMENTS": {},
    "CONFIGS_ELEMENTS": {},
    "DEFAULT": "",
    "ABDATUM": false
  }
}
```

### 8.3 Namenskonventionen
- Control-`SELF_NAME`: `<TABELLENPREFIX>_<FIELDNAME>` in GROSSBUCHSTABEN
  - Beispiel: `SYS_DISPLAY_ORDER`
- Allgemeiner Datensatz-`SELF_NAME`: `<APPPREFIX> <Bezeichnung>`
  - Beispiel: `SYS Control Dictionary`

## 9. View-Modell (`sys_viewdaten`)

### 9.1 Regeln
- Bestehende View-Funktionalität bleibt erhalten.
- Spalten-/Control-Metadaten kommen aus Dictionary-Controls, lokal überschreibbar.
- `ROOT.TABLE` ist Pflicht.
- `ROOT.NO_DATA` darf nur verwendet werden, wenn table-unabhängige Darstellung gewollt ist.

### 9.2 Zielbild
- Keys in View-Definitionen ebenfalls auf GROSS normalisieren.
- Alt-Keys in Klein-/Mischschreibung nur als Migrationszwischenstand.

## 10. Frame-Modell (`sys_framedaten`, Edit-Typ `pdvm_edit`)

### 10.1 Grundstruktur
- `ROOT` enthält Frame-Meta und Tabs (selbst als element_list in ROOT).
- Pro Zieltabelle gibt es eine Gruppe `TABELLENNAME_IN_GROSS`.
- Darin liegen die InputControls/Felder.

### 10.2 Darstellung
- Anzeige-Reihenfolge über `DISPLAY_ORDER` bzw. `EXPERT_ORDER`.
- `TYPE` steuert Rendering (`string`, `text`, `true_false`, `date`, `time`, `datetime`, `dropdown`, `element_list`, `json`).
- Ohne Framedaten: leerer Content (kein Absturz).

## 11. Konfigurationsblöcke (`CONFIGS_ELEMENTS`)

### 11.1 Dropdown
Pflichtblock bei `TYPE=dropdown`:
```json
{
  "dropdown": {
    "KEY": "",
    "FIELD": "",
    "TABLE": "",
    "GROUP": ""
  }
}
```

### 11.2 Hilfe/Tooltip
Optional:
```json
{
  "help": {
    "KEY": "",
    "FIELD": "",
    "TABLE": "",
    "GROUP": ""
  },
  "tooltip": {
    "KEY": "",
    "FIELD": "",
    "TABLE": "",
    "GROUP": ""
  }
}
```

Hinweis:
- Inhalte können HTML sein.
- Sprachabhängige Ablage über gruppen-/sprachbezogene Auflösung.

## 12. Verbindliche Mindest-Controls (Bootstrap)
Für den Start müssen mindestens die im Neuausrichtungsdokument benannten Kern-Controls vorhanden sein (u. a.):
- `SYS_SELF_GUID`, `SYS_SELF_NAME`, `SYS_TABLE`, `SYS_GRUPPE`, `SYS_FIELD`, `SYS_TYPE`, `SYS_LABEL`
- `SYS_DISPLAY_SHOW`, `SYS_DISPLAY_ORDER`, `SYS_EXPERT_ORDER`
- `SYS_FILTER_TYPE`, `SYS_SORTABLE`, `SYS_SEARCHABLE`, `SYS_READ_ONLY`, `SYS_HISTORICAL`
- `SYS_CONFIGS_ELEMENTS`, `SYS_FIELDS_ELEMENTS`
- Dialog-/Tab-Controls wie `SYS_TAB_ELEMENTS`, `SYS_MODULE`, `SYS_GUID`, `SYS_EDIT_TYPE`, `SYS_OPEN_EDIT`

## 13. Umsetzungsvorgabe (für Schritt 2/3)
Aus dieser Spezifikation folgen:
1. Validator-Regeln (Schema + Pflichtfelder + Namenskonventionen)
2. Migrationsregeln (Case-Normalisierung + Struktur-Normalisierung)
3. Vereinheitlichung der Neuanlage in View/Dialog

## 14. Nicht-Ziele in V1
- Kein sofortiger Komplettumbau aller Editoren.
- Keine Abschaffung von Legacy-Fallbacks in einem Schritt.
- Keine UI-Feature-Erweiterungen außerhalb der linearen Datenstruktur.

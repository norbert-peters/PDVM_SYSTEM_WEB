# PDVM Elemente-List - Spec (V1)

## Ziel
Eine generische InputControl zur Pflege von Listen-Elementen mit GUID-Keys.
Die Elemente koennen komplette Control-Objekte enthalten (z.B. FIELDS eines edit_frame).

## Grundprinzip
- `elemente_list` verwaltet eine Map mit GUID-Keys.
- Jedes Element ist ein Objekt mit frei definierbaren Properties.
- Anzeige erfolgt als Liste, Bearbeitung in einem Modal.
- Neue Elemente werden aus einem Template erzeugt.

## Einsatzgebiete
- `edit_frame.FIELDS` verwalten
- `CONFIG.COLUMNS` (Import Data) verwalten
- Optional: komplexe `configs`-Strukturen pflegen

## Datenmodell

### 1) Source-Map (Guid keyed)
Beispiel fuer `FIELDS`:
```json
{
  "FIELDS": {
    "7a0d...": {
      "tab": 1,
      "feld": "VORNAME",
      "name": "user_vorname",
      "type": "string",
      "label": "Vorname",
      "table": "SYS_BENUTZER",
      "gruppe": "USER",
      "display_order": 40
    }
  }
}
```

### 2) Template-UIDs
- Neue Saetze: `66666666-6666-6666-6666-666666666666`
- Element-Templates: `55555555-5555-5555-5555-555555555555`

Template-Ablage (verbindlich):
- Gruppe: `ELEMENTS`
- Felder: Template-Keys (z.B. `INPUT_CONTROL`, `TAB_DEF`, `ACTION_STEP`)

Beispiel fuer Element-Template:
```json
{
  "ELEMENTS": {
    "INPUT_CONTROL": {
      "tab": 4,
      "feld": "START.MENU",
      "name": "meineapps_start",
      "type": "go_select_view",
      "label": "Start-Menue",
      "table": "SYS_BENUTZER",
      "gruppe": "MEINEAPPS",
      "abdatum": false,
      "configs": {
        "help": {"key": "", "feld": "", "table": "", "gruppe": ""},
        "dropdown": {"key": "", "feld": "", "table": "", "gruppe": ""}
      },
      "tooltip": "",
      "read_only": false,
      "historical": false,
      "source_path": "root",
      "display_order": 10
    }
  }
}
```

## UI-Verhalten

### Listenansicht
- Zeigt `label` (Fallback: `name`, dann `feld`).
- Elemente mit GUID-Key duerfen nicht ohne Anzeigefeld bleiben (keine GUID-Anzeige im UI).
- Sortierung ueber `display_order` (Fallback: alphabetisch nach `label`).
- Aktionen pro Element: Bearbeiten, Entfernen, Duplizieren.

### Bearbeitungs-Modal
- Alle Properties des Elements sind editierbar.
- Speichern aktualisiert das Element in der Map.
- Abbrechen verwirft Aenderungen.

### Validierung (MVP)
- `label` ist Pflicht, wenn kein `name` oder `feld` existiert.
- Wenn ein Element keinen gueltigen Anzeigewert hat, wird es als Fehler markiert (keine GUID-Anzeige).
- `name` oder `feld` muss vorhanden sein.
- `display_order` ist optional, Default = 10.
- Bei `type=dropdown` muss `configs.dropdown` gueltig sein.

## API/Backend Regeln
- Keine direkten SQL-Queries in Routern.
- Persistenz ueber PdvmCentralDatabase / PdvmDatabase.
- GUID-Key bleibt stabil bei Updates.

## Architektur-Regeln
- InputControls sind generisch, keine speziellen Layouts.
- Dialog View/Edit Autonomie bleibt erhalten.
- Keine Browser-Dialoge, nur PdvmDialogModal.

## Offene Punkte
- Wie sollen `configs` editiert werden (separate `elemente_list` oder Nested-Form)?
- Regeln fuer GUID-Erzeugung (Frontend vs Backend) abstimmen.

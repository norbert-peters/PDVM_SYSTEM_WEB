# Erster konkreter Dialog für `sys_control_dict` (View + Frame)

## Ziel
Ein erster produktiver Referenz-Dialog für `sys_control_dict`, der die aktuellen Architekturregeln erfüllt:
- Dialog V2 mit `TAB_01(view)` und `TAB_02(edit)`
- `EDIT_TYPE = pdvm_edit`
- Neuanlage über linearen Draft-Flow (`draft/start` → `draft/update` → `draft/commit`)
- Frame mit `ROOT`-Feldern plus `ELEMENTS`-`element_list` (für strukturierte Listenpflege)

## Plan (konkret)
1. View-Definition für `sys_control_dict` anlegen (Liste + Sortierung/Filter)
2. Frame-Definition mit 3 PIC-Tabs anlegen:
   - Basis (`ROOT`): Name, Label, Tabelle, Gruppe, Typ, Sortierung
   - Anzeige (`ROOT`): read_only, required, show, tooltip
   - Elements (`ELEMENTS`): `items` als `element_list`
3. Dialog-Definition im V2-Format anlegen und View/Frame verknüpfen
4. Draft-Flow per API smoke-testen

## Umsetzung
Skript: [backend/tools/create_sys_control_dict_dialog.py](backend/tools/create_sys_control_dict_dialog.py)

Standard-GUIDs (überschreibbar über CLI):
- Dialog: `9f06711e-4ad8-4ea4-9837-2f40f3a6f101`
- View: `9f06711e-4ad8-4ea4-9837-2f40f3a6f102`
- Frame: `9f06711e-4ad8-4ea4-9837-2f40f3a6f103`

## Ausführen
```powershell
python backend/tools/create_sys_control_dict_dialog.py
```

Optional mit eigenen GUIDs:
```powershell
python backend/tools/create_sys_control_dict_dialog.py `
  --dialog-uid <uuid> `
  --view-uid <uuid> `
  --frame-uid <uuid>
```

## API-Schnelltest
Nach dem Seed:
1. Dialog laden
   - `GET /api/dialogs/9f06711e-4ad8-4ea4-9837-2f40f3a6f101`
2. Draft starten (Neuanlage)
   - `POST /api/dialogs/9f06711e-4ad8-4ea4-9837-2f40f3a6f101/draft/start`
3. Draft speichern
   - `PUT /api/dialogs/9f06711e-4ad8-4ea4-9837-2f40f3a6f101/draft/{draft_id}`
4. Draft committen
   - `POST /api/dialogs/9f06711e-4ad8-4ea4-9837-2f40f3a6f101/draft/{draft_id}/commit`

## Nächste Replikation (Folgeschritt)
Wenn dieser Referenzdialog stabil läuft, denselben Aufbau auf die Metatabellen spiegeln:
- `sys_dialogdaten`
- `sys_viewdaten`
- `sys_framedaten`

Dabei jeweils gleiches Muster:
- V2-Dialogstruktur
- `pdvm_edit` im Edit-Tab
- Neuanlage ausschließlich über Draft-Flow

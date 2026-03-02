# PDVM Template+Delta Storage V1

Stand: 2026-03-01  
Status: verbindlich fuer `sys_control_dict` und `sys_framedaten`

## 1. Zielbild

Ein Control wird zentral ueber ein Template definiert und lokal nur ueber **Overrides** erweitert.

- **Laden/Verwendung:** immer **vollstaendiges (effective) Control**
- **Speichern/Persistenz:** nur **Delta (abweichende Properties)**

Damit gilt:
- Neue Defaults im zentralen Template (555...) sind sofort bei allen Controls wirksam.
- Redundante Vollkopien in `sys_control_dict` und `sys_framedaten.FIELDS` entfallen.

## 2. Kernprinzipien

1. **Single Source of Truth**
   - Basis liegt in `sys_control_dict` Template `55555555-5555-5555-5555-555555555555`.
2. **Effective on Read**
   - Runtime merged: `defaults + overrides`.
3. **Delta on Write**
   - Persistiert wird nur `overrides = effective - defaults`.
4. **GUID-Referenz bleibt fuehrend**
   - Frames/Views referenzieren Controls per GUID, niemals per Vollkopie.

## 3. `sys_control_dict` Regelwerk

### 3.1 Effective-Aufloesung

Defaults werden aus 555 geladen:
- `TEMPLATES.CONTROL` (gemeinsame Defaults)
- `MODUL[modul_type]` (modul-spezifische Defaults)

`effective_control = defaults + gespeicherte_overrides`

### 3.2 Persistenz

Beim Speichern eines Controls:
- Eingabe wird als effective betrachtet
- gegen Defaults diffen
- nur Delta speichern
- `modul_type` bleibt immer explizit gespeichert

## 4. `sys_framedaten.FIELDS` Regelwerk

Jedes Field kann per GUID (Key oder `dict_ref`) auf ein Control zeigen.

### 4.1 Effective-Aufloesung

`effective_field = control_effective + field_overrides`

### 4.2 Persistenz

Beim Speichern von Frame-Daten:
- fuer GUID-referenzierte Felder nur Abweichungen ggü. Control speichern
- lokale Felder ohne GUID-Referenz bleiben unveraendert

## 5. Warum diese Loesung strukturell passend ist

Die vorgeschlagene Struktur ist die richtige Richtung fuer maximale Flexibilitaet:

- keine tausendfachen Property-Kopien
- zentrale Nachpflege im Template reicht aus
- geringer Migrations- und Wartungsaufwand
- konsistent mit bestehender GUID-Referenzlogik

Weitere Optimierung ist eher **operativ** (Caching, Bulk-Migration, Monitoring), nicht mehr im Grundmodell.

## 6. Implementierungsstatus

Umgesetzt in Backend:
- `backend/app/core/pdvm_datenbank.py`
  - `load_control_definition` liefert effective Control (Template+Delta)
- `backend/app/core/dialog_service.py`
  - `load_dialog_record`: effective fuer `sys_control_dict` und `sys_framedaten`
  - `update_dialog_record_json`: Delta-Persistenz fuer `sys_control_dict`/`sys_framedaten`
  - `create_dialog_record_from_template`: initiale Speicherung ebenfalls als Delta
- `backend/app/core/control_template_service.py`
  - create/switch speichern kompakt (Delta)
- `backend/app/api/control_dict.py`
  - GET/PUT liefern effective Controls, speichern Delta

## 7. Datenanpassung bestehender Datensaetze

Neues Tool:
- `backend/tools/migrate_template_delta_storage_v1.py`

Aufruf:
- Analyse: `python backend/tools/migrate_template_delta_storage_v1.py --dry-run`
- Anwenden: `python backend/tools/migrate_template_delta_storage_v1.py --apply`

Das Tool normalisiert:
- `sys_control_dict` auf Template-Overrides
- `sys_framedaten.FIELDS` auf lokale Field-Overrides

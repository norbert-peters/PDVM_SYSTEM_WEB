# Spezifikation: GILT_BIS / SELF_GILT_BIS V1

## 1. Ziel
Diese Spezifikation definiert die lineare Behandlung von `ROOT.SELF_GILT_BIS` in Write- und Read-Pfaden.

## 2. Begriffe
- `ROOT.SELF_GILT_BIS`: Fachlicher Gueltigkeitswert im PDVM-Format `YYYYDDD.FRACTION`.
- `gilt_bis` (Spalte): Technische DB-Wahrheit fuer Gueltigkeit.
- `offen`: Sentinel `9999365.99999` (`31.12.9999 23:59:59`).

## 3. Anforderungen
1. Datetime/Date/Time InputControl:
- Wenn das Control-Feld `ROOT.SELF_GILT_BIS` adressiert, wird ein Zusatz-Button `offen` angezeigt.
- Klick auf `offen` setzt den Wert auf `9999365.99999`.

2. Speichern / Persistenz:
- Bei Create/Update gilt: Wenn `ROOT.SELF_GILT_BIS` vorhanden und nicht leer ist, wird die Spalte `gilt_bis` aus diesem Wert gesetzt.
- Bei Create ohne expliziten Wert wird `gilt_bis` auf `offen` gesetzt.
- Nach jedem Write werden `SELF_*` in `daten.ROOT` aus den DB-Spalten gespiegelt (inkl. `SELF_GILT_BIS`).

3. Lesen in Views:
- Datensaetze mit `gilt_bis <= stichtag` werden in der View-Basis ausgeschlossen.
- Datensaetze mit offenem Sentinel bleiben sichtbar.

## 4. Implementierungsorte
- Backend Write-Layer: `backend/app/core/pdvm_datenbank.py`
- View-Basis-Filter: `backend/app/core/view_service.py`
- Frontend InputControl: `frontend/src/components/common/PdvmInputControl.tsx`

## 5. Abgleich mit ARCHITECTURE_RULES
Abgleich gegen `ARCHITECTURE_RULES.md`:
- Zeitformatregel (PDVM `YYYYDDD.FRACTION`): eingehalten.
- Zentraler Write-Pfad: eingehalten (Persistenz im zentralen DB-Layer).
- Read-Vertrag (Spalten als technische Wahrheit): eingehalten.
- Sichtbarkeitsregel fuer Views ueber Stichtag: verbindlich definiert.

## 6. Testkriterien (Smoke)
1. Neuer Satz ohne Eingriff in `SELF_GILT_BIS` -> DB `gilt_bis` = offen, `ROOT.SELF_GILT_BIS` = offen.
2. `SELF_GILT_BIS` im Dialog auf frueheres Datum setzen -> Speichern -> Spalte `gilt_bis` und `ROOT.SELF_GILT_BIS` identisch.
3. View mit Stichtag >= `gilt_bis` des Satzes -> Satz nicht sichtbar.
4. `ROOT.SELF_GILT_BIS` InputControl zeigt Button `offen`; Klick setzt Sentinel.

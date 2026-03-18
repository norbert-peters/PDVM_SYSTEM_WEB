# PDVM DateTime Funktionssammlung (Plan)

Ziel: Technische Verbesserungen an DateTime-Hilfsfunktionen gesammelt, ohne die verbindliche Formatdefinition zu verletzen.

Verbindliche Basis:
- Format bleibt immer `YYYYDDD.FRACTION` (Bruchteil des Tages).
- Normative Referenz ist `backend/app/core/pdvm_datetime.py`.
- Keine alternativen Legacy-Encodings im Nachkommateil.

## Kandidaten fuer neue Hilfsfunktionen

1. Einheitliche Parser-API (Backend + Frontend)
- `parse_pdvm(value)` mit klaren Fehlercodes statt stiller Fallbacks.
- Ausgabe: strukturierte Komponenten (`year`, `yday`, `seconds_of_day`).

2. Rundungsstrategie zentralisieren
- Definieren, wann auf 5 Stellen gerundet wird (Persistenz) und wann intern volle Praezision bleibt.

3. Zeitbezug explizit machen
- Funktionen fuer `now_local` vs `now_utc`, damit Aufrufe nicht implizit mischen.

4. Konvertierungs-Tests erweitern
- Golden-Tests fuer Schaltjahre, Tagesgrenzen, Sommerzeit-nahe Zeitpunkte.
- Back-to-back-Test: `datetime -> pdvm -> datetime`.

5. Frontend Utility an Referenz koppeln
- Dokumentierte Spiegel-Implementierung mit identischen Formeln wie Backend.
- Optional: gemeinsame Test-Vektoren als JSON-Datei im Repo.

## Status
- Dokumentation erstellt.
- Implementierung erfolgt in separaten, kleinen Schritten mit Regressionstests.

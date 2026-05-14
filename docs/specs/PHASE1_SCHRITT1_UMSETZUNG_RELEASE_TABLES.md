# Phase 1 - Schritt 1 Umsetzung (Release Tables + Check API)

## Ziel
Erster, kleiner und reviewbarer Implementierungsschritt fuer das Release-Paket-System gemaess Architecture Rules:

- Kein SQL in Routern
- Service-Layer kapselt Datenbanklogik
- Idempotente Initialisierung
- Schrittweise Erweiterbarkeit fuer Phase 1.2+

## Umgesetzte Komponenten

### 1) Neuer Service-Layer
Datei: backend/app/core/release_service.py

Implementiert:
- ensure_release_tables(system_pool)
  - legt folgende Tabellen in pdvm_system an (falls fehlend):
    - sys_release_state
    - sys_release_log
    - dev_release
    - dev_release_item
    - sys_change_log
  - nutzt bestehendes Standard-Schema aus pdvm_table_schema (JSONB daten + Standard-Indizes)
- get_installed_releases(system_pool)
  - liest installierte Releases aus sys_release_state
  - erwartet Daten unter daten.ROOT.*
- check_updates(system_pool, available_releases)
  - MVP-Vergleich zwischen installierten und optional uebergebenen verfuegbaren Releases

### 2) Neue API-Endpunkte
Datei: backend/app/api/releases.py

Endpunkte:
- POST /api/releases/bootstrap
  - prueft/erstellt Release-Tabellen idempotent in System-DB
- POST /api/releases/check
  - liest installierte Releases
  - vergleicht optional gegen uebergebenen Katalog

Wichtig:
- Router enthaelt keine SQL-Statements
- Zugriff erfolgt ausschliesslich ueber ReleaseService
- GCS-Session wird wie in bestehender Architektur aus JWT-Token aufgeloest

### 3) Router-Registrierung
Datei: backend/app/main.py

Ergaenzt:
- Import von releases
- include_router fuer /api/releases

## Verifikation (manuell)

1. Login und Mandantenauswahl durchfuehren (damit GCS-Session aktiv ist).
2. Bootstrap aufrufen:

```bash
POST /api/releases/bootstrap
```

Erwartung:
- success=true
- tables_created listet neu angelegte Tabellen
- Wiederholter Aufruf bleibt idempotent (keine Fehler)

3. Check ohne Katalog:

```bash
POST /api/releases/check
{
  "available_releases": []
}
```

Erwartung:
- success=true
- installed enthaelt aktuelle sys_release_state-Eintraege (oder leer)
- has_updates=false

4. Check mit Katalog (Beispiel):

```bash
POST /api/releases/check
{
  "available_releases": [
    {"app_id": "PDVM_WEB", "version": "1.0.1", "release_id": "rel_001"}
  ]
}
```

Erwartung:
- updates_available listet Differenzen zur installierten Version

## Architektur-Status

Erfuellte Regeln:
- Keine direkte SQL im Router
- Service-Layer als Single Point fuer Release-DB-Logik
- Bestehende Session/GCS-Architektur wiederverwendet
- Kleine, isolierte Aenderung fuer sichere schrittweise Einfuehrung

## Geplante naechste Schritte (Phase 1 - Schritt 2)

- GitHub Package/Release-Quelle anbinden (Katalog automatisch laden)
- Release-Policy im Check beruecksichtigen (auto/manual/deferred)
- erweitertes Logging in sys_release_log (Check-Ergebnis pro Login)
- optional read-only UI-Endpunkt fuer Frontend-Badge/Notifier

# Phase 1 - Schritt 3 Umsetzung (Installer + Admin Apply + Logging)

## Ziel
Implementierung des naechsten MVP-Bausteins fuer Release-Pakete:

1. Validierung und transaktionales Apply von Release-Items
2. Kontrollierter Admin-Endpunkt fuer manuelles Apply
3. Laufprotokollierung in `sys_release_log`
4. Status-Tracking in `sys_release_state`

## Umgesetzte Komponenten

### 1) ReleaseService erweitert
Datei: backend/app/core/release_service.py

Neu implementiert:
- `validate_release_package(system_pool, package)`
  - prueft Pflichtfelder (`release_id`, `app_id`, `version`, `items`)
  - validiert `table_name` (`sys_*`), `operation` (`upsert|delete`), UID-Infos
  - prueft Existenz der Zieltabellen
- `apply_release_package(system_pool, package, applied_by)`
  - ruft Preflight/Validierung auf
  - fuehrt Items in Reihenfolge `order_no` in **einer DB-Transaktion** aus
  - `upsert`: `INSERT ... ON CONFLICT(uid) DO UPDATE`
  - `delete`: fachlich via `historisch=1` + `gilt_bis`
  - bei Fehlern Rollback (transaktional) + failed-State/Log
- `append_release_log(...)`
  - schreibt technische Ereignisse nach `sys_release_log`
- `append_release_state(...)`
  - schreibt Apply-Status nach `sys_release_state`
- `check_updates(..., check_source=...)`
  - schreibt nun ebenfalls Check-Log-Eintrag in `sys_release_log`

### 2) Release API erweitert
Datei: backend/app/api/releases.py

Neu:
- Request-Modelle fuer Apply:
  - `ReleaseApplyItem`
  - `ReleaseApplyRequest`
- Endpunkt `POST /api/releases/admin/apply`
  - `dry_run=true` -> nur Validierung
  - `dry_run=false` -> echtes Apply ueber Service
  - nur authentifizierte User; Admin-Check ist integriert (mit Legacy-Kompatibilitaet)

Zusatz:
- bestehende Check-Endpunkte geben `check_source` an den Service weiter, damit Check-Logs Quelle enthalten.

## Verifikation (manuell)

Voraussetzung:
- Login + Mandantenauswahl abgeschlossen (aktive GCS-Session)
- Release-Tabellen vorhanden (ggf. zuerst `POST /api/releases/bootstrap`)

### 1) Dry-Run Validierung

```bash
POST /api/releases/admin/apply
{
  "release_id": "rel_system_1_0_1",
  "app_id": "SYSTEM",
  "version": "1.0.1",
  "dry_run": true,
  "items": [
    {
      "table_name": "sys_systemdaten",
      "operation": "upsert",
      "order_no": 10,
      "record_uid": "11111111-1111-1111-1111-111111111111",
      "data": {
        "uid": "11111111-1111-1111-1111-111111111111",
        "name": "SYSTEM_CONFIG",
        "daten": {
          "ROOT": {"KEY": "VALUE"}
        }
      }
    }
  ]
}
```

Erwartung:
- `success=true`
- `validation.items_count` entspricht Anzahl validierter Items

### 2) Echtes Apply

```bash
POST /api/releases/admin/apply
{
  "release_id": "rel_system_1_0_1",
  "app_id": "SYSTEM",
  "version": "1.0.1",
  "package_hash": "sha256:demo",
  "source_commit": "abc123",
  "dry_run": false,
  "items": [
    {
      "table_name": "sys_systemdaten",
      "operation": "upsert",
      "order_no": 10,
      "record_uid": "11111111-1111-1111-1111-111111111111",
      "data": {
        "uid": "11111111-1111-1111-1111-111111111111",
        "name": "SYSTEM_CONFIG",
        "daten": {
          "ROOT": {"KEY": "VALUE"}
        }
      }
    }
  ]
}
```

Erwartung:
- `success=true`, `status=applied`
- Eintrag in `sys_release_state` mit `STATUS=applied`
- Log-Eintraege in `sys_release_log` (`preflight`, `commit`)

### 3) Rollback-Verhalten bei Fehler

- bewusst fehlerhafte Item-Struktur senden (z. B. ungueltige Tabelle)
- Erwartung:
  - HTTP-Fehler bei Validierung oder Apply
  - bei Laufzeitfehler: `sys_release_state` mit `STATUS=failed`
  - `sys_release_log` enthaelt `rollback`-Eintrag

## Architektur-Status

Erfuellte Regeln:
- Kein SQL in Routern
- Release-Logik vollstaendig im Service-Layer
- Transaktionales Apply umgesetzt
- Logging/Audit im Zielsystem ergaenzt

## Offene Punkte (naechster Schritt)

1. Paketformat-Importer (`manifest.json`, `items.jsonl`, `data/*.jsonl`) serverseitig anbinden
2. Semver-Vergleich statt reiner Ungleichheitspruefung im Check
3. Strikter, zentraler Rollencheck fuer Admin-Rechte harmonisieren

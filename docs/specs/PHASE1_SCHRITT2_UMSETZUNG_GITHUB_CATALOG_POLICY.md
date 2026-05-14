# Phase 1 - Schritt 2 Umsetzung (GitHub-Katalog + Policy im Update-Check)

## Ziel
Erweiterung des bereits umgesetzten Release-Checks um:

1. Abruf verfuegbarer Releases aus GitHub
2. Policy-basierte Ergebnisbewertung (`manual`, `auto`, `deferred`)
3. Weiterhin strikte Einhaltung der Architekturregeln (kein SQL im Router)

## Umgesetzte Komponenten

### 1) Konfiguration erweitert
Datei: backend/app/core/config.py

Neue Settings:
- `GITHUB_RELEASE_REPO` (Format: `owner/name`)
- `GITHUB_RELEASE_TOKEN` (optional, fuer private Repos/higher rate limits)

### 2) ReleaseService erweitert
Datei: backend/app/core/release_service.py

Neu:
- `fetch_available_releases_from_github(repo=None, token=None, timeout_seconds=10.0)`
  - ruft GitHub Releases ueber API ab
  - mappt Releases auf internen Katalog
- `_parse_release_name(name)`
  - MVP-Namenskonvention: `APP_ID@VERSION` (z. B. `SYSTEM@1.2.0`)
- `check_updates(..., policy_mode='manual')`
  - bewertet Ergebnis policy-basiert
  - liefert `recommended_action`:
    - `show_dialog` (manual)
    - `auto_apply` (auto + updates)
    - `defer` (deferred + updates)

### 3) API-Endpunkte erweitert
Datei: backend/app/api/releases.py

Ergaenzt:
- Request-Feld `policy_mode` in `POST /api/releases/check`
- Neuer Endpunkt: `POST /api/releases/catalog/github`
  - liefert GitHub-Katalog roh/normalisiert
- Neuer Endpunkt: `POST /api/releases/check/github`
  - laedt Katalog aus GitHub und fuehrt direkten Vergleich aus

## Verifikation (manuell)

Voraussetzung:
- Login + Mandantenauswahl abgeschlossen (aktive GCS-Session)
- optional `.env` in backend gesetzt:
  - `GITHUB_RELEASE_REPO=norbert-peters/PDVM_SYSTEM_WEB`
  - `GITHUB_RELEASE_TOKEN=<optional>`

### 1) GitHub-Katalog laden

```bash
POST /api/releases/catalog/github
{
  "repo": "norbert-peters/PDVM_SYSTEM_WEB"
}
```

Erwartung:
- `success=true`
- `available_releases` enthaelt Eintraege mit `app_id`, `version`
- nur Releases mit Name im Pattern `APP_ID@VERSION` werden uebernommen

### 2) Update-Check mit Policy (direkter Katalog)

```bash
POST /api/releases/check
{
  "policy_mode": "auto",
  "available_releases": [
    {"app_id": "SYSTEM", "version": "1.0.1", "release_id": "rel_001"}
  ]
}
```

Erwartung:
- `policy_mode=auto`
- Bei Differenz: `has_updates=true`, `recommended_action=auto_apply`

### 3) Update-Check direkt gegen GitHub

```bash
POST /api/releases/check/github
{
  "policy_mode": "manual"
}
```

Erwartung:
- `catalog_count` > 0 (wenn passende Releases vorhanden)
- `recommended_action=show_dialog` bei Updates im Manual-Modus

## Architektur-Status

Erfuellte Regeln:
- Kein SQL in Routern
- Business-Logik ausschliesslich im Service-Layer
- Session/GCS-Pattern unveraendert
- Kleine, additive Erweiterung ohne Bruch bestehender Endpunkte

## Hinweise / Grenzen (MVP)

1. Aktuell wird nur Release-Name Pattern `APP_ID@VERSION` ausgewertet.
2. Semver-Sortierung ist noch nicht enthalten (Vergleich ist differenzbasiert, nicht groesser/kleiner).
3. `auto_apply` ist derzeit nur Empfehlung im Check-Ergebnis, noch keine transaktionale Apply-Ausfuehrung.

## Naechster Schritt (Phase 1 - Schritt 3)

1. Installer-Service (validate + transaktionales apply) implementieren
2. Logging in `sys_release_log` pro Check-/Apply-Lauf einfuehren
3. Optional: Admin-Endpunkt fuer kontrolliertes manuelles Apply

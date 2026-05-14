# Phase 1 - Schritt 4 Umsetzung (Importer + Semver + zentraler Admin-Guard)

## Ziel
Abschluss der naechsten Ausbaustufe mit drei Punkten:

1. Serverseitiger Importer fuer Paketquellen `manifest.json`, `items.jsonl`, `data/*.jsonl`
2. Semver-aehnlicher Versionsvergleich im Update-Check
3. Zentraler, harmonisierter Admin-Rollencheck fuer Admin-Endpunkte

## Umgesetzte Komponenten

### 1) Zentraler Admin-Guard in Security
Datei: backend/app/core/security.py

Neu:
- `has_admin_rights(current_user)`
- `require_admin_user(...)`

Verhalten:
- Prueft `user_data.SECURITY.IS_ADMIN` und `user_data.SECURITY.ROLE`
- erlaubt Admin/Superadmin
- liefert bei fehlender Berechtigung `403`

Verwendung:
- `backend/app/api/admin.py`
- `backend/app/api/processes.py`
- `backend/app/api/releases.py` (Release-Admin-Funktionen)

### 2) Semver-aehnlicher Vergleich im Release-Check
Datei: backend/app/core/release_service.py

Neu:
- `_version_parts(version)`
- `_compare_versions(a, b)`

Aenderung in `check_updates(...)`:
- Updates werden nur gemeldet, wenn `available_version > installed_version`
- Nicht mehr nur Ungleichheit

### 3) Paket-Importer fuer manifest/items/data JSONL
Datei: backend/app/core/release_service.py

Neu:
- `_parse_jsonl(content, label)`
- `build_package_from_jsonl_payload(manifest, items_jsonl, data_jsonl_by_table)`

Importer-Logik:
- liest `manifest` Pflichtwerte (`release_id`, `app_id`, `version`)
- parst `items.jsonl`
- mappt `data/<table>.jsonl` ueber `uid` auf `upsert`-Items
- erzeugt internes `package` fuer bestehenden Validate/Apply-Flow

### 4) Neuer Release-API-Endpunkt fuer JSONL-Import
Datei: backend/app/api/releases.py

Neu:
- Request-Modell `ReleaseImportJsonlRequest`
- Endpunkt `POST /api/releases/admin/import-jsonl`

Modi:
- `dry_run=true`: Import + Validierung ohne Apply
- `dry_run=false`: Import + transaktionales Apply

## Verifikation (manuell)

Voraussetzung:
- Login + Mandantenauswahl (aktive GCS-Session)
- Admin-Berechtigung im Token (`SECURITY.IS_ADMIN` oder `SECURITY.ROLE`)

### 1) Dry-Run Import

```bash
POST /api/releases/admin/import-jsonl
{
  "manifest": {
    "release_id": "rel_system_1_0_2",
    "app_id": "SYSTEM",
    "version": "1.0.2",
    "package_hash": "sha256:demo",
    "source_commit": "abc999"
  },
  "items_jsonl": "{\"TABLE_NAME\":\"sys_systemdaten\",\"OPERATION\":\"upsert\",\"RECORD_UID\":\"11111111-1111-1111-1111-111111111111\",\"ORDER_NO\":10}",
  "data_jsonl_by_table": {
    "sys_systemdaten": "{\"uid\":\"11111111-1111-1111-1111-111111111111\",\"name\":\"SYSTEM_CONFIG\",\"daten\":{\"ROOT\":{\"KEY\":\"VALUE\"}}}"
  },
  "dry_run": true
}
```

Erwartung:
- `success=true`
- `validation` vorhanden
- keine Datenaenderung

### 2) Echter Import + Apply

- gleiche Payload mit `dry_run=false`

Erwartung:
- `status=applied`
- `sys_release_state` und `sys_release_log` enthalten Eintraege

### 3) Semver-Check

- installierte Version: `1.0.10`
- verfuegbare Version: `1.0.2`

Erwartung:
- kein Update mehr gemeldet

## Architektur-Status

Erfuellte Regeln:
- Kein SQL in Routern
- Admin-Pruefung zentralisiert
- Import/Parse/Apply-Logik im Service-Layer
- transaktionaler Apply-Flow aus Schritt 3 wiederverwendet

## Nächster optionaler Schritt

1. Multipart-Upload (ZIP oder Dateiliste) fuer manifest/items/data statt JSON-Strings
2. Strengere Semver-Regeln (Pre-Release/Prioritaeten)
3. Signaturpruefung (Phase 2) vor Apply

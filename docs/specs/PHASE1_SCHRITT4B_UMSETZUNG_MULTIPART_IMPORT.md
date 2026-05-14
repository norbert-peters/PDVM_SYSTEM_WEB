# Phase 1 - Schritt 4b Umsetzung (Multipart Datei-Import)

## Ziel
Ergaenzung zum Schritt 4 JSON-Importer:

- Paketimport mit echten Upload-Dateien statt JSON-Strings
- kompatibel zum vorhandenen Validate/Apply-Flow

## Umgesetzte Komponenten

Datei: backend/app/api/releases.py

Neu:
- Endpoint `POST /api/releases/admin/import-files`
- akzeptiert Multipart-Form:
  - `manifest_file` (manifest.json)
  - `items_file` (items.jsonl)
  - `data_files[]` (optional, mehrere data/*.jsonl)
  - `dry_run` (Form-Feld: true/false)

Interne Verarbeitung:
1. Dateien werden als UTF-8 gelesen.
2. `manifest_file` wird als JSON geparst.
3. `data_files` werden ueber Dateinamen einer Tabelle zugeordnet:
   - `sys_systemdaten.jsonl`
   - `data_sys_systemdaten.jsonl`
   - `data-sys_systemdaten.jsonl`
4. Anschliessend wird derselbe Service-Flow genutzt wie bei JSON-Import:
   - `build_package_from_jsonl_payload(...)`
   - `validate_release_package(...)` (bei dry_run)
   - `apply_release_package(...)` (bei echtem Apply)

## API-Beispiel (curl)

```bash
curl -X POST "http://localhost:8000/api/releases/admin/import-files" \
  -H "Authorization: Bearer <TOKEN>" \
  -F "manifest_file=@manifest.json" \
  -F "items_file=@items.jsonl" \
  -F "data_files=@sys_systemdaten.jsonl" \
  -F "data_files=@sys_menudaten.jsonl" \
  -F "dry_run=true"
```

## Erwartetes Verhalten

- `dry_run=true`:
  - Import und Validierung ohne Datenaenderung
  - Response enthaelt Validation-Ergebnis
- `dry_run=false`:
  - transaktionales Apply
  - Logging/State wie in Schritt 3

## Architektur-Status

Erfuellte Regeln:
- kein SQL im Router
- Admin-Guard bleibt zentral
- Datei-Parsing in API, Business-Logik im Service

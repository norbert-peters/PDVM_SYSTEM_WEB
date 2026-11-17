# Backend-Komponenten (Service-Architektur)

Überblick über die Bausteine des Backends und ihre Zuständigkeiten. Die **verbindlichen Regeln** stehen ausschließlich in [ARCHITECTURE_RULES.md](../ARCHITECTURE_RULES.md); dieses Dokument beschreibt nur den Ist-Stand. Bei Widerspruch gilt `ARCHITECTURE_RULES.md`.

## Schichten

```
Router (app/api)            kein SQL, kein asyncpg (Regel 1.1)
   │
Services (app/core/*_service.py, Central-Klassen)
   │   Lesen:      PdvmDatabase (pdvm_datenbank.py)
   │   Schreiben:  central_write_service
   │
Verbindungen: DatabasePool (auth) · ConnectionManager (Mandanten) · PoolRegistry (geteilte Pools)
   │
PostgreSQL: auth · system · Mandanten-DBs
```

`backend/test_architecture_guard.py` prüft die Schichtregeln statisch (Router ohne SQL, Schreiben nur über den Gateway).

## Datenbankzugriff

| Baustein | Datei | Aufgabe |
|---|---|---|
| `DatabasePool`, `resolve_db_name_by_prefix` | `core/database.py` | Pool der AUTH-DB (`DATABASE_URL_AUTH`); Routing Tabellenpräfix → Datenbank (`asy_`→auth, `sys_`/`dev_`→system, `msy_` und App-Präfixe→mandant, Regel 1.7a) |
| `ConnectionManager` | `core/connection_manager.py` | Verbindungsparameter aller weiteren Datenbanken aus `asy_mandanten` (Regel 1.2): Adressen je Mandanten-DB und System-DB, Zugangsdaten über `resolve_mandant_connections` |
| Credential-Store | `core/credential_store.py` | `get_credential(name)`: Zugangsdaten weiterer Server aus `PDVM_DB_CREDENTIALS` (austauschbar gegen einen Secret-Store); Passwörter stehen nie in `asy_mandanten` |
| `PoolRegistry` | `core/pool_registry.py` | Gemeinsam genutzte asyncpg-Pools (Verbindungsaufbau kostet ca. 150 ms); GCS-Sessions teilen Pools und schließen sie beim Logout nicht |
| `PdvmDatabase` | `core/pdvm_datenbank.py` | Zentraler Lesezugriff auf alle PDVM-Tabellen, Routing nach Tabellenname, Tabellennamen-Validierung |
| `central_write_service` | `core/central_write_service.py` | Einziger Schreibpfad (`create_record_central`, `update_record_central`, `delete_record_central`) inkl. Actor-Kontext aus der GCS-Session |
| `PdvmCentralDatabase` | `core/pdvm_central_datenbank.py` | Business-Schicht für einen Datensatz: `.load()`, `get_value`/`set_value`, Historie und Stichtag |
| `PdvmCentralSystemsteuerung` (GCS) | `core/pdvm_central_systemsteuerung.py` | Sitzungskontext je Benutzer und Mandant: Pools, Stichtag, Benutzer-/Mandanteneinstellungen (`msy_systemsteuerung`, `msy_anwendungsdaten`, `msy_layout`) |
| `pdvm_table_schema`, `pdvm_mandant_provisioning`, `mandant_setup_service`, `mandant_access` | `core/` | Standard-Tabellenstruktur, Anlage der Mandantentabellen, Mandant anlegen (`create_mandant`: Satz, Zuweisung, Datenbank; Aktion `mandant.setup`), Mandanten-Zulassung eines Benutzers (`MANDANTEN.LIST`, Login/Wahl/Listen) |
| `PdvmDateTime` | `core/pdvm_datetime.py` | Einzige Umrechnung zwischen Python-/JS-Datum und dem PDVM-Format `YYYYDDD.FRACTION` (Regel 1.9) |

Sonderpfade (dokumentierte Ausnahmen in Regel 1.1/1.13):
- `asy_benutzer` hat die Zusatzspalten `benutzer` und `passwort`: `user_manager.py` (`UserManager`) und `pdvm_central_benutzer.py`.
- `MandantDataManager` (`data_managers.py`) pflegt `asy_mandanten` über `PdvmDatabaseService` (`pdvm_database.py`, generischer CRUD-Service). `PersonDataManager` wird im Backend nicht mehr verwendet.

## Fachliche Services

| Bereich | Dateien |
|---|---|
| Dialoge | `dialog_service.py`, `dialog_frame_helpers.py`, `dialog_runtime_config.py`, `dialog_create_helpers.py`, `dialog_api_helpers.py`, `dialog_info.py` |
| Frame-Runtime (Masken ohne Dialog) | `frame_runtime_service.py` (Frame + Controls als ein Modell, Cache; Typ `password_input` nur in `public_form`-Frames), `public_frame_service.py` (öffentliche Login-Frames ohne Token: Allowlist, Typmenge), `rate_limit.py` (Begrenzung je Schlüssel im Speicher), `frame_action_service.py` (Aktionsregister für Controls `action`/`info`: Rollen, Parameter, Zustände, Regel 2.17), `mandant_record_rules.py` (Regeln der Mandanten-Neuanlage), `immutable_fields_service.py` (Sperre unveränderlicher Felder im Schreibpfad) |
| Zugangsdaten | `credential_store.py` (`.env` + entschlüsselter Cache), `credential_service.py` (Tabelle `asy_credentials`, setzen/Status), `secret_box.py` (Fernet, `PDVM_SECRET_KEY`) |
| Textvorlagen | `text_template_service.py` (Auswahl nach Schlüssel/aktiv/freigegebener Sprache, Rendern inkl. HTML, Prüfen, Schreib-Guard mit Rollen und Freigabelogik, Kopie), siehe [PDVM_TEXTVORLAGEN_SPEC_V1.md](../docs/specs/PDVM_TEXTVORLAGEN_SPEC_V1.md) |
| Neuanlage (Draft) | `workflow_draft_service.py`, `workflow_draft_access.py` |
| Views | `view_service.py`, `view_matrix_service.py`, `view_state_service.py`, `view_table_state_service.py` |
| Control Dictionary | `control_dict_service.py`, `control_template_service.py`, `control_runtime_service.py` |
| Menü, Dropdowns, Systemdaten | `menu_editor_service.py`, `dropdown_service.py`, `systemdaten_service.py` |
| Theming | `theme_service.py`, `theme_schema.py`, `theme_color.py`, `layout_schema.py` |
| Mandanten | `mandant_db_provisioning_service.py`, `mandant_db_maintenance.py`, `db_admin_service.py` |
| Benutzer und Mail | `password_reset_service.py`, `email_service.py`, `security.py` |
| Releases, Import, Historie | `release_service.py`, `import_data_service.py`, `feld_aenderungshistorie_service.py` |
| Fehler und I18N | `error_handlers.py`, `i18n_policy.py` |

## API-Router

Registriert in `app/main.py`:

| Präfix | Router |
|---|---|
| `/api/auth` | `auth.py` |
| `/api/mandanten`, `/api/admin` | `mandanten.py`, `admin.py` |
| `/api/gcs` | `gcs.py` |
| `/api/tables`, `/api/lookups`, `/api/systemdaten` | `tables.py`, `lookups.py`, `systemdaten.py` |
| `/api/menu`, `/api/menu-editor` | `menu.py`, `menu_editor.py` |
| `/api/views`, `/api/dialogs`, `/api/workflow-drafts` | `views.py`, `dialogs.py`, `workflow_drafts.py` |
| `/api/frames` | `frames.py` (`GET /{uid}/runtime?language=`, mit und ohne GCS-Session; liefert Dropdown-Optionen aus `sys_dropdowndaten`) |
| `/api/frame-actions` | `frame_actions.py` (`POST /{id}/run` führt eine Aktion aus, `POST /state` liefert Rechte und Zustände je Satz; Register und Prüfung in `frame_action_service.py`, Regel 2.17) |
| `/api/public` | `public_frames.py` (`GET /login-frames`, ohne Token: die drei Login-Frames; Allowlist, Typprüfung und Laden in `public_frame_service.py`, Begrenzung je IP über `rate_limit.py`, Regel 2.15) |
| `/api/credentials` | `credentials.py` (Zugangsdaten setzen/Status, nur Admin, write-only) |
| `/api/control`, `/api/import`, `/api/releases` | `control_dict.py`, `import_data.py`, `releases.py` |
| `/api/layout` | `layout.py` (Theming, siehe [THEMING_SYSTEM.md](../docs/specs/THEMING_SYSTEM.md)) |

## Typischer Ablauf

```python
# Lesen im Service/Router: Pools kommen aus der GCS-Session
db = PdvmDatabase("sys_menudaten", system_pool=gcs._system_pool, mandant_pool=gcs._mandant_pool)
row = await db.get_by_uid(uid)

# Schreiben: ausschließlich über den Gateway
await update_record_central(...)   # app/core/central_write_service.py
```

Fachlogik auf Datensatzebene (Defaults, Historie, Stichtag) läuft über `PdvmCentralDatabase.load(...)` (Regel 1.3), nie über direkte JSON-Zugriffe auf `row["daten"]`.

## Betrieb und Tests

- Starten: [SYSTEM_STARTUP_GUIDE.md](../SYSTEM_STARTUP_GUIDE.md)
- Tests: `..\.venv\Scripts\python.exe -m pytest` aus `backend/`
- Werkzeuge (Audit, Seeder, Migrationen): [tools/README.md](./tools/README.md)
- Datenbanken und Routing im Überblick: [README.md](../README.md)

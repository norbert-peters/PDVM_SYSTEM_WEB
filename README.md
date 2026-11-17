# PDVM System Web

Mandantenfähiges Business-Management-System: FastAPI (Python 3.11+) + React 18/TypeScript + PostgreSQL (JSONB).

```
Frontend (React, Vite)  ←→  Backend (FastAPI)  ←→  PostgreSQL (JSONB)
```

## Einstieg

| Thema | Dokument |
|---|---|
| System starten (Backend, Frontend, Tests, Stoppen) | [SYSTEM_STARTUP_GUIDE.md](./SYSTEM_STARTUP_GUIDE.md) |
| Verbindliche Architekturregeln | [ARCHITECTURE_RULES.md](./ARCHITECTURE_RULES.md) |
| Schema der Systemtabellen und Frames | [docs/specs/PDVM_LINEAR_SCHEMA_V1.md](./docs/specs/PDVM_LINEAR_SCHEMA_V1.md) |
| Backend-Komponenten (Ist-Stand) | [backend/SERVICE_ARCHITECTURE.md](./backend/SERVICE_ARCHITECTURE.md) |
| Werkzeuge (Audit, Seeder, Migrationen) | [backend/tools/README.md](./backend/tools/README.md) |
| Spezifikationen | [docs/specs/](./docs/specs) |
| Pläne | [docs/](./docs) |

## Voraussetzungen

- Python 3.11+ (virtuelle Umgebung `.venv` im Repo-Root)
- Node.js + npm
- PostgreSQL

## Einrichtung

```powershell
# Python-Umgebung (Repo-Root)
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt

# Konfiguration
Copy-Item backend\.env.example backend\.env   # DATABASE_URL_AUTH und SECRET_KEY anpassen

# Frontend
cd frontend
npm install
```

Starten: siehe [SYSTEM_STARTUP_GUIDE.md](./SYSTEM_STARTUP_GUIDE.md).

## Datenbanken

- Konfiguriert ist nur die Datenbank `auth` (`DATABASE_URL_AUTH`). Sie enthält `asy_benutzer` und `asy_mandanten`.
- Alle weiteren Datenbanken (System, Mandanten) werden dynamisch aus `asy_mandanten` geladen. Dort stehen nur Adressen (`HOST`, `PORT`, `DATABASE`, `SYSTEM_*`) und Verweise auf Zugangsdaten (`CREDENTIAL`), keine Passwörter. System-DB und Mandanten-DB können auf verschiedenen Instanzen liegen.
- Zugangsdaten stehen in `backend/.env`: `DATABASE_URL_AUTH` gilt für die AUTH-Instanz; weitere Server als JSON in `PDVM_DB_CREDENTIALS`. Details: [docs/specs/PDVM_DB_VERBINDUNGEN_UND_ZUGANGSDATEN_SPEC_V1.md](./docs/specs/PDVM_DB_VERBINDUNGEN_UND_ZUGANGSDATEN_SPEC_V1.md).
- Das Routing erfolgt über das Tabellenpräfix (`backend/app/core/database.py`):

| Präfix | Datenbank |
|---|---|
| `asy_` | `auth` |
| `sys_`, `dev_` | `system` |
| `msy_` und App-Präfixe | `mandant` |

- Schemas: `database/schema_pdvm_system.sql` (System-DB) und `database/schema_mandant.sql` (Mandanten-DBs, wird bei der Mandantenanlage angewendet). Für die AUTH-DB gibt es kein Schema-Skript; sie wird per Backup/Restore bereitgestellt (siehe unten).
- Tabellenstruktur, Basissätze (UID 000/555/666) und Konventionen: [ARCHITECTURE_RULES.md](./ARCHITECTURE_RULES.md), [docs/specs/PDVM_LINEAR_SCHEMA_V1.md](./docs/specs/PDVM_LINEAR_SCHEMA_V1.md).

## Backup und Restore (PostgreSQL in Docker)

Skripte in `database/scripts` (Standard-Container `pdvm_postgres`):

```powershell
cd database\scripts
.\backup_postgres.ps1                 # Dump nach database\backups
.\backup_postgres.ps1 -KeepDays 30    # eigene Aufbewahrung
.\restore_postgres.ps1                # letztes Backup zurückspielen
.\restore_postgres.ps1 -BackupFile ..\backups\<datei>.dump
```

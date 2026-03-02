# PDVM System Web

Modern web-based business management system built with FastAPI and React.

## 🏗️ Architecture

```
Backend (FastAPI)  ←→  PostgreSQL (JSONB)
     ↕
Frontend (React + TypeScript)
```

## 🚀 Quick Start

### Prerequisites
- Python 3.11+
- Node.js 18+
- PostgreSQL 14+
- Docker (optional)

### Backend Setup
```bash
cd backend
python -m venv venv
venv\Scripts\activate  # Windows
pip install -r requirements.txt
uvicorn app.main:app --reload
```

### Frontend Setup
```bash
cd frontend
npm install
npm run dev
```

### Database Setup
```bash
cd database
psql -U postgres -f schema.sql
```

## 📁 Project Structure

```
PDVM_SYSTEM_WEB/
├── backend/           # FastAPI Application
│   ├── app/
│   │   ├── api/      # API Routes
│   │   ├── core/     # Database, Auth, Config
│   │   ├── models/   # Pydantic Models
│   │   └── main.py   # FastAPI App
│   └── requirements.txt
├── frontend/          # React Application
│   ├── src/
│   │   ├── components/
│   │   ├── api/
│   │   └── App.tsx
│   └── package.json
├── database/          # PostgreSQL Schema
│   └── schema.sql
└── docker/           # Docker Setup
    └── docker-compose.yml
```

## 🔑 Key Features

- **Unified Table Structure**: All tables follow PDVM standard schema
- **JSONB Storage**: Flexible data structure with PostgreSQL JSONB
- **JWT Authentication**: Secure token-based auth
- **Real-time Updates**: Fast API with async/await
- **Type Safety**: TypeScript throughout

## 🛠️ Development

Backend API: http://localhost:8000
Frontend UI: http://localhost:5173
API Docs: http://localhost:8000/docs

## 📊 Database Schema

Each table follows the PDVM standard:
- `uid` - UUID primary key
- `daten` - JSONB main data
- `name` - Display name
- `historisch` - Historical flag
- `sec_id` - Security profile
- `gilt_bis` - Valid until
- `created_at` - Creation timestamp
- `modified_at` - Last modified
- `daten_backup` - Backup data

## 💾 PostgreSQL Backup (Docker)

PowerShell-Skripte für Backup und Restore liegen in `database/scripts`:

```powershell
# Backup erstellen (legt .dump in database/backups ab)
cd database\scripts
.\backup_postgres.ps1

# Optional mit eigener Aufbewahrung (z. B. 30 Tage)
.\backup_postgres.ps1 -KeepDays 30

# Direkt auf externe Platte sichern + lokales Fallback, falls Platte fehlt
.\backup_postgres.ps1 -OutputDir "E:\PDVM_Backups" -FallbackOutputDir "..\backups"

# Letztes Backup zurückspielen
.\restore_postgres.ps1

# Konkretes Backup zurückspielen
.\restore_postgres.ps1 -BackupFile ..\backups\pdvm_system_20260223_120000.dump
```

### Automatisierung (Windows Aufgabenplanung)

Beispiel (täglich 02:00 Uhr):

```powershell
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -File \"C:\Users\norbe\OneDrive\Dokumente\PDVM_SYSTEM_WEB\database\scripts\backup_postgres.ps1\""
$trigger = New-ScheduledTaskTrigger -Daily -At 2:00AM
Register-ScheduledTask -TaskName "PDVM_Postgres_Backup" -Action $action -Trigger $trigger -Description "Tägliches PostgreSQL Backup für PDVM"
```

## 📝 Änderungen

- 2026-02-03: Mandanten-Setup aktualisiert `ROOT.DB_CREATED_AT` über `MandantDataManager.update_value()` (kein direkter Router-DB-Zugriff).
- 2026-02-03: `go_dialog` akzeptiert `dialog_table`, `table` oder `root_table` als Tabellen-Override; Dialog-Seite liest auch `?table=`.
- 2026-02-04: Idle-Session gemäß `ROOT.IDLE_TIMEOUT`/`ROOT.IDLE_WARNING` (Sekunden) inkl. Keep-Alive und Warn-Dialog.

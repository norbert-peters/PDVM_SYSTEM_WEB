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

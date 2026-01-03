# PDVM System Web - Quick Start Guide

## Prerequisites
- Python 3.11+
- Node.js 18+
- PostgreSQL 14+ (or use Docker)

## Local Development Setup

### 1. Database Setup (Option A: PostgreSQL Lokal)
```powershell
# Install PostgreSQL, then:
createdb pdvm_system
psql pdvm_system < database/schema.sql
```

### 1. Database Setup (Option B: Docker)
```powershell
cd docker
docker-compose up -d postgres
```

### 2. Backend Setup
```powershell
cd backend

# Create virtual environment
python -m venv venv
.\venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt

# Create .env file
Copy-Item .env.example .env
# Edit .env and set DATABASE_URL

# Run backend
uvicorn app.main:app --reload
# Backend runs at http://localhost:8000
# API docs at http://localhost:8000/docs
```

### 3. Frontend Setup
```powershell
cd frontend

# Install dependencies
npm install

# Run dev server
npm run dev
# Frontend runs at http://localhost:5173
```

## Docker Setup (All Services)

```powershell
cd docker
docker-compose up -d

# Check logs
docker-compose logs -f

# Stop all services
docker-compose down
```

## Default Login
- **Email**: admin@example.com
- **Password**: admin

## Project Structure
```
PDVM_SYSTEM_WEB/
├── backend/          # FastAPI backend
│   ├── app/
│   │   ├── api/      # API endpoints
│   │   ├── core/     # Config, DB, Security
│   │   └── models/   # Pydantic schemas
│   └── requirements.txt
├── frontend/         # React frontend
│   ├── src/
│   │   ├── api/      # API client
│   │   └── components/
│   └── package.json
├── database/         # SQL schemas
└── docker/           # Docker setup
```

## MVP Features
✅ Login with JWT authentication
✅ Table list dashboard
✅ View records from any table
✅ JSONB data storage
✅ SEC_PROFILES security filtering

## Next Steps
- [ ] Add record editing UI
- [ ] Add record creation UI
- [ ] Add delete functionality
- [ ] Improve table visualization
- [ ] Add search/filter

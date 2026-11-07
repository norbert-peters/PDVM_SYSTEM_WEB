# PDVM System Web - Development Instructions

## Verbindliche Arbeitsregeln (immer beachten)
- Arbeitsbereich ist standardmäßig dieses Repository (https://github.com/norbert-peters/PDVM_SYSTEM_WEB), sofern nicht ausdrücklich anders angegeben.
- Vor jeder Änderung (Backend, Frontend, Datenbank, Doku) die Architekturregeln lesen und einhalten:
  - [ARCHITECTURE_RULES.md](../ARCHITECTURE_RULES.md) (verbindlich, hat Vorrang)
  - [FRAME_ARCHITECTURE_V2.md](../FRAME_ARCHITECTURE_V2.md)
  - [backend/SERVICE_ARCHITECTURE.md](../backend/SERVICE_ARCHITECTURE.md)
  - [backend/ARCHITECTURE_REDESIGN.md](../backend/ARCHITECTURE_REDESIGN.md)
- Bei Konflikt zwischen Anforderung und Architekturregel: nicht stillschweigend abweichen, sondern nachfragen.
- Wird eine Regel durch eine Änderung berührt, die zugehörige Dokumentation mitpflegen.

## Project Overview
FastAPI + React TypeScript web application for multi-user business management system with PostgreSQL.

## Tech Stack
- **Backend**: FastAPI (Python 3.11+), PostgreSQL, JWT Auth
- **Frontend**: React 18 + TypeScript, Vite, React Router, TanStack Query
- **Database**: PostgreSQL with JSONB for flexible data storage

## Progress Checklist

- [x] Clarify Project Requirements - FastAPI + React + PostgreSQL system
- [ ] Scaffold the Project - Create folder structure and basic files
- [ ] Customize the Project - Add PDVM-specific table structure and business logic
- [ ] Install Required Extensions - Python, JavaScript/TypeScript extensions
- [ ] Compile the Project - Install dependencies (pip, npm)
- [ ] Create and Run Task - Backend and Frontend dev servers
- [ ] Launch the Project - Run both servers
- [ ] Ensure Documentation is Complete - README with setup instructions

# 🎯 System mit Login & Service-Management

## ✅ Was wurde erstellt:

### 1. **Backend API** - Process Management (`/api/processes/*`)

```
GET  /api/processes/services        - Alle Services auflisten
POST /api/processes/services/start  - Service starten
POST /api/processes/services/stop   - Service stoppen
POST /api/processes/services/restart - Service neustarten
GET  /api/processes/system/status   - System-Status (CPU, RAM, Disk)
```

### 2. **Frontend - Login-Flow**

#### Login.tsx
- Formular mit E-Mail + Passwort
- Standard-Login: `admin@example.com` / `admin`
- Speichert Token in localStorage
- Redirect zu Dashboard nach erfolgreicher Anmeldung

#### Dashboard.tsx
- **Header**: User-Info + Logout-Button
- **Navigation**: Übersicht | Services & Lauscher
- **Übersicht-Tab**: System-Status (CPU, RAM, Disk, Services)
- **Services-Tab**: Service-Manager-Komponente

#### ServiceManager.tsx
- Zeigt alle laufenden Services (Port, PID, RAM, CPU)
- Stop-Button für jeden Service
- Auto-Refresh alle 5 Sekunden
- Erkennt automatisch uvicorn-Prozesse

### 3. **Management-Script** - `manage_services.py`

```powershell
# Alle Services starten
python manage_services.py start

# Alle Services stoppen
python manage_services.py stop

# Services neustarten
python manage_services.py restart

# Status anzeigen
python manage_services.py status
```

**Features:**
- Startet Backend in neuem Konsolenfenster
- Erkennt laufende Services automatisch
- Zeigt PIDs und Ports an
- Sauberes Stoppen (terminate + kill fallback)

## 🚀 Ablauf

### 1. System starten
```powershell
cd c:\Users\norbe\OneDrive\Dokumente\PDVM_SYSTEM_WEB\backend
.\venv\Scripts\Activate.ps1
python manage_services.py start
```

**Ergebnis:**
- Backend läuft auf http://localhost:8000
- Neues PowerShell-Fenster öffnet sich mit uvicorn
- API Docs: http://localhost:8000/docs

### 2. Frontend starten (separates Terminal)
```powershell
cd c:\Users\norbe\OneDrive\Dokumente\PDVM_SYSTEM_WEB\frontend
npm run dev
```

Öffne: http://localhost:5173

### 3. Login
1. E-Mail: `admin@example.com`
2. Passwort: `admin`
3. Click "Anmelden"

### 4. Dashboard nutzen
- **Übersicht**: Sieh System-Ressourcen (CPU, RAM, Disk, Services)
- **Services & Lauscher**: Verwalte laufende Services
  - Sieh Port, PID, RAM, CPU
  - Stoppe Services per Klick
  - Auto-Refresh alle 5 Sekunden

### 5. Logout
Click "Abmelden" → zurück zu Login

## 📊 Architektur

**Eine Strecke (Backend):**
- ✅ Port 8000 für alle APIs
- `/api/auth/*` - Login/Logout
- `/api/tables/*` - CRUD Operationen
- `/api/admin/*` - DB-Verwaltung
- `/api/processes/*` - Service-Management

**Frontend:**
- React auf Port 5173 (Vite)
- Protected Routes (Login-Check via localStorage)
- Dashboard mit Tabs
- Automatisches Token-Handling via apiClient

## 🔧 Service-Management

### Über Frontend (Browser):
1. Login → Dashboard
2. Tab "Services & Lauscher"
3. Siehe laufende Services
4. Klick "Stoppen" um Service zu beenden

### Über Command Line:
```powershell
# Starten
python manage_services.py start

# Stoppen
python manage_services.py stop

# Status
python manage_services.py status
```

### Über API (für eigene Tools):
```bash
# Services auflisten
curl http://localhost:8000/api/processes/services \
  -H "Authorization: Bearer <token>"

# Service stoppen
curl -X POST "http://localhost:8000/api/processes/services/stop?service_name=uvicorn_8000" \
  -H "Authorization: Bearer <token>"
```

## ⚡ Vorteile dieser Architektur

✅ **Eine Strecke** - Backend auf Port 8000, klare API-Struktur
✅ **Protected Routes** - Nur nach Login zugänglich
✅ **Auto-Erkennung** - Services werden automatisch erkannt
✅ **Echtzeitit** - Status updates alle 5-10 Sekunden
✅ **Management-Scripts** - CLI für schnelles Starten/Stoppen
✅ **Process-Info** - Siehe RAM, CPU, PID jedes Service

## 📝 Nächste Schritte

1. **Frontend fertig bauen**: App.tsx mit React Router
2. **Mehr Services**: Weitere Lauscher hinzufügen
3. **Permissions**: Echte Admin-Rollen-Prüfung
4. **Logs**: Service-Logs im Dashboard anzeigen
5. **Notifications**: Push-Benachrichtigungen wenn Service stoppt

## 🎯 Zusammenfassung

Du hast jetzt:
- ✅ Login-System mit Logout
- ✅ Dashboard mit User-Info
- ✅ System-Übersicht (CPU, RAM, Disk)
- ✅ Service-Manager (Start/Stop)
- ✅ Management-Script für CLI
- ✅ API für Service-Verwaltung

**Alles läuft über eine "Strecke"** (Backend Port 8000) mit verschiedenen Endpoints für verschiedene Funktionen!

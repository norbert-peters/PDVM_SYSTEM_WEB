# System starten (Backend + Frontend)

## Voraussetzungen
- Python-Umgebung im Repo-Root: `.venv` (Interpreter: `.venv\Scripts\python.exe`)
- Node.js + npm
- PostgreSQL läuft und ist in `backend/.env` konfiguriert

## 1. Backend starten (Terminal 1)
```powershell
cd C:\Users\norbe\dev\PDVM_SYSTEM_WEB\backend
$env:PYTHONUTF8 = 1
..\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000
```

- `PYTHONUTF8=1` ist unter Windows nötig, sonst bricht der Start wegen der Emojis in den Startmeldungen mit `UnicodeEncodeError` ab.
- API: http://127.0.0.1:8000
- API-Docs: http://127.0.0.1:8000/docs
- Für lokale HTTP-Clients `127.0.0.1` statt `localhost` verwenden (schneller).
- Optional mit Auto-Reload: `--reload` anhängen.

## 2. Frontend starten (Terminal 2)
```powershell
cd C:\Users\norbe\dev\PDVM_SYSTEM_WEB\frontend
npm install   # nur beim ersten Mal bzw. nach Änderungen an package.json
npm run dev
```

Troubleshooting:
- `npm WARN npm does not support Node.js v20` / `cb.apply is not a function`: Ein global installiertes altes npm 6 (`%APPDATA%\npm\npm.cmd`) überdeckt das npm von Node. Mit `where.exe npm` prüfen; das npm von Node liegt z. B. unter `C:\nvm4w\nodejs`. Abhilfe: `$env:Path = 'C:\nvm4w\nodejs;' + $env:Path` vor `npm install`/`npm run dev`, oder die Dateien `npm`, `npm.cmd`, `npx`, `npx.cmd` in `%APPDATA%\npm` umbenennen/entfernen.
- `EPERM: operation not permitted, rmdir ...node_modules\.vite\deps`: Vite-Cache löschen (`Remove-Item -Recurse -Force node_modules\.vite`) und erneut starten.

Frontend: http://localhost:5173 (Vite, leitet API-Aufrufe per Proxy an das Backend weiter; siehe `frontend/vite.config.ts`).

## 3. Login
Die Anmeldemaske ist mit `admin@example.com` vorbelegt (siehe `frontend/src/components/Login.tsx`). Das Passwort ist das des jeweiligen Benutzers in der Datenbank.

## 4. Services über das Dashboard verwalten
Nach dem Login zeigt der Tab "Services & Lauscher" die laufenden Prozesse (Port, PID, RAM, CPU) und erlaubt das Stoppen. Die zugehörige API liegt unter `/api/processes/*` (`backend/app/api/processes.py`).

## 5. Stoppen
Im jeweiligen Terminal `Strg+C`. Alternativ einen Prozess gezielt über seine PID beenden:
```powershell
Get-NetTCPConnection -LocalPort 8000 -State Listen | Select-Object OwningProcess
Stop-Process -Id <PID>
```

## Tests (Backend)
```powershell
cd C:\Users\norbe\dev\PDVM_SYSTEM_WEB\backend
..\.venv\Scripts\python.exe -m pytest
```

## Hinweise
- Das frühere Skript `manage_services.py` liegt nur noch unter `backend/_archive_scripts/` und gehört nicht mehr zum Standard-Ablauf.
- Architekturregeln: [ARCHITECTURE_RULES.md](./ARCHITECTURE_RULES.md)

# Multi-Database Setup Anleitung

## Datenbank-Architektur

Das PDVM System verwendet drei separate PostgreSQL Datenbanken:

### 1. **pdvm_system** - System-Konfiguration
- sys_beschreibungen
- sys_dialogdaten
- sys_framedaten
- sys_viewdaten
- sys_menudaten
- sys_layout
- sys_dropdowndaten

### 2. **auth** - Authentifizierung
- sys_benutzer (mit admin@example.com / admin)
- sys_mandanten

### 3. **mandant** - Mandantendaten
- sys_anwendungsdaten
- sys_systemsteuerung
- sys_security
- sys_error_log
- sys_error_acknowledgments
- persondaten (mit Demo-User Max Mustermann)
- finanzdaten

## Setup in pgAdmin 4

### Schritt 1: Datenbank pdvm_system erstellen
1. Öffne pgAdmin 4
2. Expandiere "Servers" → "PostgreSQL 18" (oder deine Version)
3. Rechtsklick auf "Databases" → **Create** → **Database...**
4. Name: `pdvm_system`
5. Owner: `postgres`
6. Klicke **Save**

### Schritt 2: Schema für pdvm_system ausführen
1. Rechtsklick auf Datenbank `pdvm_system` → **Query Tool**
2. Öffne die Datei: `database/schema_pdvm_system.sql`
3. Kopiere den gesamten Inhalt in das Query Tool
4. Klicke **Execute** (▶️) oder drücke **F5**
5. Überprüfe: Rechtsklick auf `pdvm_system` → **Refresh**, dann expandiere **Schemas** → **public** → **Tables**
   - Du solltest 7 Tabellen sehen

### Schritt 3: Datenbank auth erstellen
1. Rechtsklick auf "Databases" → **Create** → **Database...**
2. Name: `auth`
3. Owner: `postgres`
4. Klicke **Save**

### Schritt 4: Schema für auth ausführen
1. Rechtsklick auf Datenbank `auth` → **Query Tool**
2. Öffne die Datei: `database/schema_auth.sql`
3. Kopiere den gesamten Inhalt in das Query Tool
4. Klicke **Execute** (▶️) oder drücke **F5**
5. Überprüfe: Expandiere `auth` → **Schemas** → **public** → **Tables**
   - Du solltest 2 Tabellen sehen: sys_benutzer, sys_mandanten
6. Überprüfe admin User: Rechtsklick auf `sys_benutzer` → **View/Edit Data** → **All Rows**
   - Email: admin@example.com
   - Passwort: (bcrypt hash für "admin")

### Schritt 5: Datenbank mandant erstellen
1. Rechtsklick auf "Databases" → **Create** → **Database...**
2. Name: `mandant`
3. Owner: `postgres`
4. Klicke **Save**

### Schritt 6: Schema für mandant ausführen
1. Rechtsklick auf Datenbank `mandant` → **Query Tool**
2. Öffne die Datei: `database/schema_mandant.sql`
3. Kopiere den gesamten Inhalt in das Query Tool
4. Klicke **Execute** (▶️) oder drücke **F5**
5. Überprüfe: Expandiere `mandant` → **Schemas** → **public** → **Tables**
   - Du solltest 7 Tabellen sehen
6. Überprüfe Demo-Daten: Rechtsklick auf `persondaten` → **View/Edit Data** → **All Rows**
   - Name: Max Mustermann

## Backend neu starten

Nach der Datenbank-Erstellung:

1. Stoppe den laufenden Backend-Server (falls aktiv)
2. Öffne neues PowerShell-Terminal
3. Starte Backend:

```powershell
cd "c:\Users\norbe\OneDrive\Dokumente\PDVM_SYSTEM_WEB\backend"
.\venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

4. Öffne http://localhost:8000/docs

## API Testen

### 1. Login
- POST `/api/auth/login`
- Username: `admin@example.com`
- Password: `admin`
- Kopiere den `access_token` aus der Response

### 2. Authorize
- Klicke auf **Authorize** Button (🔓) oben rechts
- Eingabe: `Bearer <dein_access_token>`
- Klicke **Authorize**

### 3. Test API Calls
- GET `/api/tables/persondaten` - Zeigt Max Mustermann
- GET `/api/tables/sys_benutzer` - Zeigt admin User (aus auth DB)
- GET `/api/tables/sys_menudaten` - Zeigt Menü-Konfiguration (aus system DB)

## Datenbank-Mapping

Die Datei `backend/app/core/database.py` enthält die Tabelle-zu-Datenbank-Zuordnung:

```python
TABLE_DATABASE_MAP = {
    "sys_beschreibungen": "system",    # → pdvm_system DB
    "sys_benutzer": "auth",            # → auth DB
    "persondaten": "mandant",          # → mandant DB
    # ...
}
```

Neue Tabellen können hier einfach hinzugefügt werden.

## Troubleshooting

### Backend startet nicht
- Prüfe `.env` Datei: Alle drei DATABASE_URL_* sollten gesetzt sein
- Prüfe PostgreSQL: Alle drei Datenbanken sollten existieren

### Tabellen nicht gefunden
- Stelle sicher, dass alle SQL-Skripte erfolgreich ausgeführt wurden
- Prüfe in pgAdmin: Expandiere Datenbank → Schemas → public → Tables

### Login funktioniert nicht
- Prüfe in pgAdmin: auth → sys_benutzer → sollte admin@example.com enthalten
- Schema wurde korrekt ausgeführt (INSERT Statement am Ende von schema_auth.sql)

## Nächste Schritte

Nach erfolgreichem Setup:
1. Frontend starten (erfordert Node.js 18+)
2. Weitere Tabellen in den Datenbanken anlegen
3. Produktions-Daten importieren

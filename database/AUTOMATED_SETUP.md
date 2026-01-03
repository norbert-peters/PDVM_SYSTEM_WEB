# Automatisiertes Database Setup

## Erstellt

### 1. Python Setup-Skript: `setup_databases.py`
**Funktion**: Automatische Erstellung aller drei Datenbanken + Schema-Ausführung

**Ausführen:**
```powershell
cd c:\Users\norbe\OneDrive\Dokumente\PDVM_SYSTEM_WEB\backend
.\venv\Scripts\Activate.ps1
python setup_databases.py
```

**Was es tut:**
- Verbindet zu PostgreSQL Server (postgres-Datenbank)
- Erstellt `pdvm_system`, `auth`, `mandant` Datenbanken
- Führt automatisch die SQL-Schema-Dateien aus
- Zeigt Fortschritt und Ergebnis an

### 2. Admin API Endpoints: `app/api/admin.py`
**Endpunkte für Frontend-Verwaltung:**

#### `GET /api/admin/databases`
- Listet alle Datenbanken auf PostgreSQL-Server
- Zeigt managed und unmanaged DBs

#### `POST /api/admin/databases/mandant`
```json
{
  "name": "firma_xyz",
  "description": "Firma XYZ GmbH",
  "copy_from_template": true
}
```
- Erstellt neue Mandantendatenbank (z.B. `mandant_firma_xyz`)
- Führt automatisch `schema_mandant.sql` aus
- Registriert Mandant in `sys_mandanten` Tabelle

#### `POST /api/admin/tables`
```json
{
  "table_name": "neue_tabelle",
  "database": "mandant"
}
```
- Erstellt neue Tabelle in gewählter Datenbank
- Nutzt `create_pdvm_table()` Function für einheitliche Struktur

#### `GET /api/admin/tables/{database}`
- Listet alle Tabellen in Datenbank (system/auth/mandant)

#### `DELETE /api/admin/databases/{db_name}`
- Löscht Mandantendatenbank (nur `mandant_*` erlaubt)
- Sicherheitscheck: System-DBs können nicht gelöscht werden

### 3. Automatisches Datenbank-Routing
**In `database.py`:**
- `TABLE_DATABASE_MAP` = Mapping welche Tabelle zu welcher DB gehört
- `PdvmDatabase` erkennt automatisch die richtige Datenbank
- Beispiel: `PdvmDatabase("sys_benutzer")` → verwendet auth-DB

## Verwendung

### Initial-Setup (einmalig):
```powershell
cd backend
python setup_databases.py
```

### Neue Mandantendatenbank erstellen (via API):
1. Login in Swagger UI: http://localhost:8000/docs
2. POST `/api/auth/login` mit admin@example.com / admin
3. Authorize mit Token
4. POST `/api/admin/databases/mandant`:
```json
{
  "name": "kunde_a",
  "description": "Kunde A GmbH",
  "copy_from_template": true
}
```

### Neue Tabelle erstellen (via API):
```json
{
  "table_name": "vertraege",
  "database": "mandant"
}
```

## Vorteile

✅ **Keine manuelle pgAdmin-Arbeit** - alles maschinell  
✅ **Frontend-Integration ready** - API für Admin-Panel  
✅ **Mandantenfähig** - beliebig viele Mandantendatenbanken  
✅ **Automatisches Routing** - Code weiß automatisch welche DB  
✅ **Template-System** - neue Mandanten-DBs mit Standard-Schema  
✅ **Sicherheit** - nur Mandanten-DBs können gelöscht werden  

## Nächste Schritte

1. **Jetzt testen**: `python setup_databases.py` ausführen
2. **Backend starten**: `python -m uvicorn app.main:app --reload`
3. **Admin-APIs testen**: http://localhost:8000/docs → `/api/admin/*`
4. **Frontend-Integration**: Admin-Panel mit Vue/React für DB-Verwaltung

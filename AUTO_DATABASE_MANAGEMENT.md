# 🚀 Automatisiertes Database Management

## ✅ Was wurde erstellt:

### 1. **setup_databases.py** - Automatisches Setup-Skript
Erstellt alle drei Datenbanken automatisch:

```powershell
cd backend
python setup_databases.py
```

Ergebnis:
- ✓ `pdvm_system` Datenbank erstellt
- ✓ `auth` Datenbank erstellt (mit admin@example.com)
- ✓ `mandant` Datenbank erstellt (mit Demo-Daten)
- ✓ Alle Tabellen automatisch angelegt

### 2. **Admin API Endpoints** (`/api/admin/*`)

#### Neue Mandantendatenbank erstellen:
```http
POST /api/admin/databases/mandant
{
  "name": "firma_xyz",
  "description": "Firma XYZ GmbH",
  "copy_from_template": true
}
```
→ Erstellt `mandant_firma_xyz` Datenbank mit allen Tabellen

#### Alle Datenbanken auflisten:
```http
GET /api/admin/databases
```

#### Neue Tabelle erstellen:
```http
POST /api/admin/tables
{
  "table_name": "vertraege",
  "database": "mandant"
}
```

#### Tabellen in DB anzeigen:
```http
GET /api/admin/tables/mandant
```

#### Mandanten-DB löschen:
```http
DELETE /api/admin/databases/mandant_firma_xyz
```
*(Nur `mandant_*` DBs dürfen gelöscht werden)*

### 3. **Automatisches DB-Routing**
```python
# Code weiß automatisch welche Datenbank
db = PdvmDatabase("sys_benutzer")  # → auth DB
db = PdvmDatabase("persondaten")   # → mandant DB
db = PdvmDatabase("sys_menudaten") # → pdvm_system DB
```

## 🎯 Wie du es nutzt:

### Initial Setup (einmalig):
```powershell
cd c:\Users\norbe\OneDrive\Dokumente\PDVM_SYSTEM_WEB\backend
.\venv\Scripts\Activate.ps1
python setup_databases.py
```

### Backend starten:
```powershell
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### API testen:
1. Öffne http://localhost:8000/docs
2. Login: POST `/api/auth/login` → admin@example.com / admin
3. Authorize mit Token
4. Teste `/api/admin/*` Endpoints

### Aus Frontend nutzen:
```javascript
// Admin Panel Component
async function createMandantDatabase(name) {
  const response = await fetch('/api/admin/databases/mandant', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      name: name,
      description: `Mandant ${name}`,
      copy_from_template: true
    })
  });
  return await response.json();
}
```

## 💡 Vorteile:

✅ **Keine manuelle pgAdmin-Arbeit mehr**
✅ **Frontend kann Mandanten anlegen**
✅ **Tabellen dynamisch erstellen**
✅ **Skalierbar für Multi-Tenant**
✅ **Code weiß automatisch welche DB**

## 📂 Dateien:

- `backend/setup_databases.py` - Setup-Skript
- `backend/app/api/admin.py` - Admin API Routes
- `backend/app/core/database.py` - Multi-DB Manager
- `database/schema_*.sql` - Schema Templates
- `database/AUTOMATED_SETUP.md` - Detaillierte Doku

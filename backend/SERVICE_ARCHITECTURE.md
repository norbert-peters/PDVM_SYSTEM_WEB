# PDVM Service-Architektur

## 🏗️ Übersicht

Die neue Service-Architektur folgt dem Desktop-Vorbild und bietet eine saubere Trennung zwischen Datenzugriff und Business Logic.

```
┌─────────────────────────────────────────┐
│           API Layer (FastAPI)           │
│         /api/mandanten, /api/tables     │
└─────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────┐
│        DataManager (Business Logic)      │
│  - MandantDataManager                   │
│  - PersonDataManager                    │
│  - Cache, Validierung, Geschäftslogik   │
└─────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────┐
│      PdvmDatabaseService (CRUD)         │
│  - Generic für alle PDVM-Tabellen       │
│  - list_all(), get_by_uid(), create()   │
│  - update(), delete(), search()         │
└─────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────┐
│            PostgreSQL                    │
│  auth.sys_benutzer, auth.sys_mandanten  │
│  mandant.persondaten, ...               │
└─────────────────────────────────────────┘
```

## 📁 Dateien

### Core Services
- **`app/core/pdvm_database.py`** - Generischer Database Service
- **`app/core/data_managers.py`** - Business Logic Layer (Manager-Klassen)
- **`app/core/user_manager.py`** - User-spezifischer Manager (existiert bereits)

### API Endpoints
- **`app/api/mandanten.py`** - Mandanten-Verwaltung (nutzt MandantDataManager)
- **`app/api/auth.py`** - Authentifizierung
- **`app/api/tables.py`** - Generischer Tabellen-Zugriff (TODO)

### Setup Scripts
- **`backend/setup_mandanten.py`** - Erstellt Standard-Mandanten
- **`backend/test_architecture.py`** - Test der Architektur
- **`backend/create_test_user.py`** - Erstellt Test-User

## 🔧 PDVM Standard-Tabellenstruktur

Alle Tabellen (außer sys_benutzer) haben diese Struktur:

```sql
CREATE TABLE tabelle (
    uid UUID PRIMARY KEY,              -- Eindeutige ID
    daten JSONB NOT NULL,              -- Hauptdaten (verschachtelt)
    name TEXT,                         -- Anzeigename
    historisch INTEGER DEFAULT 0,     -- 0=aktiv, 1+=historisch
    source_hash TEXT,                  -- Änderungsverfolgung
    sec_id UUID,                       -- Security/Verknüpfung
    gilt_bis TIMESTAMP DEFAULT '31.12.9999-59:59',  -- Gültigkeitsdatum default offen
    created_at TIMESTAMP DEFAULT NOW(),
    modified_at TIMESTAMP DEFAULT NOW(),
    daten_backup JSONB                 -- Backup bei Änderungen
);
```

### JSONB Daten-Format (Desktop-Kompatibel)

```json
{
  "ROOT": {},
  "PERSDATEN": {
    "PERSONALNUMMER": {"2025356.0": "A1"},
    "FAMILIENNAME": {"2025356.0": "Mustermann"},
    "VORNAME": {"2025356.0": "Max"}
  },
  "ANSCHRIFT_PERSON": {
    "STRASSE": {"2025356.0": "Hauptstraße 1"},
    "PLZ": {"2025356.0": "10115"},
    "ORT": {"2025356.0": "Berlin"}
  }
}
```

Zeitstempel-Format: `YYYYDDD.0` (Jahr + Tag des Jahres)

## 💻 Verwendung

### 1. PdvmDatabaseService (Low-Level CRUD)

```python
from app.core.pdvm_database import PdvmDatabaseService

# Initialisieren für spezifische Tabelle
db = PdvmDatabaseService(database="mandant", table="persondaten")

# Liste alle aktiven Datensätze
personen = await db.list_all(historisch=0, limit=100)

# Lade per UID
person = await db.get_by_uid("ed21cb69-046b-465f-b231-6e75852b50b3")

# Erstellen
new_person = await db.create(
    daten={
        "ROOT": {},
        "PERSDATEN": {"FAMILIENNAME": {"2025356.0": "Schmidt"}}
    },
    name="Anna Schmidt"
)

# Aktualisieren (mit Backup)
updated = await db.update(
    uid=person['uid'],
    daten=new_data,
    name="Neuer Name",
    backup_old=True  # Alte Daten in daten_backup
)

# Löschen (soft delete)
await db.delete(uid, soft=True)  # historisch=1

# Suchen
results = await db.search("Schmidt", search_fields=['name'])

# Zählen
count = await db.count(historisch=0)
```

### 2. DataManager (High-Level Business Logic)

```python
from app.core.data_managers import MandantDataManager

# Initialisieren
manager = MandantDataManager()

# Liste mit Cache
mandanten = await manager.list_all()

# Lade per ID (mit Cache)
mandant = await manager.get_by_id(mandant_id)

# Erstellen mit Validierung
mandant = await manager.create(
    name="Neuer Mandant",
    database="mandant_neu",
    description="Beschreibung",
    is_allowed=True
)

# Berechtigung prüfen
has_access = await manager.check_access(mandant_id, user_id)

# Datenbank-Name holen
db_name = await manager.get_database_name(mandant_id)

# Aktualisieren
updated = await manager.update(
    mandant_id,
    name="Neuer Name",
    is_allowed=False
)

# Cache leeren (bei Bedarf)
manager.clear_cache()
```

### 3. Person DataManager (Mandanten-spezifisch)

```python
from app.core.data_managers import PersonDataManager

# Initialisieren für Mandanten-Datenbank
manager = PersonDataManager(mandant_database="mandant")

# Liste
personen = await manager.list_all()

# Erstellen mit PDVM-Datenstruktur
person = await manager.create(
    personalnummer="A001",
    familienname="Schmidt",
    vorname="Anna",
    anrede="w",
    strasse="Teststraße 1",
    plz="10115",
    ort="Berlin"
)

# Suchen
results = await manager.search_by_name("Schmidt")
```

### 4. In API Endpoints verwenden

```python
from fastapi import APIRouter, Depends
from app.core.data_managers import MandantDataManager
from app.api.auth import get_current_user

router = APIRouter()

@router.get("/mandanten/list")
async def get_mandanten(current_user: dict = Depends(get_current_user)):
    manager = MandantDataManager()
    mandanten = await manager.list_all()
    return mandanten

@router.post("/mandanten/select")
async def select_mandant(mandant_id: str, current_user: dict = Depends(get_current_user)):
    manager = MandantDataManager()
    
    # Berechtigung prüfen
    has_access = await manager.check_access(mandant_id, current_user['sub'])
    if not has_access:
        raise HTTPException(403, "Keine Berechtigung")
    
    # Datenbank-Name holen
    database = await manager.get_database_name(mandant_id)
    
    return {"database": database, "mandant_id": mandant_id}
```

## 🚀 Setup

### 1. Mandanten erstellen
```bash
cd backend
python setup_mandanten.py
```

### 2. Test-User erstellen
```bash
python create_test_user.py
```

### 3. Architektur testen
```bash
python test_architecture.py
```

### 4. Backend starten
```bash
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## 🎯 Vorteile

### PdvmDatabaseService
✅ **Generic** - Funktioniert mit jeder PDVM-Tabelle  
✅ **JSONB-Parsing** - Automatisch  
✅ **Backup** - Alte Daten bei Update  
✅ **Soft Delete** - historisch-Flag  
✅ **Search** - Volltextsuche  
✅ **Pagination** - limit/offset  

### DataManager
✅ **Cache** - In-Memory für Performance  
✅ **Validierung** - Business Rules  
✅ **Geschäftslogik** - Mandanten-spezifisch  
✅ **Typsicherheit** - Klare Interfaces  
✅ **Wiederverwendbar** - Einmal schreiben, überall nutzen  

## 📝 Nächste Schritte

1. **Generic Table API** - REST-Endpoints für beliebige Tabellen
2. **Rechte-System** - User-spezifische Mandanten-Rechte
3. **Versionierung** - Historie mit git_bis
4. **Validation Rules** - JSON-Schema für daten-Feld
5. **Dashboard** - Frontend für Datenverwaltung

## 🔍 Debugging

```python
# Logging aktivieren
import logging
logging.basicConfig(level=logging.INFO)

# Database Service Debug
db = PdvmDatabaseService(database="auth", table="sys_mandanten")
mandanten = await db.list_all()
print(f"Gefunden: {len(mandanten)}")

# DataManager Debug
manager = MandantDataManager()
manager.clear_cache()  # Cache leeren
mandanten = await manager.list_all()
print(f"Cache: {len(manager._cache)}")
```

## 📚 Weitere Dokumentation

- [AUTO_DATABASE_MANAGEMENT.md](../AUTO_DATABASE_MANAGEMENT.md) - Datenbank-Setup
- [SYSTEM_STARTUP_GUIDE.md](../SYSTEM_STARTUP_GUIDE.md) - System starten
- [database/schema_mandant.sql](../database/schema_mandant.sql) - Tabellenstruktur

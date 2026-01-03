# PDVM System Web - Architektur-Redesign

## Ziel
Architektur des Desktop-Systems übernehmen für einheitliche und wartbare Datenbankverwaltung.

## Desktop-Architektur (Vorbild)

### 1. PdvmDatenbank (Core Manager)
- **Zweck**: Zentrale Datenbankmanager für alle PDVM-Tabellen
- **Funktionen**:
  - Findet Datenbank anhand Tabellenname
  - CRUD-Operationen auf uid + daten (JSONB)
  - JSONB-Navigation: get_value(uid, gruppe, feld), set_value(uid, gruppe, feld, value)
  - Einheitliches Interface für alle Tabellen

### 2. PdvmCentralDatenbank (Dataset Wrapper)
- **Zweck**: Wrapper für spezifische Datensätze (Tabelle + UID)
- **Funktionen**:
  - Initialisierung mit table_name + uid
  - Nutzt PdvmDatenbank intern
  - UID ist implizit (User muss nicht bei jedem Aufruf übergeben)
  - Basis-Klasse für alle Central*-Klassen

### 3. PdvmCentralSystemsteuerung (GCS Implementation)
- **Zweck**: Global Configuration System für Benutzereinstellungen
- **Funktionen**:
  - get_value(gruppe, feld): Liest Einstellung
  - set_value(gruppe, feld, value): Schreibt Einstellung
  - Verwaltet sys_systemsteuerung-Zeile des aktuellen Users
  - Gruppen: user_guid (allg. Settings), menu_guid (Menü-Settings), view_guid (View-Settings)

## Web-Architektur (Implementierung)

### Backend-Struktur

```
backend/app/core/
├── database.py                    # DatabasePool (erweitert für Multi-Tenant)
├── pdvm_datenbank.py              # Neue Klasse: PdvmDatabase (wie Desktop)
├── pdvm_central_datenbank.py      # Neue Klasse: PdvmCentralDatabase (Basis)
├── pdvm_central_systemsteuerung.py # GCS Implementation
├── pdvm_central_benutzer.py       # sys_benutzer Management
└── pdvm_central_mandanten.py      # sys_mandanten Management
```

### 1. PdvmDatabase (Neu implementieren)

**Datei**: `backend/app/core/pdvm_datenbank.py`

#### Datenbank-Routing (3-Datenbank-Architektur)

**1. auth.db** (zentral, einmalig):
- `sys_benutzer` (Zusatzspalten: benutzer, passwort)
- `sys_mandanten` (enthält Pfade zu mandant.db und system.db)

**2. system.db** (mandantenübergreifend):
- `sys_beschreibungen`
- `sys_dropdowndaten`
- `sys_menudaten`
- `sys_dialogdaten`
- `sys_viewdaten`
- `sys_framedaten`
- `sys_layout` (Themes: standard, weitere folgen)

**3. mandant.db** (pro Mandant):
- `sys_anwendungsdaten`
- `sys_systemsteuerung`
- Alle Fachdaten-Tabellen (persondaten, finanzdaten, etc.)

#### Historische Daten

**Kennzeichnung**: Spalte `historisch` (0 = aktuell, 1 = historisch)

**Datenstruktur in JSONB**:
```json
// Nicht historisch (historisch = 0):
{
  "gruppe": {
    "feld": wert
  }
}

// Historisch (historisch = 1):
{
  "gruppe": {
    "feld": {
      "2025356.00000": wert1,
      "2025300.00000": wert2,
      "2025250.00000": wert3
    }
  }
}
```

**PdvmDatabase**: Liefert vollständige `daten` + Flag `historisch`
**PdvmCentralDatabase**: Filtert nach Stichtag und gibt `{abdatum, wert}` zurück

```python
class PdvmDatabase:
    """Core Datenbank-Manager für PDVM-Tabellen"""
    
    def __init__(self, table_name: str):
        self.table_name = table_name
        self.db_name = self._find_database(table_name)
    
    def _find_database(self, table_name: str) -> str:
        """Ermittelt Datenbank anhand Tabellenname"""
        # AUTH: Benutzer und Mandanten
        if table_name in ["sys_benutzer", "sys_mandanten"]:
            return "auth"
        
        # SYSTEM: Strukturdaten und Layouts
        elif table_name in [
            "sys_beschreibungen", "sys_dropdowndaten", "sys_menudaten",
            "sys_dialogdaten", "sys_viewdaten", "sys_framedaten", "sys_layout"
        ]:
            return "system"
        
        # MANDANT: Anwendungsdaten und Fachdaten
        else:
            return "mandant"
    
    async def get_by_uid(self, uid: UUID) -> Optional[Dict]:
        """Lädt Datensatz anhand UID"""
        pool = DatabasePool.get_pool(self.db_name)
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                f"SELECT * FROM {self.table_name} WHERE uid = $1", uid
            )
            return dict(row) if row else None
    
    async def get_row(self, uid: UUID) -> Optional[Dict]:
        """Lädt vollständigen Datensatz mit historisch-Flag"""
        row = await self.get_by_uid(uid)
        if not row:
            return None
        return {
            'uid': row['uid'],
            'daten': row['daten'],
            'historisch': row['historisch'],
            'name': row['name']
        }
    
    async def set_value(self, uid: UUID, gruppe: str, feld: str, value: Any):
        """Schreibt Wert nach daten[gruppe][feld]"""
        row = await self.get_by_uid(uid)
        
        if row:
            daten = row['daten'] or {}
            if gruppe not in daten:
                daten[gruppe] = {}
            daten[gruppe][feld] = value
            
            pool = DatabasePool.get_pool(self.db_name)
            async with pool.acquire() as conn:
                await conn.execute(
                    f"UPDATE {self.table_name} SET daten = $1, modified_at = NOW() WHERE uid = $2",
                    daten, uid
                )
        else:
            # Neu erstellen
            daten = {gruppe: {feld: value}}
            pool = DatabasePool.get_pool(self.db_name)
            async with pool.acquire() as conn:
                await conn.execute(
                    f"INSERT INTO {self.table_name} (uid, daten, name) VALUES ($1, $2, $3)",
                    uid, daten, f"{self.table_name}_entry"
                )
```
**Aufgabe**: Stichtags-basierte Sicht auf historische Daten

```python
class PdvmCentralDatabase:
    """Basis-Wrapper für spezifische Datensätze mit Historie-Support"""
    
    def __init__(self, table_name: str, uid: UUID, stichtag: float = 9999365.00000):
        self.table_name = table_name
        self.uid = uid
        self.stichtag = stichtag  # Aktuellster = 9999365.00000
        self.db = PdvmDatabase(table_name)
    
    async def get_value(self, gruppe: str, feld: str, stichtag: float = None) -> Dict:
        """
        Liest Wert mit Historie-Support
        
        Returns:
            {'abdatum': float, 'wert': Any} für historische Felder
            {'abdatum': 9999365.00000, 'wert': Any} für aktuelle Felder
        """
        stichtag = stichtag or self.stichtag
        row = await self.db.get_row(self.uid)
        
        if not row or not row['daten']:
            return None
        
        daten = row['daten']
        if gruppe not in daten or feld not in daten[gruppe]:
            return None
        
        feld_wert = daten[gruppe][feld]
**Aufgabe**: 
- Verwaltet `sys_systemsteuerung` UND `sys_anwendungsdaten`
- Hält Benutzerdaten und Mandantendaten in Session
- Vermeidet erneute DB-Zugriffe während Session

```python
class PdvmCentralSystemsteuerung(PdvmCentralDatabase):
    """
    Global Configuration System
    Verwaltet Benutzer- und Mandantendaten in Session
    """
    
    def __init__(self, user_guid: UUID, mandant_guid: UUID):
        super().__init__("sys_systemsteuerung", user_guid)
        self.user_guid = user_guid
        self.mandant_guid = mandant_guid
        
        # Session-Cache
        self._user_data = None
        self._mandant_data = None
        self._anwendungsdaten = None
    
    async def load_session_data(self):
        """Lädt alle relevanten Daten einmalig beim Session-Start"""
        # Systemsteuerung (Benutzereinstellungen)
        self._user_data = await self.db.get_row(self.user_guid)
        
        # Mandantendaten aus sys_anwendungsdaten
        anwendungs_db = PdvmDatabase("sys_anwendungsdaten")
        self._anwendungsdaten = await anwendungs_db.get_row(self.mandant_guid)
**Besonderheit**: sys_benutzer hat Zusatzspalten `benutzer` und `passwort`

```python
class PdvmCentralBenutzer(PdvmCentralDatabase):
    """
    Benutzer-Management
    Wird vom Administrator für Benutzerverwaltung verwendet
    """
    
    def __init__(self, user_guid: UUID):
        super().__init__("sys_benutzer", user_guid)
        self.user_guid = user_guid
    
    async def get_user(self) -> Optional[Dict]:
        """
        Lädt kompletten User
        Zusatzspalten: benutzer, passwort
        """
        pool = DatabasePool.get_pool("auth")
        async with pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT uid, email, benutzer, passwort, daten,
                       historisch, sec_id, created_at, modified_at
                FROM sys_benutzer 
                WHERE uid = $1
            """, self.user_guid)
            return dict(row) if row else None
    
    async def change_password(self, new_password_hash: str):
        """Ändert Passwort"""
        pool = DatabasePool.get_pool("auth")
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE sys_benutzer SET passwort = $1, modified_at = NOW() WHERE uid = $2",
                new_password_hash, self.user_guid
            )
    
    async def get_all_users(self) -> List[Dict]:
        """Lädt alle Benutzer (für Admin)"""
        pool = DatabasePool.get_pool("auth")
        async with pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT uid, email, benutzer, daten, created_at
                FROM sys_benutzer
                WHERE historisch = 0
                ORDER BY benutzer
            """)
            return [dict(row) for row in rows]dungs_db = PdvmCentralDatabase("sys_anwendungsdaten", self.mandant_guid)
        return await anwendungs_db.get_static_value(gruppe, feld
        row = await self.db.get_row(self.uid)
        
        if not row:
            # Neu erstellen
            daten = {gruppe: {feld: {str(abdatum): wert}}}
            await self.db.create(self.uid, daten, historisch=1)
        else:
            daten = row['daten']
            
            if gruppe not in daten:
                daten[gruppe] = {}
            
            if row['historisch'] == 1:
                # Historisch: Wert unter abdatum ablegen
                if not isinstance(daten[gruppe].get(feld), dict):
                    daten[gruppe][feld] = {}
                daten[gruppe][feld][str(abdatum)] = wert
            else:
                # Nicht historisch: Direkter Wert
                daten[gruppe][feld] = wert
            
            await self.db.update(self.uid, daten)
    
    async def get_static_value(self, gruppe: str, feld: str) -> Any:
        """
        Für sys_* Tabellen: Direkter Zugriff ohne Historie
        Returns: Wert direkt (nicht {abdatum, wert})
        """
        row = await self.db.get_row(self.uid)
        if not row or not row['daten']:
            return None
        return row['daten'].get(gruppe, {}).get(feld)
    
    async def set_static_value(self, gruppe: str, feld: str, wert: Any):
        """
        Für sys_* Tabellen: Direktes Schreiben ohne abdatum
        """
        row = await self.db.get_row(self.uid)
        
        if not row:
            daten = {gruppe: {feld: wert}}
            await self.db.create(self.uid, daten, historisch=0)
        else:
            daten = row['daten']
            if gruppe not in daten:
                daten[gruppe] = {}
            daten[gruppe][feld] = wert
            await self.db.update(self.uid, daten
        await self.db.set_value(self.uid, gruppe, feld, value)
    
    async def get_all_data(self) -> Optional[Dict]:
        """Lädt kompletten Datensatz"""
        return await self.db.get_by_uid(self.uid)
```

### 3. PdvmCentralSystemsteuerung (GCS)

**Datei**: `backend/app/core/pdvm_central_systemsteuerung.py`

```python
class PdvmCentralSystemsteuerung(PdvmCentralDatabase):
    """Global Configuration System für User-Settings"""
    
    def __init__(self, user_guid: UUID):
        super().__init__("sys_systemsteuerung", user_guid)
        self.user_guid = user_guid
**Aufgabe**: Zentrale Stelle für Mandanten-Datenbanksteuerung

```python
class PdvmCentralMandanten(PdvmCentralDatabase):
    """
    Mandanten-Management
    Regelt Zugriff auf mandantenspezifische Datenbanken
    """
    
    def __init__(self, mandant_guid: UUID):
        super().__init__("sys_mandanten", mandant_guid)
        self.mandant_guid = mandant_guid
    
    async def get_database_info(self) -> Optional[Dict]:
        """
        Liest Datenbank-Verbindungsinfo aus daten JSONB
        
        Returns:
            {
                'mandant_db': 'mandant_firma_xyz',
                'system_db': 'pdvm_system',
                'host': 'localhost',
                'port': 5432,
                'user': 'postgres',
                'password': '***'
            }
        """
        row = await self.db.get_row(self.mandant_guid)
        if not row or not row['daten']:
            return None
        
        daten = row['daten']
        return {
            'mandant_db': daten.get('DATABASE'),
            'system_db': daten.get('SYSTEM_DATABASE', 'pdvm_system'),
            'host': daten.get('HOST', 'localhost'),
            'port': daten.get('PORT', 5432),
            'user': daten.get('USER', 'postgres'),
            'password': daten.get('PASSWORD')
        }
    
    async def create_database_pool(self):
        """Erstellt Connection Pool für diesen Mandanten"""
        db_info = await self.get_database_info()
        if not db_info:
            raise ValueError(f"Keine Datenbankinfo für Mandant {self.mandant_guid}")
        
        db_url = f"postgresql://{db_info['user']}:{db_info['password']}@{db_info['host']}:{db_info['port']}/{db_info['mandant_db']}"
        await DatabasePool.create_mandant_pool(str(self.mandant_guid), db_url)
    
    async def get_all_mandanten(self) -> List[Dict]:
        """Lädt alle Mandanten (für Auswahl beim Login)"""
        pool = DatabasePool.get_pool("auth")
        async with pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT uid, name, daten
                FROM sys_mandanten
                WHERE historisch = 0
                ORDER BY name
            """)
            return [dict(row) for row in rows]vmCentralBenutzer

**Datei**: `backend/app/core/pdvm_central_benutzer.py`

```python
class PdvmCentralBenutzer(PdvmCentralDatabase):
    """Benutzer-Management (Ausnahme: hat passwort-Spalte)"""
    
    def __init__(self, user_guid: UUID):
        super().__init__("sys_benutzer", user_guid)
        self.user_guid = user_guid
    
    async def get_user(self) -> Optional[Dict]:
        """Lädt kompletten User"""
        pool = DatabasePool.get_pool("auth")
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT uid, email, benutzer, passwort, daten FROM sys_benutzer WHERE uid = $1",
                self.user_guid
            )
            return dict(row) if row else None
    
    async def change_password(self, new_password_hash: str):
        """Ändert Passwort"""
        pool = DatabasePool.get_pool("auth")
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE sys_benutzer SET passwort = $1, modified_at = NOW() WHERE uid = $2",
                new_password_hash, self.user_guid
            )
```

### 5. PdvmCentralMandanten

**Datei**: `backend/app/core/pdvm_central_mandanten.py`

```python
class PdvmCentralMandanten(PdvmCentralDatabase):
    """Mandanten-Management"""
    
    def __init__(self, mandant_guid: UUID):
        super().__init__("sys_mandanten", mandant_guid)
        self.mandant_guid = mandant_guid
    
    async def get_database_info(self) -> Optional[Dict]:
        """Liest Datenbank-Info aus daten JSONB"""
        data = awNeu-Entwicklung
1. ✅ GCS-Endpunkte mit PdvmCentralSystemsteuerung neu entwickeln
2. ✅ Historie-Support einbauen (get_value mit Stichtag)
3. ✅ Session-Cache implementieren
4. ✅ toggle_menu fertigstellen
5. ✅ test-gcs.html durchlaufen lassen

**Anmerkung**: Nicht migrieren - wir sind am Anfang der Entwicklung!
        return {
            'database_name': data['daten'].get('DATABASE'),
            'system_database': data['daten'].get('SYSTEM_DATABASE'),
            'host': data['daten'].get('HOST', 'localhost'),
            'port': data['daten'].get('PORT', 5432)
        }
```

## Multi-Tenant Datenbank-Architektur

### DatabasePool Erweiterung

**Datei**: `backend/app/core/database.py`

```python
class DatabasePool:
    _pool_system: Optional[asyncpg.Pool] = None
    _pool_auth: Optional[asyncpg.Pool] = None
    _pool_mandant: Optional[asyncpg.Pool] = None  # Default-Mandant
    _mandant_pools: Dict[str, asyncpg.Pool] = {}  # NEU: Dynamische Mandanten-Pools
    
    @classmethod
    async def create_mandant_pool(cls, mandant_id: str, database_url: str):
        """Erstellt Pool für spezifischen Mandanten"""
        if mandant_id not in cls._mandant_pools:
            cls._mandant_pools[mandant_id] = await asyncpg.create_pool(database_url)
    
    @classmethod
    def get_mandant_pool(cls, mandant_id: str) -> asyncpg.Pool:
        """Gibt Pool für spezifischen Mandanten zurück"""
        if mandant_id in cls._mandant_pools:
            return cls._mandant_pools[mandant_id]
        return cls._pool_mandant  # Fallback auf Default
```Historie-Support**: Stichtags-basierte Datenverarbeitung integriert
3. **Session-Performance**: Gecachte Benutzer- und Mandantendaten
4. **Wartbarkeit**: Central-Klassen kapseln Business-Logik
5. **Skalierbarkeit**: Multi-Tenant-Architektur mit dynamischen Pools
6. **Desktop-Kompatibilität**: Identisches Pattern wie bewährtes Desktop-System
7. Wichtige Implementierungs-Details

### PDVM-Datumsformat
- Format: `JJJJTTT.SSSSS` (z.B. 2025356.00000)
- Jahr: 4-stellig
- Tag: 3-stellig (1-365/366)
- Sekunden: 5 Nachkommastellen

### Stichtag-Logik
- `9999365.00000` = aktuellster Wert
- Historische Werte: Größtes abdatum ≤ Stichtag
- Kein Wert gefunden: None

### Theme-System (sys_layout)
- Tabelle in system.db
- Mindestens "standard" Theme
- Struktur: `{theme_name: {colors: {...}, fonts: {...}, ...}}`
- Erweiterbar für weitere Themes

## Nächste Schritte

1. ✅ **GCS funktioniert** - Bugfix erfolgreich
2. ✅ **Anmerkungen eingearbeitet** - Architecture Review abgeschlossen
3. 🔨 **PdvmDatabase implementieren** - Core-Klasse mit Historie
4. 🔨 **PdvmCentralDatabase implementieren** - Wrapper mit Stichtag-Filter
5. 🔨 **PdvmCentralSystemsteuerung implementieren** - GCS mit Session-Cache
6. 🔨 **DatabasePool erweitern** - Multi-Tenant Support
7. 🔨 **Zweiten Mandanten anlegen** - Testing
8. 🔨 **Standard Theme vorbereiten** - sys_layout initialisieren
9. ✅ **toggle_menu läuft** - Test erfolgreich
    "HOST": "localhost",
    "PORT": 5432
  }
}
```

## Migration & Implementierung

### Phase 1: Core-Klassen
1. ✅ PdvmDatabase implementieren
2. ✅ PdvmCentralDatabase implementieren
3. ✅ PdvmCentralSystemsteuerung implementieren
4. ✅ Tests für Basic CRUD

### Phase 2: GCS Migration
1. ✅ GCS-Endpunkte auf PdvmCentralSystemsteuerung umstellen
2. ✅ test-gcs.html durchlaufen lassen
3. ✅ toggle_menu implementieren

### Phase 3: Multi-Tenant
1. ✅ DatabasePool erweitern
2. ✅ Zweiten Mandanten erstellen (mandant_test2)
3. ✅ PdvmDatabase erkennt Mandant-DB automatisch
4. ✅ Tests mit beiden Mandanten

### Phase 4: Weitere Central-Klassen
1. ✅ PdvmCentralBenutzer für User-Management
2. ✅ PdvmCentralMandanten für Mandanten-Verwaltung
3. ✅ Schrittweise bestehende Endpunkte migrieren

## Vorteile

1. **Einheitlichkeit**: Alle Tabellen-Zugriffe über PdvmDatabase
2. **Wartbarkeit**: Central-Klassen kapseln Business-Logik
3. **Skalierbarkeit**: Multi-Tenant-Architektur eingebaut
4. **Desktop-Kompatibilität**: Identisches Pattern wie bewährtes Desktop-System
5. **Typsicherheit**: Klare Interfaces, weniger Fehler

## Nächste Schritte

1. ✅ **Entwurf reviewen** - Dieser Entwurf
2. 🔨 **PdvmDatabase implementieren** - Core-Klasse
3. 🔨 **PdvmCentralDatabase implementieren** - Wrapper-Basis
4. 🔨 **PdvmCentralSystemsteuerung implementieren** - GCS
5. 🔨 **GCS-Endpoints refactoren** - Verwenden neue Klassen
6. 🔨 **DatabasePool erweitern** - Multi-Tenant Support
7. 🔨 **Zweiten Mandanten anlegen** - Testing
8. ✅ **toggle_menu fertigstellen** - Ursprüngliches Ziel

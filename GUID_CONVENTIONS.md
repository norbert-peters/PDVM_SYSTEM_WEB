# GUID-Konventionen im PDVM-System

**Datum:** 14. Februar 2026  
**Status:** Standardisierung aktiv

## 📋 Übersicht

Das PDVM-System verwendet ein standardisiertes GUID-System zur Verwaltung von Metadaten, Templates und regulären Datensätzen.

## 🔑 Fiktive GUIDs (System-reserviert)

Jede Tabelle im System **MUSS** drei fiktive System-Sätze mit reservierten GUIDs enthalten:

### 1. Tabellen-Metadaten: `00000000-0000-0000-0000-000000000000`

**Zweck:** Zentrale Metadaten und Konfiguration für die Tabelle selbst

**Verwendung:**
- Tabellen-Beschreibung
- Berechtigungen auf Tabellenebene
- System-Parameter
- Metadaten zur Tabellenstruktur

**Beispiel:**
```json
{
  "uid": "00000000-0000-0000-0000-000000000000",
  "name": "Tabellen-Metadaten",
  "daten": {
    "TABLE_INFO": {
      "description": "Frame-Definitionen für Dialoge",
      "version": "2.0",
      "schema_migrated": true
    }
  },
  "historisch": 0
}
```

### 2. Standard-Template (Neuer Satz): `66666666-6666-6666-6666-666666666666`

**Zweck:** Default-Template für neue Datensätze

**Verwendung:**
- Wird beim Erstellen eines neuen Datensatzes als Vorlage verwendet
- Enthält Standardwerte für alle Felder
- Definiert initiale FIELDS/TABS Struktur

**Besonderheit:** Modul-Referenzierung
- Wenn im CONTROL-Feld ein `MODUL`-Feld existiert:
  - Suche in `55555555-5555-5555-5555-555555555555` unter MODUL nach passendem Template
  - Ersetze `"MODUL": "..."` durch das gefundene Template-Modul

**Beispiel:**
```json
{
  "uid": "66666666-6666-6666-6666-666666666666",
  "name": "Template neuer Satz",
  "daten": {
    "ROOT": {
      "EDIT_TYPE": "",
      "SELF_GUID": "",
      "SELF_NAME": ""
    },
    "FIELDS": {}
  },
  "historisch": 0
}
```

### 3. Modul-Templates-Container: `55555555-5555-5555-5555-555555555555`

**Zweck:** Container für verschiedene Template-Varianten nach Modul

**Verwendung:**
- Speichert mehrere Templates für unterschiedliche Verwendungszwecke
- Organisiert nach Modul/Typ
- Wird bei Insert referenziert wenn CONTROL.MODUL existiert

**Beispiel:**
```json
{
  "uid": "55555555-5555-5555-5555-555555555555",
  "name": "Templates",
  "daten": {
    "TEMPLATES": {
      "edit_frame": {
        "ROOT": { ... },
        "FIELDS": { ... }
      },
      "view_frame": {
        "ROOT": { ... },
        "FIELDS": { ... }
      }
    }
  },
  "historisch": 0
}
```

## 🆔 Reguläre GUIDs (UUID v4)

**Alle anderen Datensätze** verwenden echte UUIDs (v4):
- Generiert mit Python `uuid.uuid4()`
- Eindeutig über alle Tabellen hinweg
- Keine Kollisionen mit fiktiven GUIDs

## 🔄 Insert-Logik mit Modul-Referenzierung

```python
async def insert_new_record(table_name: str, control_data: dict):
    """
    Erstellt neuen Datensatz mit Template-Logik
    
    1. Lade Template aus 66666666... Satz
    2. Wenn control_data['MODUL'] existiert:
       - Lade Templates aus 55555555... Satz
       - Suche unter TEMPLATES[MODUL] nach passendem Template
       - Ersetze "MODUL": "..." durch gefundenes Template
    3. Generiere neue UUID für neuen Satz
    4. Insert mit befüllten Daten
    """
    # Template laden
    template = await load_record(UUID("66666666-6666-6666-6666-666666666666"))
    new_data = copy.deepcopy(template['daten'])
    
    # Modul-Referenzierung
    if 'MODUL' in control_data:
        modul_name = control_data['MODUL']
        templates_container = await load_record(UUID("55555555-5555-5555-5555-555555555555"))
        
        if modul_name in templates_container['daten']['TEMPLATES']:
            modul_template = templates_container['daten']['TEMPLATES'][modul_name]
            # Ersetze Modul-Referenz durch konkretes Template
            new_data = merge_template(new_data, modul_template)
    
    # Neue UUID generieren
    new_uid = uuid.uuid4()
    
    # Insert
    await db.insert({
        'uid': new_uid,
        'name': control_data.get('name', 'Neuer Satz'),
        'daten': new_data,
        'historisch': 0
    })
    
    return new_uid
```

## 📊 Betroffene Datenbanken

Die Standardisierung gilt für alle Tabellen in:

1. **auth** - Authentifizierungs-Datenbank
   - sys_login
   - sys_sessions
   - ...

2. **pdvm_system** - System-Tabellen
   - sys_framedaten
   - sys_control_dict
   - sys_dialogdaten
   - sys_menudaten
   - sys_viewdaten
   - ...

3. **mandant** - Mandanten-spezifische Daten
   - (je nach Mandant-Schema)

4. **pdvm_standard** - Standard-Vorlagen
   - (Standard-Templates über Mandanten hinweg)

## 🔧 Migration

### Prüfung: Welche Tabellen haben die fiktiven Sätze?

```sql
-- Prüfe ob fiktive GUIDs vorhanden
SELECT 
    '00000000-0000-0000-0000-000000000000' as guid_type,
    EXISTS(SELECT 1 FROM table_name WHERE uid = '00000000-0000-0000-0000-000000000000') as exists
UNION ALL
SELECT 
    '66666666-6666-6666-6666-666666666666',
    EXISTS(SELECT 1 FROM table_name WHERE uid = '66666666-6666-6666-6666-666666666666')
UNION ALL
SELECT 
    '55555555-5555-5555-5555-555555555555',
    EXISTS(SELECT 1 FROM table_name WHERE uid = '55555555-5555-5555-5555-555555555555');
```

### Migration-Script

Siehe: `backend/migrate_fictional_guids.py`

## ⚠️ Wichtige Regeln

1. **NIEMALS** fiktive GUIDs für reguläre Daten verwenden
2. **IMMER** UUID v4 für neue Datensätze generieren
3. **Prüfen** ob fiktive Sätze existieren bevor darauf zugegriffen wird
4. **Nicht löschen** - fiktive Sätze sind system-kritisch
5. **historisch = 0** - fiktive Sätze werden NIE historisiert

## 🔍 Validierung

```python
def is_fictional_guid(uid: UUID) -> bool:
    """Prüft ob GUID fiktiv (system-reserviert) ist"""
    fictional = [
        UUID("00000000-0000-0000-0000-000000000000"),
        UUID("66666666-6666-6666-6666-666666666666"),
        UUID("55555555-5555-5555-5555-555555555555")
    ]
    return uid in fictional

def ensure_fictional_records(table_name: str):
    """Stellt sicher dass alle fiktiven Sätze existieren"""
    for fictional_uid in FICTIONAL_GUIDS:
        if not record_exists(table_name, fictional_uid):
            create_fictional_record(table_name, fictional_uid)
```

## 📝 Zusammenfassung

| GUID | Zweck | Inhalt | Verwendung |
|------|-------|--------|------------|
| `00000000...` | Tabellen-Metadaten | TABLE_INFO | System-Konfiguration |
| `66666666...` | Standard-Template | Default-Struktur | Insert neuer Satz |
| `55555555...` | Modul-Templates | TEMPLATES[modul] | Modul-spezifische Vorlagen |
| UUID v4 | Reguläre Daten | Business Data | Alle anderen Sätze |

---

**Status:** Spezifikation definiert | Migration ausstehend

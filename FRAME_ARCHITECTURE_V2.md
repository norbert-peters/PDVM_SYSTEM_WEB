# Frame-Architektur V2 - Konzeptanalyse & Umsetzungsplan

**Datum:** 14. Februar 2026  
**Status:** Phase 1, 2, 3 & 4 (Basis) abgeschlossen ✅ | Phase 5 & 6 ausstehend

> **⚠️ WICHTIG:** Diese Architektur basiert auf dem standardisierten GUID-System.  
> Siehe [GUID_CONVENTIONS.md](GUID_CONVENTIONS.md) für Details zu fiktiven GUIDs.

## 📋 Zusammenfassung des Vorschlags

### 🎯 Implementierungs-Fortschritt

| Phase | Status | Dauer | Abgeschlossen |
|-------|--------|-------|---------------|
| 1. Control Dictionary erweitern | ✅ Fertig | 2 Tage | 14.02.2026 |
| 2. Frame-Struktur standardisieren | ✅ Fertig | 1 Tag | 14.02.2026 |
| 3. parent_guid Hierarchie | ✅ Fertig | 1 Tag | 14.02.2026 |
| 4. element_list als Frame (Basis) | ✅ Fertig | 1 Tag | 14.02.2026 |
| 5. Self-Editing Sicherheit | 🔒 Optional | 1-2 Tage | - |
| 6. Zentrale Services | 🔧 Optional | 2-3 Tage | - |

**Gesamtfortschritt:** 66% (Phase 1-4 Basis von 6 abgeschlossen)

---

## ✅ Update 18.02.2026: Linearer Draft-Flow (generisch für alle Tabellen)

Der bisherige "Neuer Satz"-Ablauf wurde auf einen **linearen, tabellenunabhängigen Draft-Flow** umgestellt.

### Ziel
- Kein nicht-linearer Sonderpfad mehr bei der Neuanlage.
- Kein Tabellen-Spezialfall im Frontend.
- Fehler müssen zielgenau pro InputControl (Gruppe/Feld) zurückgegeben werden.

### Neuer Ablauf (linear)
1. `POST /api/dialogs/{dialog_guid}/draft/start`
  - lädt Template `6666...`
  - baut Draft-Daten (inkl. `ROOT`) generisch auf
  - persistiert Draft im Dialog-UI-Scope
2. Edit im bestehenden Frame (alle Gruppen, inkl. `element_list`)
  - Gruppen sind generisch (`ROOT`, `CONTROL`, weitere Tabellen-/Sprachgruppen, etc.)
3. `PUT /api/dialogs/{dialog_guid}/draft/{draft_id}`
  - aktualisiert Draft-Daten
  - liefert `validation_errors` mit Zielpfad (`group`, `field`, `code`, `message`)
4. `POST /api/dialogs/{dialog_guid}/draft/{draft_id}/commit`
  - validiert Draft
  - erstellt echten Datensatz
  - übernimmt Draft-Daten in den Satz
  - entfernt Draft

### Architektur-Regeln eingehalten
- **Keine SQL im Router**: Router nutzt Service-Funktionen und Systemsteuerung-API.
- **Dialog View/Edit Autonomie**: Neuanlage startet im View, Pflege im Edit.
- **API-Layer-Trennung**: Frontend nutzt ausschließlich `src/api/client.ts`.
- **Linearität**: Create → Edit → Commit ohne 428-Sonderpfad für modul-Auswahl.

### Technische Hinweise
- Drafts werden pro Dialog-Scope (`dialog_guid::table::edit_type`) gespeichert.
- `ROOT.SELF_GUID` wird beim Commit auf die echte UID gesetzt (kein Draft-GUID-Leak).
- Validierungsfehler werden im Frontend an `Gruppe.Feld`-Controls gebunden.

---

### 1. Control Dictionary mit Modultypierung
- ✅ **sys_control_dict** wird erweitert um `modul_type`
- ✅ **Werte:** `view`, `edit`, `tabs`
- ✅ **SELF_NAME:** Automatische Benennung `[3-Buchstaben-Tabelle]_[feldname]`
  - Beispiel: `sys_familienname` oder `per_vorname`

### 2. element_list als autonomes Frame
- ✅ element_list **IST selbst ein Frame**
- ✅ Kann Elemente hinzufügen/löschen
- ✅ Jedes Element hat eigene GUID
- ✅ Hierarchie über `parent_guid`

### 3. Frame-Struktur (vereinfacht)
```json
{
  "ROOT": {
    "ROOT_TABLE": "persondaten",
    "SELF_GUID": "uuid...",
    "SELF_NAME": "Personen bearbeiten",
    "TABS": 2
  },
  "TABS": {
    "tab_1_guid": { "dict_ref": "tab_control_guid" },
    "tab_2_guid": { "dict_ref": "tab_control_guid" }
  },
  "FIELDS": {
    "field_1_guid": { "dict_ref": "control_guid", "parent_guid": null },
    "field_2_guid": { "dict_ref": "control_guid", "parent_guid": "element_list_guid" }
  }
}
```

### 4. parent_guid Hierarchie
- Controls **ohne** parent_guid: Direkte Felder
- Controls **mit** parent_guid: Gehören zu element_list
- element_list selbst: Hat `parent_guid = null`

### 5. Drei Verwendungsarten von element_list

| modul_type | Verwendung | Gruppe | Beispiel |
|------------|------------|--------|----------|
| `tabs` | Tab-Definitionen | TABS | Liste der Tabs im Frame |
| `view` | View-Spalten | [TABLE] | Spalten für Matrix-Views |
| `edit` | Feld-Definitionen | FIELDS | Controls für Edit-Frames |

### 6. Self-Editing Spezialfall (sys_framedaten)

**Problem:** Frame editiert seine eigene Struktur
**Lösung:** 
1. Felder mit element_list referenzieren
2. `parent_guid` entfernen (Entkopplung)
3. Satz mit `sec_id = "read_only"` sperren
4. Zentrale Verwaltung über PdvmDatabase

## 🎯 Bewertung der Architektur

### ✅ Stärken

1. **Klarheit:** Eindeutige Trennung von modul_type
2. **Hierarchie:** parent_guid schafft klare Beziehungen
3. **Wiederverwendbarkeit:** Controls zentral in Dictionary
4. **Self-Editing:** Pragmatische Lösung mit Sperrmechanismus
5. **Linear umsetzbar:** Schrittweise Migration möglich

### ⚠️ Zu bedenken

1. **SELF_NAME Eindeutigkeit:**
   - Problem: Was bei mehrdeutigen Feldnamen?
   - Lösung: Prüfung bei Erstellung, ggf. Suffix `_01`, `_02`

2. **parent_guid Konsistenz:**
   - Problem: Orphaned Controls wenn element_list gelöscht wird
   - Lösung: CASCADE DELETE oder Warnmeldung

3. **element_list als Frame:**
   - Problem: Rekursionstiefe (element_list in element_list?)
   - Lösung: Max. Tiefe = 1 (keine verschachtelten element_lists)

4. **sec_id = read_only:**
   - Problem: Spätere Änderungen kompliziert
   - Lösung: Admin-Modus zum Entsperren

### ❓ Offene Fragen

1. **Frame-Definition vs. Frame-Instanz:**
   - Wie unterscheiden wir Template (sys_framedaten) vs. Instanz (konkretes Frame)?
   - Vorschlag: `is_template` Flag in ROOT?

2. **element_list Frame-Referenz:**
   - Wo wird das Frame für element_list gespeichert?
   - Vorschlag: `element_frame_guid` in Control-Definition?

3. **Daten-Struktur für element_list:**
   - Wie sehen die Daten aus? Liste? Dict?
   - Vorschlag: Dict mit GUIDs als Keys (wie FIELDS aktuell)

## 🔧 Linearer Umsetzungsplan

### Phase 1: Control Dictionary erweitern ✅ ABGESCHLOSSEN

**Ziel:** sys_control_dict um neue Felder erweitern

```python
# In sys_control_dict.daten:
{
  "name": "familienname",
  "label": "Familienname",
  "type": "string",
  "modul_type": "edit",           # NEU ✅
  "parent_guid": null,             # NEU ✅
  "SELF_NAME": "per_familienname", # NEU ✅ (automatisch generiert)
  "table": "persondaten",
  "gruppe": "PERSDATEN",
  "feld": "FAMILIENNAME"
}
```

**Aufgaben:**
1. ✅ Schema-Dokumentation aktualisieren
2. ✅ Migration-Skript für bestehende Controls (migrate_control_dict_v2.py)
3. ✅ Generierung von SELF_NAME implementiert (generate_self_name())
4. ✅ modul_type Validation (enum: view, edit, tabs)
5. ✅ Labels für alle Controls hinzugefügt (add_missing_labels.py)

**Ergebnis:**
- 22 Controls erfolgreich migriert
- Verteilung: 19× edit, 2× tabs, 1× view
- Alle Controls haben eindeutige SELF_NAMEs (Format: sys_[fieldname])
- Alle Controls haben deutsche Labels
- SELF_NAME Eindeutigkeit validiert (keine Kollisionen)
- parent_guid vorbereitet für Phase 3

**Dateien:**
- `backend/migrate_control_dict_v2.py` - Migrations-Script
- `backend/add_missing_labels.py` - Label-Ergänzung
- `backend/check_control_dict_status.py` - Status-Prüfung

### Phase 2: Frame-Struktur anpassen ✅ ABGESCHLOSSEN

**Ziel:** ROOT-Gruppe standardisieren

```python
# In sys_framedaten.daten:
{
  "ROOT": {
    "ROOT_TABLE": "persondaten",       # Pflicht
    "SELF_GUID": "uuid...",            # Pflicht (Frame-UID)
    "SELF_NAME": "Personen bearbeiten", # Pflicht
    "TABS": 2,                         # Pflicht
    "EDIT_TYPE": "edit_frame"          # Optional (Kompatibilität)
  },
  "TABS": {
    # Tab-Controls mit dict_ref
  },
  "FIELDS": {
    # Feld-Controls mit dict_ref + parent_guid
  }
}
```

**Aufgaben:**
1. ✅ ROOT-Felder Validation implementieren (analyze_frames.py)
2. ✅ Migration bestehender Frames (migrate_frames_phase2.py)
3. ✅ SELF_GUID = Frame-UID automatisch setzen
4. ✅ Alle Frames in sys_framedaten geprüft (14 Frames)
5. ✅ EDIT_TYPE für Kompatibilität beibehalten

**Ergebnis:**
- 14 Frames erfolgreich migriert
- Verteilung: 4× mit ROOT_TABLE, 10× generic (NULL)
- EDIT_TYPE → ROOT_TABLE Mapping: sys_login, sys_framedaten, sys_menudaten
- Alle Frames haben vollständige ROOT-Struktur
- NULL als gültiger Wert für generische Frames akzeptiert

**Dateien:**
- `backend/analyze_frames.py` - Frame-Struktur Analyse
- `backend/migrate_frames_phase2.py` - Phase 2 Migration
- `backend/check_table_structure.py` - Tabellen-Struktur Prüfung

### Phase 3: parent_guid Hierarchie ✅ ABGESCHLOSSEN

**Ziel:** Hierarchische Beziehungen etablieren

**Aufgaben:**
1. ✅ parent_guid Spalte in Controls (Phase 1 vorbereitet)
2. ✅ Hierarchie-Analyse durchgeführt (analyze_control_hierarchy.py)
3. ✅ parent_guid für 6 Child-Controls gesetzt
4. ⚠️ Funktion: `get_children(parent_guid)` in PdvmDatabase (Phase 6)
5. ⚠️ Validation: parent_guid muss auf element_list zeigen (Phase 6)
6. ⚠️ CASCADE oder WARNING bei parent_guid DELETE (Phase 6)

**Ergebnis:**
- 6 Controls erfolgreich mit parent_guid verknüpft
- tabs_def als Parent für Tab-Controls etabliert
- Hierarchie-Baum: 3 element_lists, 6 children, 13 orphans
- Controls mit parent_guid: tab_order, tab_visible, tab01_gruppe, tab01_head, tab02_gruppe, tab02_head

**Hierarchie-Struktur:**
```
tabs_def (a88ee663-745f-4ab8-b8d0-c024d0a0987b)
├─ tab_order
├─ tab_visible
├─ tab01_gruppe
├─ tab01_head
├─ tab02_gruppe
└─ tab02_head
```

**Dateien:**
- `backend/analyze_control_hierarchy.py` - Hierarchie-Analyse
- `backend/migrate_parent_guid_phase3.py` - Phase 3 Migration
- `backend/show_hierarchy.py` - Hierarchie-Visualisierung

### Phase 4: element_list als Frame ✅ BASIS IMPLEMENTIERT

**Ziel:** element_list wird zu eigenständigem Frame-Typ

**Konzept:**
```python
# element_list Control in sys_control_dict:
{
  "name": "fields",
  "label": "Felder",
  "type": "element_list",
  "modul_type": "edit",
  "element_frame_guid": "uuid...",  # Zeigt auf Frame in sys_framedaten
  "SELF_NAME": "fra_fields"
}

# Referenziertes Frame in sys_framedaten:
{
  "ROOT": {
    "ROOT_TABLE": null,  # Kein eigenes Datenziel
    "SELF_GUID": "uuid...",
    "SELF_NAME": "Field Definition",
    "TABS": 1,
    "IS_ELEMENT": true    # Marker: Ist Teil einer element_list
  },
  "FIELDS": {
    "name": { "dict_ref": "..." },
    "label": { "dict_ref": "..." },
    "type": { "dict_ref": "..." }
  }
}
```

**Aufgaben:**
1. ✅ `element_frame_guid` in element_list Controls (2 von 3 migriert)
2. ✅ `IS_ELEMENT` Flag in Frame ROOT (2 Frames gesetzt)
3. ✅ Service: `load_element_list_frame(control_guid)` implementiert
4. ⚠️ Service: `create_element_instance(element_list_guid)` KONZEPT
5. ⚠️ Service: `delete_element_instance(element_guid)` KONZEPT
6. ✅ Service: `get_element_list_children(element_list_uid)` implementiert
7. ✅ Service: `validate_element_list_setup()` implementiert

**Ergebnis:**
- 2 element_lists mit element_frame_guid: tabs_def, fields
- 2 Frames mit IS_ELEMENT=true: Element-List FIELDS/TABS Templates
- 1 element_list ohne Frame: tabs (noch unklar)
- Referenz-Integrität validiert: alle Referenzen gültig
- Basis-Services implementiert und getestet

**Zuordnungen:**
```
tabs_def (a88ee663-745f-4ab8-b8d0-c024d0a0987b)
  → Element-List TABS Template (55555555-0002-4001-8001-000000000002)
  
fields (9ccb9eb8-ae9f-4308-97b7-a9e78b3d5c78)
  → Element-List FIELDS Template (55555555-0001-4001-8001-000000000001)
```

**Dateien:**
- `backend/analyze_element_list_frames.py` - Frame-Zuordnungs-Analyse
- `backend/migrate_element_frames_phase4.py` - Phase 4 Migration
- `backend/test_phase4_setup.py` - Setup Validierung
- `backend/app/core/element_list_service.py` - Service-Implementierung

**Hinweise:**
- create/delete Services sind konzeptuell implementiert
- Konkrete Implementierung hängt vom Datenmodell ab (wie element_lists in Records gespeichert werden)
- UI-Integration noch ausstehend (außerhalb Scope dieser Phase)

### Phase 5: Self-Editing mit Sperrmechanismus 🔒

**Ziel:** sys_framedaten kann sich sicher bearbeiten

**Sperrmechanismus:**
```python
# In PdvmDatabase:
class PdvmDatabase:
    async def lock_record(self, uid: UUID, lock_mode: str = "read_only"):
        """Sperrt Datensatz mit sec_id"""
        await self.update(uid, sec_id=lock_mode)
    
    async def unlock_record(self, uid: UUID):
        """Entsperrt Datensatz"""
        await self.update(uid, sec_id=None)
    
    async def is_locked(self, uid: UUID) -> bool:
        """Prüft Lock-Status"""
        row = await self.get_by_uid(uid)
        return row.get('sec_id') == 'read_only'
```

**Aufgaben:**
1. 🔒 Lock/Unlock Methoden in PdvmDatabase
2. 🔒 UI-Warnung bei gesperrten Datensätzen
3. 🔒 Admin-Modus zum Entsperren
4. 🔒 Automatisches Sperren bei Self-Editing-Frames

### Phase 6: Zentrale Services 🔧

**Ziel:** Wiederverwendbare Funktionalität

```python
# frame_service.py (NEU)

class FrameService:
    
    @staticmethod
    async def generate_self_name(table: str, field: str) -> str:
        """Generiert SELF_NAME: [3-Buchstaben]_[feld]"""
        prefix = table[:3].lower() if table else "xxx"
        return f"{prefix}_{field.lower()}"
    
    @staticmethod
    async def validate_frame_structure(frame_daten: dict) -> bool:
        """Validiert ROOT-Struktur"""
        required = ["ROOT_TABLE", "SELF_GUID", "SELF_NAME", "TABS"]
        root = frame_daten.get("ROOT", {})
        return all(field in root for field in required)
    
    @staticmethod
    async def resolve_controls_with_hierarchy(
        fields: dict,
        gcs
    ) -> dict:
        """Resolved Controls MIT parent_guid Hierarchie"""
        # Controls aus sys_control_dict laden
        # parent_guid berücksichtigen
        # Hierarchie aufbauen
        pass
    
    @staticmethod
    async def create_element_list_frame(
        name: str,
        modul_type: str,
        child_controls: List[str],
        gcs
    ) -> UUID:
        """Erstellt Frame für element_list"""
        # Frame in sys_framedaten anlegen
        # IS_ELEMENT = true setzen
        # FIELDS mit child_controls befüllen
        pass

# element_list_service.py (NEU)

class ElementListService:
    
    @staticmethod
    async def add_element(
        element_list_guid: UUID,
        record_daten: dict,
        new_element_data: dict,
        gcs
    ) -> UUID:
        """Fügt neues Element zu element_list hinzu"""
        # Neue GUID generieren
        # Element in record_daten einfügen
        # parent_guid setzen
        pass
    
    @staticmethod
    async def delete_element(
        element_list_guid: UUID,
        element_guid: UUID,
        record_daten: dict,
        gcs
    ) -> None:
        """Löscht Element aus element_list"""
        # Element aus record_daten entfernen
        # Orphaned children warnen
        pass
```

**Aufgaben:**
1. 🔧 `frame_service.py` erstellen
2. 🔧 `element_list_service.py` erstellen
3. 🔧 Integration in dialog_service.py
4. 🔧 Tests schreiben

## ✅ Machbarkeitsanalyse

### Linear umsetzbar? **JA ✅**

Die Phasen bauen aufeinander auf und können einzeln getestet werden:
1. Dictionary erweitern (keine Breaking Changes)
2. Frame-Struktur anpassen (Migration möglich)
3. parent_guid hinzufügen (optional, abwärtskompatibel)
4. element_list implementieren (neue Funktionalität)
5. Self-Editing absichern (isoliert)
6. Services zentralisieren (Refactoring)

### Zentrale Funktionalitäten? **JA ✅**

Alle Operationen können über zentrale Services laufen:
- `FrameService`: Frame-Verwaltung
- `ElementListService`: element_list Operationen
- `PdvmDatabase`: Lock-Mechanismus
- `dialog_service`: Integration

### Mit bestehendem System kompatibel? **JA ✅**

- Bestehende Frames funktionieren weiter
- Neue Felder sind optional
- Migration Schritt für Schritt möglich

## 🚧 Was du vergessen haben könntest

### 1. Versionierung
**Problem:** Alte Frames vs. neue Struktur
**Lösung:** `SCHEMA_VERSION` in ROOT?

### 2. Validation Rules
**Problem:** Welche Kombinationen sind erlaubt?
**Lösung:** Validation-Matrix für modul_type + parent_guid

### 3. Frontend-Komplexität
**Problem:** element_list braucht eigene UI-Komponente
**Lösung:** PdvmElementList-Widget (analog Desktop)

### 4. Daten-Migration
**Problem:** Bestehende Frames müssen konvertiert werden
**Lösung:** Migration-Skript mit Rollback

### 5. Performance
**Problem:** Viele DB-Queries für Hierarchie-Auflösung
**Lösung:** Caching + Batch-Loading

## 🎯 Empfohlene Implementierungs-Reihenfolge

1. ✅ **Control Dictionary erweitern** ✅ ABGESCHLOSSEN (14.02.2026)
   - Schema definiert
   - Migration-Skript implementiert
   - SELF_NAME Generator implementiert
   - Labels ergänzt
   - 22 Controls migriert

2. ✅ **Frame-Struktur standardisieren** ✅ ABGESCHLOSSEN (14.02.2026)
   - ROOT-Validation implementiert
   - 14 Frames migriert
   - SELF_GUID automatisch gesetzt
   - NULL-Handling für generische Frames

3. ✅ **parent_guid Hierarchie** ✅ ABGESCHLOSSEN (14.02.2026)
   - 6 Controls mit parent_guid verknüpft
   - tabs_def als Parent etabliert
   - Hierarchie-Baum validiert
   - Visualisierungs-Tools implementiert

4. ✅ **element_list als Frame (Basis)** ✅ ABGESCHLOSSEN (14.02.2026)
   - element_frame_guid in 2 element_list Controls gesetzt
   - IS_ELEMENT Flag in 2 Frame Templates gesetzt
   - Basis-Services implementiert (load, children, validate)
   - Setup validiert und getestet
   - create/delete Services konzeptuell definiert
   - UI-Integration ausstehend

5. 🔒 **Self-Editing Sicherheit** (1-2 Tage)
   - Lock-Mechanismus
   - Admin-Modus

6. 🔧 **Zentralisierung** (2-3 Tage)
   - Services auslagern
   - Refactoring
   - Dokumentation

**Gesamt:** 10-16 Arbeitstage

## 📝 Fazit

**Dein Vorschlag ist:** ✅ Durchdacht, ✅ Linear umsetzbar, ✅ Zukunftssicher

**Start:** Phase 1 (Control Dictionary) - keine Breaking Changes
**Kritischste Phase:** Phase 4 (element_list) - braucht sorgfältiges Design
**Wichtigste Entscheidung:** Datenstruktur für element_list (Dict vs. Array)

**Empfehlung:** 
1. Mit Phase 1+2 starten (Quick Win)
2. Phase 4 ausführlich designen (Prototype)
3. Frontend parallel konzipieren

---

## 📊 Aktueller Status (14. Februar 2026, 21:30 Uhr)

### ✅ Phase 1: ABGESCHLOSSEN

**Erreicht:**
- 22 Controls erfolgreich auf V2-Schema migriert
- modul_type Verteilung: 19× edit, 2× tabs, 1× view
- Alle SELF_NAMEs eindeutig (Format: `sys_[fieldname]`)
- Alle Controls haben deutsche Labels
- parent_guid-Spalte vorbereitet für Phase 3
- Keine Schema-Kollisionen

**Implementierte Skripte:**
- `backend/migrate_control_dict_v2.py` - Vollständige Migration
- `backend/add_missing_labels.py` - Label-Ergänzung
- `backend/check_control_dict_status.py` - Status-Validierung

**Control Beispiele (migriert):**
```python
# self_name Control:
{
  "name": "self_name",
  "label": "Frame-Name",
  "type": "string",
  "modul_type": "edit",
  "SELF_NAME": "sys_self_name",
  "parent_guid": null
}

# tabs_def Control (element_list):
{
  "name": "tabs_def",
  "label": "Tab-Definitionen",
  "type": "element_list",
  "modul_type": "tabs",
  "SELF_NAME": "sys_tabs_def",
  "parent_guid": null
}

# tab01_head Control (gehört zu tabs_def):
{
  "name": "tab01_head",
  "label": "Tab 1 Überschrift",
  "type": "string",
  "modul_type": "edit",
  "SELF_NAME": "sys_tab_01.head",
  "parent_guid": null  # Wird in Phase 3 gesetzt
}
```

### ✅ Phase 2: ABGESCHLOSSEN

**Erreicht:**
- 14 Frames erfolgreich auf V2-Struktur migriert
- Alle Frames haben standardisierte ROOT-Gruppe
- SELF_GUID automatisch aus Frame-UID befüllt
- SELF_NAME aus name-Feld übernommen
- TABS automatisch gezählt (aus TABS-Gruppe)
- ROOT_TABLE aus EDIT_TYPE-Mapping ermittelt
- NULL als gültiger Wert für generische Frames akzeptiert

**Frame-Verteilung:**
- 4× mit spezifischem ROOT_TABLE (sys_framedaten, sys_login, sys_menudaten)
- 10× generic Frames (ROOT_TABLE = NULL)
  - 2× element_list Templates
  - 2× JSON-Editor Frames
  - 2× Import Frames
  - 2× Test Frames
  - 2× Template/System Frames

**Implementierte Skripte:**
- `backend/analyze_frames.py` - Frame-Struktur Analyse
- `backend/migrate_frames_phase2.py` - Phase 2 Migration
- `backend/check_schemas.py` - Schema-Prüfung
- `backend/check_table_structure.py` - Tabellen-Struktur Prüfung

**Frame Beispiele (migriert):**
```python
# Edit Frame (mit ROOT_TABLE):
{
  "ROOT": {
    "ROOT_TABLE": "sys_framedaten",
    "SELF_GUID": "4413571e-6bf6-4f42-b81a-bc898db4880c",
    "SELF_NAME": "Edit Frame",
    "TABS": 2,
    "EDIT_TYPE": "edit_frame"  # Kompatibilität
  },
  "FIELDS": { ... }
}

# Element-List Template (generic):
{
  "ROOT": {
    "ROOT_TABLE": null,  # Generic frame
    "SELF_GUID": "55555555-0001-4001-8001-000000000001",
    "SELF_NAME": "Element-List FIELDS Template",
    "TABS": 0
  },
  "FIELDS": { ... }
}
```

### ✅ Phase 3: ABGESCHLOSSEN

**Erreicht:**
- 6 Controls erfolgreich mit parent_guid verknüpft
- tabs_def als Parent für Tab-Controls etabliert
- Hierarchie-Baum: 3 element_lists, 6 children, 13 orphans
- Controls mit parent_guid: tab_order, tab_visible, tab01_gruppe, tab01_head, tab02_gruppe, tab02_head

**Hierarchie-Struktur:**
```
tabs_def (a88ee663-745f-4ab8-b8d0-c024d0a0987b)
├─ tab_order
├─ tab_visible
├─ tab01_gruppe
├─ tab01_head
├─ tab02_gruppe
└─ tab02_head
```

**Implementierte Skripte:**
- `backend/analyze_control_hierarchy.py` - Hierarchie-Analyse
- `backend/migrate_parent_guid_phase3.py` - Phase 3 Migration
- `backend/show_hierarchy.py` - Hierarchie-Visualisierung

### ✅ Phase 4: BASIS IMPLEMENTIERT

**Erreicht:**
- 2 element_lists mit element_frame_guid verknüpft (tabs_def, fields)
- 2 Frame-Templates mit IS_ELEMENT=true markiert
- Referenz-Integrität: alle Zuordnungen gültig
- Basis-Services implementiert und getestet

**Zuordnungen:**
```
tabs_def → Element-List TABS Template
  Control: a88ee663-745f-4ab8-b8d0-c024d0a0987b
  Frame:   55555555-0002-4001-8001-000000000002
  
fields → Element-List FIELDS Template
  Control: 9ccb9eb8-ae9f-4308-97b7-a9e78b3d5c78
  Frame:   55555555-0001-4001-8001-000000000001
```

**Implementierte Services (`element_list_service.py`):**
- ✅ `load_element_list_frame()` - Lädt Frame-Template für element_list
- ✅ `get_element_list_children()` - Holt Child-Controls via parent_guid
- ✅ `validate_element_list_setup()` - Validiert Setup nach Phase 4
- ⚠️ `create_element_instance()` - KONZEPT (abhängig vom Datenmodell)
- ⚠️ `delete_element_instance()` - KONZEPT (abhängig vom Datenmodell)

**Implementierte Skripte:**
- `backend/analyze_element_list_frames.py` - Frame-Zuordnungs-Analyse
- `backend/migrate_element_frames_phase4.py` - Phase 4 Migration
- `backend/test_phase4_setup.py` - Setup Validierung

**Offene Punkte:**
- tabs element_list ohne Frame (Verwendung noch unklar)
- create/delete Services benötigen konkrete Datenmodell-Definition
- UI-Integration ausstehend

### 🔒 Phase 5 & 6: OPTIONAL

**Phase 5: Self-Editing Sicherheit**
- Lock-Mechanismus für sys_framedaten
- Admin-Modus zum Entsperren
- Optional: nur bei Bedarf implementieren

**Phase 6: Zentrale Services**
- Refactoring bestehender Services
- Zentralisierung
- Dokumentation
- Optional: schrittweise bei Bedarf

---

**Gesamtfortschritt:** Phase 1-4 (Basis) von 6 abgeschlossen (ca. 66% der Kern-Implementierung)

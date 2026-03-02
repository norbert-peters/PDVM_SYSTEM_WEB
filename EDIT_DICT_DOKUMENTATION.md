# edit_dict - Control Dictionary Editor

## 📋 Überblick

`edit_dict` ist das zentrale Tool zur Verwaltung von Control Definitions im PDVM System. Es ermöglicht das Erstellen und Bearbeiten von Controls mit einem Template-basierten Ansatz.

## 🎯 Konzept

### Template-System

Jedes neue Control wird aus **2 Templates** zusammengesetzt:

1. **Basis-Template** (GUID: `66666666-6666-6666-6666-666666666666`)
   - Enthält ROOT-Struktur (SELF_GUID, SELF_NAME, MODUL_TYPE)
   - Liegt in `sys_control_dict`

2. **Modul-Template** (GUID: `55555555-5555-5555-5555-555555555555`)
   - Enthält MODUL-spezifische Felder in `daten.MODUL[edit|view|tabs]`
   - Liegt in `sys_control_dict`

### Template-Merge-Logik

```python
# 1. Basis laden
basis = load_template('66666666-6666-6666-6666-666666666666')

# 2. Modul laden
modul_template = load_template('55555555-5555-5555-5555-555555555555')
modul_felder = modul_template['daten']['MODUL'][modul_type]  # z.B. 'edit'

# 3. Deep Copy Merge
control = copy.deepcopy(BASIS)
control['CONTROL']['MODUL'] = copy.deepcopy(modul_felder)

# 4. User-Daten überschreiben
control['ROOT']['SELF_NAME'] = table_prefix + field_name
control['CONTROL']['MODUL'].update(field_data)
```

## 🏗️ Architektur

### Backend Services

#### control_template_service.py

```python
class ControlTemplateService:
    async def load_base_template() -> dict
    async def load_modul_template(modul_type: str) -> dict
    async def merge_templates(basis, modul_template, modul_type, field_data) -> dict
    async def create_new_control(user_guid, modul_type, table_name, field_data) -> dict
    async def switch_modul_type(uid, new_modul_type) -> dict
    async def map_fields_on_modul_change(old_data, new_template) -> dict
```

**Wichtige Features:**
- Template loading mit JSON parsing
- Deep copy merge (keine Referenzen!)
- Automatic SELF_NAME generation (table_prefix + name)
- Intelligent field mapping bei MODUL_TYPE Switch

#### REST API (control_dict.py)

```
POST   /api/control/create                  # Neues Control erstellen
PUT    /api/control/{uid}/switch-modul      # MODUL_TYPE wechseln
GET    /api/control/template/{modul_type}   # Template laden
GET    /api/control/{uid}                   # Control laden
PUT    /api/control/{uid}                   # Control aktualisieren
DELETE /api/control/{uid}                   # Soft delete (historisch=1)
GET    /api/control/list                    # Liste mit Filter/Pagination
```

**Request Models:**

```python
class CreateControlRequest(BaseModel):
    modul_type: str  # 'edit', 'view', 'tabs'
    table_name: str
    field_data: dict

class SwitchModulRequest(BaseModel):
    new_modul_type: str

class UpdateControlRequest(BaseModel):
    field_data: dict
```

### Frontend

**edit-dict.html** - Single-Page HTML Anwendung

Features:
- ✅ MODUL-Typ Selektor (edit/view/tabs)
- ✅ Formular für Control-Daten
- ✅ Live-Vorschau (JSON)
- ✅ Automatische SELF_NAME Generierung
- ✅ Error-Handling mit Alerts

## 📐 Control-Typen

### MODUL: edit

Editierbare Felder in Dialogen

**Template-Felder:**
```json
{
  "feld": "",
  "name": "",
  "type": "string",
  "label": "",
  "table": "",
  "gruppe": "",
  "abdatum": 0,
  "configs": {},
  "read_only": false,
  "historical": false,
  "modul_type": "edit",
  "parent_guid": null,
  "source_path": null,
  "display_order": 0,
  "SELF_NAME": ""
}
```

**Verwendung:**
- Text-Felder, Dropdowns, Datums-Picker
- Mit/ohne AB-Datum Tracking
- Read-only für berechnete Felder

### MODUL: view

Spalten in Tabellen/Listen

**Template-Felder:**
```json
{
  "feld": "",
  "name": "",
  "type": "string",
  "label": "",
  "table": "",
  "gruppe": "",
  "show": true,
  "width": 100,
  "sortable": true,
  "searchable": true,
  "abdatum": 0,
  "configs": {},
  "historical": false,
  "modul_type": "view",
  "parent_guid": null,
  "source_path": null,
  "display_order": 0,
  "data_format": "default",
  "css_class": "",
  "tooltip": "",
  "frozen_left": false,
  "frozen_right": false,
  "SELF_NAME": ""
}
```

**Features:**
- Sortierbar, durchsuchbar
- Spaltenbreite konfigurierbar
- Frozen columns (left/right)
- Custom CSS-Klassen

### MODUL: tabs

Element-Lists (z.B. Tabs, Buttons)

**Template-Felder:**
```json
{
  "feld": "",
  "name": "",
  "type": "element_list",
  "label": "",
  "table": "",
  "gruppe": "",
  "element_frame_guid": null,
  "element_fields": [],
  "SELF_NAME": "",
  "display_order": 0
}
```

**Verwendung:**
- Tab-Listen in Dialogen
- Button-Groups
- Dynamic Element-Arrays

## 🔧 MODUL_TYPE Switching

### Konzept

Controls können ihren Typ ändern (z.B. edit → view). Dabei werden:
- **Gemeinsame Felder** beibehalten (name, label, type, table, gruppe, configs, display_order)
- **Typ-spezifische Felder** gelöscht (z.B. read_only bei edit)
- **Neue Felder** hinzugefügt (z.B. show, sortable bei view)

### Implementierung

```python
async def switch_modul_type(uid: str, new_modul_type: str):
    # 1. Control laden
    control = await load_control(uid)
    
    # 2. Neues Template laden
    new_template = await load_modul_template(new_modul_type)
    
    # 3. Gemeinsame Felder extrahieren
    COMMON_FIELDS = ['feld', 'name', 'type', 'label', 'table', 'gruppe', 
                     'configs', 'display_order', 'SELF_NAME']
    common_data = {k: v for k, v in old_data.items() if k in COMMON_FIELDS}
    
    # 4. Template-Defaults hinzufügen
    new_data = copy.deepcopy(new_template)
    new_data.update(common_data)
    
    # 5. DB Update
    await update_control(uid, new_data)
```

### Beispiel

```
VORHER (edit):
{
  "name": "test_field",
  "label": "Test Feld",
  "type": "string",
  "read_only": false,    ← Spezifisch für edit
  "abdatum": 0
}

SWITCH edit → view

NACHHER (view):
{
  "name": "test_field",
  "label": "Test Feld",
  "type": "string",
  "show": true,          ← Neu für view
  "sortable": true,      ← Neu für view
  "searchable": true,    ← Neu für view
  "width": 100
}
```

## 📊 Datenbank-Struktur

### sys_control_dict

```sql
CREATE TABLE sys_control_dict (
    uid UUID PRIMARY KEY,
    user_guid UUID,
    name VARCHAR(255),
    modul_type VARCHAR(50),     -- 'edit', 'view', 'tabs'
    daten JSONB,                -- Template + User-Daten merged
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    historical INTEGER DEFAULT 0
);
```

### Template-Sätze

1. **Basis-Template**
   ```sql
   uid = '66666666-6666-6666-6666-666666666666'
   daten = {
     "ROOT": {"SELF_GUID": "", "SELF_NAME": "", "MODUL_TYPE": ""},
     "CONTROL": {"MODUL": {}}
   }
   ```

2. **Modul-Template**
   ```sql
   uid = '55555555-5555-5555-5555-555555555555'
   daten = {
     "MODUL": {
       "edit": { /* 15 Felder */ },
       "view": { /* 21 Felder */ },
       "tabs": { /* 10 Felder */ }
     }
   }
   ```

## 🎨 Frontend-Workflow

### Control erstellen

1. **MODUL-Typ wählen** (edit/view/tabs)
2. **Felder ausfüllen:**
   - Name (Feldname, z.B. "label")
   - Label (Anzeigename, z.B. "Anzeigelabel")
   - Typ (string, number, date, dropdown, etc.)
   - Tabelle (z.B. "sys_control_dict")
   - Gruppe (Optional, z.B. "ROOT", "FIELDS")
   - Sortierung (display_order)
3. **Vorschau prüfen** (JSON wird live aktualisiert)
4. **Control erstellen** → API POST `/api/control/create`

### Erfolgreiche Erstellung

```
✅ Control erfolgreich erstellt!
UUID: 81cdb9dc-0e6c-481d-8770-bf5873840e9e
Name: sys_test_field
```

## 🔍 Standards & Regeln

### SELF_NAME Generierung

```python
table_prefix = table_name.split('_')[0] + '_'  # z.B. 'sys_'
SELF_NAME = table_prefix + field_name           # z.B. 'sys_label'
```

**Beispiele:**
- `sys_control_dict` + `label` → `sys_label`
- `sys_control_dict` + `type` → `sys_type`
- `pd_person` + `vorname` → `pd_vorname`

### Sprach-Regel

```python
if gruppe == "" or gruppe is None:
    gruppe = GCS.sprache  # z.B. 'DE-DE'
```

**Bedeutung:**
- Leere Gruppe → Wird aus GCS geholt (länderspezifisch)
- Explizite Gruppe → Bleibt unverändert

### configs.element_list

Alle Referenzen (Label, Key, etc.) werden über `configs.element_list` aufgelöst:

```json
{
  "configs": {
    "element_list": {
      "frame_guid": "c22edb00-c930-4a0b-8884-542b6d34e83d",
      "columns": ["label", "key", "feld", "table", "gruppe"]
    }
  }
}
```

**Config Reference Frame:**
- GUID: `c22edb00-c930-4a0b-8884-542b6d34e83d`
- Felder: label, key, feld, table, gruppe
- IS_ELEMENT: 1 (markiert als Element-Frame)

## 🧪 Testing

### Test Suite (test_control_template_service.py)

```bash
python backend/test_control_template_service.py
```

**Tests:**
1. ✅ Template loading (666666... + 555555...)
2. ✅ Modul templates (edit/view/tabs)
3. ✅ Control creation mit field_data merge
4. ✅ MODUL_TYPE switching (edit → view)
5. ✅ Convenience function create_control()

### Manuelle Tests

1. **Backend API:**
   ```
   http://localhost:8000/docs
   ```

2. **Frontend:**
   ```
   frontend/edit-dict.html
   ```

3. **Control erstellen:**
   - MODUL: edit
   - Name: test_field
   - Label: Test Feld
   - Type: string
   - Table: sys_control_dict
   - → Create

## 📈 Nächste Schritte

### Phase 1: Erste echte Controls ✅ READY
- [ ] `sys_label` (edit + view)
- [ ] `sys_type` (edit + view)
- [ ] `sys_name` (edit + view)
- [ ] `sys_table` (edit + view)
- [ ] `sys_gruppe` (edit + view)

### Phase 2: Edit-Dialog erweitern
- [ ] MODUL_TYPE Switch UI
- [ ] configs.element_list UI (Frame-Selektor)
- [ ] Control-Liste mit Filter
- [ ] Inline-Editing

### Phase 3: Old Controls ersetzen
- [ ] "old_*" Controls durch neue ersetzen (22 Controls)
- [ ] Alte Controls löschen
- [ ] Dialoge auf neue Controls migrieren

## 🎓 Lessons Learned

### Was funktioniert

✅ **Template-basierter Ansatz**
- Reduziert Code-Duplikation massiv
- Zentrale Anpassung für alle Controls
- Upgrade-Path durch Template-Update

✅ **MODUL_TYPE Switching**
- Flexible Control-Nutzung
- Gemeinsame Felder bleiben erhalten
- Typ-spezifische Felder automatisch

✅ **Test-driven Development**
- Echte DB-Operationen besser als Mocks
- Validiert komplette Integration

✅ **Standards VOR Implementation**
- User-Feedback: "von vorne beginnen"
- Durchgängig und geradlinig

### Was zu beachten ist

⚠️ **JSON Serialization**
- asyncpg returned manchmal string, manchmal dict
- Immer `isinstance(data, str)` + `json.loads()` prüfen
- DB Insert/Update: `json.dumps()` verwenden

⚠️ **Deep Copy für Merge**
- `copy.deepcopy()` für Template-Merge
- Keine Referenzen zwischen Controls!

⚠️ **SELF_NAME Konsistenz**
- Immer automatisch generieren
- Format: table_prefix + field_name
- Bei Update neu berechnen wenn name/table ändern

## 📚 Referenzen

### Dokumentation
- `GUID_CONVENTIONS.md` - Fiktive GUID-System
- `CONTROL_DICT_STANDARDS.md` - Control Standards
- `EDIT_DICT_KONZEPT.md` - Ursprüngliches Konzept

### Code
- `backend/app/core/control_template_service.py` - Core Service
- `backend/app/api/control_dict.py` - REST API
- `frontend/edit-dict.html` - UI
- `test_control_template_service.py` - Test Suite

---

**Status:** ✅ Backend komplett, Frontend basic ready, bereit für erste echte Controls

**Version:** 1.0.0

**Datum:** 2025-01-15

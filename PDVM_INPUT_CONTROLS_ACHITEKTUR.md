# PDVM Input-Controls V2 - Architektur-Dokumentation

**AUTOR**: Norbert Peters  
**DATUM**: 21.10.2025  
**VERSION**: 2.0 (Neu-Bau)

---

# PDVM Web System – PIC/PdvmInputModal Spezifikation (Ableitung aus `pdvm_input_*`)

**Ziel**: Die bewährte Desktop-Architektur (Control = Rahmen, Type = Logik) wird 1:1 auf das Web übertragen. Das Web benötigt **keine Historie im Start**, sondern eine **stufenweise Einführung**. Der Menü-Editor (`edit_type=menu`) ist der erste Testpunkt.
Zusätzlich wird ein **PdvmInputModal** definiert: ein autonomes Eingabemodul, das seine Controls ausschließlich aus `sys_framedaten` lädt.

## 1) Architektur-Prinzipien (direkt aus Desktop abgeleitet)

### ✅ 1.1 PIC = Rahmen, Type = Logik
**Desktop**: `PdvmInputControlV4` ist nur Rahmen (Label, Hilfe, Historie), Logik ist in `PdvmInputType*`.

**Web (Zielbild)**:
- `PdvmInputControl` = Rahmen (Label, Tooltip, Help-Button, optional History-Icon)
- `PdvmInputType*` = Logik + konkrete Input-UI (string, text, dropdown, true_false, später datetime/viewtable)

### ✅ 1.2 Type-Registry (plug-in Pattern)
**Desktop**: `TYPE_CLASSES = { text, datetime, dropdown, viewtable }`

**Web (Zielbild)**:
```
PIC_TYPE_REGISTRY = {
    string: PdvmInputTypeString,
    text: PdvmInputTypeText,
    dropdown: PdvmInputTypeDropdown,
    true_false: PdvmInputTypeBoolean,
    # später:
    datetime: PdvmInputTypeDatetime,
    viewtable: PdvmInputTypeViewtable,
    guid: PdvmInputTypeGuidLookup
}
```

### ✅ 1.3 Metadaten aus `sys_framedaten`
**Desktop**: Manager lädt Controls-Metadaten aus `sys_framedaten` und baut daraus Controls.

**Web (Zielbild)**:
- Ein **PIC-Renderer** baut Controls aus `sys_framedaten` (Gruppe = `SYS_<TABELLE>`)
- Für `sys_menudaten` → Gruppe `SYS_MENUDATEN`
- Ordnung per `display_order`
- Labels, Tooltips, Type, Help etc. ausschließlich aus Metadaten (kein Hardcoding)

### ✅ 1.4 Controls bleiben autonom – Manager koordiniert
**Desktop**: Manager koordiniert `render/save/refresh`, Controls beschaffen Instanzen selbst.

**Web (Zielbild)**:
- Manager/Renderer erzeugt Controls aus Metadaten
- Controls arbeiten auf **einem Datenobjekt** (z.B. MenüItem-Draft)
- Kommandos: `render`, `save`, `refresh` als Web-Pattern: *hydrate → edit → persist*

---

## 2) PIC/PdvmInputModal Datenmodell (Web)

### 2.1 Metadaten-Quelle (aus `sys_framedaten`)
**Konzept**: Die Controls liegen in `daten["FIELDS"]` der jeweiligen Frame-Definition.

**Achtung**: Das Control-Objekt ist nicht array-basiert, sondern als Map mit GUID-Keys abgelegt.

Minimales Beispiel:
```json
{
    "FIELDS": {
        "7e4ba8d2-85ed-41f4-aec7-b4ddb0b8dc09": {
            "tab": 1,
            "name": "pers_anrede",
            "label": "",
            "tooltip": "",
            "type": "",
            "table": "",
            "gruppe": "",
            "feld": "",
            "display_order": 0,
            "read_only": false,
            "source_path": "root",
            "historical": true,
            "display_ti_ab_short": true,
            "display_ti_val_short": false,
            "abdatum": true,
            "display_ab": "all",
            "display_val": "all",
            "conversion_in": null,
            "conversion_out": null,
            "configs": {
                "dropdown": {
                    "table": "",
                    "key": "",
                    "feld": "",
                    "gruppe": ""
                },
                "help": {
                    "table": "",
                    "key": "",
                    "feld": "",
                    "gruppe": ""
                }
            }
        }
    }
}
```

### 2.2 Pflichtfelder (Web)
| Feld | Bedeutung |
|---|---|
| `table` | Zieltabelle (z.B. `SYS_MENUDATEN`) |
| `gruppe` | logische Gruppe (z.B. `MENU`) |
| `feld` | Feldname/Key im Datenobjekt |
| `label` | UI-Label |
| `display_order` | Sortierung |
| `type` | `string | text | dropdown | true_false` (Fallback = `string`) |

### 2.3 Optionale Konfigurationen
| Feld | Bedeutung |
|---|---|
| `tooltip` | Tooltip an Label/Control |
| `read_only` | ReadOnly |
| `historical` | Historie erlaubt (später) |
| `abdatum` | Historie/Abdatum aktiv (später) |
| `configs.dropdown` | Dropdown-Quelle (z.B. `table/key/feld/gruppe`) |
| `configs.help` | Help-Key/Config für Hilfetext |
| `configs.viewtable` | View-GUID für Viewtable-Selector |

---

## 3) Web-Komponenten (Zielbild)

### 3.1 `PdvmInputControl` (PIC Rahmen)
- Label links
- Input rechts (Type-Widget)
- Help-Icon (immer sichtbar; disabled wenn keine help-config)
- optional History-Icon (später)

### 3.2 `PdvmInputType*`
| Type | UI | Wert | Quelle |
|---|---|---|---|
| `string` | Input | string | local value |
| `text` | Textarea | string | local value |
| `dropdown` | Select | string | `configs.dropdown` |
| `true_false` | Checkbox/Toggle | boolean | local value |
| **später** `datetime` | DateTime Picker | float / ISO | GCS |
| **später** `viewtable` | Lookup-Dialog | guid | View |
| **später** `guid` | Lookup | guid | `/lookups/{table}` |

---

## 4) Menü-Editor: Blind-Tab-UX (Pflicht)

### Problem
Inline-Editor im selben Scroll-Bereich ist unpraktisch (ständiges Scrollen).

### Ziel-UX
- **Tab 1: Struktur** (Tree-Editor)
- **Tab 2: Eigenschaften** (blind / leer bis Auswahl)
- Wechsel zwischen Tabs ohne Scroll-Verlust
- Beim Zurückkommen **bleibt Auswahl erhalten**

### Persistenz
- `selectedItemUid` pro Gruppe in Dialog-UI-State speichern
- Beim Tab-Wechsel `selectedItemUid` wiederherstellen
- Optional: `menu_active_tab` bleibt wie bisher

---

## 4.1 Menü-Editor (edit_type=menu) – aktuelle Implementierung (Stand 01/2026)

### A) FIELDS-Driven Rendering (SYS_MENUDATEN)
- Controls kommen **ausschließlich** aus `sys_framedaten.daten.FIELDS`.
- Unterstützte Typen:
    - `string`, `text`, `dropdown`, `true_false`
    - `menu_command` (Sonder-Block für Handler + Params)
    - `selected_view` (Lookup über `PdvmLookupSelect`, filtert fiktive GUIDs)

### B) Menü-Commands via `sys_systemdaten`
- `MENU_COMMANDS` liefert Katalog (`handler`, `label`, `params`).
- Help-Text via `systemdaten/text` (Key = `menu_command_{param}` möglich).
- Param-Konfiguration via `MENU_CONFIGS` (z. B. `go_select_view`, `go_dropdown`).

Verbindlich (Regression-Fix 06/2026):

- Das Inputcontrol `type=menu_command` bezieht Handler/Parameter aus `sys_systemdaten` mit UID `00000000-0000-0000-0000-000000000000`, Gruppen `MENU_COMMANDS` und `MENU_CONFIGS`.
- Service-Auflösung läuft mit Tabellen-Priorität:
    1. `sys_systemdaten` (kanonisch)
    2. `asy_systemdaten` (Legacy-Fallback)
- Wenn `MENU_COMMANDS` leer ist, darf im Menüeditor keine Param-Aktivierung erfolgen; dies gilt als Daten-/Konfigurationsproblem und nicht als UI-Logikfehler.

### C) Templates (ROOT.is_template)
- Menü ist **entweder** `GRUND+VERTIKAL` **oder** `TEMPLATE`.
- Steuerung über `ROOT.is_template` (true = Template-Menü).
- Menüeditor zeigt bei Template-Menüs nur die Gruppe `TEMPLATE`.
- `template_guid` im MenüItem erzwingt `type=SPACER` (bei Entfernen → `BUTTON`).
- Template-Einfügung: SPACER wird an Laufzeit durch Template‑Items ersetzt (Sortierung via `spacer_sort + template_sort/10`).

### D) Separator-Regel (einfacher Separator)
- Wenn `label` = `SEPERATOR` oder `SEPARATOR` und Item **kein Submenü** ist,
    wird `type=SEPARATOR` gesetzt. Submenü bleibt Submenü.

### E) Icon-Katalog (Lucide)
- Dropdown-Auswahl im Menüeditor (kein eigener IC‑Type).
- Vorschau direkt unter dem Dropdown.
- Menü rendert Icon via `lucide-react` (Fallback auf Text bei unbekanntem Key).

---

## 5) PdvmInputModal (Autonomes Modul)

### 5.1 Verantwortung
- Ist ein **autonomes Eingabemodul** (ähnlich Desktop-Manager)
- Bekommt **frame_guid** und **root_table**
- Lädt Controls **ausschließlich** aus `sys_framedaten.daten.FIELDS`
- Baut pro Control ein `PdvmInputControl` (PIC)

### 5.2 Datenbindung (Pflicht)
- Jedes Control verwaltet seinen Wert **über PdvmCentralDatabase**
- Zugriff über `get_value(GRUPPE, FELD, STICHTAG)`
- Speichern via `set_value(GRUPPE, FELD, value, ABDATUM)`
- Persistenz erst durch `save_all_values()`
- **Mehrere Tabellen-Instanzen** ⇒ für jede Instanz `save_all_values()`

### 5.3 Default Type
- **Basistyp = `string`**
- Wird verwendet, wenn `type` fehlt oder unbekannt ist

---

## 6) Stufenweise Umsetzung (Start = MenüItem-Properties)

### **Stufe 1 – MenüItem Properties (ohne Historie)**
**Ziel**: PIC minimal produktiv, **ohne Historie**.
- Feld-Set: `label`, `tooltip`, `icon`, `enabled`, `visible`
- `command.handler` + `command.params`
- keine Historie/Abdatum
- Controls aus `sys_framedaten` optional (fallback erlaubt)

**UI-Ort**: Menü-Editor via Popover (PdvmInputModal) – separater Content, nicht mitscrolling.

### **Stufe 2 – PIC-Renderer aus `sys_framedaten`**
- Controls 100% aus `sys_framedaten`
- Sortierung via `display_order`
- `help` Konfiguration wird angezeigt (Modal mit Text)

### **Stufe 3 – Dropdown + GUID Lookup stabilisieren**
- Dropdowns via `configs.dropdown`
- GUIDs via `/lookups/{table}` oder `viewtable`

### **Stufe 4 – Historie/Abdatum (optional)**
- History-Icon aktivieren
- Abdatum-Picker und History-Dialog (später)

---

## 7) Konkreter Startpunkt (MenüItems)

**Konfiguration in `sys_framedaten`**:
- Gruppe: `SYS_MENUDATEN`
- Felder: `label`, `tooltip`, `icon`, `enabled`, `visible`, `command.handler`, `command.params.*`

**Hinweis**: Im Menü-Editor sind `sort_order` und `parent_guid` **maschinenverwaltet** und deshalb **read_only**.

---

## 8) Entscheidung

**Vorschlag**: Implementierung in **PdvmInputModal (Popover)** + **PIC-Renderer** aus `sys_framedaten`, beginnend mit MenüItems (ohne Historie). Die PIC-Architektur bleibt dadurch **tab-unabhängig** und kann später auch im Dialog-Modul genutzt werden.

---

## 9) Element-List Linear (ab 2026)

Hinweis (verbindlich):
- Fuer die technische Umsetzung gilt zusaetzlich die Spezifikation
    `docs/specs/PDVM_LINEAR_FRAME_CONTROL_PIPELINE_SPEC_V1.md`.
- Diese definiert den einheitlichen Runtime-Control-Vertrag fuer
    Haupteditor, Element-Modal und Child-Frame-Rendering.

### Verbindliche Quelle
- `type=element_list` und `type=group_list` werden linear aus einem Element-Frame aufgeloest.
- Felddefinitionen kommen aus `sys_framedaten.daten.FIELDS` des referenzierten Frames.
- Der Add-Katalog kommt aus `sys_framedaten.daten.ROOT.ELEMENTS` des referenzierten Frames.

### ROOT.ELEMENTS Format
`ROOT.ELEMENTS` darf als Objekt-Map oder Array geliefert werden.

Objekt-Map Beispiel:
```json
{
    "ROOT": {
        "ELEMENTS": {
            "ELEMENT_A": {
                "label": "Element A",
                "template": {
                    "FIELD": "",
                    "TAB": 1
                }
            },
            "ELEMENT_B": {
                "label": "Element B",
                "template": {
                    "FIELD": "",
                    "TAB": 2
                }
            }
        }
    }
}
```

Array Beispiel:
```json
{
    "ROOT": {
        "ELEMENTS": [
            {
                "uid": "ELEMENT_A",
                "label": "Element A",
                "template": { "FIELD": "", "TAB": 1 }
            },
            {
                "uid": "ELEMENT_B",
                "label": "Element B",
                "template": { "FIELD": "", "TAB": 2 }
            }
        ]
    }
}
```

### Laufzeitregeln
- Beim Hinzufuegen wird zuerst ein Element aus dem Katalog ausgewaehlt.
- Jede definierte Element-UID ist im Zielwert nur einmal erlaubt.
- Bereits genutzte UIDs werden nicht mehr als Add-Option angeboten.
- Ohne `ROOT.ELEMENTS` bleibt der Legacy-Add-Fall aktiv (freie GUID-Erzeugung).

### Migration-Hinweis
- Die fruehere implizite Element-Ableitung ohne klaren Katalog soll nicht mehr als Standard betrachtet werden.
- Fuer stabile, wiederverwendbare Elementlisten muss `ROOT.ELEMENTS` im Element-Frame gepflegt werden.

---

## 🎯 ZIELE

Die V2-Architektur löst die Komplexität der V1-Implementierung auf durch:

1. **Klare Trennung**: Manager (Steuerung) vs. Control (Autonome Komponente)
2. **Command-Pattern**: Lineare Durchläufe mit klaren Kommandos
3. **Matrix-basiert**: Einfache Erweiterung (Order, Tabs, Gruppen)
4. **GCS-Integration**: Direkte Nutzung von Systemwerten (Stichtag, Neues Abdatum)

---

## 🏗️ ARCHITEKTUR-ÜBERSICHT

```
┌─────────────────────────────────────────────────────────┐
│           PdvmInputControlsManagerV2                    │
│                                                         │
│  ┌─────────────────┐      ┌──────────────────────┐   │
│  │ Instanzen-Pool  │      │  Controls-Matrix     │   │
│  │                 │      │  [                   │   │
│  │ persondaten.g1  │◄─────┤    {                 │   │
│  │ finanzdaten.g2  │      │      control: C1,    │   │
│  │ ...             │      │      order: 1,       │   │
│  └─────────────────┘      │      tab: "Haupt",   │   │
│                            │      instance_key    │   │
│                            │    },               │   │
│  ┌─────────────────┐      │    {...}            │   │
│  │ Neues Abdatum   │      │  ]                   │   │
│  │ (Pdvm_DateTime) │      └──────────────────────┘   │
│  │ aus GCS         │                                  │
│  └─────────────────┘      ┌──────────────────────┐   │
│                            │ Kommandos            │   │
│                            │ - render_all()       │   │
│                            │ - save_all()         │   │
│                            │ - refresh_all()      │   │
│                            └──────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

---

## 📦 KOMPONENTEN

### **1. PdvmInputControlV2** (`pdvm_input_control_v2.py`)

**Verantwortlichkeiten**:
- Wert aus DB-Instanz laden (mit GCS-Stichtag)
- Wert anzeigen (mit Abdatum-Tooltip)
- Änderungen tracken (`is_dirty`)
- Wert speichern (mit GCS Neuem Abdatum)
- UI aktualisieren (refresh)

**Wichtige Eigenschaften**:
```python
self.instance_key      # z.B. "PERSONDATEN_guid1"
self.db_instance       # PdvmCentralDatenbank Instanz (vom Manager!)
self.gruppe            # z.B. "PERSDATEN"
self.feld              # z.B. "FAMILIENNAME"
self.label_text        # z.B. "Familienname"
self.order             # Sortierung
self.tab               # Tab-Zugehörigkeit

# AUTONOME ABDATUM-INSTANZ (nur für Anzeige!)
self.abdatum_dt        # Pdvm_DateTime für Tooltip

# DATEN
self.wert              # Aktueller Wert (aus DB)
self.abdatum_wert      # Abdatum des Wertes (Float aus DB)

# ZUSTAND
self.original_value    # Ursprungswert (für is_dirty)
self.current_value     # Aktueller Wert (editiert)
self.is_dirty          # Geändert?
```

**Kommandos**:
```python
control.render()              # Wert laden + UI erstellen
control.save(neues_abdatum)   # Wert speichern (wenn dirty)
control.refresh()             # Wert neu laden + UI aktualisieren
```

**Interne Methoden**:
```python
control._load_value_from_db()  # Lädt mit gcs.st_inst.PdvmDateTime
control._create_ui()           # Erstellt Widgets
control._update_ui()           # Aktualisiert Anzeige
```

---

### **2. PdvmInputControlsManagerV2** (`pdvm_input_controls_manager_v2.py`)

**Verantwortlichkeiten**:
- Instanzen-Pool aufbauen und verwalten
- Controls-Matrix aufbauen
- Kommandos an alle Controls senden
- Neues Abdatum verwalten (aus GCS)
- Widget mit allen Controls erstellen

**Wichtige Eigenschaften**:
```python
self.instances         # Dict: {instance_key: PdvmCentralDatenbank}
self.controls_matrix   # List: [{control, order, tab, instance_key}, ...]
self.neues_abdatum_dt  # Pdvm_DateTime aus GCS
self.abdatum_picker    # PdvmDateTimePicker Widget
```

**Public API**:
```python
manager.get_widget()   # Erstellt Widget mit allen Controls
manager.save_all()     # Speichert alle Controls
manager.refresh_all()  # Refresht alle Controls
```

**Interne Methoden**:
```python
manager._load_framedaten_and_meta()    # Lädt Metadaten
manager._build_instances_pool()        # Baut Instanzen auf
manager._build_controls_matrix()       # Baut Matrix auf
manager._initialize_neues_abdatum()    # Lädt aus GCS
manager._create_ui()                   # Erstellt UI-Struktur
manager._render_all_controls()         # RENDER-Kommando
manager._show_save_confirmation()      # Bestätigung
```

---

## 🔄 ABLAUF-DIAGRAMME

### **INITIALISIERUNG** (bei `get_widget()`)

```
┌─────────────────────────────────────────────┐
│ 1. Framedaten + Metadaten laden            │
│    - Header-Text                            │
│    - Root-Table                             │
│    - Controls-Metadaten (JSON)             │
└─────────────────┬───────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────┐
│ 2. Instanzen-Pool aufbauen                 │
│    - Root-Instanz (historisch)             │
│    - Weitere Instanzen aus Metadaten       │
│    → self.instances = {...}                │
└─────────────────┬───────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────┐
│ 3. Controls-Matrix aufbauen                │
│    FOR meta IN controls_meta:              │
│      - Control erstellen (NICHT rendern!)  │
│      - In Matrix einfügen mit Metadata     │
│    → Matrix nach Order sortieren           │
└─────────────────┬───────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────┐
│ 4. Neues Abdatum initialisieren            │
│    - Pdvm_DateTime Instanz erstellen       │
│    - GCS lesen: EDIT.NEUES_ABDATUM         │
│    - Falls leer: Fallback + sofort speich. │
└─────────────────┬───────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────┐
│ 5. UI erstellen                            │
│    - Header mit Neues Abdatum Picker       │
│    - ScrollArea für Controls               │
│    - Buttons (Speichern, etc.)             │
└─────────────────┬───────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────┐
│ 6. RENDER-Kommando an alle Controls        │
│    FOR item IN controls_matrix:            │
│      control.render()                      │
│        → _load_value_from_db()             │
│        → _create_ui()                      │
│        → _update_ui()                      │
└─────────────────┬───────────────────────────┘
```

---

### **SPEICHERN** (bei `save_all()`)

```
┌─────────────────────────────────────────────┐
│ 1. Neues Abdatum aus GCS holen             │
│    - Picker.save() → UI → Pdvm_DateTime    │
│    - neues_abdatum = dt.PdvmDateTime       │
└─────────────────┬───────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────┐
│ 2. Dirty Controls sammeln                  │
│    dirty = [item for item IF is_dirty]     │
│    → Falls leer: Meldung + return          │
└─────────────────┬───────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────┐
│ 3. Alle dirty Controls durchlaufen         │
│    FOR item IN dirty:                      │
│      control.save(neues_abdatum)           │
│        → IF is_dirty:                      │
│             instance.set_value(            │
│               gruppe, feld, wert,          │
│               neues_abdatum                │
│             )                              │
└─────────────────┬───────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────┐
│ 4. Alle Instanzen committen                │
│    FOR instance IN instances.values():     │
│      instance.save_all_values()            │
└─────────────────┬───────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────┐
│ 5. Neues Abdatum in GCS speichern          │
│    gcs._db.set_value(                      │
│      'EDIT', 'NEUES_ABDATUM',              │
│      neues_abdatum                         │
│    )                                       │
│    gcs._db.save_all_values()               │
└─────────────────┬───────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────┐
│ 6. REFRESH-Kommando (siehe unten)          │
└─────────────────┬───────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────┐
│ 7. Bestätigungsfenster anzeigen            │
│    - Anzahl geänderter Felder              │
│    - Neues Abdatum (formatiert)            │
│    - Liste der Änderungen (max 10)         │
└─────────────────────────────────────────────┘
```

---

### **REFRESH** (bei `refresh_all()`)

```
┌─────────────────────────────────────────────┐
│ 1. Neues Abdatum aus GCS neu laden         │
│    value, _ = gcs._db.get_value(           │
│      'EDIT', 'NEUES_ABDATUM'               │
│    )                                       │
│    dt.PdvmDateTime = value                 │
└─────────────────┬───────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────┐
│ 2. Neues Abdatum Picker aktualisieren      │
│    abdatum_picker.load()                   │
│      → Lädt Wert aus dt Instanz            │
└─────────────────┬───────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────┐
│ 3. Alle Controls durchlaufen               │
│    FOR item IN controls_matrix:            │
│      control.refresh()                     │
│        → _load_value_from_db()             │
│            stichtag = gcs.st_inst.PdvmDT   │
│            wert, abdatum = get_value(...)  │
│            abdatum_dt.PdvmDT = abdatum     │
│        → _update_ui()                      │
│            value_label.setText(wert)       │
│            tooltip = abdatum_dt.FormTS     │
│        → is_dirty = False                  │
└─────────────────┬───────────────────────────┘
```

---

## 🔑 WICHTIGE KONZEPTE

### **1. Abdatum-Konzept**

Es gibt **DREI verschiedene Abdatum-Werte**:

#### **a) GCS Stichtag** (`gcs.st_inst.PdvmDateTime`)
- **Systemwert** (für alle Controls gleich)
- Wird bei `get_value()` verwendet
- "Zeige mir den Wert zu diesem Zeitpunkt"

#### **b) GCS Neues Abdatum** (`gcs._db EDIT.NEUES_ABDATUM`)
- **Systemwert** (für alle Controls gleich)
- Wird bei `set_value()` verwendet
- "Speichere mit diesem Abdatum"

#### **c) Control Abdatum-Instanz** (`control.abdatum_dt`)
- **Pro Control** (für Anzeige!)
- Wird bei jedem `get_value()` aktualisiert
- Enthält das **tatsächliche Abdatum des Wertes aus DB**
- Wird im Tooltip angezeigt

**Beispiel-Ablauf**:
```python
# LADEN:
stichtag = gcs.st_inst.PdvmDateTime  # z.B. 2025213.0 (aktueller Stichtag)
wert, abdatum_wert = instance.get_value(gruppe, feld, stichtag)
# wert = "Müller" (der Wert am Stichtag)
# abdatum_wert = 2025059.0 (wann "Müller" gespeichert wurde)

control.abdatum_dt.PdvmDateTime = abdatum_wert  # Für Tooltip-Anzeige

# SPEICHERN:
neues_abdatum = gcs._db.get_value('EDIT', 'NEUES_ABDATUM')  # z.B. 2025294.0
instance.set_value(gruppe, feld, "Müller-Schmidt", neues_abdatum)
# Speichert "Müller-Schmidt" mit Abdatum 2025294.0
```

---

### **2. Matrix-Struktur**

Die **Controls-Matrix** ist eine Liste von Dictionaries:

```python
self.controls_matrix = [
    {
        'control': <PdvmInputControlV2 Instanz>,
        'order': 1,
        'tab': 'Hauptdaten',
        'instance_key': 'PERSONDATEN_guid1'
    },
    {
        'control': <PdvmInputControlV2 Instanz>,
        'order': 2,
        'tab': 'Hauptdaten',
        'instance_key': 'PERSONDATEN_guid1'
    },
    {
        'control': <PdvmInputControlV2 Instanz>,
        'order': 10,
        'tab': 'Finanzen',
        'instance_key': 'FINANZDATEN_guid2'
    },
    # ...
]
```

**Vorteile**:
- ✅ **Sortierbar**: `sorted(matrix, key=lambda x: x['order'])`
- ✅ **Filterbar**: `[x for x in matrix if x['tab'] == 'Hauptdaten']`
- ✅ **Erweiterbar**: Neue Metadata einfach hinzufügen
- ✅ **Multi-Tab**: Einfaches Rendern in verschiedenen Tabs

**Beispiel Multi-Tab**:
```python
for tab_name in ['Hauptdaten', 'Finanzen', 'Sonstiges']:
    tab_controls = [x for x in matrix if x['tab'] == tab_name]
    tab_widget = create_tab(tab_name)
    
    for item in sorted(tab_controls, key=lambda x: x['order']):
        tab_widget.layout().addWidget(item['control'])
```

---

### **3. Command-Pattern**

**Prinzip**: Manager sendet Kommandos, Controls reagieren autonom.

**Vorteile**:
- ✅ **Lose Kopplung**: Manager kennt nur Interface (render/save/refresh)
- ✅ **Testbar**: Controls können einzeln getestet werden
- ✅ **Erweiterbar**: Neue Kommandos einfach hinzufügen
- ✅ **Linear**: Keine verschachtelten IFs, nur Schleifen

**Beispiel**:
```python
# Manager sendet RENDER-Kommando
for item in self.controls_matrix:
    item['control'].render()  # ← Control entscheidet, was passiert

# Manager sendet SAVE-Kommando
for item in self.controls_matrix:
    item['control'].save(neues_abdatum)  # ← Control prüft is_dirty selbst
```

---

## 🚀 VERWENDUNG

### **Im Dialog integrieren**:

```python
# In pdvm_genereller_dialog.py

# Manager registrieren
self.edit_modules = {
    'input_controls': PdvmInputControlsManagerV2
}

# Bei Datensatz-Auswahl:
def _on_datensatz_ausgewaehlt(self, selected_guid):
    # Manager initialisieren
    manager = PdvmInputControlsManagerV2(
        framedaten_db=self.framedaten_db,
        selected_guid=selected_guid
    )
    
```

---

## ✅ ZUSAMMENFASSUNG

Die V2-Architektur ist **autonom**, **linear**, **erweiterbar** und **GCS-integriert**.
Sie bildet die Grundlage für alle Editoren und wird im Web als PIC-Framework in den Menü-Editor integriert.

---
````

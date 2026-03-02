# edit_dict Implementation - Konzept & Analyse

**Datum:** 14. Februar 2026  
**Zweck:** Temporärer edit_type für sys_control_dict Bearbeitung

## 📊 Struktur-Analyse

### Template 666666... (Standard neuer Satz)
```json
{
  "ROOT": {
    "SELF_GUID": "",
    "SELF_NAME": "",
    "MODUL_TYPE": ""
  },
  "CONTROL": {
    "MODUL": ""
  }
}
```

### Template 555555... (Modul-Templates)
```json
{
  "MODUL": {
    "edit": {
      "tab": 1,
      "feld": "",
      "name": "",
      "type": "string",
      "label": "",
      "table": "",
      "gruppe": "",
      "abdatum": false,
      "configs": {
        "element_list": {
          "frame_guid": {},
          "element_list_parent": ""
        }
      },
      "read_only": false,
      "historical": false,
      "parent_guid": null,
      "source_path": "root",
      "display_order": 0
    },
    "view": { ... },
    "tab": { ... }
  }
}
```

### Aktuelle Controls
- **19 edit Controls** (z.B. label, name, type, etc.)
- **2 tabs Controls** (element_list: TABS)
- **1 view Control** (element_list: FIELDS)

### configs Struktur (Beispiele)
```json
// Element-List Definition (tabs_def)
{
  "element_fields": [
    {"name": "index", "type": "number", "label": "Index"},
    {"name": "HEAD", "type": "text", "label": "Head"},
    {"name": "GRUPPE", "type": "text", "label": "Gruppe"}
  ],
  "element_template": {
    "HEAD": "Tab 1",
    "index": 1,
    "GRUPPE": "ROOT"
  }
}

// Dropdown-Definition (type Control)
{
  "dropdown": {
    "options": [
      {"label": "Text (einzeilig)", "value": "string"},
      {"label": "Auswahlliste", "value": "dropdown"},
      {"label": "Datum", "value": "date"}
    ]
  }
}

// Help + Dropdown Referenz (tab01_gruppe)
{
  "help": {"key": "", "feld": "", "table": "", "gruppe": ""},
  "dropdown": {"key": "", "feld": "", "table": "", "gruppe": ""}
}
```

## 🎯 Anforderungen

### 1. Dialog-Setup
- ✅ **Normaler Dialog** (sys_dialogdaten)
- ✅ **View:** sys_control_dict
- ✅ **Frame:** OHNE FIELDS (nur ROOT-Ebene)

### 2. Anlegen neuer Sätze
- ✅ **Standard-Template:** 666666... wird geladen
- ✅ **MODUL wählbar:** User wählt edit/view/tabs
- ✅ **Template-Loading:** Aus 555555... MODUL[gewählter_typ] laden

### 3. Dynamisches Template-Switching
- 🔧 **MODUL_TYPE ändern** → Neues Template laden
- 🔧 **Daten übernehmen:** Gemeinsame Felder bleiben erhalten
- 🔧 **Daten bereinigen:** Nicht mehr vorhandene Felder löschen

### 4. tooltip_ref System
- ⚠️ **PROBLEM:** tooltip_ref existiert nicht in Controls
- ✅ **AKTUELL:** help_text direkt im Control
- 🔧 **GEWÜNSCHT:** Referenz auf sys_systemdaten unter Sprach-Gruppe (DE-DE)

### 5. element_list als Standard
- ✅ **BEREITS VORHANDEN:** TABS und FIELDS sind element_lists
- ✅ **element_fields:** GUIDs zu Child-Controls
- ⚠️ **FRAGE:** Neue element_list Implementation oder bestehende nutzen?

## 🚨 Identifizierte Schwierigkeiten

### 1. tooltip_ref vs help_text
**Problem:** Zwei konkurrierende Konzepte

**Aktuell:**
```json
{
  "help_text": "Anzeigename für das Feld (z.B. 'Familienname')"
}
```

**Gewünscht:**
```json
{
  "tooltip_ref": {
    "table": "sys_systemdaten",
    "gruppe": "DE-DE",
    "feld": "control_label_tooltip"
  }
}
```

**Empfehlung:** 
- tooltip_ref als **primär** einführen
- help_text als **Fallback** beibehalten
- Migration später: help_text → sys_systemdaten → tooltip_ref

### 2. configs Struktur Inkonsistenz
**Problem:** Unterschiedliche Struktur in Template vs. Controls

**Template (555555...):**
```json
{
  "configs": {
    "element_list": {
      "frame_guid": {},
      "element_list_parent": ""
    }
  }
}
```

**Reale Controls:**
```json
{
  "configs": {
    "element_fields": [...],
    "element_template": {...}
  }
}
```

**Empfehlung:** Template anpassen an reale Struktur

### 3. element_list als Standard
**Problem:** Zwei element_list Systeme

**Phase 4 System:**
- element_list Control hat `element_frame_guid`
- Frame hat `IS_ELEMENT` Flag
- Child-Controls via parent_guid

**Control configs System:**
- `element_fields` Array mit GUIDs
- `element_template` mit Default-Werten

**Empfehlung:** 
- Phase 4 System als **langfristig**
- configs System als **kurzfristig** (für edit_dict)
- Später Migration konfigs → Phase 4 System

### 4. MODUL_TYPE Switching
**Problem:** Daten-Mapping bei Template-Wechsel

**Szenario:**
```
edit Control:    {feld, name, type, label, table, gruppe, display_order, read_only, ...}
↓ Switch zu tabs
tabs Control:    {name, type, label, table, gruppe, display_order, element_fields, ...}
```

**Gemeinsame Felder:** name, type, label, table, gruppe, display_order  
**edit-spezifisch:** feld, read_only, abdatum, historical  
**tabs-spezifisch:** element_fields, element_template

**Empfehlung:**
- **Übernehmen:** Alle gemeinsamen Felder
- **Löschen:** Alte spezifische Felder
- **Hinzufügen:** Neue spezifische Felder mit Defaults aus Template

## 💡 Lösungsvorschlag

### Phase 1: Template-Korrektur
1. ✅ 555555... Template anpassen:
   - configs für edit/view/tabs korrekt definieren
   - tooltip_ref System einbauen

### Phase 2: edit_dict Dialog erstellen
1. ✅ sys_dialogdaten: Neuer Dialog "edit_dict"
2. ✅ sys_dialogdaten.CONTROL: Minimale FIELDS (nur MODUL-Selektor)
3. ✅ View-Referenz: sys_control_dict

### Phase 3: MODUL Template-Loading
1. ✅ Backend: `load_modul_template(modul_type: str) -> dict`
2. ✅ Merge-Funktion: Bestehende Daten + Template
3. ✅ Cleanup-Funktion: Alte Felder löschen

### Phase 4: UI Template-Switching
1. ✅ On MODUL_TYPE change:
   - Hole neues Template aus 555555...
   - Merge mit bestehenden Daten
   - Re-render UI mit neuen Controls

### Phase 5: element_list Integration
1. ⚠️ **ENTSCHEIDUNG ERFORDERLICH:**
   - **Option A:** configs System nutzen (schnell, temporär)
   - **Option B:** Phase 4 System nutzen (korrekt, aufwändig)

## 🤔 Offene Fragen

1. **tooltip_ref Implementation:**
   - Soll ich tooltip_ref sofort einbauen oder schrittweise migrieren?
   - Struktur in sys_systemdaten definieren?

2. **element_list Standard:**
   - configs System (temporär) oder Phase 4 System (final)?
   - Wenn Phase 4: Migration-Strategie?

3. **Template-Struktur:**
   - 555555... Template jetzt korrigieren?
   - Oder mit aktueller Struktur arbeiten?

4. **Dropdown-Daten:**
   - Wo werden Dropdown-Optionen gespeichert?
   - In configs oder separate sys_dropdowndaten?

5. **MODUL-Selektor:**
   - Als normales Dropdown im Dialog?
   - Oder als spezieller Control-Type?

## 📋 Nächste Schritte

**VORSCHLAG:**

1. **Template 555555... korrigieren** (30 Min)
   - configs für edit/view/tabs korrekt
   - tooltip_ref Struktur definieren

2. **Backend Services erstellen** (2-3 Std)
   - load_modul_template()
   - merge_with_template()
   - cleanup_obsolete_fields()

3. **Dialog erstellen** (1 Std)
   - sys_dialogdaten Insert
   - Minimale FIELDS

4. **UI Implementation** (3-4 Std)
   - Template-Loading
   - Dynamic Form Rendering
   - MODUL_TYPE Switching

5. **element_list später** (nach Diskussion)
   - Klarheit über welches System

---

**STATUS:** Konzept bereit | Schwierigkeiten identifiziert | Entscheidungen erforderlich

# PDVM System Web - Control Dictionary Standards

**Datum:** 14. Februar 2026  
**Status:** Aktiv - Neuanlage mit edit_dict ab sofort
**Version:** 2.0

---

## 🎯 Übersicht

Diese Standards gelten ab sofort für **alle neuen Controls** in sys_control_dict. Alte Controls sind mit `old_` Präfix markiert und werden nach erfolgreicher Migration gelöscht.

## 📋 Grundprinzipien

### 1. Tabellenpräfix-Regel
**SELF_NAME und name müssen IMMER Tabellenpräfix enthalten**

```json
{
  "name": "sys_label",           // ✅ RICHTIG
  "SELF_NAME": "sys_label",      // ✅ RICHTIG
  "table": "sys_control_dict"
}
```

```json
{
  "name": "label",               // ❌ FALSCH
  "SELF_NAME": "label",          // ❌ FALSCH
  "table": "sys_control_dict"
}
```

**Regel:** Präfix = Erste 3-4 Buchstaben der Tabelle + "_"
- `sys_control_dict` → `sys_`
- `persondaten` → `per_`
- `finanzdaten` → `fin_`

### 2. Referenzen über configs.element_list
**KEINE fixen Texte in Controls - ALLES über Referenzen**

❌ **VERBOTEN:**
```json
{
  "help_text": "Anzeigename für das Feld",
  "tooltip": "Freitext hier"
}
```

✅ **KORREKT:**
```json
{
  "configs": {
    "element_list": {
      "frame_guid": "c22edb00-c930-4a0b-8884-542b6d34e83d",
      "element_list_parent": "",
      "elements": [
        {
          "label": "Hilfetext",
          "key": "help",
          "feld": "control_label_help",
          "table": "sys_systemdaten",
          "gruppe": ""  // Leer = Sprache (DE-DE)
        },
        {
          "label": "Tooltip",
          "key": "tooltip",
          "feld": "control_label_tooltip",
          "table": "sys_systemdaten",
          "gruppe": ""
        }
      ]
    }
  }
}
```

### 3. Sprach-Regel für Referenzen
**Wenn gruppe leer → Automatisch Sprache aus GCS**

```json
{
  "gruppe": ""  // → Wird zu "DE-DE" (aus GCS)
}
```

```json
{
  "gruppe": "ADMIN"  // → Bleibt "ADMIN"
}
```

**Lookup-Logik:**
1. Wenn `gruppe` leer → `gruppe = GCS.sprache.toUpperCase()` (z.B. "DE-DE")
2. Query: `SELECT daten->feld FROM table WHERE gruppe = gruppe`

## 🏗️ Template-Struktur (555555...)

### Standard-Felder ALLE Modul-Typen
```json
{
  "name": "",           // DB-Feldname (ohne Präfix!)
  "type": "string",     // string, text, number, date, dropdown, etc.
  "label": "",          // UI-Label
  "table": "",          // Zieltabelle
  "gruppe": "",         // DB-Gruppe
  "feld": "",           // DB-Feldname (redundant zu name - historisch)
  "SELF_NAME": "",      // sys_[name] - Auto-generiert
  "modul_type": "",     // edit, view, tabs
  "parent_guid": null,  // Hierarchie
  "display_order": 0,   // Sortierung
  "configs": {
    "element_list": {
      "frame_guid": "c22edb00-c930-4a0b-8884-542b6d34e83d",
      "element_list_parent": "",
      "elements": []
    }
  }
}
```

### Modul-Typ: edit
```json
{
  "modul_type": "edit",
  "read_only": false,
  "abdatum": false,
  "historical": false,
  "source_path": "root"
}
```

**Verwendung:** Editierbare Felder in Edit-Dialogen

### Modul-Typ: view
```json
{
  "modul_type": "view",
  "show": true,
  "sortable": true,
  "searchable": true,
  "filterType": "contains",
  "sortDirection": "asc",
  "sortByOriginal": false,
  "expert_mode": true,
  "expert_order": 99,
  "control_type": "base",
  "default": "",
  "dropdown": null
}
```

**Verwendung:** Spalten in Tabellen/Listen

### Modul-Typ: tabs
```json
{
  "modul_type": "tabs",
  "element_fields": [],
  "element_frame_guid": null,
  "read_only": false
}
```

**Verwendung:** Element-Lists (z.B. Tab-Definitionen)

## 🔧 Config Reference Frame

**GUID:** `c22edb00-c930-4a0b-8884-542b6d34e83d`  
**Tabelle:** sys_framedaten  
**Name:** Config Reference Frame

### Felder
| Feld | Type | Zweck |
|------|------|-------|
| label | string | Display-Label für UI |
| key | string | Referenz-Key (help, tooltip, dropdown) |
| feld | string | Feldname in Zieltabelle |
| table | string | Zieltabelle (sys_systemdaten, etc) |
| gruppe | string | Gruppe (leer = Sprache) |

### Beispiel-Verwendung
```json
{
  "configs": {
    "element_list": {
      "frame_guid": "c22edb00-c930-4a0b-8884-542b6d34e83d",
      "elements": [
        {
          "label": "Hilfetext",
          "key": "help",
          "feld": "sys_label_help",
          "table": "sys_systemdaten",
          "gruppe": ""
        }
      ]
    }
  }
}
```

## 📊 Datenorganisation

### sys_systemdaten Struktur
```sql
-- Sprach-Gruppen
INSERT INTO sys_systemdaten (gruppe, daten) VALUES
  ('DE-DE', '{"sys_label_help": "Anzeigename für das Feld", ...}'),
  ('EN-US', '{"sys_label_help": "Display name for the field", ...}'),
  ('FR-FR', '{"sys_label_help": "Nom d''affichage du champ", ...}');

-- Spezial-Gruppen (unabhängig von Sprache)
INSERT INTO sys_systemdaten (gruppe, daten) VALUES
  ('ADMIN', '{"admin_note": "Internal admin notes", ...}'),
  ('CONFIG', '{"config_values": {...}, ...}');
```

### Dropdown-Daten
**Phase 1 (Aktuell):** Manuell in configs
```json
{
  "configs": {
    "dropdown": {
      "options": [
        {"label": "Text (einzeilig)", "value": "string"},
        {"label": "Auswahlliste", "value": "dropdown"}
      ]
    }
  }
}
```

**Phase 2 (Später):** sys_dropdowndaten Referenz
```json
{
  "configs": {
    "element_list": {
      "elements": [
        {
          "key": "dropdown",
          "table": "sys_dropdowndaten",
          "feld": "control_types",
          "gruppe": "DROPDOWNS"
        }
      ]
    }
  }
}
```

## 🚀 Workflow: Neue Controls anlegen

### 1. Mit edit_dict anlegen
1. Dialog öffnen: edit_dict
2. View: sys_control_dict
3. MODUL wählen: edit / view / tabs
4. Template wird aus 555555... geladen
5. Felder ausfüllen:
   - `name`: Feldname **OHNE** Präfix (z.B. "label")
   - `SELF_NAME`: **MIT** Präfix (z.B. "sys_label")
   - `table`: Zieltabelle
   - `gruppe`: DB-Gruppe
   - `configs.element_list`: Referenzen hinzufügen

### 2. MODUL_TYPE wechseln (während Bearbeitung)
- MODUL_TYPE ändern → Neues Template wird geladen
- **Gemeinsame Felder** bleiben erhalten
- **Spezifische Felder** werden gelöscht/hinzugefügt

**Mapping:**
```
edit → tabs:
  Behalten: name, type, label, table, gruppe, display_order, configs
  Löschen: read_only, abdatum, historical, source_path
  Hinzufügen: element_fields, element_frame_guid
```

### 3. Referenzen in sys_systemdaten anlegen
```json
// In sys_systemdaten, gruppe = "DE-DE"
{
  "sys_label_help": "Anzeigename für das Feld (z.B. 'Familienname')",
  "sys_label_tooltip": "Wird als Label im Frontend angezeigt",
  "sys_type_help": "Datentyp des Feldes",
  "sys_type_tooltip": "Bestimmt UI-Komponente und Validierung"
}
```

## 📐 Validierung

### SELF_NAME Prüfung
```sql
-- Alle Controls OHNE Tabellenpräfix finden
SELECT name, SELF_NAME, table
FROM sys_control_dict
WHERE historisch = 0
  AND name NOT LIKE 'old_%'
  AND NOT (
    name LIKE SUBSTRING(table FROM 1 FOR 3) || '_%'
  );
```

### configs Prüfung
```sql
-- Alle Controls OHNE configs.element_list
SELECT name, daten->'configs' as configs
FROM sys_control_dict
WHERE historisch = 0
  AND name NOT LIKE 'old_%'
  AND NOT (daten->'configs' ? 'element_list');
```

## 🗑️ Alte Controls bereinigen

### Nach erfolgreicher Migration
```sql
-- Alle alten Controls löschen
DELETE FROM sys_control_dict
WHERE name LIKE 'old_%'
  AND historisch = 0;
```

## 🔍 Referenz-Lookup (Backend)

```python
async def resolve_config_reference(
    control: dict,
    ref_key: str,
    gcs: GlobalConfigService
) -> str:
    """
    Löst config Referenz auf
    
    Args:
        control: Control aus sys_control_dict
        ref_key: z.B. "help", "tooltip", "dropdown"
        gcs: Global Config Service (für Sprache)
    
    Returns:
        Aufgelöster Wert aus sys_systemdaten
    """
    configs = control.get('configs', {}).get('element_list', {})
    elements = configs.get('elements', [])
    
    # Finde Element mit key
    ref = next((e for e in elements if e['key'] == ref_key), None)
    if not ref:
        return None
    
    # Gruppe auflösen
    gruppe = ref['gruppe'] or gcs.sprache.upper()
    
    # Query
    result = await db.execute(f"""
        SELECT daten->>'{ref['feld']}' as value
        FROM {ref['table']}
        WHERE gruppe = $1
    """, gruppe)
    
    return result['value']
```

## ⚠️ Wichtige Regeln

1. ✅ **IMMER** Tabellenpräfix in SELF_NAME/name
2. ✅ **NIEMALS** fixen Text in Controls (help_text, tooltip)
3. ✅ **IMMER** configs.element_list für Referenzen
4. ✅ **Sprach-Regel:** gruppe leer = GCS.sprache
5. ✅ **Template 555555...** als Single Source of Truth
6. ✅ **Alte Controls:** Mit old_ markiert, nach Migration löschen

## 📚 Weitere Dokumentation

- [GUID_CONVENTIONS.md](GUID_CONVENTIONS.md) - Fiktive GUIDs System
- [FRAME_ARCHITECTURE_V2.md](FRAME_ARCHITECTURE_V2.md) - Frame-Architektur
- [EDIT_DICT_KONZEPT.md](EDIT_DICT_KONZEPT.md) - edit_dict Implementation

---

**Status:** Standards definiert ✅ | Template aktualisiert ✅ | Bereit für edit_dict Implementation 🚀

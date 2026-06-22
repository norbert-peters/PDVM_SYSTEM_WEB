# PDVM Element-List Frame Beispiel V1

Status: Referenzbeispiel zur direkten Nachbildung
Datum: 2026-06-19

Ziel:

1. Ein element_list-Control bearbeitet `CONFIGS`.
2. Die auswählbaren Elementtypen kommen aus einem Parent-Template-Frame.
3. Jeder Elementtyp verweist optional auf ein eigenes Child-Frame (`ROOT.FRAME_TYPE=element`).
4. Child-Frame-Felder nutzen immer `GRUPPE=ELEMENT`.

---

## 1. GUIDs im Beispiel

1. Parent-Template-Frame: `73cec3ac-95f9-4667-89df-f2a5d3c8e910`
2. Child-Frame help: `73cec3ac-95f9-4667-89df-f2a5d3c8e911`
3. Child-Frame dropdown_source: `73cec3ac-95f9-4667-89df-f2a5d3c8e912`

Hinweis:

1. Die GUIDs sind Beispielwerte und können frei ersetzt werden.

---

## 2. Parent-Template-Frame (Elementdefinitionen)

Tabelle: `sys_framedaten`
UID: `73cec3ac-95f9-4667-89df-f2a5d3c8e910`

```json
{
  "ROOT": {
    "FRAME_TYPE": "element_list",
    "FIELD": "CONFIGS",
    "TABLE": "sys_control_dict",
    "SELF_GUID": "73cec3ac-95f9-4667-89df-f2a5d3c8e910",
    "SELF_NAME": "Elemente fuer CONFIGS"
  },
  "FIELDS": {
    "CONFIGS": {
      "help": {
        "label": "Hilfe",
        "frame": "73cec3ac-95f9-4667-89df-f2a5d3c8e911"
      },
      "dropdown_source": {
        "label": "Dropdown Source",
        "frame": "73cec3ac-95f9-4667-89df-f2a5d3c8e912"
      },
      "tooltips": {
        "label": "Tooltip",
        "no_fields": true
      }
    }
  }
}
```

Regeln:

1. `frame` und `frame_guid` sind gleichwertig.
2. Ohne `frame` nur mit `no_fields=true` gültig.

---

## 3. Child-Frame fuer help

Tabelle: `sys_framedaten`
UID: `73cec3ac-95f9-4667-89df-f2a5d3c8e911`

```json
{
  "ROOT": {
    "FRAME_TYPE": "element",
    "FIELD": "help",
    "TABLE": "sys_control_dict",
    "SELF_GUID": "73cec3ac-95f9-4667-89df-f2a5d3c8e911",
    "SELF_NAME": "Element help"
  },
  "FIELDS": {
    "10000000-0000-0000-0000-000000000001": {
      "gruppe": "ELEMENT",
      "feld": "key",
      "label": "Datensatz UID",
      "type": "string",
      "display_order": 10,
      "required": true,
      "save_path": "key"
    },
    "10000000-0000-0000-0000-000000000002": {
      "gruppe": "ELEMENT",
      "feld": "feld",
      "label": "Feld",
      "type": "string",
      "display_order": 20,
      "save_path": "feld"
    },
    "10000000-0000-0000-0000-000000000003": {
      "gruppe": "ELEMENT",
      "feld": "table",
      "label": "Tabelle",
      "type": "string",
      "display_order": 30,
      "save_path": "table"
    },
    "10000000-0000-0000-0000-000000000004": {
      "gruppe": "ELEMENT",
      "feld": "gruppe",
      "label": "Gruppe",
      "type": "string",
      "display_order": 40,
      "save_path": "gruppe"
    }
  }
}
```

---

## 4. Child-Frame fuer dropdown_source

Tabelle: `sys_framedaten`
UID: `73cec3ac-95f9-4667-89df-f2a5d3c8e912`

```json
{
  "ROOT": {
    "FRAME_TYPE": "element",
    "FIELD": "dropdown_source",
    "TABLE": "sys_control_dict",
    "SELF_GUID": "73cec3ac-95f9-4667-89df-f2a5d3c8e912",
    "SELF_NAME": "Element dropdown_source"
  },
  "FIELDS": {
    "20000000-0000-0000-0000-000000000001": {
      "gruppe": "ELEMENT",
      "feld": "type",
      "label": "Source Type",
      "type": "string",
      "display_order": 10,
      "required": true,
      "save_path": "type"
    },
    "20000000-0000-0000-0000-000000000002": {
      "gruppe": "ELEMENT",
      "feld": "params.limit",
      "label": "Limit",
      "type": "number",
      "display_order": 20,
      "save_path": "params.limit"
    },
    "20000000-0000-0000-0000-000000000003": {
      "gruppe": "ELEMENT",
      "feld": "params.include_inactive",
      "label": "Include Inactive",
      "type": "true_false",
      "display_order": 30,
      "save_path": "params.include_inactive"
    }
  }
}
```

---

## 5. Control-Definition, die den Parent-Frame nutzt

Tabelle: `sys_control_dict`

```json
{
  "CONTROL": {
    "TYPE": "element_list",
    "FIELD": "CONFIGS",
    "TABLE": "sys_control_dict",
    "CONFIGS": {
      "element": {
        "key": "73cec3ac-95f9-4667-89df-f2a5d3c8e910",
        "table": "sys_framedaten"
      }
    }
  }
}
```

---

## 6. Erwartetes Laufzeitverhalten

1. Liste zeigt nur belegte Elemente aus dem Datensatz.
2. Hinzufügen zeigt die Elementtypen aus `FIELDS.CONFIGS` des Parent-Frames.
3. Nach Auswahl eines Typs werden Felder aus dessen Child-Frame angezeigt.
4. Für `tooltips` mit `no_fields=true` darf ohne Child-Frame gespeichert werden.
5. Backend blockiert Save, wenn eine Definition weder `frame` noch `no_fields=true` hat.

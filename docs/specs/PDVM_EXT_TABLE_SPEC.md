# PDVM External Tables (Import) - Spezifikation (V0)

## Ziel
Ein generisches System zum Importieren und Aktualisieren externer Tabellen (z.B. Laendertabellen),
bei dem die Import- und Update-Logik im Datensatz selbst konfiguriert wird.

Der Benutzer arbeitet ueber einen Dialog im edit_type `import_data` und kann:
- eine Datei lokal waehlen,
- Daten vor dem Speichern sichten und einzelne Zeilen entfernen,
- mit konfigurierbaren Regeln in die Datenbank schreiben,
- bestehende Datensaetze aktualisieren.

Die Architekturregeln werden eingehalten:
- Kein direkter SQL-Zugriff in Routern.
- Datenzugriff ueber zentrale Business-Logik.
- Parsing erfolgt immer im Backend.
- Uploads erfolgen immer als Streaming-Upload.

---

## 1. Neue Systemtabellen

### 1.1 sys_ext_table (Systemdatenbank: pdvm_system)
Speichert die Import-Konfiguration und die aktuelle Datenbasis (global, systemweit).

### 1.2 sys_ext_table_man (Mandantendatenbank)
Speichert mandantenspezifische Konfigurationen und/oder gemischte Daten, wenn die
mandantenspezifische Sicht oder Pflege gewuenscht ist.

Hinweis:
- Beide Tabellen folgen dem Standard-JSONB-Schema (uid, daten, name, historisch ...).
- Zugriff nur ueber PdvmCentralDatabase / PdvmDatabase gemaess ARCHITECTURE_RULES.

---

## 2. Datensatz-Struktur (JSONB)

Daten werden in drei Gruppen organisiert:

### 2.1 ROOT
Metadaten und Importparameter.

Beispiel:
```json
{
  "ROOT": {
    "DATASET_KEY": "laender",
    "NAME": "Laendertabelle",
    "BASE_SOURCE": "Laendertabelle1.xlsx",
    "UPDATE_SOURCES": [
      "sds_laenderliste.xlsx#Tabelle1",
      "sds_laenderliste.xlsx#Tabelle2"
    ],
    "EDIT_TYPE": "import_data",
    "MATCH_KEYS": ["ISO2", "ISO3", "LANDNAME"],
    "CONFLICT_POLICY": "field_priority",
    "CONFLICT_RULES": {
      "ISO2": "base",
      "ISO3": "base",
      "LANDNAME": "base",
      "LANDNAME_EN": "update"
    },
    "ALLOW_ROW_DELETE": true,
    "ALLOW_OVERWRITE": true,
    "ALLOW_INSERT_NEW": true,
    "LAST_IMPORT_AT": "2026-02-06T12:00:00Z"
  }
}
```

### 2.2 CONFIG
Spaltendefinitionen und Mapping-Regeln. Header sind format-agnostisch (XLSX, CSV, PDF-Tabellen, etc.).
Die Zuordnung erfolgt ueber Aliase und Normalisierung.

WICHTIG (neues Modell):
- `CONFIG.COLUMNS` verwendet GUIDs als Key.
- Der Anzeigename kommt aus `label` im Element.
- Jede Spalte ist stabil ueber die GUID, Tippfehler im `label` erzeugen keine neue Spalte.

Beispiel:
```json
{
  "CONFIG": {
    "COLUMNS": {
      "b6a9...": {"label": "ISO2", "key": "ISO2", "type": "str", "required": true, "source": "base", "aliases": ["iso_2", "ISO 2", "Iso2"]},
      "c7d1...": {"label": "ISO3", "key": "ISO3", "type": "str", "required": true, "source": "base", "aliases": ["iso_3"]},
      "d8e2...": {"label": "LANDNAME", "key": "LANDNAME", "type": "str", "required": true, "source": "base", "aliases": ["Land", "Country", "Laendername"]},
      "e9f3...": {"label": "LANDNAME_EN", "key": "LANDNAME_EN", "type": "str", "required": false, "source": "update"}
    },
    "NORMALIZE": {
      "LANDNAME": {"trim": true, "upper": false},
      "ISO2": {"trim": true, "upper": true},
      "ISO3": {"trim": true, "upper": true}
    },
    "ROW_UID_MODE": "new_guid",
    "KEY_MERGE_PRIORITY": ["ISO2", "ISO3", "LANDNAME"]
  }
}
```

### 2.3 DATAS
Die eigentlichen Datensaetze, jeweils mit eigener GUID.

Beispiel:
```json
{
  "DATAS": {
    "b6a9...": {"ISO2": "DE", "ISO3": "DEU", "LANDNAME": "Deutschland", "LANDNAME_EN": "Germany"}
  }
}
```

---

## 3. Import- und Update-Logik (fachlicher Ablauf)

1. Datensatz laden aus `sys_ext_table` oder `sys_ext_table_man` (je nach Kontext).
2. ROOT/CONFIG lesen und Importparameter anwenden.
3. Datei-Upload als Streaming-Upload ins Backend (format-agnostisch).
4. Backend parst die Datei (XLSX/CSV/PDF-Tabellen) und erstellt eine Normalform mit Headern.
5. Basisdatei einlesen (z.B. Laendertabelle1.xlsx).
6. Updatequellen einlesen (z.B. sds_laenderliste.xlsx, mehrere Tabellen/Sheets).
5. Mapping/Normalisierung gemaess CONFIG anwenden.
6. Merge gemaess MATCH_KEYS und KEY_MERGE_PRIORITY.
7. Konfliktstrategie aus ROOT.CONFLICT_POLICY anwenden.
8. Ergebnis als Preview an den Benutzer geben.
9. Nach Benutzerbestaetigung in DATAS schreiben.

---

## 4. Konflikt- und Update-Regeln

Die Update-Regeln sind konfigurierbar und werden im Datensatz beschrieben:

- `base_wins`: Basiswerte bleiben, Updatewerte werden nur fuer leere Felder uebernommen.
- `update_wins`: Updatewerte ueberschreiben Basiswerte.
- `insert_new_only`: Nur neue Saetze werden eingefuegt, keine Ueberschreibung.
- `new_record_on_conflict`: Bei Konflikt neuer Datensatz mit neuer GUID und Kennzeichnung.

Zusatzoptionen (optional):
- `CONFLICT_MARKER_FIELD`: Feldname fuer Kennzeichnung bei Konflikt.
- `ALLOW_ROW_DELETE`: Benutzer darf in der Preview einzelne Zeilen entfernen.

Beispiel fuer flexible Feldregeln (ROOT.CONFLICT_RULES):
- Basis-Quellen behalten ISO2/ISO3 immer.
- Update-Quellen duerfen LANDNAME_EN ueberschreiben.

---

## 5. Dialog: edit_type = import_data

### 5.1 Aufruf
Ein Menu-Item ruft den Dialog auf und uebergibt die Tabelle:
- `dialog_guid`: Dialogdefinition
- `dialog_table`: z.B. `sys_ext_table` oder `sys_ext_table_man`

### 5.2 Verhalten
- Tab 1: View auf die effektive Tabelle (normaler View).
- Tab 2: Import-Editor mit Konfiguration + Datei-Upload + Preview.
- Konfiguration erfolgt ueber Inputcontrol `elemente_list`.

### 5.3 Templates
Inputcontrols werden durch Template-UID bereitgestellt:
- Template-UID: `55555555-5555-5555-5555-555555555555`
Der Template-Datensatz muss in der jeweiligen Tabelle existieren (sys_ext_table / sys_ext_table_man).

### 5.5 Inputcontrol `elemente_list`
Zweck: Verwaltung von `CONFIG.COLUMNS` (GUID-Keyed) ueber eine Liste.

Regeln:
- Die Liste zeigt `label` je Element.
- Die Detailansicht erfolgt per Popup (Speichern/Abbrechen).
- Alle Eigenschaften des Elements sind editierbar (Inputcontrols im Popup).
- Tooltips koennen die JSON-Zusammenfassung eines Elements anzeigen.
- Validierung beim Speichern: `key` ist Pflicht und muss eindeutig sein.
- Normalisierung: `label` wird (falls leer) aus `key` gesetzt, `aliases` wird immer als Liste gespeichert.

Template:
- Ein Element-Template liegt unter UID `5555...` vor.
- Neue Elemente werden aus diesem Template erzeugt.

Frame-Definition (Beispiel):
```json
{
  "FIELDS": {
    "elemente_list_01": {
      "label": "Spalten",
      "type": "elemente_list",
      "source_path": "CONFIG.COLUMNS",
      "template_uid": "55555555-5555-5555-5555-555555555555"
    }
  }
}
```

### 5.6 Migration bestehender CONFIG.COLUMNS
Alte Eintraege (key=bisheriger Spaltenname) werden in GUID-Keyed Elemente migriert.
Ein Helper-Script konvertiert bestehende Datensaetze und fuellt `key`/`label` nach:

- Script: `backend/tools/migrate_ext_table_columns_guid.py`
- Ziel-DBs: `system`, `mandant`, `pdvm_standard`
- Ergebnis: `CONFIG.COLUMNS` wird GUID-Keyed, bestehende Daten bleiben erhalten.

### 5.4 Datei-Upload und Preview
- Datei wird lokal vom Endgeraet geladen.
- Upload erfolgt als Streaming-Upload ins Backend.
- Parsing erfolgt im Backend und ist format-agnostisch (XLSX, CSV, PDF-Tabellen, etc.).
- Daten werden geparst und in einem Popup/Preview angezeigt.
- Einzelne Zeilen koennen entfernt werden.
- Erst bei "Speichern" werden die Daten in DATAS geschrieben.

---

## 6. Architekturkonformitaet

Konforme Punkte:
- Kein direkter SQL-Zugriff in Routern.
- Nutzung von PdvmCentralDatabase fuer Systemtabellen.
- Mandantenspezifische Daten in `sys_ext_table_man`.

Offene Punkte / zu klaeren:
- Prioritaeten pro Feld muessen bei jeder Tabelle bewusst gesetzt werden (CONFLICT_RULES).
- Bei sehr grossen Dateien muss die Preview paginiert werden.

---

## 7. Vor- und Nachteile

### Vorteile
- Flexibel: Importregeln liegen im Datensatz selbst.
- Wiederverwendbar fuer verschiedene externe Tabellen.
- Dialog bleibt generisch, nur Parameter aendern sich.
- System- und Mandantenebene sind getrennt.

### Nachteile / Risiken
- JSONB-Struktur kann sehr gross werden (Performance beachten).
- Konfliktregeln muessen klar dokumentiert sein, sonst entstehen Inkonsistenzen.
- Preview und Delete-Logik benoetigen solide Validierung.
- Unterschiedliche Header (XLSX/CSV/PDF) koennen zu Mapping-Fehlern fuehren.

---

## 8. Next Steps (vor Implementierung)

1. Festlegen der kanonischen Header und Aliase (format-agnostisch).
2. Festlegen der Standard-Konfliktstrategie pro Feld (CONFLICT_RULES).
3. Erstellen eines Template-Datensatzes in sys_ext_table (UID 5555...).
4. Migration alter CONFIG.COLUMNS zu GUID-Keyed ausfuehren.
5. Pruefen der Preview-Strategie (Paging) fuer grosse Dateien.

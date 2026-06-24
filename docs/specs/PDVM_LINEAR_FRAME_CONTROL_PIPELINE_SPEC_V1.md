# PDVM Linear Frame-Control Pipeline Spec V1

Status: Draft zur verbindlichen Umsetzung
Datum: 2026-06-22
Scope: frontend/dialog + element-list + input-controls

## Umsetzungsstand (2026-06-22)

Bereits umgesetzt (Frontend):
- Zentrale Runtime-Vertragsfunktion fuer Element-Felder in `PdvmDialogPage` (`resolveElementFieldRuntime`).
- Runtime-Vertrag in eigenes Frontend-Modul ausgelagert: `frontend/src/components/dialogs/elementFieldRuntimeContract.ts`.
- Verbindliche Aufloesungsreihenfolge: `CONTROL_UID` zuerst, inline `CONTROL` als Override/Fallback mit Warnung.
- Qualifizierte Warnung bei `go_select_view` ohne `resolved_configs.go_select_view.table`.
- Einheitliche Warnweitergabe in `help_text`, `resolution_warning` und `control_debug.RESOLUTION_WARNING`.
- Beide Edit-Renderpfade verwenden denselben gemeinsamen Element-Runtime-Builder.
- Vollstaendige Build-Validierung erfolgreich durchgefuehrt (`frontend`: `npm run build` mit `tsc && vite build`).
- `PdvmInputControl` verwendet fuer `go_select_view` primaer `resolvedConfigs.go_select_view.table`; `lookupTable` bleibt nur Legacy-Fallback.

## 1. Zielbild

Das System folgt einem strikt linearen Ablauf mit genau einer Runtime-Quelle pro Feld.

1. Frame laden
2. Runtime-Control normalisieren
3. Wert linear aus SOURCE_PATH lesen
4. Control rendern
5. Wert linear ueber SOURCE_PATH + SAVE_PATH schreiben
6. Globales Dialog-Speichern persistiert den gesamten Datensatz

Es gibt keine parallelen Sonderpipelines pro Renderkontext mehr.

## 2. Kernprinzipien (verbindlich)

1. Single Runtime Model
- Jedes Control wird vor dem Rendering in genau ein Runtime-Control-Objekt ueberfuehrt.
- Dieses Objekt ist die einzige Quelle fuer Type, Config, Source und Writeback.

2. Single Read Path
- Lesen erfolgt ausschliesslich ueber SOURCE_PATH + GRUPPE + FELD.
- FRAME_TYPE beeinflusst den Host-Kontext, nicht den Datenzugriff.

3. Single Write Path
- Schreiben erfolgt ausschliesslich ueber SOURCE_PATH + SAVE_PATH.
- Rueckschreiben laeuft rekursiv bis zur Dialog-Grundstruktur.

4. Config Resolve genau einmal
- Legacy-Strukturen werden am Eingang gemappt.
- Danach nur noch resolved_configs verwenden.

5. Kein Prop-Durchreichen als Fachvertrag
- Renderer bekommen ein Runtime-Control-Objekt, keine lose Sammlung aus Teilwerten.

## 3. Verbindliches Runtime-Control-Objekt

```json
{
  "control_uid": "optional-guid",
  "field_key": "ROOT.CONFIGS.help.key",
  "type": "string|text|dropdown|multi_dropdown|true_false|go_select_view|datetime|date|time|element_list|group_list",
  "label": "...",
  "tooltip": "...",
  "read_only": false,
  "source_path": "root",
  "save_path": "key",
  "gruppe": "ELEMENT",
  "feld": "KEY",
  "resolved_configs": {
    "go_select_view": {
      "table": "sys_dropdowndaten",
      "key": "",
      "feld": "",
      "gruppe": ""
    }
  },
  "lookup_table": "optional_legacy_alias",
  "options": [],
  "validation": {
    "required": false,
    "error": null
  },
  "debug": {
    "resolution_source": "control_uid|inline_control|legacy_mapped"
  }
}
```

Pflicht:
- Bei `go_select_view` muss `resolved_configs.go_select_view.table` gesetzt sein, sonst qualifizierter Fehler.
- `lookup_table` ist optionaler Kompatibilitaetsalias fuer Altpfade und keine fachliche Pflichtquelle.

## 4. Aufloesungsreihenfolge

1. Controlquelle bestimmen (verbindlich)
- zuerst CONTROL_UID aufloesen (sys_control_dict ist Primaerquelle)
- wenn gueltig aufgeloest: inline CONTROL als gezieltes Override darueber mergen
- Uebergangsmodus: wenn keine gueltige CONTROL_UID vorhanden, darf inline CONTROL vollstaendig funktionieren
- bei fehlender/ungueltiger CONTROL_UID muss ein sichtbarer Warnhinweis im Control erscheinen (z. B. rotes !), damit Altbestaende bereinigt werden koennen
- wenn weder gueltige CONTROL_UID noch inline CONTROL vorhanden: qualifizierter Fehler

2. Legacy-Mapping einmalig
- ROOT/CONTROL Wrapper
- gemischte Gross/Kleinschreibung
- alte config keys

3. resolved_configs aufbauen
- dropdown / multi_dropdown / go_select_view / help etc.

4. go_select_view-Tabelle bestimmen
- nur aus resolved_configs.go_select_view.table
- keine zweite ad-hoc Aufloesung im Renderer

## 5. Renderer-Vertrag

Alle Renderkontexte nutzen denselben Renderer-Vertrag:

1. Haupt-Editbereich
2. Element-Modal
3. Child-Frame in element_list

Nicht erlaubt:
- Eigene Sonderlogik pro Kontext fuer denselben Controltyp.
- Zweite Aufloesung von go_select_view.table im Unterrenderer.

## 6. Fehlerregeln (qualifiziert)

1. Missing Control Source
- "Control-Aufloesung fehlt: weder CONTROL noch CONTROL_UID vorhanden."

2. Missing go_select_view.table
- "go_select_view nicht konfiguriert: resolved_configs.go_select_view.table fehlt."

3. Ungueltiger SOURCE_PATH
- "SOURCE_PATH ungueltig: Zielstruktur konnte nicht aufgeloest werden."

4. Ungueltiger SAVE_PATH
- "SAVE_PATH ungueltig: Zielpfad im Element konnte nicht beschrieben werden."

## 7. Rueckschreiblogik

1. Element-Editor schreibt lokal in den Dialog-Draft.
2. Das lokale Writeback nutzt nur source_path + save_path.
3. Uebernehmen ist lokal.
4. Speichern persistiert den Gesamt-Draft in die DB.

modified_at Regel:
- modified_at darf nur beim echten DB-Update geaendert werden.
- Lokale Dialog-Draft-Aenderungen duerfen modified_at nicht beeinflussen.

## 8. Migrationsplan

Phase A: Architektur-Haerte
1. Runtime-Control-Normalizer zentralisieren
2. Duale Aufloesungspfade entfernen
3. go_select_view lookup_table zentral im Normalizer setzen

Phase B: Renderer-Vereinheitlichung
1. Haupteditor und Element-Modal auf denselben Control-Renderer umstellen
2. doppelte Config-Resolver entfernen

Phase C: Guardrails
1. harte Fehler statt stiller Fallbacks
2. Debug-Ausgabe nur als Diagnose, nicht als Fachquelle

Phase D: Bereinigung
1. veraltete control_flat/control_original/control_root entfernen
2. Legacy-Mapping nur am Eingang behalten

## 9. Akzeptanzkriterien

1. Ein Control mit identischer Quelle rendert in jedem Kontext identisch.
2. go_select_view zieht in allen Kontexten dieselbe Auswahl aus derselben Tabelle.
3. Save-Pfad ist immer SOURCE_PATH + SAVE_PATH, ohne Kontext-Ifs.
4. Kein stilles Leerlaufen bei fehlender Config, nur qualifizierter Fehler.
5. Ein globales Speichern persistiert alle lokal uebernommenen Element-Aenderungen.

## 10. Verweis

Diese Spezifikation ist verbindlich zusammen mit:
- ARCHITECTURE_RULES.md (Linearisierungs-Regeln)
- PDVM_INPUT_CONTROLS_ACHITEKTUR.md (PIC-Kontext)

## 11. Konkrete Config-Spezifikation: go_select_view (V1.1)

Ziel:
- Ein einziger Control-Typ `go_select_view` fuer beide Modi.
- Modus A: statische Tabelle (Standardfall in Fachdialogen).
- Modus B: dynamische Tabelle aus Datensatzpfad (Spezialfall, z. B. `CONFIGS`-Zuordnungen).

Linearitaet:
- Kein zweiter Control-Typ notwendig.
- Genau ein Runtime-Control pro Feld.
- Tabellenaufloesung erfolgt einmal zentral im Runtime-Normalizer.
- Renderer bekommt nur den aufgeloesten Endwert `resolved_configs.go_select_view.table_resolved`.

### 11.1 Kanonische Config-Keys (resolved_configs.go_select_view)

Pflichtfelder:
- `table_mode`: `static` | `from_path`

Modus `static`:
- `table`: String, Pflicht

Modus `from_path`:
- `table_path`: String, Pflicht (relativ zu `SOURCE_PATH`)

Optionale Guardrails:
- `allow_empty_key`: Boolean, default `true`
- `validate_key_exists`: Boolean, default `false`
- `strict_table_required`: Boolean, default `true`

Aufgeloeste Runtime-Werte (nur Runtime, nicht persistente Fachconfig):
- `table_resolved`: String oder leer
- `table_resolution_source`: `static` | `from_path`

### 11.2 Normalisierung (Legacy-Input -> Kanonisch)

Bei fehlendem `table_mode` gilt fuer Rueckwaertskompatibilitaet:
1. Wenn `table` gesetzt ist -> `table_mode = static`
2. Wenn `table_path` gesetzt ist -> `table_mode = from_path`
3. Sonst Konfigurationsfehler `missing_table_mode`

Legacy-Alias-Mapping (nur am Eingang):
- `TABLE` -> `table`
- `TABLE_PATH` -> `table_path`
- `lookup_table` (Legacy) -> `table` nur falls `table_mode` nicht gesetzt ist

### 11.3 Aufloesungslogik (verbindlich, linear)

1. Runtime-Control laden
2. `resolved_configs.go_select_view` kanonisch aufbauen
3. `table_mode` auswerten
4. Tabelle aufloesen:
   - `static`: `table_resolved = table`
   - `from_path`: `table_resolved = read(SOURCE_PATH + table_path)`
5. Validierung anwenden (siehe 11.4)
6. Renderer verwendet ausschliesslich `table_resolved`

Kein zusaetzlicher Lookup im Renderer erlaubt.

### 11.4 Validierungsregeln

Regel V1 (`missing_table_mode`):
- Wenn weder `table_mode` noch ableitbarer Legacy-Input vorhanden -> Fehler

Regel V2 (`missing_table_static`):
- `table_mode=static` und `table` leer -> Fehler

Regel V3 (`missing_table_path`):
- `table_mode=from_path` und `table_path` leer -> Fehler

Regel V4 (`missing_table_resolved`):
- `strict_table_required=true` und `table_resolved` leer -> Fehler

Regel V5 (`invalid_key_for_table`):
- `validate_key_exists=true` und `key` ungleich leer, aber nicht in `table_resolved` vorhanden -> Fehler

Regel V6 (`empty_key_not_allowed`):
- `allow_empty_key=false` und `key` leer -> Fehler

### 11.5 Save-/Uebernehmen-Semantik

Fuer `go_select_view` (ein Feld, ein Save-Pfad):
- `table` darf ohne `key` gespeichert werden, wenn `allow_empty_key=true`.
- `key` darf nur gespeichert/uebernommen werden, wenn V5 nicht verletzt ist.
- Bei Fehlern V1-V6 wird Uebernehmen/Speichern im betroffenen Editor blockiert.

### 11.6 Konfigurationsbeispiele

Beispiel A: Statische Tabelle (Standard)

```json
{
  "go_select_view": {
    "table_mode": "static",
    "table": "sys_bankdaten",
    "allow_empty_key": true,
    "validate_key_exists": true,
    "strict_table_required": true
  }
}
```

Beispiel B: Dynamische Tabelle aus Pfad (CONFIGS-Spezialfall)

```json
{
  "go_select_view": {
    "table_mode": "from_path",
    "table_path": "TABLE",
    "allow_empty_key": true,
    "validate_key_exists": true,
    "strict_table_required": true
  }
}
```

Beispiel C: Rueckwaertskompatibel (Legacy, wird normalisiert)

```json
{
  "go_select_view": {
    "TABLE": "sys_dropdowndaten"
  }
}
```

Normalisiert zu:

```json
{
  "go_select_view": {
    "table_mode": "static",
    "table": "sys_dropdowndaten",
    "allow_empty_key": true,
    "validate_key_exists": false,
    "strict_table_required": true
  }
}
```

### 11.7 Abgrenzung

Nicht Bestandteil von V1.1:
- Neuer Control-Typ `go_select_table_view`
- Composite-Writeback in zwei unabhaengige Save-Pfade durch ein Control

Begruendung:
- Wuerde den linearen Ein-Feld-Vertrag unnoetig aufweiten.
- Der Spezialfall wird mit `table_mode=from_path` im bestehenden Typ linear abgedeckt.

## 12. Konkrete Config-Spezifikation: element_list Frame-Quelle (V1.2)

Ziel:
- `element_list` und `group_list` nutzen eine eindeutige, lineare Frame-Quelle.
- Modus A: statisches Element-Frame (heutiger Standardfall).
- Modus B: dynamisches Element-Frame aus Datensatzpfad (z. B. `FRAME_GUID` im aktuellen Datensatz).

Linearitaet:
- Kein neuer Control-Typ.
- Genau ein Runtime-Control pro Feld.
- Frame-Aufloesung erfolgt genau einmal zentral vor Rendering.
- Renderer bekommt nur den aufgeloesten Endwert `resolved_configs.element.frame_guid_resolved`.

### 12.1 Kanonische Config-Keys (resolved_configs.element)

Pflichtfelder:
- `frame_mode`: `static` | `from_path`

Modus `static`:
- `frame_guid`: GUID-String, Pflicht

Modus `from_path`:
- `frame_path`: String, Pflicht (relativ zu `SOURCE_PATH`)

Optionale Guardrails:
- `strict_frame_required`: Boolean, default `true`
- `require_element_definitions`: Boolean, default `true`
- `require_source_path_per_definition`: Boolean, default `true`

Aufgeloeste Runtime-Werte (nur Runtime, nicht persistente Fachconfig):
- `frame_guid_resolved`: GUID-String oder leer
- `frame_resolution_source`: `static` | `from_path`

### 12.2 Normalisierung (Legacy-Input -> Kanonisch)

Bei fehlendem `frame_mode` gilt fuer Rueckwaertskompatibilitaet:
1. Wenn `frame_guid` gesetzt ist -> `frame_mode = static`
2. Wenn `frame_path` gesetzt ist -> `frame_mode = from_path`
3. Wenn `key` gesetzt ist und GUID ist -> `frame_mode = static`, `frame_guid = key`
4. Sonst Konfigurationsfehler `missing_frame_mode`

Legacy-Alias-Mapping (nur am Eingang):
- `KEY`/`key` -> `frame_guid` (nur wenn GUID)
- `FRAME_GUID`/`frame_guid` -> `frame_guid`
- `FRAME_PATH`/`frame_path` -> `frame_path`
- `frame` (GUID) -> `frame_guid`

### 12.3 Aufloesungslogik (verbindlich, linear)

1. Runtime-Control laden
2. `resolved_configs.element` kanonisch aufbauen
3. `frame_mode` auswerten
4. Frame-GUID aufloesen:
   - `static`: `frame_guid_resolved = frame_guid`
   - `from_path`: `frame_guid_resolved = read(SOURCE_PATH + frame_path)`
5. Validierung anwenden (siehe 12.4)
6. Element-Frame genau einmal laden (`/dialogs/frame/{frame_guid_resolved}`)
7. Renderer nutzt ausschliesslich das aufgeloeste Frame

Kein zusaetzlicher Frame-Resolver im Renderer erlaubt.

### 12.4 Validierungsregeln

Regel E1 (`missing_frame_mode`):
- Wenn weder `frame_mode` noch ableitbarer Legacy-Input vorhanden -> Fehler

Regel E2 (`missing_frame_static`):
- `frame_mode=static` und `frame_guid` leer/ungueltig -> Fehler

Regel E3 (`missing_frame_path`):
- `frame_mode=from_path` und `frame_path` leer -> Fehler

Regel E4 (`missing_frame_resolved`):
- `strict_frame_required=true` und `frame_guid_resolved` leer/ungueltig -> Fehler

Regel E5 (`frame_not_found`):
- `frame_guid_resolved` gesetzt, aber Frame kann nicht geladen werden -> Fehler

Regel E6 (`missing_element_definitions`):
- `require_element_definitions=true`, `FRAME_TYPE=element_list`, aber keine gueltigen `ELEMENTS`-Definitionen -> Fehler

Regel E7 (`missing_definition_source_path`):
- `require_source_path_per_definition=true` und Definition ohne `SOURCE_PATH` -> Fehler

### 12.5 Save-/Uebernehmen-Semantik

Fuer `element_list`/`group_list`:
- Uebernehmen/Speichern ist blockiert bei E1-E7.
- Bei gueltiger Frame-Aufloesung bleibt Writeback unveraendert linear ueber `SOURCE_PATH + SAVE_PATH`.

### 12.6 Konfigurationsbeispiele

Beispiel A: Statisches Element-Frame

```json
{
  "element": {
    "frame_mode": "static",
    "frame_guid": "4413571e-6bf6-4f42-b81a-bc898db4880c",
    "strict_frame_required": true,
    "require_element_definitions": true,
    "require_source_path_per_definition": true
  }
}
```

Beispiel B: Dynamisches Element-Frame aus Datensatzpfad

```json
{
  "element": {
    "frame_mode": "from_path",
    "frame_path": "FRAME_GUID",
    "strict_frame_required": true,
    "require_element_definitions": true,
    "require_source_path_per_definition": true
  }
}
```

Beispiel C: Rueckwaertskompatibel (Legacy, wird normalisiert)

```json
{
  "element": {
    "key": "4413571e-6bf6-4f42-b81a-bc898db4880c"
  }
}
```

Normalisiert zu:

```json
{
  "element": {
    "frame_mode": "static",
    "frame_guid": "4413571e-6bf6-4f42-b81a-bc898db4880c",
    "strict_frame_required": true,
    "require_element_definitions": true,
    "require_source_path_per_definition": true
  }
}
```

### 12.7 Abgrenzung

Nicht Bestandteil von V1.2:
- Mehrere konkurrierende Frame-Quellen pro Control
- Kontextabhaengige Sonderauflosung (Haupteditor vs. Element-Modal)

Begruendung:
- Wuerde die Single-Source-of-Truth-Regel brechen.
- Das Ziel wird mit `frame_mode=static|from_path` im bestehenden `element`-Configknoten linear erreicht.

## 13. Konkrete Config-Spezifikation: element_list Add-Auswahl (V1.3)

Ziel:
- Beim Hinzufuegen eines Elements darf die Auswahlquelle nicht aus zufaelligen Runtime-Elementen kommen.
- Die Auswahlquelle wird zentral ueber `CONFIGS` als `go_select_view` definiert.
- Der Add-Flow bleibt linear: eine Quelle, ein Auswahlwert, ein Element-Key.

Linearitaet:
- Kein neuer Control-Typ.
- `element_list` nutzt exakt einen Add-Selector aus `resolved_configs`.
- Aufloesung der Lookup-Tabelle erfolgt mit derselben V1.1-Logik (`table_mode=static|from_path`).

### 13.1 Kanonische Config-Keys

Empfohlen:

```json
{
  "element": {
    "add_select": {
      "go_select_view": {
        "table_mode": "static",
        "table": "sys_control_dict"
      }
    }
  }
}
```

Unterstuetzte Alias-Eingaenge (nur Eingangsnormalisierung):
- `element_add.go_select_view`
- `element.element_add.go_select_view`
- `element.go_select_view` (Legacy)

Optional fuer relative Aufloesung:
- `element.add_select.source_path`

### 13.2 Aufloesungslogik (verbindlich, linear)

1. Add-Selector-Config aus `resolved_configs` lesen.
2. `go_select_view`-Tabelle ueber V1.1 aufloesen (`table_mode=static|from_path`).
3. Benutzer waehlt genau einen UID-Wert aus der konfigurierten Tabelle.
4. Der UID-Wert wird als Element-Key (`__ELEMENT_UID`) verwendet.
5. Modal erlaubt Ueberschreiben beliebiger Properties; Save bleibt linear ueber `SOURCE_PATH + SAVE_PATH`.

### 13.3 Validierungsregeln

Regel A1 (`missing_add_selection`):
- Add mit aktivem Add-Selector ohne ausgewaehlten UID-Wert -> blockieren.

Regel A2 (`duplicate_element_uid`):
- Add-UID bereits vorhanden (bei `FRAME_TYPE=element_list`) -> blockieren.

Regel A3 (`invalid_add_uid_mapping`):
- Bei FIELDS-Editor kann UID nicht auf gueltige Control-UID aufgeloest werden -> blockieren.

### 13.4 Rueckwaertskompatibilitaet

- Ohne Add-Selector-Config bleibt das bisherige Verhalten aktiv:
1. `ELEMENTS`-Definitionen (falls vorhanden) steuern die Add-Auswahl.
2. Sonst freier Add-Flow mit Modal.

### 13.5 Beispiel: FIELDS in sys_framedaten

Ziel: Beim Hinzufuegen eines FIELDS-Eintrags Auswahl aus `sys_control_dict`.

```json
{
  "element": {
    "frame_mode": "from_path",
    "frame_path": "FRAME_GUID",
    "add_select": {
      "go_select_view": {
        "table_mode": "static",
        "table": "sys_control_dict"
      }
    }
  }
}
```

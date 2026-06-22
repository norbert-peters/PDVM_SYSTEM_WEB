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

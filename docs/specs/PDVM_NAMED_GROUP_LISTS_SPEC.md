# PDVM Named Group Lists Spec (V1)

Stand: 2026-02-27  
Status: verbindlich fuer lineare Neuanlage in Dialogen

## 1. Ziel
Ergaenzung zur bestehenden `element_list`-Logik:
- Neben klassischen `ELEMENTS` soll das System mehrere benannte Gruppen auf derselben Ebene einfuegen koennen.
- Beispiel in `sys_framedaten`: `PER_PERSONEN`, `FIN_BASIS` als gleichrangige Gruppen mit eigenen Feldern.

## 2. Entscheidung: eigener Typ statt Ueberladung von element_list
Fuer lineare Verarbeitung wird ein eigener fachlicher Typ verwendet:
- `group_list` (fachlich)

Begruendung:
- `element_list` bleibt fuer Listen von Elementen (z. B. Tabs, Tabellenzeilen).
- `group_list` steht fuer das Einfuegen kompletter Gruppenbloecke auf Top-Level.
- Keine verschachtelte Mehrdeutigkeit, klare lineare Ausfuehrung.

## 3. Datenquelle (Template 555...)
Benannte Gruppenlisten liegen in:
- `sys_control_dict.uid = 55555555-5555-5555-5555-555555555555`
- `daten.ELEMENTS.GROUP_LISTS`

Struktur:
```json
{
  "ELEMENTS": {
    "GROUP_LISTS": {
      "PER_PERSONEN": {
        "GROUP_NAME": "PER_PERSONEN",
        "GROUP_TEMPLATE": {
          "ANZEIGE": true,
          "DISPLAY_ORDER": 10
        },
        "AUTO_APPLY": true,
        "TYPE": "group_list"
      },
      "FIN_BASIS": {
        "GROUP_TEMPLATE": {
          "ANZEIGE": true,
          "DISPLAY_ORDER": 20
        },
        "AUTO_APPLY": false,
        "TYPE": "group_list"
      }
    }
  }
}
```

Hinweise:
- `GROUP_NAME` optional; wenn leer, wird der Key (`PER_PERSONEN`) verwendet.
- `GROUP_TEMPLATE` ist Pflicht und muss Objekt sein.
- `TYPE` ist semantisch (fuer UI/Editor), aktuell optional in der Laufzeit.

## 4. Auswahl der einzufuegenden Gruppen
Steuerung im Zieldatensatz ueber:
- `ROOT.GROUP_LISTS` als Liste von Namen

Beispiel:
```json
{
  "ROOT": {
    "SELF_GUID": "...",
    "SELF_NAME": "...",
    "GROUP_LISTS": ["PER_PERSONEN", "FIN_BASIS"]
  }
}
```

Regel:
1. Wenn `ROOT.GROUP_LISTS` gesetzt ist -> exakt diese Eintraege anwenden.
2. Sonst -> alle Eintraege mit `AUTO_APPLY=true` anwenden.

## 5. Linearer Merge-Ablauf (verbindlich)
Neuanlage aus Dialog-Template:
1. Basis aus `666...` laden.
2. Fuer jede in `666...` vorhandene Gruppe (ausser ROOT/TEMPLATES/ELEMENTS) passende Defaults aus `555...daten.TEMPLATES` anwenden.
3. Benannte Gruppenlisten aus `555...daten.ELEMENTS.GROUP_LISTS` anwenden.
4. Optionaler MODUL-Merge (`MODUL`) anwenden.
5. `ROOT.SELF_GUID` / `ROOT.SELF_NAME` setzen.
6. Template-Metagruppen `TEMPLATES` und `ELEMENTS` aus dem Ergebnis entfernen.

Merge-Prioritaet innerhalb einer Zielgruppe:
- Default = `GROUP_TEMPLATE`
- vorhandene Basiswerte der Zielgruppe ueberschreiben Defaults

Damit gilt: Template liefert Standardwerte, bestehende Basisdefinition bleibt fuehrend.

Identity-Regel:
- `ROOT.SELF_GUID` und `ROOT.SELF_NAME` werden in der Neuanlage final gesetzt.
- Diese beiden Felder duerfen nicht durch `root_patch` ueberschrieben werden.

## 6. Abgrenzung zu element_list
- `element_list`: Listen-Elemente innerhalb einer Gruppe/Feld-Konfiguration.
- `group_list`: Erzeugung gleichrangiger Gruppenbloecke auf Top-Level.

Beide duerfen parallel eingesetzt werden.

## 7. Kompatibilitaet
- Bestehende Dialoge ohne `ELEMENTS.GROUP_LISTS` bleiben unveraendert.
- Bestehende `element_list`-Funktion bleibt unveraendert.

## 8. UI/Validierungs-Contract (Querverweis)
Auch fuer Felder aus `group_list` gilt der zentrale InputControl-Contract unveraendert:
- Frontend rendert generisch aus Control-Metadaten und darf nur UX-Vorpruefung machen.
- Backend ist verbindlich fuer finale Normalisierung/Validierung bei Leave/Commit.
- Commit-Logik nutzt die Klassen `ok`, `hint_*` (nicht blockierend), `error_*` (blockierend).

Verbindliche Details sind in der Edit-Control-Spezifikation definiert:
- `docs/specs/PDVM_EDIT_CONTROL_SPEC.md` (Abschnitt "7. Verbindlicher InputControl-Contract")

## 9. Implementierungsstatus
Backend umgesetzt in:
- `backend/app/core/dialog_service.py`
  - `_resolve_groups_from_templates` (nur Basis-Gruppen + Template-Defaults, Basis-Override)
  - `_resolve_named_group_lists_from_elements` (neuer Schritt fuer benannte Gruppenlisten)
  - `_strip_template_meta_groups` (entfernt TEMPLATES/ELEMENTS aus Instanzen)
  - `_apply_root_identity` (schuetzt SELF_GUID/SELF_NAME vor Patch-Override)
  - Aufruf in `build_dialog_draft_from_template` und `create_dialog_record_from_template`

## 10. PIC Control-Format (linear, flach, verbindlich)

Stand: 2026-03-02

Fuer die Steuerung der `PdvmInputControl` gilt ab sofort ein einheitliches, lineares Control-Objekt:

1. Alle steuernden Attribute liegen auf Root-Ebene (flach, keine mehrfachen Spiegelungen).
2. Basis ist `resolved_control.data.CONTROL`.
3. Es werden standardisiert folgende Zusatzattribute hinzugefuegt:
   - `FIELD_KEY` (z. B. `CTRL.ROOT.TABS`)
   - `GUID_KEY` (aus `resolved_control.data.ROOT.SELF_GUID`)
   - `VALUE` (Wertehuelle)
   - `VALUE_TIME_KEY` (aktiver Zeitschluessel in `VALUE`)

Beispiel:
```json
{
  "NAME": "TABS",
  "TYPE": "number",
  "FIELD": "TABS",
  "LABEL": "Tabs",
  "READ_ONLY": false,
  "FIELD_KEY": "CTRL.ROOT.TABS",
  "GUID_KEY": "b78b41ec-5372-49e3-b34a-8ddb2fc25c98",
  "VALUE": {
    "ORIGINAL": 2
  },
  "VALUE_TIME_KEY": "ORIGINAL"
}
```

### 10.1 Regel fuer VALUE
- `VALUE` ist eine Map (Zeit-/Version-Schluessel -> Wert).
- Minimal muss `VALUE.ORIGINAL` vorhanden sein.
- `VALUE_TIME_KEY` zeigt auf den aktuell aktiven Eintrag in `VALUE`.
- In der aktuellen Web-Implementierung wird standardmaessig `VALUE_TIME_KEY = "ORIGINAL"` verwendet.

### 10.2 Persistenz-Regel
- Das flache PIC-Control ist Laufzeitstruktur fuer Rendering/Steuerung.
- Persistiert wird weiterhin der fachliche Datensatzwert im Dialog-Draft/Record.
- Erweiterte Zeitstapel (mehrere Zeitkeys in `VALUE`) sind zulaessig und koennen spaeter ohne Strukturbruch eingefuehrt werden.

### 10.3 Anzeige-Regel im PdvmInputControl
- Der Control-Dialog (`{}`-Button) zeigt ausschliesslich das flache Control-Objekt.
- Es sind keine zusaetzlichen Wrapper-Schluessel erlaubt (z. B. `label`, `input_type_raw`, `input_type_effective`, `read_only`, `disabled`, `value`, `options`, `control`).
- Wenn solche Werte benoetigt werden, muessen sie als regulaere Attribute im flachen Control-Template definiert werden.
- Der `{}`-Button ist nur im Expert-Mode sichtbar (`EXPERT_MODE=true` im flachen Control).

## 11. Dropdown-Regeln (verbindlich)

Quelle fuer Dropdown-Config:
- Primaer: `control_flat.CONFIGS_ELEMENTS.dropdown`
- Fallback (legacy): `def.configs.dropdown`

Entscheidungstabelle:

1. `key=GUID`, `field=Feld`, `table=Tabelle`, `group=""`
  - Lade aus `table` den Datensatz `key`.
  - Verwende Gruppe = aktuelle Sprache in Grossbuchstaben (z. B. `DE-DE`).
  - Suche in der Gruppe das Dropdown ueber `field` (Name/List-Name oder Item-GUID).

2. `key=GUID`, `field=Feld`, `table=Tabelle`, `group=Gruppe`
  - Wie oben, aber feste Gruppe = `group`.

3. `key=view_guid`, `group=*VIEW`, `table=""`
  - Lade Optionen aus der View (`view_guid`) und uebernehme als Value die `uid`.

4. `key=view_guid`, `group=*VIEW`, `table=Tabelle`
  - Wie 3, aber mit Table-Override fuer die View-Abfrage.

Rückgabeformat fuer UI-Select bleibt linear:
- `[{ value: <uid|key>, label: <name|value> }]`

## 12. Type `multi_dropdown` (verbindlich)

Basis:
- Nutzt dieselbe Datenquelle und dieselben Aufloesungsregeln wie `dropdown` (siehe Abschnitt 11).

Wertvertrag:
- Laufzeitwert ist linear als String-Array: `string[]`.
- Im flachen Control liegt der aktive Wert unter `VALUE[VALUE_TIME_KEY]`.
- Der gespeicherte Fachwert im Datensatz ist ebenfalls `string[]`.

Kompatibilitaet (Legacy-Werte):
- Wenn ein Altwert als String vorliegt (Trenner `,` `;` `|`), wird er fuer die UI in `string[]` normalisiert.
- Beim Speichern wird immer das lineare Array-Format verwendet.

## 13. Type `true_false` (verbindlich)

Wertvertrag:
- Laufzeitwert ist linear als Boolean: `true | false`.
- Im flachen Control liegt der aktive Wert unter `VALUE[VALUE_TIME_KEY]`.
- Der gespeicherte Fachwert im Datensatz ist Boolean.

Kompatibilitaet (Legacy-Werte):
- Altwerte werden fuer die UI robust normalisiert, z. B. `"true"`, `"1"`, `"ja"`, `1` -> `true`.
- Entsprechend werden `"false"`, `"0"`, `"nein"`, `0`, `null`, `""` als `false` behandelt.
- Bei Benutzeränderung schreibt das InputControl immer ein echtes Boolean (`checked`).

## 14. Type `text` (verbindlich)

Wertvertrag:
- Laufzeitwert ist linear als String.
- Im flachen Control liegt der aktive Wert unter `VALUE[VALUE_TIME_KEY]`.
- Der gespeicherte Fachwert im Datensatz ist String.

Normalisierung:
- `null` und `undefined` werden in der UI als leerer String dargestellt.
- Andere Altwerte (z. B. Number/Boolean) werden fuer die Anzeige in String konvertiert.
- Bei Benutzeränderung schreibt das InputControl den Textwert als String zurueck.

## 15. Type `string` (verbindlich)

Wertvertrag:
- Laufzeitwert ist linear als String.
- Im flachen Control liegt der aktive Wert unter `VALUE[VALUE_TIME_KEY]`.
- Der gespeicherte Fachwert im Datensatz ist String.

Normalisierung:
- `null` und `undefined` werden in der UI als leerer String dargestellt.
- Andere Altwerte werden fuer die Anzeige in String konvertiert.
- Bei Benutzeränderung schreibt das InputControl den Eingabewert als String zurueck.

## 16. Type `number` (verbindlich)

Wertvertrag:
- Laufzeitwert ist linear als Number-String (Ziffernfolge) im InputControl.
- Im flachen Control liegt der aktive Wert unter `VALUE[VALUE_TIME_KEY]`.
- Der gespeicherte Fachwert im Datensatz ist aktuell als Number-String kompatibel.

Normalisierung:
- Erlaubt sind nur Ziffern `1-9` (aktueller UI-Standard).
- `0`, Minuszeichen, Dezimaltrenner und sonstige Zeichen werden entfernt.
- `null` und `undefined` werden als leerer String dargestellt.
- Bei Benutzeränderung schreibt das InputControl den bereinigten Number-String zurueck.

## 17. Type `element_list` (verbindlich)

Wertvertrag:
- Laufzeitwert ist linear als Map: `Record<string, object>`.
- Im flachen Control liegt der aktive Wert unter `VALUE[VALUE_TIME_KEY]`.
- Der gespeicherte Fachwert im Datensatz ist die gleiche Map-Struktur.

Normalisierung:
- Wenn bereits Objekt-Map vorhanden ist, wird sie direkt verwendet.
- Legacy-Array wird in eine Map mit laufenden String-Keys (`"1"`, `"2"`, ...) umgewandelt.
- Legacy-JSON-String (Objekt) wird geparst und als Map verwendet.
- Sonstige/ungültige Werte werden als leere Map behandelt.
- Im `edit_control`-Fallback gilt: Objekt-Maps ohne explizites `TYPE` werden als `element_list` interpretiert (z. B. `TAB_ELEMENTS` mit `TAB_01`, `TAB_02`, ...).

Frame-Regel fuer `pdvm_edit`:
- Für ein Feld `<FELD>` vom Typ `element_list` wird optional `<FELD>_GUID` in derselben Gruppe gelesen.
- Ist `<FELD>_GUID` eine gültige GUID, wird dieses Frame aus `sys_framedaten` geladen und als Element-Editorstruktur verwendet.
- Ist keine gültige GUID vorhanden oder Frame nicht auffindbar, greift der `edit_control`-Fallback (auto-infer aus Elementobjekt).

Darstellung:
- InputControl zeigt Anzahl der Einträge (`Einträge: N`).
- Bei leerer Liste wird ein klarer Empty-State angezeigt.

Lineare Render-/Save-Regel:
- Element-Editor rendert Controls wie im normalen Edit als Matrix von `PdvmInputControl`.
- Reihenfolge kommt aus `display_order` der Frame-Controls.
- Zielpfad im Elementobjekt wird je Control ausschließlich über `SAVE_PATH` festgelegt.
- Fehlt `SAVE_PATH`, gilt Fallback auf den Control-Namen/Feldnamen.

Einheitliche Pipeline-Quelle (verbindlich):
- `edit_control`: Quelle sind die Gruppen/Felder des gelesenen Datensatzes; jede Gruppe wird als eigener Tab projiziert.
- `pdvm_edit`: Quelle sind die im Frame definierten Felder aus allen Gruppen außer `ROOT`.

Einheitliche Control-Vererbung (verbindlich):
- Basis: Control-Template aus `sys_control_dict` (`55555555-5555-5555-5555-555555555555`).
- Danach: spezifisches Feld-Control aus `sys_control_dict` (nach `TABLE/GRUPPE/FELD`).
- Danach: Frame-Definition (z. B. Tab/Order/Anzeige-Metadaten).
- Ergebnis ist ein lineares `control_flat`, das für Rendern und Debug (`{}`) verwendet wird.

## 18. Type `group_list` (verbindlich)

Wertvertrag:
- Entspricht in der Runtime-Darstellung dem Type `element_list` (gleiche lineare Map-Struktur).
- Fachlich bleibt die Bedeutung unterschiedlich (Top-Level Gruppenblock statt Elementliste), technisch identischer Editor-Vertrag.

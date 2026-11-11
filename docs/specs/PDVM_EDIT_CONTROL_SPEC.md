# PDVM EDIT_CONTROL Spec (V1)

Stand: 2026-03-01  
Status: implementiert

## 1. Ziel

`EDIT_TYPE = edit_control` erlaubt die direkte Bearbeitung der Properties eines Datensatzes, ohne dass beim Start von "Neuer Satz" bereits eine vollständige Template-Auflösung erzwungen wird.

Neu (vereinheitlicht):
- `pdvm_edit`, `edit_user` und `edit_control` nutzen denselben technischen Ablauf ab der Control-Matrix.
- Unterschiedlich ist nur der Aufbau bis zur Matrix (Control-Quelle).
- Ab Matrix sind Darstellung, Typprüfung, Konvertierung und Speichern identisch.

## 1.1 Gemeinsames Zielbild fuer `pdvm_edit` + `edit_user` + `edit_control`

Jede editierbare Eigenschaft wird als Control-Matrix-Eintrag behandelt.

- Matrix-Key: GUID des Feldes/der Eigenschaft (feld_guid).
- Matrix-Wert: effektive Control-Definition (Template + Dict + Override).
- Matrix-Metadaten: `gruppe`, `tab`, `display_order`, `type`, `configs`, `read_only`.

Damit gilt:
- Ein gemeinsamer Renderer (`PdvmInputControl`) fuer beide Edit-Typen.
- Eine gemeinsame Save-Logik (gleicher Draft/Commit- und Update-Flow).
- Keine editor-spezifische Sondervalidierung pro Typ.

## 1.2 Quelle bis zur Matrix (einziger Unterschied)

### A) `pdvm_edit`
- Control-Quelle: `sys_framedaten` des `frame_guid` (Gruppe `FIELDS`).
- Es werden nur Controls angeboten, die im Frame definiert sind.
- Effektive Werte je Control: `dict.Template -> dict -> framedaten`.

### B) `edit_control`
- Control-Quelle: aktueller Datensatz selbst (alle Gruppen/Felder im Datensatz).
- Jede Datensatz-Gruppe wird automatisch zu einem eigenen Tab.
- Felder werden innerhalb ihrer Gruppe in die Matrix aufgenommen.
- Effektive Control-Werte: `dict.Template -> dict`.

## 1.3 Gemeinsamer Pipeline-Contract (verbindlich)

1. **Source-Aufbau**
  - `pdvm_edit`: aus `frame.daten.FIELDS`
  - `edit_control`: aus Datensatz-Gruppen
2. **Matrix-Normalisierung**
  - einheitliches `PicDef`-/Control-Modell
3. **Render**
  - einheitlich ueber `PdvmInputControl`
4. **Validation/Conversion**
  - einheitlich ueber zentrale Typzuordnung (`normalizePicType`) + Backend-Validierung
5. **Save**
  - einheitlich ueber `dialogsAPI.updateRecord` bzw. Draft-Commit

Wichtig:
- Der `edit_type` entscheidet nur die Source-Strategie (Schritt 1).
- Schritte 2 bis 5 sind fuer beide Edit-Typen identisch.

## 2. Neuer-Satz-Verhalten

Für `edit_control` (und `sys_control_dict`) gilt im Draft/Create-Flow:
- Neuer Satz folgt dem generischen linearen Standard-Flow.
- Basis ist 666..., Gruppen werden über 555...`TEMPLATES` aufgelöst (z. B. `CONTROL` aus `TEMPLATE.CONTROL`).
- Es gibt keinen separaten `edit_control`-Sonderpfad für die Neuanlage.
- Kanonischer Ablauf: `draft/start` → Draft-Edit → `draft/commit`.

## 3. Edit-Modell

Im Edit-Tab ist die Property-Liste des Datensatzes die Feldliste:
- Top-Level Properties werden direkt als Eingabefelder angeboten.
- Bool-Werte werden als `true_false` gerendert.
- Objekt-/Listenwerte werden als Sammlung erwartet (`element_list` oder `group_list`).

Neu:
- Für jede Top-Level-Gruppe wird ein eigener Tab gebildet.
- Die Gruppe `ROOT` wird explizit mit angezeigt und ist editierbar.
- Felder werden innerhalb ihres Gruppen-Tabs bearbeitet (`gruppe=<Gruppenname>`, `feld=<Fieldname>`).

Wenn für Objekt-/Listenwerte keine Typisierung vorhanden ist:
- Das Backend erzeugt Hinweise (`hint_missing_collection_type`, `hint_nested_collection_depth`).
- Hinweise sind **nicht blockierend**.
- Commit bleibt möglich, aber der Benutzer sieht den Hinweis zur Strukturkorrektur.

## 4. Collection-Regel

Gesammelte Werte sollen genau eine Ebene tiefer modelliert sein und über
`TYPE = element_list` oder `TYPE = group_list` erkennbar sein.

Fehlt diese Typisierung, wird ein Hinweis ausgegeben.

## 5. Implementierung

Backend:
- `backend/app/api/dialogs.py`
  - `edit_control` als erlaubter `edit_type`
  - hint-Codes sind im Commit nicht blockierend
- `backend/app/core/dialog_service.py`
  - `validate_dialog_daten_generic(..., edit_type=...)`
  - edit_control-Hinweislogik für fehlende Collection-Typisierung
  - einheitlicher 6er/5er-Gruppenmerge im Draft/Create-Builder

Frontend:
- `frontend/src/components/dialogs/PdvmDialogPage.tsx`
  - `edit_control` als Field-Editor-Modus
  - Property-basierte dynamische Feldliste aus dem Datensatz
  - Collection-Typen `element_list`/`group_list` berücksichtigt
- `frontend/src/components/common/PdvmInputControl.tsx`
  - `group_list` als unterstützter Input-Typ

## 6. Eingabevalidierung über PdvmInputControl

Regel (Stufe 1):
- Wenn ein Control als `type=number` gerendert wird, akzeptiert `PdvmInputControl` nur die Ziffern `1-9`.
- Ungültige Eingaben erzeugen die Meldung: `Es sind nur die Ziffern 1-9 möglich`.

Wichtig:
- Die Regel wirkt global überall dort, wo ein Editor `PdvmInputControl` **mit** `type='number'` aufruft.
- Daher muss pro Editor das Type-Mapping auf `number` vorhanden sein.

Aktuell angebunden:
- `PdvmDialogPage` (`edit_control`, `edit_frame`, `pdvm_edit` Pfade über `normalizePicType`)
- `PdvmMenuEditor` (`normalizePicType`)

Hinweis:
- `PdvmImportDataEditor` verwendet `PdvmInputControl`, aber derzeit eigenes Typ-Inferencing aus Rohwerten (nicht control-basiert).

## 7. Verbindlicher InputControl-Contract (Frontend/Backend)

Ziel:
- Einmal definierte Control-Regeln gelten identisch fuer alle Edit-Pfade (`edit_control`, `edit_frame`, `pdvm_edit`, weitere).
- Der `edit_type` aendert nur den Kontext, nicht die Grundlogik eines Feldes.

### 7.1 Single Source of Truth
- Fachliche Felddefinition kommt aus `sys_control_dict` (Control-GUID als stabile Identitaet).
- Frontend rendert strikt aus Control-Metadaten (Typ, Label, Optionen, Basis-Hinweise).
- Backend bleibt verbindliche Instanz fuer Normalisierung, Formatregeln und finale Validierung.

### 7.2 Frontend-Pflichten (UX-Validierung)
- Zeichen-Zulaessigkeit darf direkt im `PdvmInputControl` vorgeprueft werden (z. B. Regex).
- Diese Pruefung ist nur Vorfilter fuer bessere UX, nicht fachlich abschliessend.
- Alle Editoren muessen denselben Typ-Mapper verwenden: Control-Typ -> `PdvmInputControl.type`.
- Fuer `type=number` gilt aktuell global im Control: nur `1-9`, Fehlermeldung wie in Abschnitt 6.

### 7.3 Backend-Pflichten (verbindliche Validierung)
- Verbindliche Pruefung erfolgt bei `blur/leave`, `save/commit` oder gleichwertiger Aktivitaet.
- Backend validiert unabhaengig davon, ob Frontend bereits vorgeprueft hat.
- Backend liefert standardisierte Rueckgaben (ok/hint/error + Code + Message + Feldbezug).

### 7.4 Ergebnis-Klassen
- `ok`: Feld ist gueltig.
- `hint_*`: Hinweis, nicht blockierend (Commit erlaubt).
- `error_*`: Fachlicher Fehler, blockierend (Commit gesperrt bis Korrektur).

### 7.5 GUID- und Instanz-Regel
- Primarschluessel fuer Felddefinition ist die Control-GUID aus dem Dict.
- Bei wiederholten Kontexten (Listen/mehrfache Vorkommen) wird zusaetzlich ein Instanzbezug verwendet
  (z. B. `record_guid + group + feld + path`), damit Fehlerzustand pro Vorkommen eindeutig ist.

### 7.6 Kompatibilitaets-Regel
- Neue Editoren sind nur freigegeben, wenn sie den zentralen Mapper und `PdvmInputControl` nutzen.
- Sonderlogik pro Editor ist nur zulaessig fuer Darstellung, nicht fuer abweichende Fachvalidierung.

### 7.7 Kein Edit-Type-Fallback fuer Control-Metadaten
- `edit_user` und `pdvm_edit` muessen dieselbe Control-Resolution (`sys_control_dict` + Template) verwenden.
- Es sind keine edit_type-spezifischen Ersatz-Payloads fuer Control-Debug/Expert-Mode erlaubt.
- Fehlt eine Control-Aufloesung, darf kein separater Fallback-Pfad mit abweichender Expert-Mode-Logik greifen.

### 7.8 Type-Fallback-Regel (verbindlich)
- Wenn ein Control-Type fehlt, leer ist oder unbekannt ist, gilt im Frontend immer der Fallback auf `string`.
- Diese Regel ist global und wird direkt im `PdvmInputControl` durchgesetzt (nicht nur im jeweiligen Editor).
- Es gibt keine Ausschlusslogik fuer unbekannte Types; das Feld bleibt editierbar als Textfeld.

### 7.9 Markierbare Anzeigefelder (`selectable`)
- `readOnly` rendert das Feld `disabled` (nicht markierbar). Mit der Opt-in-Eigenschaft `selectable` (nur zusammen mit `readOnly`) wird stattdessen das HTML-Attribut `readonly` gesetzt: Text bleibt markier- und kopierbar (CSS: `.pdvm-pic__input[readonly]`, `.pdvm-pic__textarea[readonly]`).
- Verwendung: Info-Fenster der Dialoge (`PdvmDialogInfoModal`, siehe `PDVM_DIALOG_SPEC.md` Abschnitt 7a).

## 8. Theme-Typen (P3, Design-System)

`PdvmInputControl` kennt zusaetzlich fuenf Typen fuer das Theming-System (Details: `docs/specs/THEMING_SYSTEM.md`, Abschnitt 5.10). Sie werden im Typ-Mapper (`normalizeInputType`, `normalizePicType` in `PdvmDialogPage`) durchgereicht und fallen nicht auf `string` zurueck:

| Typ | Wert | Darstellung |
| :--- | :--- | :--- |
| `color` | CSS-Farbe (`#hex`, `rgb()`, `hsl()`, `var(--...)`, `transparent`) oder leer | Farbfeld + Textfeld, Kontrast-Badge und Button „Vorschlag übernehmen“ (nächste konforme Farbe) |
| `css_length` | 1-4 Laengen (`8px`, `0.5rem`, `4px 8px`) oder leer | Textfeld mit Pruefung |
| `css_border` | `<n>px <solid\|dashed\|dotted\|double> <Farbe>` oder `none` oder leer | Breite + Stil + Farbe |
| `font_family` | Schriftfamilie (Komma-Liste) oder leer | Auswahl + eigene Eingabe |
| `theme_preview` | `{gruppe: {token: wert}}` (nur Anzeige) | Live-Vorschau, Variablen nur im Container |

Regeln:
- Leerer Wert bedeutet "nicht ueberschrieben" (Overlay-Prinzip); die Controls rufen `onChange('')`.
- Gueltige Werte (und leer) gehen sofort an `onChange`, ungueltige zeigen eine Meldung und aendern den Wert nicht. Die Serverpruefung (`theme_service.validate_token_value`) bleibt massgeblich (7.1/7.3).
- Konfiguration ueber `resolved_configs.theme_token`: `contrast_against` = `{ value | var, min, label }` (Gegenfarbe als Wert oder CSS-Variable), `mode` = `light|dark` (nur `theme_preview`). Optionen (`font_family`, `dropdown`) kommen ueber die ueblichen `options`.
- Kontrast (P6): Bei `contrast_against` zeigt `color` unter dem Mindestwert den naechsten konformen Wert an (`utils/themeColor.ts`, nur Helligkeit wird veraendert) und uebernimmt ihn auf Klick. Der Control sperrt die Eingabe nicht; verbindlich ist die Serverpruefung (Speichern wird mit 422 abgelehnt, `THEMING_SYSTEM.md` Abschnitt 9).

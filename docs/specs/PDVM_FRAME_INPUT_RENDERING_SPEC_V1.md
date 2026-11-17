# PDVM Frame-gesteuerte Eingabe (Rendering) V1

Status: verbindlich ab 2026-11-13, Pilot `Mandanten Edit` umgesetzt. Ergänzt Regel 2.15 in `ARCHITECTURE_RULES.md` und baut auf [PDVM_LINEAR_FRAME_CONTROL_PIPELINE_SPEC_V1.md](./PDVM_LINEAR_FRAME_CONTROL_PIPELINE_SPEC_V1.md) auf.

## 1. Grundsatz

Jede Eingabe in der Anwendung erfolgt über das `PdvmInputControl`. Das Control hat Modi (Typen); seine Eigenschaften (Typ, Label, Konfiguration, Standardwert, schreibgeschützt) stehen im `sys_control_dict`. Welche Controls auf einer Maske erscheinen und in welcher Reihenfolge, steht in `sys_framedaten`. Gerendert wird über die UID des Frames.

```
sys_control_dict   Was ist ein Feld?         (Eigenschaften je Control)
sys_framedaten     Welche Felder, wo?        (FIELDS: Control-UID -> TAB, DISPLAY_ORDER, ...)
Runtime-Modell     Ein Modell je Frame       (GET /api/frames/{uid}/runtime)
PdvmFrameForm      Rendern                   (PdvmInputControl je Feld)
```

Ein Feld aus einer Maske zu entfernen heißt: den Eintrag in `FIELDS` des Frames löschen. Es ist keine Codeänderung nötig.

## 2. Regeln (Kurzfassung, Quelle: ARCHITECTURE_RULES.md 2.15)

1. **Eingabe nur über `PdvmInputControl`.** Komponenten enthalten keine eigenen `<input>`/`<select>`/`<textarea>` für Fachdaten und kein Typ→Markup-Mapping.
2. **Properties im Dictionary.** Typ, Label, Tooltip-Verweis, `CONFIGS`, Standardwert und `READ_ONLY` kommen aus `sys_control_dict`. Der Frame ergänzt nur Layout (`TAB`, `DISPLAY_ORDER`, `SOURCE_PATH`, `SAVE_PATH`) und die Kontextbindung `GRUPPE`/`TABLE` (Regel 1.10b).
3. **Anzeige über die Frame-UID.** Eine Maske kennt nur die UID ihres Frames; die Felder werden nie im Code aufgezählt.
4. **Ein Runtime-Modell.** Frames werden mit `GET /api/frames/{uid}/runtime` (oder der Dialog-API) geladen. Frame und Controls kommen in einer Antwort (Bulk, kein Request je Feld). Der Renderer liest nur `SOURCE_PATH + GRUPPE + FELD` und schreibt nur über `SOURCE_PATH + SAVE_PATH` (Regel 1.10d).
5. **Keine stillen Fallbacks.** Fehlt das Control oder ist der Typ im Kontext nicht darstellbar, zeigt der Renderer einen qualifizierten Fehler am Feld.
6. **Keine Geheimnisse in Daten.** Passwörter, Tokens und Schlüssel stehen weder in Datensätzen noch in Vorlagen oder Frames, sondern im Credential-Store; im Datensatz steht nur der Verweis (`CREDENTIAL`). Das Backend lehnt solche Felder beim Speichern ab (`mandant_record_rules.FORBIDDEN_SECRET_FIELDS`).
7. **Pflichtprüfung im Backend.** Fachliche Pflichtfelder prüft das Backend und liefert Fehler mit Zielpfad (`group`, `field`, `message`, vgl. Regel 2.5a). Der Renderer markiert das Feld. `REQUIRED` ist keine Control-Eigenschaft (nicht im Muttercontrol, Regel 1.10a).
8. **Zugriff zentral.** Jede Frame-Auslieferung geht durch `frame_runtime_service.ensure_frame_access`. Die Security außerhalb der Menüpunkte wird dort ergänzt, nicht in Routern oder Komponenten.
9. **Performance.** Siehe Abschnitt 5.
10. **Neue Masken** nutzen dieses Verfahren von Beginn an; bestehende werden nach Abschnitt 6 umgestellt.

## 3. Runtime-Modell

`GET /api/frames/{frame_guid}/runtime` (angemeldeter Benutzer; mit GCS-Session über deren Pools, sonst über den gemeinsamen Pool der System-DB `pdvm_system`, damit Masken vor der Mandantenwahl funktionieren):

```json
{
  "uid": "…", "name": "Mandanten Edit",
  "root": { "EDIT_TYPE": "pdvm_edit", "FRAME_TYPE": "standard", "ROOT_TABLE": "asy_mandanten", "TABLE": "" },
  "tabs": [ { "index": 1, "head": "Mandant" } ],
  "fields": [
    { "key": "<control-uid>", "control_uid": "<control-uid>", "tab": 1, "display_order": 10,
      "type": "string", "label": "Bezeichnung", "tooltip": null,
      "gruppe": "ROOT", "feld": "NAME", "source_path": "root", "save_path": null,
      "table": "asy_mandanten", "read_only": false, "immutable": false, "default": null, "configs": {},
      "resolution_warning": null }
  ]
}
```

- Sortierung: `tab`, `display_order`, `label`.
- `tabs` stammen aus `ROOT.TAB_ELEMENTS` (`TAB`, `HEAD`); fehlt ein Eintrag, heißt der Tab `Tab <n>`. Mit nur einem Tab zeigt `PdvmFrameForm` keine Tableiste (Regel 2.9).
- `resolution_warning` ist gesetzt, wenn das Control nicht in `sys_control_dict` gefunden wurde.

## 4. Renderer

- `frontend/src/components/frames/PdvmFrameForm.tsx`: Tabs und `PdvmInputControl` je Feld; Daten und Fehler kommen von außen.
- `frontend/src/components/frames/frameRuntime.ts`: Lesen/Schreiben über `GRUPPE` (Punkt-Pfad) und `FELD`; Prüfung, ob der Typ im Kontext darstellbar ist.
- Darstellbar ohne weitere Quellen: `string`, `text`, `text_popup`, `number`, `true_false`, `password`. `dropdown` ist darstellbar, weil das Backend die Optionen aus `sys_dropdowndaten` mitliefert (Abschnitt 11). Typen, die Lookup-Tabellen oder Element-Frames brauchen (`multi_dropdown`, `go_select_view`, `element_list`, …), erscheinen im Vor-Session-Kontext als Fehlermeldung am Feld. Sie werden ergänzt, sobald eine Maske sie braucht.
- Buttons und Zusatzangaben in Frames sind seit 2026-11-15 spezifiziert: Control-Typen `action` und `info`, Aktionen im Backend-Register, siehe `PDVM_FRAME_ACTIONS_SPEC_V1.md` und Regel 2.17. `PdvmDialogPage` stellt sie dar (Dialoge `edit_user`, Textvorlagen, Mandanten bearbeiten, Workflow-Builder); `PdvmFrameForm` überspringt sie.

## 5. Performance

- Backend: zwei Abfragen je Frame (Frame, Controls per `ANY($1)`), Ergebnis-Cache je Pool und Frame-UID mit 30 s TTL. Der Cache wird bei jedem Schreibzugriff über `PdvmDatabase` auf `sys_framedaten` oder `sys_control_dict` geleert; direkte SQL-Werkzeuge werden spätestens nach der TTL wirksam.
- Pool: Masken ohne Session nutzen den gemeinsamen Pool (`PoolRegistry`), keine neue Verbindung je Aufruf.
- Frontend: Frame-Runtime wird mit TanStack Query 5 Minuten gehalten (`staleTime`); Template-Daten und Frame werden parallel geladen, sobald die Frame-UID bekannt ist.
- Gemessen (lokal): kalt 163 ms inklusive Pool-Aufbau, danach 1,7 ms aus dem Cache.

## 5a. Mandanten-Neuanlage (Pilot)

- Frame `Mandanten Edit`, UID `b7f0c1a2-5d3e-4c8a-9a61-3e2d7c5f4a10` (`mandant_record_rules.MANDANT_FRAME_GUID`), `ROOT_TABLE=asy_mandanten`, vier Tabs (Mandant, Verbindung, Kontakt, E-Mail-Versand), 32 Controls `ASY_*` (`TABLE=asy_mandanten`; bei gleichem Feldnamen mit abweichender Semantik `ASY_<GRUPPE>_<FELD>`, Regel 1.10).
- Angelegt durch `backend/tools/seed_mandant_frame_v1.py` (idempotent).
- `GET /api/mandanten/template` liefert die 666-Vorlage in Datensatzform (`ROOT` + Gruppen aus `TEMPLATES`, ohne Geheimnisse) und die Frame-UID; `POST /api/mandanten/create` prüft (`validate_new_mandant`) und antwortet bei Fehlern mit `422 {"detail": {"errors": [{group, field, message}]}}`.
- Die 666-Vorlage enthält kein `MANDANT.PASSWORD` und kein `SEND_EMAIL.SMTP_PASS` mehr; neu: `MANDANT.CREDENTIAL`, `MANDANT.SYSTEM_CREDENTIAL`, `SEND_EMAIL.CREDENTIAL`, `SYSTEM_HOST/PORT/USER`. Testdaten sind durch neutrale Vorgaben ersetzt (leere Datenbank, Adresse, Kontakt und Mail-Zugang; leer bedeutet AUTH-Instanz bzw. Credential), `ROOT.DB_CREATED_AT` ist nicht vorbelegt, damit ein neuer Mandant als „Datenbank noch nicht eingerichtet“ gilt.

## 6. Umstellungsliste interne Masken

| Maske | Stand | Anmerkung |
|---|---|---|
| `MandantCreate.tsx` | ✅ umgestellt | Pilot, Frame `Mandanten Edit` |
| `MandantSetup.tsx` | ✅ entfernt (2026-11-15) | ersetzt durch die Aktion `mandant.setup` im Dialog „Mandanten bearbeiten“ (nur `superadmin`), Regel 2.17 |
| `Login.tsx` | ✅ umgestellt (2026-11-16) | Frames `Login`, `Passwort vergessen`, `Passwort ändern` über `GET /api/public/login-frames`, Typ `password_input`, Notfall-Rückfall; `PDVM_LOGIN_FRAME_SPEC_V1.md` |
| `MandantSelect.tsx` | offen | Auswahlliste, kein Formular |
| Bearbeiten bestehender Mandanten (Dialog `asy_mandanten`) | ✅ umgestellt | Dialog `Mandanten bearbeiten` (`pdvm_edit`) mit Frame `Mandanten Edit`, Modus `edit`, Abschnitt 8 |
| `PdvmViewPage.tsx` (Filter/Suche, 8 Roheingaben) | offen | zu prüfen, ob Filter Controls sein müssen |
| `PdvmImportDataEditor.tsx` (7 Roheingaben) | offen | zu prüfen |
| `PdvmThemeInputs.tsx`, `ThemeEditorPage.tsx` | offen | Theme-Controls (`color`, `css_length`, …) sind bereits Typen des Controls |
| Dialog-Add-ons (`edit_user`: Passwort/Account-Aktionen) | ✅ umgestellt (2026-11-15) | Controls `action`/`info` im Frame `Benutzer Edit`, Regel 2.17 |

Die Spalte „Stand“ wird mit jeder Umstellung gepflegt. Die Einträge „offen“ sind eine Bestandsaufnahme anhand der Suche nach Roh-Eingabeelementen, keine geprüfte Analyse.

## 7. Offene Punkte

1. ~~Buttons und Zusatzangaben in Frames~~ umgesetzt (erste und zweite Welle), siehe `PDVM_FRAME_ACTIONS_SPEC_V1.md`. Offen: `PdvmFrameForm` stellt `action`/`info` nicht dar (zurückgestellt).
2. Zugriffsregeln je Frame (`ensure_frame_access` ist heute ein Platzhalter ohne Einschränkung).
3. ~~Passwort-Modus im `PdvmInputControl` und Login als Frame~~ umgesetzt 2026-11-16 (E, `PDVM_LOGIN_FRAME_SPEC_V1.md`): Typ `password_input`, öffentlicher Endpunkt mit Allowlist, Notfall-Rückfall, Härtung von Anmeldung und Passwortwechsel (F1 bis F3).
4. ~~Frame-Modus für unveränderliche Felder~~ umgesetzt, siehe Abschnitt 8.
5. ~~Neuanlage von Mandanten~~ umgesetzt 2026-11-16 (G, `PDVM_MANDANT_ANLEGEN_FLOW_SPEC_V1.md`): Menüpunkt „Neuer Mandant“ (Seite `/mandant/new`), ein Endpunkt `POST /api/mandanten/create` (Satz, Zuweisung, Datenbank), danach Abmeldung. Offen: die Neuanlage anderer Tabellen über den Draft-Flow (Regel 2.5a).
6. **Generelle Dropdown-Umstellung (Regel 2.16):** Bestandsaufnahme aller Dropdown-Quellen (feste Listen im Code, Quellen außerhalb von `sys_dropdowndaten`, Prefix-/View-/Tabellen-Dropdowns) und Überführung nach `sys_dropdowndaten`. Regel 2.16 gilt vorerst für neue Dropdowns.
7. `multi_dropdown`, `go_select_view` und `element_list` im Frame-Renderer ohne Session (heute nur `dropdown`).
8. **Sprachabhängiges Wörterbuch für Oberflächentexte** (Labels, Tooltips, Tab-Köpfe, Menüs, feste Code-Texte, Backend-Meldungen). Eigener Entwurf nach D. Zu klären: (a) Ebenen (Daten, Code, Backend-Meldungen), (b) Form der Texte in den Datensätzen, (c) Pflege und Freigabe je Sprache (Regel 1.19), Überschreiben durch den Mandanten wie bei den Textvorlagen, (d) Laden als Bündel je Sprache (ein Request, gecacht), (e) Zahlen-/Datumsformate (heute fest `de-DE`). Vorbereitung in `PDVM_FRAME_ACTIONS_SPEC_V1.md`, Abschnitt 3.11.

## 8. Modus für unveränderliche Felder (umgesetzt 2026-11-13)

Beim Ändern eines Mandanten bleiben einzelne Felder (z. B. `MANDANT.DATABASE`) unveränderlich; Neuanlage und Ändern nutzen dasselbe Frame.

- Der **Modus** (`create` oder `edit`) kommt vom Host, nicht vom Frame: Draft/Neuanlage = `create`, vorhandener Satz = `edit`. Ein zweites Frame oder ein Frame-Typ je Modus entfällt. `PdvmFrameForm` hat dafür die Eigenschaft `mode`; der Dialog (`PdvmDialogPage`) wertet `isDraftMode` aus.
- Die **Unveränderlichkeit** ist eine Eigenschaft des Feldes und steht im Control: `CONTROL.IMMUTABLE` (Standard `false`). Sie ist im Muttercontrol 666 freigegeben (Regel 1.10a, Freigabe 2026-11-13; `CONTROL` und `TEMPLATES.CONTROL`), das Control `SYS_IMMUTABLE` macht sie im Control-Editor bearbeitbar. Das Runtime-Modell liefert sie als `immutable`.
- Im Modus `edit` setzt der Renderer ein Feld mit `immutable=true` auf `readOnly`, **sobald es im gespeicherten Datensatz einen Wert hat** (`frameRuntime.isImmutableLocked`, gleiche Regel wie das Backend). Maßgeblich ist der gespeicherte Stand, nicht der Entwurf (`savedData` im `PdvmFrameForm`, `currentDaten` im Dialog): sonst würde sich ein leeres Feld beim ersten getippten Zeichen selbst sperren. Ein leeres unveränderliches Feld bleibt bis zum Speichern bearbeitbar.
- **Kennzeichnung:** `PdvmInputControl` markiert jedes schreibgeschützte Feld einheitlich: gedämpfte Fläche, gestrichelter Rahmen, kursives Label und ein Schloss am Label (Tooltip über `readOnlyHint`, bei unveränderlichen Feldern „Nach der Anlage unveränderlich“). Die Darstellung steckt in `PdvmInputControl.css` (`.pdvm-pic--readonly`) und gilt damit für alle Masken.
- **Backend-Pflicht:** `central_write_service.update_record_central` ruft `immutable_fields_service.enforce_immutable_fields` auf und lehnt Änderungen an solchen Feldern ab (`ImmutableFieldError`, im Dialog als `400`). Die Sperre im Formular ist nur Komfort, keine Sicherheit.
- **Set-Once:** Ein Feld, das im bestehenden Satz leer ist, darf einmalig gesetzt werden; ist es gesetzt, darf es weder geändert noch geleert werden. Verglichen wird der Wert als Text (`5432` = `"5432"`).
- Performance: die Liste der unveränderlichen Felder je Tabelle ist 30 s gecacht (Template-Cache, wird bei Schreibzugriffen auf `sys_control_dict` geleert); der Satz selbst wird nur gelesen, wenn die Tabelle solche Felder hat (gemessen: 17 ms beim ersten, 2 ms bei weiteren Aufrufen).
- Unveränderlich bei Mandanten (`mandant_record_rules.IMMUTABLE_MANDANT_FIELDS`): `MANDANT.DATABASE`, `HOST`, `PORT`, `SYSTEM_DB`, `SYSTEM_HOST`, `SYSTEM_PORT`. **Bedingt (2026-11-16):** diese Controls tragen `IMMUTABLE_AFTER=ROOT.DB_CREATED_AT`; bis die Datenbank eingerichtet ist (Aktion `mandant.setup`), sind sie korrigierbar (z. B. Tippfehler im Host), danach gesperrt. `IMMUTABLE_AFTER` ist im Muttercontrol 666 und als Control `SYS_IMMUTABLE_AFTER` im Control-Editor angelegt (`backend/tools/seed_immutable_after_v1.py`); das Runtime-Modell liefert `immutable_after`. Ein leerer oder `-eingeben-` Wert des Bedingungsfelds gilt als nicht gefüllt.
- Dialog `Mandanten bearbeiten` (`3c9e1f50-8a2b-4d67-b1e4-7f0a5c2d9e31`, `pdvm_edit`, View `Mandantendaten`, Frame `Mandanten Edit`) ersetzt im Menü Admin-Administration den bisherigen JSON-Dialog, der als `Mandanten (JSON)` erhalten bleibt. `GO_NEW_SET=false`: neue Mandanten entstehen über den Menüpunkt „Neuer Mandant“ (`MandantCreate`, inklusive Datenbank-Einrichtung), nicht über den Draft des Dialogs. Angelegt durch `backend/tools/seed_mandant_dialog_v1.py`.
- Rollen- oder kontextabhängiges `readOnly` (z. B. nur Admin darf ändern) wäre ein Frame-Override `READ_ONLY` je Feld; das ist eine eigene Entscheidung und hier nicht vorgesehen.

## 9. Geheimnisse bearbeiten: Control-Typ `password` (umgesetzt 2026-11-14)

Passwörter (z. B. SMTP-Passwort) müssen änderbar sein, dürfen aber weder im Mandantensatz noch im Frontend stehen. Lösung: Der Datensatz hält nur den **Namen** des Zugangsdatensatzes (`SEND_EMAIL.CREDENTIAL`), das Passwort liegt verschlüsselt im Backend.

- **Control-Typ `password` (write-only):** `PdvmInputControl` rendert `PdvmSecretInput`. Es zeigt nur „Passwort gesetzt“ bzw. „Noch kein Passwort gesetzt“ und ein Eingabefeld. Die Eingabe geht mit „Speichern“ direkt an `PUT /api/credentials/{name}`; sie wird nie angezeigt, nie als Feldwert gehalten und nie zurückgeliefert. Der Feldwert (Name) wird beim ersten Speichern erzeugt (`CONTROL.CONFIGS.password.name_prefix`, z. B. `mail` → `mail-3f9a12bc`). Namen aus der `.env` sind schreibgeschützt.
- **Speicher:** Tabelle `asy_credentials` in der AUTH-DB (PDVM-Standardstruktur, angelegt von der Auth-Wartung). `name` = Credential-Name, `daten.CREDENTIAL` = `USER`, `PASSWORD` (Fernet-Chiffretext `enc:v1:…`), `SSL`, `UPDATED_AT`. Schlüssel: `PDVM_SECRET_KEY` in der `.env` (nie in der Datenbank; **sichern**, ohne ihn sind die Passwörter unlesbar). `daten_backup` enthält damit ebenfalls nur Chiffretext.
- **Auflösung:** `credential_store.get_credential(name)`: zuerst `.env` (`PDVM_DB_CREDENTIALS`), dann der entschlüsselte Cache der gespeicherten Einträge. Der Cache wird beim Start, nach jedem Setzen und höchstens alle 30 s vor Verbindungsaufbau und E-Mail-Versand aktualisiert (`credential_service.ensure_fresh`); mehrere Backend-Instanzen bleiben so nahezu aktuell. Wirkt für DB-Verbindungen (`MANDANT.CREDENTIAL`) und SMTP gleichermaßen.
- **API** (`/api/credentials`, nur Admin, auch vor der Mandantenwahl): `GET /{name}` liefert nur Metadaten (`exists`, `source`, `user`, `ssl`, `updated_at`), `PUT /{name}` setzt das Passwort. Namen: `[A-Za-z0-9][A-Za-z0-9_.-]{0,63}`. Das Passwort steht in keiner Antwort, keinem Log und keiner Fehlermeldung.
- **Versand:** `issue_password_reset` liest `SEND_EMAIL` beim Versand frisch aus `asy_mandanten`, nicht aus den Login-Daten der Session (sonst wirkten Änderungen erst nach erneuter Mandantenwahl; Ursache für `535 Authentication credentials invalid` nach einem Passwortwechsel).
- **Migration:** `backend/tools/migrate_smtp_credentials_v1.py` überführt vorhandene `SMTP_PASS` (Name `mail-<erste 8 Zeichen der Mandanten-UID>`), setzt `SEND_EMAIL.CREDENTIAL`, entfernt `SMTP_PASS` aus `daten` **und** `daten_backup` und stellt das Control `ASY_SEND_EMAIL_CREDENTIAL` auf Typ `password` um (2026-11-14 ausgeführt: 2 Mandanten).
- **Bewusst offen:** Wird ein neuer Mandant angelegt und das Passwort gesetzt, aber die Neuanlage abgebrochen, bleibt der Zugangsdatensatz bestehen (verwaist, harmlos). Ein Löschen/Umbenennen von Zugangsdatensätzen und ein Schlüsselwechsel (Neuverschlüsselung) sind nicht umgesetzt.

## 10. Langtexte bearbeiten: `text` und `text_popup` (umgesetzt 2026-11-14)

Mehrzeilige Texte (Mailtexte, Beschreibungen) sind in einem 3-zeiligen Feld unhandlich. Beide Typen öffnen deshalb dasselbe große Fenster (`PdvmTextEditorModal`), das nur bei Bedarf gerendert wird (keine Zusatzlast, keine neue Bibliothek, keine Anfrage an das Backend).

- **`text`:** Textfeld wie bisher plus Schaltfläche ⤢ („Großes Textfenster“). Standardmäßig für **alle** `text`-Controls; abschaltbar mit `CONFIGS.text.expand = false`.
- **`text_popup`:** Platzsparend, nur eine Schaltfläche mit erster Zeile und Zeichenanzahl; Klick öffnet das Fenster. Für dichte Frames und Übersichten.
- **Fenster:** großer Editor (bis 960 px Breite, 80 % der Höhe, nie größer als der sichtbare Bereich), gerendert per Portal im `body` (unabhängig vom umgebenden Container), Zeichen-/Zeilenzähler, Entwurf: **Übernehmen** schreibt den Text zurück (Strg+Enter), **Abbrechen/Esc** verwirft. Ein Klick neben das Fenster schließt nur, solange nichts geändert ist. Schreibgeschützte oder gesperrte Felder (`READ_ONLY`, `IMMUTABLE`) öffnen es im Lesemodus. Gespeichert wird wie immer erst im Dialog/Frame.
- **Konfiguration** (`CONTROL.CONFIGS.text`, alles optional): `rows` (Zeilen im Feld, Standard 3, max. 30), `expand` (Standard `true`), `title` (Fenstertitel, Standard Label), `mono` (Festbreitschrift, z. B. für HTML), `html_preview` (Reiter „Vorschau“).
- **HTML-Vorschau:** rendert den Text in einem abgeschotteten `iframe` (`sandbox=""`, also ohne Skripte, Formulare und Navigation; CSP `default-src 'none'`, nur Inline-Stile und `data:`-Bilder). Platzhalter `{{name}}` erscheinen unersetzt. Die Fläche ist bewusst hell (wie beim Empfänger), unabhängig vom Theme (`guard-allow-color`).
- **Textvorlagen:** `BODY` (8 Zeilen) und `BODY_HTML` (6 Zeilen, `mono`, `html_preview`) sind so konfiguriert (`seed_text_template_dialogs_v1.py`, zieht bestehende Controls nach).
- **Nebenpfade:** `text_popup` zählt in Anlage-Fenstern und Element-Feldern wie `text` (`textarea`).

## 11. Dropdowns im Frame (umgesetzt 2026-11-14, Regel 2.16)

- **Quelle:** ausschließlich `sys_dropdowndaten`; das Control trägt `CONFIGS.dropdown = { key: <UID des Dropdown-Satzes>, table: "sys_dropdowndaten", feld: "", gruppe: "" }`.
- **Auslieferung:** `frame_runtime_service` löst die Optionen beim Laden des Frames auf (`fields[].options = [{value, label}]`, Parser `dropdown_service._parse_dataset`) und liest dafür nur die System-DB; es ist keine Session nötig (Masken vor der Mandantenwahl). Sprache: `GET /api/frames/{uid}/runtime?language=…`, sonst `DEFAULT_LANGUAGE` der I18N-Policy; der Cache gilt je Frame und Sprache und wird bei Schreibzugriffen auf `sys_dropdowndaten`, `sys_framedaten` und `sys_control_dict` geleert.
- **Fehlerfall:** Ein `dropdown`-Control ohne `CONFIGS.dropdown.key` (oder mit anderer Tabelle) liefert einen qualifizierten Fehler am Feld, keinen stillen Fallback.
- **Sprachauswahl in Eigenbezeichnung:** `CONFIGS.dropdown.label_language = "own"` zeigt jede Option in ihrer eigenen Sprache (Deutsch, English, Italiano), unabhängig von der Oberflächensprache. Voraussetzung: Der Optionsschlüssel ist der Sprachcode (`DE-DE`, …), das Label steht in `OPTIONS.<code>.<code>`. Fehlt es, gilt die Oberflächensprache. Ohne die Eigenschaft bleiben Dropdowns in der Oberflächensprache. Eine neue Sprache braucht nur einen Eintrag im Dropdown-Satz (Eigenbezeichnung) und je eine Zeile in den übrigen.
- **Beispiel:** `CONFIG.DEFAULT_LANGUAGE` im Frame „Mandanten Edit“ (Control `ASY_CONFIG_DEFAULT_LANGUAGE`, Tab „Mandant“, Dropdown `Sprachen::sprache` mit `DE-DE`, `EN-US`, `IT-IT`), angelegt durch `backend/tools/seed_mandant_language_v1.py` (idempotent). Die Sprachkette der Textvorlagen liest das Feld bereits aus.

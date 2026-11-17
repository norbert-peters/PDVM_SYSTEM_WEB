# PDVM Frame-Aktionen und Hinweise V1

Status: **freigegeben und umgesetzt (erste Welle), 2026-11-15**. Regel 2.17 in `ARCHITECTURE_RULES.md`. Freigegebene Entscheidungen: Aktionen im Backend-Register (Control nur mit ID), Platzierung `field` und `header`, bei ungespeicherten Änderungen **Hinweis mit Abbruchmöglichkeit** (Bestätigungsfenster, die Aktion wird nicht gesperrt), nicht erlaubte Aktionen ausblenden, `info` als eigener Control-Typ, erste Welle `edit_user` und Textvorlagen, Sofortmaßnahme vorab, Wörterbuch als eigener offener Punkt.

**Abweichungen von der Entwurfsfassung (Stand der Umsetzung):**
- Rechte und Zustände kommen in **beiden** Rendering-Pfaden aus `POST /api/frame-actions/state`; die Frame-Runtime (`GET /api/frames/{uid}/runtime`) enthält nur die Konfiguration und meldet unbekannte Aktions-IDs als Fehler am Feld (`resolution_warning`). Statische Rolleninformationen im Runtime-Modell entfallen (sie wären nur für `PdvmFrameForm` nötig, das in der ersten Welle keine Aktionen zeigt).
- Antwort einer Aktion: `refresh` (Liste `record`/`rows`/`state`) statt `reload: bool`.
- Bedingungen sind `visible_when`/`enabled_when`; `state.<pfad>` liest den Zustand der Aktion, alles andere den Datensatz. Texte können `{{pfad}}` enthalten.
- Die alten Endpunkte `/api/users/{uid}/…` und `/api/textvorlagen/…` sind **entfernt** (kein Frontend-Aufruf mehr); Rechte hängen an der Aktion.
- Benutzer-Aktionen wirken nur auf Benutzer des Mandanten der Sitzung (`MANDANTEN.LIST`, `superadmin` ausgenommen).
- `PdvmFrameForm` (Mandanten-Neuanlage) überspringt `action`/`info` (zurückgestellt, siehe Abschnitt 6); der Dialog „Mandanten bearbeiten“ nutzt `PdvmDialogPage` und zeigt sie.

**Zweite Welle (2026-11-15, freigegeben):** Mandanten-Maske, Workflow-Draft-Builder und Absicherung der Mandanten-Endpunkte, siehe Abschnitt 3.12.

Betrifft Regel 2.15 (Zeile „Offen: Buttons und Zusatzangaben in Frames“), 2.14 (Add-ons von `edit_user`) und die Rendering-Spec, Abschnitte 4 und 7.

## 1. Ausgangslage (Bestand vor der Umstellung)

| Stelle | Aktion / Hinweis | Heute |
|---|---|---|
| `edit_user` (`PdvmDialogPage`) | „Maschinelles Passwort senden“, „Account sperren/entsperren“, Anzeigen „Passwortwechsel erforderlich“, „Account gesperrt“ | fest im Komponentencode, Endpunkte `/api/users/{uid}/password-reset`, `/lock`, `/unlock` |
| Textvorlagen-Dialoge | „Kopie anlegen“, „Neue Systemfassung übernehmen“, Hinweis „Systemvorlage ist neuer“ | fest im Komponentencode (Tabellenname wird abgefragt) |
| Workflow-Draft-Builder | Controls vom Typ `action` (validate, save, apply …) | die Aktion wird aus dem **Label/Namen per Textsuche** erraten (`buildActionToken`) |
| `MandantCreate`, `MandantSetup` | Speichern, Abbrechen, Datenbank einrichten | feste Buttons |

Probleme: Aktionen stehen im Code und nicht in den Daten (Regel 2.15 gilt für sie nicht), die Zuordnung per Textsuche ist fehleranfällig, und es gibt keine einheitliche Rechteprüfung.

**Sicherheitsbefund (behoben 2026-11-15):** `post_password_reset`, `post_lock_account` und `post_unlock_account` (`backend/app/api/users.py`) prüften nur, dass eine Mandanten-Session existiert, keine Rolle; `issue_password_reset` und `update_account_lock` prüfen ebenfalls keine. Jeder angemeldete Benutzer konnte damit fremde Konten sperren oder ein Einmalpasswort auslösen. Sofortmaßnahme war eine Admin-Prüfung (`security.session_has_admin_rights`); mit der Umstellung ersetzt das Aktionsregister die Endpunkte, die Rolle hängt jetzt an der Aktion (Abschnitt 3.7). **Hinweis:** Die Services `issue_password_reset`/`update_account_lock` prüfen selbst weiterhin keine Rolle; jeder neue Aufrufer muss über das Register gehen.

## 2. Ziele und Nicht-Ziele

Ziele:
- Aktionen (Buttons) und Hinweise (Statusanzeigen) werden wie Felder im `sys_control_dict` definiert und über den Frame platziert (Regel 2.15).
- Eine Aktion verweist nur auf eine **Aktions-ID**. Was sie tut und wer sie ausführen darf, steht im Backend.
- Ein Frame genügt für „anlegen“ und „ändern“; Aktionen erscheinen nur, wo sie sinnvoll sind (Modus, gespeicherter Satz).
- Kein zusätzlicher Request je Feld.

Nicht-Ziele (V1):
- Keine frei konfigurierbaren URLs oder Skripte in Controls.
- Kein Workflow-Draft-Builder (Umstellung später), keine Mehrschritt-Assistenten.
- Speichern/Abbrechen des Dialogs bleiben Aufgabe des Hosts, keine Aktionen.

## 3. Entwurf

### 3.1 Grundprinzip

Das Control trägt eine Aktions-ID; das Aktionsregister im Backend legt Rechte, Bedingungen und Handler fest. Ein Datenbankeintrag kann so nie eine neue, ungeprüfte Funktion auslösen.

### 3.2 Control-Typen

Zwei neue Typen im `PdvmInputControl` (Freigabe der Typen und von `CONFIGS.action`/`CONFIGS.info` im Muttercontrol 666 wie bei `text_popup`; `CONFIGS` ist frei, nur die Doku ist zu pflegen). Der vorhandene Typ `action` wird auf diese Definition umgestellt.

```json
{
  "TYPE": "action", "LABEL": "Account sperren", "TOOLTIP": "…",
  "CONFIGS": { "action": {
    "id": "user.lock",
    "modes": ["edit"],
    "confirm": { "title": "Account sperren", "message": "…", "label": "Sperren" },
    "params": [ { "name": "reason", "label": "Grund", "type": "text", "required": false } ],
    "visible_when": { "path": "SECURITY.ACCOUNT_LOCKED", "not": true },
    "placement": "field"
  } }
}
```

```json
{
  "TYPE": "info", "LABEL": "Account gesperrt",
  "CONFIGS": { "info": {
    "value_path": "SECURITY.ACCOUNT_LOCKED",
    "format": "yes_no",
    "severity": "warning",
    "visible_when": { "path": "SECURITY.ACCOUNT_LOCKED", "equals": true }
  } }
}
```

- `info` ist ein reiner Anzeige-Typ (kein Eingabefeld, nie schreibend). Quelle: `value_path` aus dem Datensatz, ein festes `text` oder der Status einer Aktion (`state`, Abschnitt 3.4). `severity`: `info`, `warning`, `error` (Theme-Tokens, keine Farbliterale).
- `visible_when`/`enabled_when`: deklarativ, nur `path` plus `equals`, `not`, `in`, `empty`/`not_empty`; kein Code. Der Renderer wertet sie auf den Daten des Satzes aus (kein Request).
- `modes`: Standard `["edit"]` (Aktionen brauchen einen gespeicherten Satz).
- `params`: kleines Formular im vorhandenen `PdvmDialogModal`; die Werte gehen mit der Anfrage mit.
- `placement`: `field` (Zelle im Raster, Standard) oder `header` (Aktionsleiste über dem Frame, rechtsbündig). Mehr Layout gibt es in V1 nicht.

### 3.3 Aktionsregister (Backend)

`backend/app/core/frame_action_service.py` mit einem Register fest eingebauter Aktionen. Beispiel (Python-Code, nicht Datenbank):

```python
Action(
    id="user.lock",
    tables={"asy_benutzer"},
    roles={"admin", "superadmin"},
    needs_record=True,
    params={"reason": ParamSpec(type="text", max_length=500)},
    handler=lock_account,        # ruft den vorhandenen Service
    state=None,
)
```

- Der Handler ruft die bestehenden Services (`update_account_lock`, `issue_password_reset`, `text_template_service.copy_template` …). Geschrieben wird weiter über den zentralen Gateway (Regel 1.1); die Aktion enthält kein SQL.
- Ein Eintrag kann `state(table, uid, gcs)` liefern (z. B. „Systemvorlage ist neuer“ = `source_status`). Das speist `info`-Controls und `visible_when` auf Serverdaten.
- Unbekannte ID, falsche Tabelle oder fehlende Rolle werden abgelehnt (Abschnitt 3.7).

### 3.4 API

| Endpunkt | Zweck |
|---|---|
| `POST /api/frame-actions/{action_id}/run` | Aktion ausführen. Body: `{table, uid, params}`. Antwort: `{status: "ok"|"error", message, message_key, severity, refresh: ["record"|"rows"|"state"], data}`. Fehler: 400 (Eingabe/fachlich), 403 (Rolle, Tabelle, Mandant), 404 (unbekannte ID) |
| `POST /api/frame-actions/state` | Zustände für einen Satz **gebündelt**: Body `{table, uid, ids: [...]}`; je ID `{allowed, reason, state}`. Wird einmal je Satz geladen (TanStack Query, `staleTime` 60 s) |

Der Router (`backend/app/api/frame_actions.py`) enthält kein SQL (Regel 1.1) und delegiert an `frame_action_service`. Die früheren Endpunkte `/api/users/{uid}/…` und `/api/textvorlagen/…` sind entfernt.

### 3.5 Rechte und Frame-Cache

Die Frame-Runtime ist **je Frame gecacht, nicht je Benutzer** (30 s). Ob eine Aktion für den Benutzer erlaubt ist (`allowed`, mit Begründung), liefert deshalb `POST /api/frame-actions/state` je Satz aus den Sitzungsrollen; das gecachte Frame-Modell bleibt benutzerunabhängig. Der Renderer zeigt eine nicht erlaubte Aktion nicht an, solange die Zustände laden oder verweigert sind (`CONFIGS.action.when_denied = "hide"|"disable"`, Standard `hide`; bei `disable` mit Begründung als Tooltip). Das ist nur Komfort; entscheidend ist die Prüfung bei `run`.

### 3.6 Renderer-Verhalten

- **Gespeicherter Stand:** Aktionen wirken auf den gespeicherten Satz. Bei ungespeicherten Änderungen erscheint **vor der Ausführung ein Hinweisfenster** („Es gibt ungespeicherte Änderungen … Abbrechen, um zuerst zu speichern“, Schaltflächen „Abbrechen“ / „Trotzdem ausführen“). So kann der Benutzer abbrechen und zuerst speichern; die Aktion ist nicht gesperrt.
- **Bestätigung/Parameter:** über `PdvmDialogModal` (`confirm`, `params`); kein neues Fenster. Hinweis und Bestätigung sind ein Fenster.
- **Ablauf:** Button gesperrt während der Anfrage; Ergebnis als Info/Fehler-Fenster; bei `refresh` mit `record` wird der Satz neu geladen (z. B. nach Sperren), bei `rows` die Liste.
- **Lesemodus/Draft:** im Modus `create` werden Aktionen nicht angezeigt (außer `modes` nennt `create` ausdrücklich).
- Der Renderer kennt keine Fachlogik und keine Tabellennamen mehr; die Abfrage nach `msy_textvorlagen` im Dialog entfällt. Umsetzung: `frontend/src/components/frames/frameActions.tsx` (Bedingungen, Zustände, Ablauf), Darstellung in `PdvmInputControl` (`action`, `info`), Platzierung `field` im Raster, `header` in der Leiste über dem Frame.

### 3.7 Sicherheit

- **Allowlist:** nur Aktions-IDs aus dem Register; eine ID im Control ist ein Verweis, keine Funktion.
- **Zentrale Prüfung** in `run`: Session vorhanden, Rolle (`roles` des Registers, gleiche Quelle wie `security.normalized_roles`), Tabelle erlaubt, UID gültig und Satz vorhanden, Parameter nach `ParamSpec` geprüft (Typ, Länge). Fehler liefern 4xx mit Klartext; es wird nichts geraten.
- **Mandantenbezug:** `user.*`-Aktionen wirken nur auf Benutzer, die dem Mandanten der Sitzung zugeordnet sind (`MANDANTEN.LIST` des Benutzersatzes enthält `gcs.mandant_guid`); `superadmin` ist ausgenommen. Aktionen auf Mandantentabellen (`msy_*`) arbeiten nur in der Mandanten-DB der Sitzung.
- **Protokoll:** jede Ausführung schreibt eine Zeile ins Log (Aktion, Benutzer, Satz, Ergebnis; keine Parameterwerte mit Geheimnissen). Schreibende Handler protokollieren zusätzlich über den Gateway (Akteur/IP).
- **Missbrauch:** Wiederholbare, teure Aktionen (E-Mail-Versand) behalten ihre vorhandene Ratenbegrenzung (`OTP_RATE_LIMIT`).
- Behebt den Befund aus Abschnitt 1, weil Rollen künftig an der Aktion hängen und nicht im Endpunkt vergessen werden können.

### 3.8 Performance

- Keine Zusatzanfrage beim Rendern: Aktionen und Hinweise stecken als Konfiguration im Frame (gecacht).
- Serverzustände und Rechte in **einer** gebündelten Anfrage je Satz (`state`), nur wenn der Frame solche Controls enthält; Cache `staleTime` 60 s, Invalidierung nach `run` mit `refresh`.
- Bedingungen (`visible_when`) rechnet der Renderer lokal auf den geladenen Daten.

### 3.9 Umstellung des Bestands

| Bisher | Aktions-ID | Rollen |
|---|---|---|
| Maschinelles Passwort senden | `user.password_reset` | `admin`, `superadmin` |
| Account sperren / entsperren | `user.lock`, `user.unlock` | `admin`, `superadmin` |
| Anzeigen Passwortwechsel / gesperrt | `info`-Controls auf `SECURITY.*` | lesen wie der Satz |
| Textvorlage kopieren | `texttemplate.copy` | wie Pflege der Tabelle (`text_template_service.EDIT_ROLES`, Regel 1.24) |
| Neue Systemfassung übernehmen | `texttemplate.adopt_source` | wie Pflege (nur `msy_textvorlagen`) |
| Hinweis „Systemvorlage ist neuer“ | `info` mit `state` von `texttemplate.adopt_source` | wie Pflege |

Erste Welle: `edit_user` und Textvorlagen (Controls im Frame statt im Code, Seed-Tool `seed_frame_actions_v1.py`, Endpunkte auf das Register). Zweite Welle: `mandant.setup` und Workflow-Draft-Builder (Abschnitt 3.12); die Textsuche `buildActionToken` ist entfernt.

### 3.10 Tests

- `backend/test_frame_actions.py`: unbekannte ID, falsche Tabelle, fehlende Rolle, ungültige Parameter/UID jeweils abgelehnt; Admin führt `user.lock`/`user.password_reset` aus (Parameter `reason` wird weitergereicht); Benutzer anderer Mandanten werden abgelehnt (`superadmin` ausgenommen); Rollen der Textvorlagen-Aktionen folgen den Tabellen (Regel 1.24); `state` liefert `allowed` und den Zustand der Aktion; HTTP-Statuscodes (403/404/400/200); `session_has_admin_rights`.
- `backend/test_frame_runtime.py`: unbekannte Aktions-IDs und fehlende `CONFIGS.action.id` werden als Fehler am Feld gemeldet.
- Ende-zu-Ende gegen die echten Datenbanken (einmalig, danach zurückgebaut): Frame „Benutzer Edit“ liefert die Controls samt `CONFIGS.action.id`; Sperren und Entsperren über die API verändern `SECURITY.ACCOUNT_LOCKED` und stellen den Ausgangszustand wieder her; Benutzer ohne Admin-Rolle und Benutzer fremder Mandanten erhalten 403; Kopie einer Textvorlage über die Aktion.
- Frontend: Typprüfung und Build (keine Browser-Tests vorhanden); Theme-Guard grün (Tokens statt Farben).

### 3.11 Texte und Mehrsprachigkeit (Vorbereitung, kein Teil von D)

Ein sprachabhängiges Wörterbuch für Oberflächentexte ist ein eigener Punkt (Rendering-Spec, Abschnitt 7, Nr. 8) und wird nicht vorab entworfen. D darf es nur nicht erschweren:

- Alle Texte neuer Aktionen und Hinweise (`LABEL`, `TOOLTIP`, `confirm.*`, `params[].label`, `info.text`) stehen in den **Controls**, nie im Komponentencode. Sie laufen damit durch dieselbe Auflösungsstelle wie alle Labels: das Frame-Runtime-Modell im Backend, das schon heute Dropdown-Optionen je Sprache auflöst (`?language=`, Cache je Frame und Sprache).
- Feste Texte, die der Renderer selbst braucht (z. B. der Hinweis bei ungespeicherten Änderungen, „Abbrechen“), kommen aus **einer** Datei (`frontend/src/i18n/uiTexts.ts`, Schlüssel → deutscher Text). Spätere Umstellung auf das Wörterbuch ersetzt nur diese Datei.
- Handler liefern Meldungen mit `message_key` plus Klartext (`message`); die Übersetzung der Meldungen gehört in den Wörterbuch-Punkt. Heute stehen die Klartexte der Handler noch im Register (`frame_action_service.py`).
- Es kommt kein weiterer Text in Controls als Textfeld mit eigener Struktur hinzu; die Form (einfache Zeichenkette oder Schlüssel) legt der Wörterbuch-Punkt für **alle** Felder gemeinsam fest.

### 3.12 Zweite Welle: Mandanten und Workflow-Builder

**Mandanten (nur `superadmin`).**
- `GET /api/mandanten/template` und `POST /api/mandanten/create` verlangen `require_superadmin_user` (403 sonst). Vorher genügte eine Anmeldung; jeder Benutzer konnte Mandanten anlegen und `CREATE DATABASE` auslösen. (`POST /save` ist mit der Umsetzung von G entfallen.)
- Der Datenbankaufbau (`MandantSetup`, `/pending-setup`, `/setup/{id}`) ist die Aktion **`mandant.setup`** (Service `backend/app/core/mandant_setup_service.py`, Rolle `superadmin`, Tabelle `asy_mandanten`). Sie ist nur erlaubt, solange `ROOT.DB_CREATED_AT` fehlt oder „-eingeben-“ ist; der State-Provider liefert dafür `needs_setup`. Im Frame „Mandanten Edit“ gehören `ASY_ACTION_MANDANT_SETUP` (Button) und `ASY_INFO_MANDANT_SETUP` (Hinweis „Datenbank noch nicht eingerichtet“, `visible_when state.needs_setup`) dazu. Die Komponente `MandantSetup` ist entfernt; „Neuer Mandant“ ist ein Menüpunkt (Rolle `superadmin`, `PDVM_MANDANT_ANLEGEN_FLOW_SPEC_V1.md`). Nach erfolgreichem Aufbau trägt die Aktion den Mandanten beim ausführenden Benutzer ein (`grant_mandant_access`) und meldet `data.relogin = true`; der Runner (`useFrameActionRunner`) zeigt das Ergebnis und meldet nach der Bestätigung ab („Zur Anmeldung“), weil Mandantenliste und Token aus dem Login stammen. Das Feld `data.relogin` ist allgemein: jede Aktion kann damit eine Neuanmeldung verlangen.
- Die Rolle `superadmin` steht in `PERMISSIONS.ROLES` des Benutzers; Änderungen wirken nach erneutem Login.
- Der generische Dialog darf Mandanten nicht anlegen: `GET /api/dialogs/{guid}` liefert `meta.create_blocked_reason` (aus `mandant_record_rules.DIALOG_CREATE_BLOCKED_TABLES`), das Frontend blendet „Neuer Satz“ dann aus; `POST /api/dialogs/{guid}/draft/start` und `/record` antworten mit 403. Anlegen nur über den Menüpunkt „Neuer Mandant“.
- `POST /api/mandanten/create` (Satz, Zuweisung `grant_mandant_access`, Datenbank; ersetzt `/save`) trägt den neuen Mandanten in `MANDANTEN.LIST` des anlegenden Superadmins ein (idempotent, Antwort `access_granted`); sichtbar nach der nächsten Anmeldung.
- Das Frontend liest Rollen wie das Backend (`SECURITY`, `PERMISSIONS.ROLES`, `SETTINGS.MODE`, `AuthContext.parseSecurityRoles`).

**Mandant löschen (2026-11-17).** Aktion **`mandant.delete`** (Service `mandant_delete_service.py`, Tabelle `asy_mandanten`). Das Register kennt dafür `Action.also_require`: Rollen, die **zusätzlich** alle vorhanden sein müssen; hier `superadmin` (aus `roles_by_table`) **und** `delmand`. Parameter `confirm_name` (Pflicht) muss exakt dem Mandantennamen entsprechen. State-Provider: `can_delete` (und `reason`); Voraussetzungen: Mandant existiert und ist nicht gelöscht, nicht der Mandant der eigenen Sitzung, die Datenbank ist keine Systemdatenbank (`auth`, `pdvm_system`, `postgres`, Vorlagen, System-DB des Mandanten) und wird von keinem anderen Mandanten benutzt. Frame „Mandanten Edit“: Control `ASY_ACTION_MANDANT_DELETE` (Button, `visible_when state.can_delete`, Bestätigung mit Namenseingabe).
- **Ablauf:** (1) `pg_dump` (Custom-Format, mit `pg_restore --list` geprüft) und Mandantensatz als JSON nach `database/backups/mandant_geloescht/` (Einstellung `MANDANT_DELETE_BACKUP_DIR`; Werkzeuge über `PG_BIN_DIR`, PATH oder Standardpfade); Fehler → es wird nichts gelöscht. (2) Sessions und Pools des Mandanten schließen, Verbindungen beenden, `DROP DATABASE`. (3) UID aus `MANDANTEN.LIST` aller Benutzer entfernen, `MANDANTEN.DEFAULT` leeren, wenn er darauf zeigt. (4) `ROOT.SELF_GILT_BIS` = `created_at` (PDVM-Format; Spalte `gilt_bis` folgt, Abweichung unter 1 Sekunde).
- **Wiederholbar:** Fehlt die Datenbank schon (Abbruch nach Schritt 2, oder nie eingerichtet), entfallen Schritt 1 und 2; die Aktion setzt bei 3 fort.
- **Unerreichbar, stichtagsunabhängig:** Ein normales `gilt_bis` wirkt nur gegen den Stichtag (Stichtag vor `created_at` machte den Satz wieder sichtbar). Der Löschmarker (`gilt_bis` ≤ `created_at` + 5 s, `mandant_tombstone.is_deleted_mandant_row`) wird deshalb in allen Lesepfaden von `asy_mandanten` ausgeschlossen: `PdvmDatabase.get_by_uid|get_by_link_uid|get_all` (außer `include_deleted=True`), `PdvmDatabaseService` (damit `MandantDataManager`: Login-Liste, Auswahl, `/select`), `ConnectionManager.get_mandant_config` und die View-Pipeline (`view_service`). Damit sind Dialog-Listen, Datensatz-Zugriff, Mandantenwahl und Wartung ohne Zusatzcode gesperrt; ein Löschen schreibt nichts in andere Datenbanken.
- Nach Erfolg `data.relogin = true` (Mandantenliste und Token des ausführenden Benutzers stammen aus dem Login). Rollen `delmand` wirken wie `superadmin` und `overlay` erst nach erneutem Login.
- Tests: `test_mandant_delete.py`. Seed: `seed_frame_actions_v1.py` (Control `ASY_ACTION_MANDANT_DELETE`).

**Host-Aktionen (`executor = "host"`).** Der Workflow-Draft-Builder arbeitet auf dem Editorzustand des Dialogs. Das Register führt solche Aktionen nicht aus (`run` lehnt sie ab), liefert aber Rechte und Sichtbarkeit über `state`; der Dialog ruft die Aktion selbst über eine Map ID → Handler auf (`hostActions` in `useFrameActionRunner`). Die zugehörigen Endpunkte erzwingen ihre Rollen selbst.
- IDs `workflow.validate|save|build|save_view|save_content|create_control|create_property|abort|dry_run` (Rollen `admin`, `superadmin`, `develop`, `developer`) und `workflow.apply` (nur `admin`, `superadmin`).
- Die Controls tragen die ID explizit in `CONFIGS.action {id, modes:[create,edit]}` (Seed). Die Zuordnung per Textsuche im Label entfällt; Controls ohne ID werden nicht angezeigt.
- Tabellenschlüssel `"*"` im Register gilt für jede Tabelle; `POST /api/frame-actions/state` akzeptiert `uid` weglassen (nur Aktionen ohne Datensatzbezug; Server-Aktionen melden „Kein Datensatz ausgewählt“). Standard-Modi: Host-Aktionen `create` und `edit`, Server-Aktionen `edit`.
- `POST /api/workflow-drafts/.../commit-live` mit `dry_run=false` verlangt Admin-Recht (403 sonst); vorher war der Live-Commit nur im Frontend gesperrt.

Tests: `test_frame_actions.py` (`mandant.setup`, Host-Aktionen, State ohne UID), `test_mandant_access.py` (403 für Nicht-Superadmin, entfernte Endpunkte, Live-Commit nur Admin). Seed: `seed_frame_actions_v1.py` (Controls, Frame-Einträge, Workflow-IDs; entfernt die wirkungslosen Alt-Buttons `ASY_LOCK`/`ASY_PASSWORD` aus „Benutzer Edit“, die Control-Sätze bleiben).

## 4. Entscheidungen (getroffen 2026-11-15)

1. **Register im Backend, Control nur mit ID** statt frei konfigurierbarer Endpunkte in den Controls (ein Datenfehler könnte sonst beliebige Endpunkte aufrufen).
2. **Platzierung:** `field` und `header`.
3. **Ungespeicherte Änderungen:** Hinweis ausgeben, damit abgebrochen werden kann (statt Sperre oder automatisches Speichern).
4. **Nicht erlaubte Aktionen:** ausblenden (`when_denied = "disable"` je Control möglich).
5. **Typ `info`** als eigener Control-Typ.
6. **Erste Welle:** `edit_user` und Textvorlagen; Mandanten-Masken und Workflow-Builder danach.
7. **Sofortmaßnahme:** Admin-Prüfung vorab (umgesetzt).
8. **Wörterbuch:** eigener offener Punkt; D hält sich an Abschnitt 3.11.

## 5. Umsetzung (2026-11-15)

1. Sofortmaßnahme: Rollenprüfung an den `/api/users`-Endpunkten, Test (umgesetzt; die Endpunkte sind inzwischen durch das Register ersetzt).
2. `backend/app/core/frame_action_service.py` (Register, Prüfung, Zustände), Router `backend/app/api/frame_actions.py`, fünf Aktionen, Tests.
3. Frame-Runtime meldet unbekannte Aktions-IDs; Rechte und Zustände über `POST /api/frame-actions/state`.
4. `PdvmInputControl`: Typen `action` und `info` (`actionView`/`infoView`), Logik in `frontend/src/components/frames/frameActions.tsx` (Bedingungen, Zustände, Ablauf mit Hinweis/Bestätigung/Parametern/Ergebnis), eingebunden in `PdvmDialogPage` (Platzierung `field` im Raster, `header` in der Leiste).
5. Seed `backend/tools/seed_frame_actions_v1.py`: Controls und Frame-Einträge für `edit_user` (Frame `Benutzer Edit`) und die Textvorlagen-Frames; die festen Buttons und Anzeigen und die alten Endpunkte/Client-Aufrufe sind entfernt.
6. Doku: Regel 2.17, Anpassung 2.15/2.14 und 1.10a, Rendering-Spec (Abschnitte 4, 7, 12), `SERVICE_ARCHITECTURE`, Tools-README, Passwort- und Textvorlagen-Spec.

## 6. Offen

- `PdvmFrameForm` (Mandanten-Neuanlage) kann `action`/`info` nicht darstellen und überspringt sie (zurückgestellt; die Aktion `mandant.setup` liegt im Dialog „Mandanten bearbeiten“). Die Alt-Control-Sätze `ASY_LOCK`/`ASY_PASSWORD` sind gelöscht (Snapshot im Session-Ordner). Der Workflow-Builder ist nur per Typprüfung/Build, nicht im Browser getestet.
- Die Services `issue_password_reset`/`update_account_lock` prüfen selbst keine Rolle; Aufrufer müssen über das Register gehen.
- Meldungstexte der Handler im Wörterbuch (Rendering-Spec, Abschnitt 7, Nr. 8).

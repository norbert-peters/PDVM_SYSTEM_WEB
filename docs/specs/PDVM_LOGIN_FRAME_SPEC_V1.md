# PDVM Login als Frame: Passwort-Eingabe und öffentlicher Zugang V1

Status: **freigegeben und umgesetzt (2026-11-16)**, offener Punkt E der Rendering-Spec (Abschnitt 7, Nr. 3). Umgesetzt wie in Abschnitt 4 entschieden, einschließlich der Härtung F2 und F3. Abweichungen vom Entwurf: `CONFIGS.input {name, autocomplete}` gilt für `string` und `password_input` (statt `CONFIGS.password_input.autocomplete`); der Notfall-Rückfall baut dieselben drei Frames als Runtime-Modell im Code und nutzt denselben Renderer. F1: das Passwort des Kontos `admin@example.com` wurde zurückgesetzt (Snapshot im Session-Ordner). F2: Claim `pwc` (Laufzeit 15 min), `POST /auth/password-change` liefert danach ein vollwertiges Token. F3: einheitliche Meldung „E-Mail oder Passwort falsch“, Sperre nur nach korrektem Passwort sichtbar, Begrenzung (20 Fehlversuche je IP in 5 min; 5 Anfragen „Passwort vergessen“ je IP in 15 min), „Passwort vergessen“ antwortet immer gleich und versendet im Hintergrund. Betrifft Regel 2.15 (Frames), 2.4 (keine nativen Dialoge), 2.3 (API-Layer) und die Abschnitte 6 und 7 der Rendering-Spec. Entschieden ist bereits: vor der Anmeldung gibt es kein Theme der Sitzung, nur der zuletzt benutzte Hell/Dunkel-Modus wird angewendet (`THEMING_SYSTEM.md`, Abschnitt 6). Die Abschnitte 1 und 2 beschreiben den Stand **vor** der Umsetzung.

## 1. Ausgangslage

`frontend/src/components/Login.tsx` enthält drei Masken mit Roh-Eingabeelementen und festen Texten:

| Maske | Heute | Eingaben |
|---|---|---|
| Anmeldung | Karte im Code | E-Mail (`<input type="email">`), Passwort (`<input type="password">` mit Auge-Schalter) |
| Passwort vergessen | `PdvmDialogModal` mit Feldliste im Code | E-Mail |
| Passwort ändern (nach maschinellem Passwort) | `PdvmDialogModal` mit Feldliste im Code | neues Passwort, Bestätigung (mind. 12 Zeichen) |

Der Control-Typ `password` (Regel 2.15, Credential-Store) ist **nicht** geeignet: Er ist write-only, sein Feldwert ist der Name eines Zugangsdatensatzes, und er schreibt direkt nach `PUT /api/credentials/{name}`. Eine Anmeldung braucht das Gegenteil: ein Passwort, das nur bis zum Absenden im Speicher des Formulars steht.

Zwei Voraussetzungen fehlen: ein Eingabemodus für Passwörter ohne Speicherung und ein Weg, Frames **ohne Token** zu laden (`GET /api/frames/{uid}/runtime` verlangt heute `get_current_user`).

## 2. Befunde aus der Prüfung

| # | Befund | Schwere | Vorschlag |
|---|---|---|---|
| F1 | Die Schaltfläche „DEMO - Login“ enthält E-Mail und Passwort eines Admin-Kontos (`admin@example.com`) im Frontend-Code und damit im ausgelieferten Bundle. Wer das Bundle liest, kennt die Zugangsdaten; sie stehen außerdem in der Git-Historie. | hoch, wenn das Konto das Passwort noch hat | Schaltfläche **sofort entfernen**, Passwort des Kontos ändern (oder Konto sperren). Unabhängig von E. |
| F2 | Der Server stellt bei `password_change_required` ein vollwertiges Token aus; `get_current_user` prüft das Flag nicht. Das Wechsel-Fenster erzwingt nur das Frontend: Wer das Token direkt verwendet, umgeht den Passwortwechsel (und kann mit dem maschinellen Passwort alle API-Endpunkte nutzen). | mittel | Token mit Claim `pwc=true`: erlaubt nur `/auth/password-change` und `/auth/logout`; nach dem Wechsel stellt der Server ein neues Token ohne Claim aus. |
| F3 | Benutzer-Aufzählung: `/auth/login` unterscheidet „Falsche Email oder Passwort“ (unbekannt) von „Falsches Passwort. Verbleibende Versuche: N“ (bekannt) und „Account gesperrt“; `/auth/forgot-password` antwortet „E-Mail-Adresse nicht gefunden“ bzw. „stimmt nicht überein“. Die Sperre nach 5 Fehlversuchen lässt sich von außen gegen fremde Konten auslösen. | mittel | Einheitliche Meldung („E-Mail oder Passwort falsch“), keine Restversuche, bei „Passwort vergessen“ immer dieselbe Antwort („Falls die Adresse bekannt ist, wurde eine E-Mail gesendet“). Gründe nur im Log. Begrenzung je IP zusätzlich zur Kontosperre. Ändert sichtbares Verhalten, daher eigene Freigabe. |

F2 und F3 sind keine Voraussetzung für E, betreffen aber dieselbe Oberfläche; sie werden als eigener Härtungsschritt nach E vorgeschlagen (F2 zuerst).

## 3. Entwurf

### 3.1 Grundprinzip

Die Login-Masken sind Frames (Regel 2.15): Felder, Typen, Beschriftungen und Reihenfolge stehen in `sys_framedaten` und `sys_control_dict`. `Login.tsx` bleibt der **Host**: Er kennt den Ablauf (Anmelden, Passwort vergessen, Passwort ändern), die Schaltflächen und die API-Aufrufe, aber keine Felder. Es ist derselbe Zuschnitt wie bei `MandantCreate` (Frame für die Felder, Host für den Ablauf). Der Formularzustand ist lokal und wird nie gespeichert.

### 3.2 Neuer Control-Typ `password_input`

Eingabe eines Passworts, das **nicht** gespeichert wird (Gegenstück zum Credential-Typ `password`, der unverändert bleibt).

- Maskierte Eingabe als natives `<input type="password">` mit `name` und `autocomplete`, damit Passwort-Manager des Browsers arbeiten. Voraussetzung ist ein umschließendes `<form>` (Enter sendet).
- `CONFIGS.password_input`: `reveal` (Auge-Schalter, Standard `true`), `min_length`, `confirm_with` (Feldname; das Formular zeigt die Abweichung an, der Server prüft ebenfalls). `CONFIGS.input` (`name`, `autocomplete`) gilt für `string` und `password_input`.
- Der Wert lebt nur im Zustand des Formulars bis zum Absenden. Er wird nicht in `localStorage`, URL, Query-Cache, Logs oder Fehlermeldungen übernommen. Nach Fehlversuch wird das Feld geleert.
- Ein Frame mit `password_input` ist ein **flüchtiger** Frame (`ROOT.FRAME_TYPE = "public_form"`). Die Frame-Runtime meldet `password_input` in jedem anderen Frame als Fehler am Feld (`resolution_warning`), sodass kein Datensatz-Frame ein Passwortfeld bekommt (Rendering-Spec, Regel „keine Geheimnisse in Daten“).
- Registrierung nach der bekannten Liste (kein Backend-Typregister): `PdvmInputType` und `normalizeInputType` in `PdvmInputControl.tsx`, `normalizePicType` in `PdvmDialogPage.tsx`, `SIMPLE_FIELD_TYPES` in `frameRuntime.ts`.

### 3.3 Die drei Frames

| Frame | Felder (Gruppe `LOGIN`) |
|---|---|
| `Login` | `EMAIL` (`string`, `autocomplete=username`), `PASSWORD` (`password_input`, `current-password`) |
| `Passwort vergessen` | `BENUTZER` (`string`, `autocomplete=username`; aus dem Login-Feld vorbelegt), `EMAIL` (`string`, `autocomplete=email`; hinterlegte Adresse). Beide müssen zum Konto passen, siehe `PASSWORD_MANAGEMENT_SPEC.md` Abschnitt 6.1 |
| `Passwort ändern` | `NEW_PASSWORD`, `CONFIRM_PASSWORD` (`password_input`, `new-password`, `min_length=12`, `confirm_with`) |

Die UIDs sind feste Konstanten im Code (Allowlist, Abschnitt 3.4), angelegt durch `backend/tools/seed_login_frames_v1.py` (Controls und Frames, idempotent, Dry-Run Standard). Die Controls gehören zu keiner Datenbanktabelle (virtuelle Tabelle `auth_login`); ob die Frame-Runtime dafür eine Tabelle verlangt, ist vor der Umsetzung zu prüfen (Risiko, siehe Abschnitt 6).

Feste Renderertexte (Schaltflächen „Anmelden“, „Passwort vergessen?“, „Senden“, Meldungen) kommen aus `frontend/src/i18n/uiTexts.ts` (Vorbereitung für das Wörterbuch, Frame-Aktionen-Spec Abschnitt 3.11).

### 3.4 Öffentlicher Zugang

- `GET /api/public/login-frames?language=` liefert in **einer** Antwort die Runtime-Modelle der drei Frames; Router `backend/app/api/public_frames.py` ohne SQL, Logik in `backend/app/core/public_frame_service.py` (Regel 1.1).
- **Allowlist:** nur die drei festen UIDs. Es gibt keinen Parameter, mit dem ein anderer Frame angefordert werden kann; der bestehende, tokenpflichtige Endpunkt `/api/frames/{uid}/runtime` bleibt unverändert.
- **Inhalt:** nur Frame-Konfiguration (Felder, Typen, Beschriftungen). Der Service prüft, dass die Typen aus einer festen Menge stammen (`string`, `password_input`) und dass keine Aktionen, Dropdown-Quellen oder Tabellenbezüge enthalten sind; sonst Fehler (500 mit Klartext im Log, nicht in der Antwort).
- **Ohne Sitzung:** nutzt `frame_runtime_service.load_frame_runtime` mit `resolve_pool_scope(None)` (Systempool), also den vorhandenen Cache (30 s je Frame und Sprache).
- **Schutz:** `Cache-Control: public, max-age=300`; einfache Begrenzung je IP (in-memory), damit der Endpunkt nicht als Verstärker dient. Keine Geheimnisse, keine Mandanten- oder Benutzerdaten.
- **Sprache (Stand 2026-11-17):** `language` ist die zuletzt benutzte Sitzungssprache, die der Browser merkt (`localStorage` `pdvm_last_language`, geschrieben nach der Mandantenwahl aus `language` der Antwort von `POST /api/mandanten/select`: `USER.SETTINGS.LANGUAGE`, sonst `CONFIG.DEFAULT_LANGUAGE` des Mandanten). Ohne gemerkte Sprache gilt die Browsersprache, sonst Deutsch. Die Sprache bleibt beim Abmelden erhalten und gilt nur für die Anmeldemaske und die festen Texte (`frontend/src/i18n/uiLanguage.ts`, `uiTexts.ts` mit Wörterbuch DE/EN, Rückfall Deutsch); sie ist unabhängig von der Oberflächensprache nach der Anmeldung. Eine Sprachauswahl auf der Login-Karte gibt es nicht.

### 3.5 Frontend-Ablauf

- `Login.tsx` lädt die Frames mit einer Query (`['public','login-frames',lang]`, `staleTime` 5 min) über `src/api/client.ts` (`publicAPI.getLoginFrames`, Regel 2.3) und rendert sie mit `PdvmFrameForm` (`mode='create'`, ohne `savedData`).
- Die drei Masken sind **Zustände derselben Karte** (`login` → `forgot` | `change`); die beiden Modale mit Roh-Feldlisten entfallen. Hinweise und Ergebnisse weiterhin über `PdvmDialogModal` (Regel 2.4).
- **Notfall-Rückfall:** Schlägt das Laden fehl oder ist ein Frame ungültig, zeigt der Login ein fest eingebautes Minimalformular (E-Mail, Passwort) mit Standardtexten. Ein beschädigter Frame darf niemanden aussperren, der ihn reparieren müsste. Das ist die einzige Ausnahme von „keine Felder im Code“ und nur für diesen Fall.
- Die Schaltfläche „DEMO - Login“ entfällt (F1).
- Ablauf und API-Aufrufe (`authAPI.login`, `changePassword`, `forgotPassword`) bleiben unverändert; die Antworten werden nicht verändert (F2/F3 folgen separat).

### 3.6 Performance

Ein zusätzlicher kleiner Request vor dem Login, gecacht im Client (5 min), im Browser (`Cache-Control`) und auf dem Server (30 s). Solange er lädt, zeigt die Karte einen neutralen Ladezustand; der Notfall-Rückfall greift nach Fehler oder Zeitüberschreitung (3 s). Kein weiterer Request im Login-Pfad.

### 3.7 Sicherheit im Überblick

- Kein Passwort in URL, `localStorage`, Query-Cache, Logs oder Fehlertexten; Feld wird nach Fehlversuch geleert.
- Öffentlicher Endpunkt nur mit fester Allowlist und fester Typmenge; kein Zugriff auf Mandanten- oder Benutzerdaten.
- Das Frame darf kein Feld enthalten, das die Anmeldung umgeht (kein `action`-Typ, keine Skripte; Regel 2.17 bleibt bestehen).
- Befunde F1 bis F3 siehe Abschnitt 2.

### 3.8 Tests

- Backend (`test_public_frames.py`): ohne Token erreichbar; nur die drei UIDs; unbekannte Typen, Aktionen und Dropdown-Quellen im Frame werden abgelehnt; `password_input` in einem Frame ohne `FRAME_TYPE = public_form` wird als Fehler am Feld gemeldet (`test_frame_runtime.py`); Sprachrückfall.
- Frontend: Typprüfung, Build, Theme-Guard (Tokens statt Farben). Kein Browser-Test vorhanden; Ablauf einmal manuell (Anmelden, falsches Passwort, vergessen, Wechsel, Rückfall bei gestopptem Endpunkt).

## 4. Entscheidungen (zur Freigabe)

1. Neuer Typ `password_input`; der Typ `password` (Credential-Store) bleibt unverändert.
2. Öffentlicher Endpunkt `GET /api/public/login-frames` mit fester Allowlist; der tokenpflichtige Frame-Endpunkt bleibt.
3. `Login.tsx` bleibt Host (Ablauf und Schaltflächen); die Frames liefern die Felder.
4. Notfall-Rückfall mit fest eingebautem Minimalformular.
5. „Passwort vergessen“ und „Passwort ändern“ werden Zustände der Karte statt Modale.
6. F1 (Demo-Schaltfläche) sofort entfernen und das Passwort des Kontos ändern.
7. F2 (Token trotz Passwortwechsel) und danach F3 (einheitliche Meldungen, Begrenzung) als eigener Härtungsschritt nach E.

## 5. Umsetzungsschritte

1. F1: Schaltfläche entfernen (Frontend), Hinweis zum Passwort des Kontos.
2. `password_input` in `PdvmInputControl` (Typ, Registrierung, native Eingabe mit Formular, Auge, `confirm_with`), Prüfung in der Frame-Runtime (`FRAME_TYPE`), Tests.
3. `public_frame_service` und Router, Allowlist, Typprüfung, Cache und Begrenzung, Tests.
4. Seed `seed_login_frames_v1.py` (Dry-Run, Apply mit Snapshot), Konstanten der UIDs.
5. `Login.tsx` auf Frames umstellen (Zustände `login`/`forgot`/`change`, Rückfall), `publicAPI`, `uiTexts.ts`.
6. Typprüfung, Build, Theme-Guard, Gesamttests; manueller Test.
7. Doku: Rendering-Spec (Abschnitte 4, 6, 7), Regel 2.15, `SERVICE_ARCHITECTURE`, Tools-README, Tests-Tabelle.
8. Härtung F2, danach F3 (eigener Entwurf/Freigabe).

## 6. Offen und Risiken

- Prüfen vor Schritt 4: Verlangt `load_frame_runtime` für Controls eine existierende Tabelle (virtuelle Tabelle `auth_login`)? Falls ja, Ausnahme für Frames mit `FRAME_TYPE = public_form`.
- Der Pool für den Systemzugriff ohne Sitzung (`resolve_pool_scope(None)`) muss beim Start verfügbar sein; bei Ausfall greift der Notfall-Rückfall.
- Zurückgestellt: systemweites Login-Theme und Mandanten-Branding vor der Anmeldung, Sprachauswahl auf der Login-Karte, Wörterbuch für IT und weitere Sprachen, Zwei-Faktor-Anmeldung.
- Passwort-Richtlinie (Komplexität) bleibt serverseitig (`UserManager.validate_password_complexity`); das Frame zeigt nur `min_length`.

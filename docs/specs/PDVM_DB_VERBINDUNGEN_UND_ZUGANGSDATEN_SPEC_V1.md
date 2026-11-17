# PDVM Datenbankverbindungen und Zugangsdaten V1

Status: Backend umgesetzt am 2026-11-12 (Frontend-Maske und Überführung offen, siehe Abschnitt 7). Setzt Regel 1.2 (Single Source of Configuration) für verteilte Installationen fort.

## 1. Ziel

Das System besteht aus genau einer AUTH-DB (`auth`). Mit der Mandantenauswahl werden die Pfade zur zugehörigen System-DB und zur Mandanten-DB geöffnet. Alle drei Datenbanken können auf verschiedenen PostgreSQL-Instanzen liegen. Zugangsdaten dürfen dabei weder im Quellcode noch im Klartext in der Datenbank stehen.

## 2. Ist-Stand

- `backend/.env` enthält `DATABASE_URL_AUTH` (Host, Benutzer, Passwort der AUTH-DB). Alle Zugangsdaten sind Pflichtwerte, es gibt keine Defaults im Code.
- `asy_mandanten.daten.MANDANT` enthält `HOST`, `PORT`, `USER`, `PASSWORD`, `DATABASE` und `SYSTEM_DB` (Datenbankname).
- `ConnectionManager.get_mandant_config` (`backend/app/core/connection_manager.py`) baut System-DB- und Mandanten-DB-Verbindung aus **denselben** `HOST`, `PORT`, `USER`, `PASSWORD`; nur der Datenbankname unterscheidet sich. Ein leeres `PASSWORD` ist ein Fehler.
- `ConnectionManager.get_system_config` (Start und Login vor der Mandantenwahl) nutzt Host und Zugangsdaten der AUTH-DB.
- `app/api/mandanten.py` baut Verbindungen für die Mandantenanlage getrennt auf und fällt bei leerem `PASSWORD` (oder dem Wert `postgres`) auf die AUTH-Zugangsdaten zurück. Die beiden Wege verhalten sich also unterschiedlich.
- Aktuell: ein Datenbankserver, ein Passwort. Alle fünf Mandanten speichern dasselbe Passwort im Klartext in `asy_mandanten`.

Probleme:
1. Klartextpasswörter in der AUTH-DB; wer sie lesen kann, hat Zugriff auf alle Mandanten.
2. System-DB und Mandanten-DB können nicht auf verschiedenen Instanzen liegen.
3. Ein Passwortwechsel erfordert Änderungen an jedem Mandantensatz.
4. Zwei unterschiedliche Auflösungswege (`ConnectionManager` vs. `mandanten.py`).

## 3. Zielmodell

### 3.1 Verbindung = Adresse + Credential-Verweis

`asy_mandanten.daten.MANDANT` beschreibt Adressen, keine Geheimnisse:

| Feld | Bedeutung | Pflicht |
|---|---|---|
| `HOST`, `PORT`, `DATABASE`, `USER` | Mandanten-DB | `HOST`/`PORT`/`USER` optional (Standard: AUTH-Instanz), `DATABASE` Pflicht |
| `CREDENTIAL` | Name des Zugangsdatensatzes für die Mandanten-DB (z. B. `default`, `srv-berlin`) | optional |
| `SYSTEM_HOST`, `SYSTEM_PORT`, `SYSTEM_DB`, `SYSTEM_USER` | System-DB | optional, Standard: Werte der Mandanten-DB bzw. AUTH-Instanz; `SYSTEM_DB` Standard `pdvm_system` |
| `SYSTEM_CREDENTIAL` | Name des Zugangsdatensatzes für die System-DB | optional, Standard: `CREDENTIAL` |

Das Feld `PASSWORD` entfällt (siehe Migration).

### 3.2 Auflösung der Zugangsdaten (Reihenfolge)

Für jede Verbindung (Mandanten-DB, System-DB) in dieser Reihenfolge:
1. Zugangsdatensatz mit dem Namen aus `CREDENTIAL` / `SYSTEM_CREDENTIAL` aus dem Credential-Store.
2. Altfeld `MANDANT.PASSWORD` (nur im Übergang, mit Warnung im Log).
3. Zugangsdatensatz `default` aus dem Credential-Store.
4. Zugangsdaten der AUTH-DB (`DATABASE_URL_AUTH`), **nur wenn Host und Port der Verbindung die AUTH-Instanz bezeichnen** (`localhost`, `127.0.0.1` und `::1` gelten als gleich). Die AUTH-Zugangsdaten werden nie an eine fremde Instanz gesendet; dort ist ein fehlender Credential ein Fehler.

Der heutige Fall (alles auf einem Server) braucht daher keine zusätzliche Konfiguration. Wird ein genannter Zugangsdatensatz nicht gefunden, ist das ein Fehler (kein stilles Weiterfallen); der Fallback gilt nur für nicht genannte Namen.

Es gibt genau eine Auflösungsfunktion, `ConnectionManager.resolve_mandant_connections` (`backend/app/core/connection_manager.py`). Sie wird vom `ConnectionManager` und von `app/api/mandanten.py` (Mandantenwahl und Mandantenanlage) verwendet.

### 3.3 Credential-Store

Quelle der Zugangsdaten ist das Backend, nicht die Datenbank:
- Umgebungsvariable `PDVM_DB_CREDENTIALS` (JSON-Objekt, Name → `{ "user": ..., "password": ..., "ssl": true|false }`; `user` und `ssl` optional), Beispiel in `backend/.env.example`; hat Vorrang und ist nicht über die Oberfläche änderbar;
- ergänzend (seit 2026-11-14) in der AUTH-DB gespeicherte, verschlüsselte Zugangsdaten (`asy_credentials`, Schlüssel `PDVM_SECRET_KEY`), die über den Control-Typ `password` gesetzt werden (siehe [PDVM_FRAME_INPUT_RENDERING_SPEC_V1.md](./PDVM_FRAME_INPUT_RENDERING_SPEC_V1.md), Abschnitt 9);
- später austauschbar gegen einen Secret-Store (Docker/Kubernetes Secrets, Key Vault): der Zugriff läuft über `get_credential(name)` in `backend/app/core/credential_store.py`; ein anderer Anbieter wird per `set_credential_provider(...)` eingehängt, ohne Änderung der Datenmodelle.

Passwörter werden nie in Logs, API-Antworten oder Fehlermeldungen ausgegeben (`ConnectionConfig` und `Credential` maskieren das Passwort in `repr`). `ConnectionConfig.to_url()` kodiert Benutzer und Passwort URL-konform.

### 3.4 Datenbankrollen

- Je Server eine eigene Rolle mit Rechten nur auf die dort liegenden Datenbanken (kein `postgres`-Superuser im Betrieb).
- Die AUTH-Rolle erhält keinen Zugriff auf Mandanten-DBs, wenn diese auf anderen Instanzen liegen.
- Bei verteilten Instanzen ist die Verschlüsselung der Verbindung (`sslmode=require` oder strenger) Pflicht; sie wird je Credential oder Verbindung konfigurierbar.

## 4. Migration

1. ✅ Credential-Store und Auflösungsfunktion; `ConnectionManager` und `app/api/mandanten.py` nutzen sie.
2. ✅ Beim Lesen eines Mandanten mit vorhandenem `PASSWORD` gilt dieses weiter (Übergang), mit Warnung im Log.
3. ✅ Werkzeug `backend/tools/mandant_clear_passwords_v1.py` leert `MANDANT.PASSWORD` in `asy_mandanten`, aber nur, wenn die Auflösung ohne das Feld dasselbe Passwort liefert (Dry-Run als Standard, `--apply` mit `--confirm-backup` und `--snapshot`). Noch nicht ausgeführt.
4. ✅ `PASSWORD` ist im Mandantenmodell unzulässig: die 666-Vorlage von `asy_mandanten` enthält weder `MANDANT.PASSWORD` noch `SEND_EMAIL.SMTP_PASS` (entfernt 2026-11-13 mit `backend/tools/seed_mandant_frame_v1.py`), `POST /api/mandanten/create` lehnt beide Felder ab (`mandant_record_rules.py`). Bestehende Mandantensätze behalten das Altfeld, bis `mandant_clear_passwords_v1.py` läuft.
5. Passwortwechsel: nur noch an den Orten des Credential-Stores (`.env`); keine Änderung an Mandantensätzen nötig, sobald `PASSWORD` geleert ist.

## 5. Betroffener Code

- `backend/app/core/credential_store.py` (neu), `backend/app/core/config.py` (`PDVM_DB_CREDENTIALS`)
- `backend/app/core/connection_manager.py` (`resolve_mandant_connections`, `same_instance`, `get_mandant_config`)
- `backend/app/api/mandanten.py` (Mandantenwahl: Existenzprüfung der Mandanten-DB über die Verwaltungs-DB der Mandanten-Instanz, wenn System-DB und Mandanten-DB auf verschiedenen Instanzen liegen; Mandantenanlage)
- `backend/tools/mandant_clear_passwords_v1.py` (neu), `backend/test_connection_credentials.py` (neu)
- `backend/.env.example`, `README.md`

## 6. Entscheidungen (2026-11-12)

1. Credential-Store: Umgebungsvariable `PDVM_DB_CREDENTIALS` plus Schnittstelle `get_credential()` für spätere Secret-Stores.
2. Keine verschlüsselte Passwortablage in `asy_mandanten`; Passwörter stehen nur im Backend-Credential-Store.
3. Die System-DB wird je Mandant über die `SYSTEM_*`-Felder zugeordnet (mit eigener Adresse möglich).
4. Vorhandene Mandanten-Passwörter: Übergang bleibt bestehen, das Werkzeug zum Leeren ist vorhanden, wird aber erst nach Freigabe ausgeführt.

## 7. Offen

- ✅ Mandanten-Maske: Frame `Mandanten Edit` (`sys_framedaten`, UID `b7f0c1a2-5d3e-4c8a-9a61-3e2d7c5f4a10`) mit Controls `ASY_*` (`TABLE=asy_mandanten`), ohne `PASSWORD`, mit `CREDENTIAL`, `SYSTEM_*`, `SYSTEM_CREDENTIAL` und `SEND_EMAIL.CREDENTIAL`. Gerendert von `MandantCreate` über `PdvmFrameForm` (siehe [PDVM_FRAME_INPUT_RENDERING_SPEC_V1.md](./PDVM_FRAME_INPUT_RENDERING_SPEC_V1.md)). Der Dialog `Mandanten bearbeiten` nutzt dasselbe Frame; `DATABASE`, `HOST`, `PORT`, `SYSTEM_DB`, `SYSTEM_HOST` und `SYSTEM_PORT` sind dort unveränderlich (`CONTROL.IMMUTABLE`).
- `SMTP_PASS` wird über `SEND_EMAIL.CREDENTIAL` aus dem Credential-Store gelesen (`email_service.py`); das Altfeld gilt nur im Übergang. Bestehende `SMTP_PASS`-Werte sind am 2026-11-14 mit `migrate_smtp_credentials_v1.py` in den verschlüsselten Store überführt (Spec Frame-Rendering, Abschnitt 9); das Passwort wird im Mandanten-Frame über den Control-Typ `password` geändert.
- Pool-Verhalten bei Passwortwechsel: `PoolRegistry` schlüsselt Pools nach URL, ein geändertes Passwort erzeugt einen neuen Pool; die alten Pools bleiben bis zum Neustart offen.
- Die Werkzeuge in `backend/tools/` (`phase*`) lösen Mandanten-Verbindungen noch mit eigener Logik auf.

# PDVM System Web – Spezifikation: Passwortverwaltung

**Datum:** 29.01.2026  
**Status:** Freigegeben (Implementierung)

---

## 1. Ziele

- Sichere Passwort-Verwaltung mit verpflichtendem Wechsel bei Bedarf.
- Maschinell erzeugte Einmal-Passwörter (OTP) für Passwortänderung.
- Zustellkanal via Mandant-spezifischer E-Mail-Konfiguration.
- Konto-Sperrung auf Benutzer-Ebene.
- Einhaltung der [ARCHITECTURE_RULES.md](ARCHITECTURE_RULES.md).

---

## 2. Datenmodell

### 2.1 Mandant: E-Mail-Versandkonfiguration
**Tabelle:** sys_mandanten (JSONB `daten`)  
**Gruppe:** `SEND_EMAIL`

**Pflichtfelder** (minimal):
- `MAIL` (string) – Absender-Adresse

**Empfohlen (erweiterbar):**
- `SMTP_HOST` (string)
- `SMTP_PORT` (int)
- `SMTP_USER` (string)
- `CREDENTIAL` (string) – Name des Zugangsdatensatzes im Credential-Store (`.env` oder verschlüsselt in `asy_credentials`); liefert das SMTP-Passwort (und den Benutzer, falls `SMTP_USER` leer ist). Im Mandanten-Frame ist das Feld ein Control vom Typ `password` („SMTP-Passwort“)
- `SMTP_PASS` (string) – **entfernt** (2026-11-14 überführt, Regel 2.15); `save` lehnt das Feld ab. Die Konfiguration wird beim Versand frisch aus `asy_mandanten` gelesen
- `SMTP_TLS` (bool)
- `SMTP_SSL` (bool)
- `REPLY_TO` (string)
- `SENDER_NAME` (string)
- `OTP_RATE_LIMIT` (int) – maximale OTP-Ausgaben pro Zeitfenster (Testphase: 4)

**Hinweis:** Speicherung in `sys_mandanten` erfolgt ausschließlich über `PdvmCentralDatabase` (Rule 1.1).

### 2.2 Benutzer: Passwort-Status
**Tabelle:** sys_benutzer

**Spalten:**
- `passwort` (string, hash) – aktuelles Login-Passwort

**JSONB `daten` (Gruppe `SECURITY`)**:
- `PASSWORD_CHANGE_REQUIRED` (bool)
- `ACCOUNT_LOCKED` (bool)
- `LOCK_REASON` (string, optional)
- `PASSWORD_RESET_ISSUED_AT` (timestamp, server-seitig)
- `PASSWORD_RESET_EXPIRES_AT` (timestamp, server-seitig)
- `PASSWORD_RESET_TOKEN_HASH` (string)
- `PASSWORD_RESET_SEND_COUNT` (int)
- `PASSWORD_RESET_SEND_WINDOW_START` (timestamp)

**Hinweis:** `SYSTEM`-Gruppe bleibt Tabellen-Spalten vorbehalten (Rule 1.5).

---

## 3. Passwort-Reset (OTP) – Ablauf

### 3.1 Auslösen (Admin im Benutzer-Edit)
1. Admin klickt „Maschinelles Passwort senden“.
2. System generiert OTP (12 Zeichen, Policy siehe 5.1).
3. Speichere Hash in `sys_benutzer.passwort` (sofortige Ungültigkeit des alten Passworts).
4. Setze:
   - `SECURITY.PASSWORD_CHANGE_REQUIRED = true`
   - `SECURITY.PASSWORD_RESET_ISSUED_AT = now`
   - `SECURITY.PASSWORD_RESET_EXPIRES_AT = now + 120 Minuten`
   - `SECURITY.PASSWORD_RESET_TOKEN_HASH = <bcrypt>`
   - `SECURITY.PASSWORD_RESET_SEND_*` (Rate-Limit)
5. Versende E-Mail an den Benutzer mit OTP. Betreff und Text kommen aus der Textvorlage `PASSWORD_RESET` (Sprache des Benutzers, nur freigegebene Sprachfassungen, siehe [PDVM_TEXTVORLAGEN_SPEC_V1.md](./PDVM_TEXTVORLAGEN_SPEC_V1.md)); ist keine freigegebene Vorlage verfügbar, bricht der Ablauf ab, bevor das Passwort geändert wird.

### 3.2 Login mit OTP
1. Benutzer meldet sich mit OTP an.
2. System prüft:
   - `ACCOUNT_LOCKED` == false
   - `PASSWORD_CHANGE_REQUIRED` == true
   - `now <= PASSWORD_RESET_EXPIRES_AT`
3. Falls gültig: Benutzer wird zur Passwortänderung gezwungen.
4. Nach erfolgreicher Änderung:
   - `PASSWORD_CHANGE_REQUIRED = false`
   - `PASSWORD_RESET_*` Felder werden gelöscht/geleert
   - `passwort` wird mit neuem Passwort gehasht

### 3.3 Ablauf/Fehler
- OTP abgelaufen → Login verweigern + Hinweis.
- Admin kann neues OTP senden (überschreibt alte Daten).
- Falls E-Mail-Versand fehlschlägt: Admin erhält Meldung, **PASSWORD_CHANGE_REQUIRED bleibt aktiv**.

---

## 4. Account-Sperrung

- Feld: `SECURITY.ACCOUNT_LOCKED = true`.
- Login verweigern, unabhängig von Passwort.
- Optional: `LOCK_REASON` zur Anzeige/Protokollierung.

---

## 5. Sicherheits-Policy

### 5.1 OTP-Generierung
- Länge: 12 Zeichen.
- Mindest-Komplexität: Groß-/Kleinbuchstabe, Zahl, Sonderzeichen.

### 5.2 Passwort-Hashing
- Bestehendes Hash-Verfahren nutzen (aktuell bcrypt in Backend).
- Keine Klartext-Passwörter speichern.

---

## 6. API/Service-Design

### 6.1 Backend (FastAPI)
- Neue Services ausschließlich über `PdvmCentralDatabase` (Rule 1.1).
- **sys_benutzer**: Spalten-Update (`passwort`) über PdvmDatabase, JSONB über PdvmCentralDatabase.

**Endpoints:**
- Aktionen `user.password_reset` (OTP erzeugen + E-Mail senden), `user.lock` und `user.unlock` über `POST /api/frame-actions/{id}/run` (Rolle `admin`/`superadmin`, nur Benutzer des Sitzungsmandanten; siehe `PDVM_FRAME_ACTIONS_SPEC_V1.md`). Die früheren Endpunkte `/api/users/{uid}/…` sind entfernt.
- **Konto bei „Passwort vergessen“:** Eingegeben werden der **Benutzer** (Anmeldename, eindeutig; die Maske übernimmt ihn aus dem Login-Feld, sonst wird er abgefragt) und die dort **hinterlegte E-Mail-Adresse** (`USER.EMAIL`, Groß-/Kleinschreibung egal). Nur wenn beide zum selben Konto gehören, läuft derselbe Vorgang wie bei der Aktion „Maschinelles Passwort setzen“ (`issue_password_reset`: Passwort erzeugen, per Mail senden, `PASSWORD_CHANGE_REQUIRED` setzen). Request: `{benutzer, email}`. Bei unbekanntem Benutzer, fehlender hinterlegter Adresse oder abweichender Adresse wird nichts versendet (Grund nur im Log); die Antwort bleibt gleich. Die Mail geht an die hinterlegte `USER.EMAIL`.
- **Mandant bei „Passwort vergessen“ (ohne Sitzung):** `issue_password_reset(gcs=None)` bestimmt den Mandanten aus dem Benutzersatz: `MANDANTEN.DEFAULT`, dann `MANDANTEN.LIST`; gewählt wird der erste zugeordnete Mandant mit gesetztem `SEND_EMAIL.SMTP_HOST`. Daraus kommen SMTP-Konfiguration, `CONFIG.DEFAULT_LANGUAGE` und (sofern die Mandanten-DB erreichbar ist) die aktive Textvorlagenkopie, sonst gilt die Systemvorlage. Hat kein zugeordneter Mandant einen SMTP-Host, bricht der Reset vor jeder Änderung am Benutzer ab (Fehler im Log). Es wird nie ein nicht zugeordneter Mandant benutzt (früher: erster Mandant mit nicht-leerer `SEND_EMAIL`-Gruppe, dadurch kam keine Mail an). Mit Sitzung (Aktion `user.password_reset`) gilt der Session-Mandant.
- `POST /api/auth/password-change` → neues Passwort setzen (Current User)
- Seit 2026-11-16 (Login-Frame-Spec F2/F3): Bei `PASSWORD_CHANGE_REQUIRED` stellt `POST /api/auth/login` ein eingeschränktes Token aus (Claim `pwc`, 15 Minuten), das nur `/auth/password-change` und `/auth/logout` erlaubt; `password-change` liefert danach ein vollwertiges Token. Anmeldung und `POST /api/auth/forgot-password` antworten einheitlich (keine Benutzer-Aufzählung); die Sperre (`ACCOUNT_LOCKED`) wird nur nach korrektem Passwort gemeldet. Begrenzung je IP: 20 Fehlversuche in 5 Minuten (Anmeldung), 5 Anfragen in 15 Minuten („Passwort vergessen“; Versand im Hintergrund).

### 6.2 Frontend (React)
- Benutzer-Edit: Button „Maschinelles Passwort senden“ sowie „Account sperren/entsperren“ als Frame-Controls vom Typ `action` (Frame `Benutzer Edit`, Seed `seed_frame_actions_v1.py`)
- Anzeige: `PASSWORD_CHANGE_REQUIRED`, `ACCOUNT_LOCKED` als `info`-Controls
- Kein direkter SMTP/Email-Call im Frontend (Rule 2.3)

---

## 7. Logging & Audit

- Serverseitig loggen:
  - OTP ausgestellt (ohne Klartext)
  - Konto gesperrt/entsperrt
  - Passwort geändert

---

## 8. Offene Fragen / Optimierung

1. **OTP-Länge & Policy:** 12 Zeichen, Mindest-Komplexität.
2. **Speicherung OTP:** Hash zusätzlich in `SECURITY.PASSWORD_RESET_TOKEN_HASH` (passwort wird ebenfalls gesetzt).
3. **Email-Config:** `SEND_EMAIL` in `sys_mandanten`.
4. **Rate-Limiting:** Konfigurierbar via `SEND_EMAIL.OTP_RATE_LIMIT` (Testphase: 4).
5. **Lock-Reason UI:** "Der Account ist gesperrt. Bitte wenden Sie sich an den Administrator."
6. **Fallback E-Mail:** Fehlermeldung im Benutzer-Edit, `PASSWORD_CHANGE_REQUIRED` bleibt aktiv.
7. **Stichtag-Relevanz:** Unabhängig vom Stichtag (sys_benutzer ist nicht historisch).

---

## 9. Architektur-Regeln (Verweise)

- [ARCHITECTURE_RULES.md](ARCHITECTURE_RULES.md)
  - Rule 1.1: Central Database Gesetz
  - Rule 1.5: SYSTEM-Gruppe = Tabellen-Spalten
  - Rule 2.3: API-Layer Separierung

---

## 10. Nächste Schritte

1. Bestätigung der offenen Fragen.
2. API-Spezifikation finalisieren.
3. Implementierungsplan (Backend → Frontend → Tests).

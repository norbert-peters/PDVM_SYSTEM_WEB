# PDVM Textvorlagen V1

Status: umgesetzt am 2026-11-14 (Tabellen, Auflösung, Kopie in den Mandanten, Passwort-Mail) und erweitert (Freigabe je Sprache, HTML, Rolle `vorlagen`, Verwaltung als Frame/Dialog).

## 1. Ziel

Texte für Nachrichten (zunächst E-Mail) stehen nicht im Quellcode, sondern als sprachbezogene Vorlagen mit Platzhaltern in der Datenbank. Das System liefert Vorlagen mit; ein Mandant übernimmt sie, passt sie an und legt eigene an.

## 2. Tabellen

| Tabelle | Datenbank | Inhalt |
|---|---|---|
| `sys_textvorlagen` | pdvm_system | Systemvorlagen (zentrale Aufgaben), Quelle für die Mandanten |
| `msy_textvorlagen` | Mandanten-DB | Vorlagen des Mandanten (Kopien mit neuer UID, eigene Vorlagen) |

Beide haben die PDVM-Standardstruktur samt Basissätzen 000/555/666 (Regel 1.12). `sys_textvorlagen` wird von der System-Wartung (`PDVM_SYSTEM_TABLES`), `msy_textvorlagen` von der Mandanten-Wartung angelegt. Der Name „Textvorlagen“ vermeidet die Verwechslung mit den Template-Sätzen 555/666.

## 3. Satzstruktur

```json
{
  "ROOT": {
    "TABLE": "sys_textvorlagen", "SELF_GUID": "…", "SELF_NAME": "Passwort zurücksetzen (E-Mail)",
    "TEMPLATE_KEY": "PASSWORD_RESET",
    "CHANNEL": "email",
    "ACTIVE": true,
    "DESCRIPTION": "…",
    "VARIABLES": ["otp", "expires_minutes", "user_email"],
    "REQUIRED_VARIABLES": ["otp"],
    "SOURCE_UID": "…", "SOURCE_HASH": "…"
  },
  "DE-DE": {
    "SUBJECT": "PDVM Passwort zurücksetzen", "BODY": "…Passwort: {{otp}}…", "BODY_HTML": "<p>…{{otp}}…</p>",
    "STATUS": "approved", "VERSION": "v1.0.0", "APPROVED_BY": "…", "APPROVED_AT": "…"
  },
  "EN-US": { "SUBJECT": "PDVM password reset", "BODY": "…Password: {{otp}}…", "STATUS": "approved", "VERSION": "v1.0.0" }
}
```

- `TEMPLATE_KEY` ist der **stabile Schlüssel**, nach dem der Code sucht. Name und UID dürfen sich ändern, der Schlüssel nicht (ebenso unveränderlich: `CHANNEL`, `VARIABLES`, `REQUIRED_VARIABLES`).
- `ACTIVE` (nur `msy_textvorlagen`): Welche Vorlage eines Schlüssels im Mandanten gilt. Pro Schlüssel ist höchstens eine Vorlage aktiv; wird eine aktiviert, deaktiviert `after_write` die übrigen.
- `CHANNEL`: heute `email`; Vorlagen für weitere Kanäle (SMS, Brief) nutzen dieselben Tabellen.
- Pro Sprache eine Gruppe (Regel 2.13). Sprachcodes gemäß `backend/config/i18n_policy_v1.json` (`DE-DE`, `EN-US`, `IT-IT`), Aliase werden normalisiert (`i18n_policy.normalize_language`).
- `SOURCE_UID`/`SOURCE_HASH` (nur im Mandanten): Herkunft und Inhaltsstand der Systemvorlage beim Kopieren; nicht änderbar. Damit lässt sich später erkennen, dass die Systemvorlage neuer ist („übernehmen?“). Der Hash umfasst Schlüssel, Kanal, Variablen und die Sprachtexte, nicht UID, Name, Zeitstempel oder Freigabefelder.

## 4. Platzhalter

- Syntax `{{name}}`, Namen `a-z`, `0-9`, `_`. Reines Ersetzen, keine Ausdrücke, kein Code.
- `VARIABLES` deklariert die erlaubten, `REQUIRED_VARIABLES` die Pflichtvariablen (müssen im `BODY` vorkommen). `text_template_service.validate_template` prüft das beim Speichern (nicht deklarierte Platzhalter, fehlende Pflichtvariablen, leere Texte, fehlender Schlüssel). Beim Rendern ist ein Platzhalter ohne Wert ein Fehler.
- Der gerenderte Text kann Geheimnisse enthalten (z. B. das Einmalpasswort) und wird nicht geloggt.
- `BODY_HTML` (optional) ergänzt `BODY` als HTML-Alternative der Mail (`multipart/alternative`). Die Werte der Platzhalter werden HTML-maskiert, der Vorlagentext selbst nicht.

## 5. Freigabe je Sprache (Regel 1.19)

Jede Sprachgruppe hat `STATUS` (`Textvorlagen::status`, Modell `backend/config/i18n_language_release_model_v1.json`). Nur `approved` wird versendet.

- Eine Textänderung (`SUBJECT`, `BODY`, `BODY_HTML`) setzt die Sprache auf `review` (neue Sprache: `new`); `APPROVED_BY`/`APPROVED_AT` werden geleert.
- Freigabe = erneutes Speichern mit `STATUS = approved` durch eine berechtigte Rolle. Der Guard setzt `APPROVED_BY`, `APPROVED_AT` und erhöht die Patch-Version (`v1.0.0` → `v1.0.1`). Ein geänderter, bisher freigegebener Text wird nie automatisch freigegeben.
- Die Freigabefelder und `VERSION` sind im Frame schreibgeschützt (`READ_ONLY`).

## 6. Rechte

Die Rollen stehen in `asy_benutzer.daten.PERMISSIONS.ROLES` (`security.normalized_roles`, `security.has_vorlagen_rights`).

| Tabelle | Bearbeiten und freigeben |
|---|---|
| `sys_textvorlagen` | `vorlagen`, `superadmin` |
| `msy_textvorlagen` | `admin`, `man_admin`, `superadmin`, `vorlagen` |

Durchgesetzt wird im Backend: `central_write_service` ruft für beide Tabellen `text_template_service.guard_write` (vor dem Schreiben) und `after_write` (danach) auf. **Voraussetzung:** Der Aufrufer übergibt `gcs`; ohne Session (Seeds, Kopie in den Mandanten) gilt der Vorgang als vertrauenswürdig und wird nur normalisiert und geprüft. Der Dialog-Pfad (`PdvmCentralDatabase.save_all_values(gcs=…)`) reicht die Session durch (Regressionstest in `test_text_templates.py`).

## 7. Auflösung (`text_template_service.load_candidates`, `select_group`)

Kandidaten in dieser Reihenfolge:

1. Die aktive Vorlage des Mandanten (`msy_textvorlagen`, `ROOT.ACTIVE = true`) mit diesem Schlüssel.
2. Die Systemvorlage (`sys_textvorlagen`).

Ohne Mandanten-DB (z. B. „Passwort vergessen“ vor der Anmeldung) gilt direkt die Systemvorlage. Gewählt wird die erste **freigegebene** Sprache der Kette, zuerst in der Mandantenvorlage, dann in der Systemvorlage. So bleibt der Versand möglich, wenn der Mandant einen Text ändert und noch nicht freigegeben hat. Gibt es keine freigegebene Sprache, ist das ein Fehler (`NoApprovedLanguageError`), der **vor** jeder Änderung am Benutzer auftritt.

**Sprache** (`language_chain`): Sprache des Empfängers (`SETTINGS.LANGUAGE`) → `CONFIG.DEFAULT_LANGUAGE` des Mandanten (optional) → `DEFAULT_LANGUAGE` der I18N-Policy.

## 8. Kopie in den Mandanten und Kopie einer Vorlage

`ensure_mandant_templates` kopiert beim Mandantenwechsel (`POST /api/mandanten/select`, nach dem Anlegen der Session) jede Systemvorlage, die der Mandant noch nicht hat, nach `msy_textvorlagen`: neue UID, `SOURCE_UID`, `SOURCE_HASH`, `ACTIVE = true`; Freigabestand und Version werden übernommen. Eine Vorlage gilt als übernommen, solange ein Satz mit dieser `SOURCE_UID` existiert; der Mandant darf ihn umbenennen und ändern. Gelöschte oder geänderte Kopien werden nicht erneut überschrieben. Die Prüfung läuft höchstens alle 15 Minuten je Pool; ein Fehler blockiert die Anmeldung nicht (Warnung im Log). Fehlt die Tabelle noch (Mandanten-Wartung läuft beim selben Login davor), passiert nichts.

`POST /api/frame-actions/texttemplate.copy/run` (Button „Kopie anlegen“ im Dialog, Control `MSY_ACTION_COPY`) legt eine Kopie in derselben Tabelle an: neue UID, inaktiv, alle Sprachen im Status `review`. Aktivieren und Freigeben erfolgen danach im Frame.

**Systemvorlage ist neuer:** `source_status` vergleicht den gespeicherten `ROOT.SOURCE_HASH` mit dem Hash der aktuellen Systemvorlage (`has_source`, `source_missing`, `outdated`, `adopted_uid`) und ist der Zustand der Aktion `texttemplate.adopt_source` (`POST /api/frame-actions/state`). Der Dialog zeigt bei `outdated` den Hinweis „Die Systemvorlage … ist neuer als diese Kopie“ (`info`-Control `MSY_INFO_SOURCE_OUTDATED`) mit der Schaltfläche **Neue Systemfassung übernehmen** (`MSY_ACTION_ADOPT_SOURCE`, Aktion `texttemplate.adopt_source/run`). Die Übernahme legt die aktuelle Systemfassung als **neue, inaktive Kopie** an (Name `<Vorlage> (Systemstand <Datum>)`, Sprachen `review`, `SOURCE_HASH` = aktueller Stand); die bisherige Mandantenvorlage bleibt unverändert und der Hinweis verschwindet, sobald eine Kopie mit dem aktuellen Stand existiert. Nichts wird überschrieben; Prüfen, Freigeben und Aktivieren erfolgen im Frame. Rollen: wie die Pflege der Tabelle (Abschnitt 6). Controls und Frame-Einträge legt `seed_frame_actions_v1.py` an.

**Nachlieferung in bestehende Mandanten (DATA_UPDATE, Regel 1.20):** `backend/tools/mandant_textvorlagen_update_v1.py` läuft über alle Mandanten (`asy_mandanten`, Verbindungen über `ConnectionManager`, Standard Dry-Run, `--apply --confirm-backup`, optional `--mandant <UID>`): legt fehlende Basissätze 000/555/666 an und kopiert fehlende Systemvorlagen (`ensure_mandant_templates(force=True)`). Nur Inserts, wiederholbar ohne Seiteneffekt. Fehlt `msy_textvorlagen` noch, wird der Mandant übersprungen (Tabelle legt die Mandanten-Wartung beim Login an) oder mit `--with-maintenance` (nur mit `--apply`) über dieselbe Wartung angelegt. Die Versionsachsen führt weiterhin `mandant_update_apply_v1.py`.

## 9. Performance und Konsistenz

- Aufgelöste Kandidaten sind je Pool und Schlüssel 30 s gecacht; jeder Schreibzugriff über `PdvmDatabase` auf `sys_textvorlagen`/`msy_textvorlagen` leert den Cache.
- Ein Versand braucht höchstens zwei kleine Abfragen; Mails sind selten.

## 10. Verwaltung (Frames, Dialoge, Menü)

Seed `backend/tools/seed_text_template_dialogs_v1.py` (idempotent) legt an: Controls `MSY_*` in `sys_control_dict`, das Dropdown `Textvorlagen::status`, die Frames „Textvorlagen Edit (Mandant)“ und „(System)“, je eine View und einen Dialog sowie die Menüeinträge „Textvorlagen (Mandant)“ und „Textvorlagen (System)“. Die Einträge liegen im Menüzweig **Systemtabellen pflegen** (Admin-Administration); `seed_systemtabellen_menu_v1.py` hängt sie dorthin um (siehe unten). Das Menü selbst hat keine Rollenbeschränkung; die Durchsetzung liegt im Backend (Abschnitt 6). Die Rolle `vorlagen` wird wie `overlay` in `PERMISSIONS.ROLES` vergeben.

**Menüzweige der Systemtabellen** (Admin-Administration): *Systemtabellen lesen*, *Systemtabellen (JSON) pflegen* (Dialoge mit `edit_json`, Rohdaten) und *Systemtabellen pflegen* (Dialoge mit Frame-Maske, z. B. `pdvm_edit`: Mandanten, Textvorlagen). Neue Frame-Dialoge werden im Zweig „Systemtabellen pflegen“ eingehängt; `seed_systemtabellen_menu_v1.py` sortiert nach dem effektiven Edit-Typ des Dialogs (idempotent). Das hält die Dropdowns kurz, die seitlich aufgehenden Untermenüs vertragen kein `overflow`/Scrollen.

## 11. Verwendung

- `password_reset_service.issue_password_reset`: Vorlage `PASSWORD_RESET`, Variablen `otp`, `expires_minutes`, `user_email`; Versand über `email_service.send_email(..., html=…)`. Gilt für „Passwort vergessen“ und „Maschinelles Passwort senden“.
- Vorlagen `PASSWORD_RESET` in `DE-DE` und `EN-US` (freigegeben): Seed `backend/tools/seed_text_templates_v1.py` (idempotent, überschreibt nie; ergänzt fehlende Freigabefelder).

## 12. Offen

1. Kontext-Variablen wie Mandantenname oder Anrede.
2. Die Systemvorlage ist neuer: Übernahme heute nur als neue Kopie; ein gezieltes Zusammenführen einzelner Sprachen (Vergleichsansicht) gibt es nicht.
3. Mandanten-DBs ohne `msy_textvorlagen` bekommen die Tabelle beim nächsten Login oder mit `mandant_textvorlagen_update_v1.py --with-maintenance --apply`.

Erledigt: Hinweis „Systemvorlage ist neuer“ mit Übernahme (Abschnitt 8), `CONFIG.DEFAULT_LANGUAGE` als Dropdown im Mandanten-Frame (Rendering-Spec, Abschnitt 11), Nachlieferung der Vorlagen und Basissätze in bestehende Mandanten (Abschnitt 8).

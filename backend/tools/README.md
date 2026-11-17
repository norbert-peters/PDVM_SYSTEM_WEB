# backend/tools

Einzige Ablage fuer Werkzeuge. Einmal-Skripte liegen in `backend/_archive_scripts/` und werden nicht mehr gepflegt.

## Aktive Werkzeuge (Phase 1/2, 06.11.2026)

| Werkzeug | Zweck | Schreibt? |
|---|---|---|
| `audit_system_data.py` | Audit der Systemdaten gegen `ARCHITECTURE_RULES.md` (Bericht als Markdown) | nein |
| `seed_base_records.py` | Seeder/Pruefung Basissaetze 000/555/666 (Dry-Run, `--check`, `--apply`) | nur mit `--apply --confirm-backup` |
| `measure_runtime.py` | Laufzeitmessung gegen laufendes Backend (Zugangsdaten per `PDVM_USER`/`PDVM_PASSWORD`) | nein |
| `profile_cold_path.py` | Login und Mandantenwahl im Prozess profilieren (zählt DB-Verbindungsaufbauten je Aufrufer) | nein |
| `mandant_clear_passwords_v1.py` | Entfernt das veraltete `MANDANT.PASSWORD` aus `asy_mandanten`, wenn die Auflösung ohne das Feld dasselbe Passwort liefert (Dry-Run Standard; Snapshot enthält Klartext, nicht ins Repo) | nur mit `--apply --confirm-backup --snapshot` |
| `seed_mandant_frame_v1.py` | Legt Frame `Mandanten Edit` und die `ASY_*`-Controls an, bereinigt die 666-Vorlage von `asy_mandanten` (Passwörter raus, `CREDENTIAL` rein, neutrale Vorgaben); idempotent (Dry-Run Standard; Snapshot enthält Klartext, nicht ins Repo) | nur mit `--apply --confirm-backup --snapshot` |
| `seed_text_templates_v1.py` | Legt `sys_textvorlagen` an und seedet die Systemvorlagen (`PASSWORD_RESET`, DE-DE/EN-US, freigegeben); ergänzt fehlende Freigabefelder; überschreibt nie (Dry-Run Standard). Danach `seed_base_records.py --db pdvm_system --apply` für die Basissätze | nur mit `--apply --confirm-backup` |
| `seed_text_template_dialogs_v1.py` | Legt Controls `MSY_*`, Dropdown `Textvorlagen::status`, Frames, Views, Dialoge und Menüeinträge „Textvorlagen (Mandant/System)“ an; idempotent (Dry-Run Standard) | nur mit `--apply --confirm-backup --snapshot` |
| `seed_systemtabellen_menu_v1.py` | Teilt den Admin-Menüzweig „Systemtabellen bearbeiten“ in „Systemtabellen (JSON) pflegen“ (JSON-Dialoge) und „Systemtabellen pflegen“ (Frame-Dialoge, z. B. `pdvm_edit`); sortiert nach effektivem Edit-Typ; idempotent (Dry-Run Standard); nach `seed_text_template_dialogs_v1.py` ausführen | nur mit `--apply --confirm-backup --snapshot` |
| `seed_mandant_language_v1.py` | Legt Dropdown `Sprachen::sprache`, Control `ASY_CONFIG_DEFAULT_LANGUAGE` und den Frame-Eintrag „Standardsprache (Texte)“ im Frame `Mandanten Edit` an; idempotent (Dry-Run Standard) | nur mit `--apply --confirm-backup --snapshot` |
| `mandant_textvorlagen_update_v1.py` | DATA_UPDATE `textvorlagen`: liefert fehlende Basissätze 000/555/666 und fehlende Systemvorlagen in alle Mandanten-DBs nach (nur Inserts, idempotent; `--mandant <UID>`, `--with-maintenance` legt fehlende Tabellen über die Mandanten-Wartung an) | nur mit `--apply --confirm-backup` |
| `seed_frame_actions_v1.py` | Legt die Controls `action`/`info` (Passwort senden, Sperren/Entsperren, Anzeigen; Kopie anlegen, Systemvorlage ist neuer; Mandanten-Datenbankaufbau) und ihre Frame-Einträge in `Benutzer Edit`, `Mandanten Edit` und den Textvorlagen-Frames an, trägt die Aktions-IDs `workflow.*` in die Workflow-Controls ein, entfernt die wirkungslosen Alt-Buttons aus `Benutzer Edit`; zieht abweichende Konfigurationen bestehender Controls nach; idempotent (Dry-Run Standard). Aktionen selbst stehen im Backend-Register (Regel 2.17) | nur mit `--apply --confirm-backup --snapshot` |
| `fix_mojibake_v1.py` | Repariert doppelt kodierte UTF-8-Zeichen (`zurÃ¼cksetzen` → `zurücksetzen`) in Quelldateien; Zeilenenden/BOM bleiben (Dry-Run Standard, Pfad `app`; **nicht** auf das ganze Repo anwenden) | nur mit `--apply` |
| `seed_mandant_dialog_v1.py` | Führt `CONTROL.IMMUTABLE` ein (Muttercontrol 666, `SYS_IMMUTABLE`, Control-Frame), setzt es an den Mandanten-Verbindungsfeldern und legt View, Dialog und Menüeintrag zum Bearbeiten von Mandanten an; idempotent (Dry-Run Standard) | nur mit `--apply --confirm-backup --snapshot` |
| `seed_mandant_menu_v1.py` | Legt den Menüpunkt „Neuer Mandant“ (`go_mandant_create`, `roles: ["superadmin"]`) hinter „Mandanten bearbeiten“ im Menü Admin-Administration an; idempotent (Dry-Run Standard) | nur mit `--apply --confirm-backup --snapshot` |
| `seed_immutable_after_v1.py` | Führt `CONTROL.IMMUTABLE_AFTER` ein (Muttercontrol 666, Control `SYS_IMMUTABLE_AFTER`, Control-Frame) und setzt `ROOT.DB_CREATED_AT` an den unveränderlichen Mandanten-Verbindungsfeldern (bedingte Sperre); idempotent (Dry-Run Standard) | nur mit `--apply --confirm-backup --snapshot` |
| `seed_login_frames_v1.py` | Legt die öffentlichen Login-Frames (`Login`, `Passwort vergessen`, `Passwort ändern`, `FRAME_TYPE public_form`) und ihre Controls (Typen `string`, `password_input`) an; Frame-UIDs fest aus `public_frame_service.LOGIN_FRAME_UIDS`; idempotent (Dry-Run Standard) | nur mit `--apply --confirm-backup --snapshot` |
| `migrate_smtp_credentials_v1.py` | Überführt `SEND_EMAIL.SMTP_PASS` der Mandanten verschlüsselt nach `asy_credentials` (Name `mail-<UID>`), entfernt es aus `daten` und `daten_backup`, stellt das Control auf Typ `password` um; idempotent, vergleicht vor dem Entfernen (Dry-Run Standard, braucht `PDVM_SECRET_KEY`) | nur mit `--apply --confirm-backup` |

Phase-5-Migrationen (07.11.2026, einmalig angewandt, alle mit Dry-Run als Standard und Snapshot in `backend/reports/`; nicht erneut ausführen, ohne vorher Backup und Dry-Run zu prüfen):

| Werkzeug | Zweck |
|---|---|
| `phase5_normalize_control_dict.py` | `sys_control_dict`: `FELD` entfernen, Namen nach Regel 1.10 korrigieren, Dubletten löschen |
| `phase5_normalize_frames.py` | Frames: inline definierte Felder als Controls anlegen, Layout-Keys GROSS (benötigt `--golden`) |
| `phase5_frame_golden.py` | Golden-Master `capture`/`compare` der aufgelösten Frame-Definitionen (Pflicht vor/nach Frame-Migration) |
| `phase5_revert_frames.py` | Frame-Migration aus dem Snapshot zurücknehmen |
| `phase5_fix_misc.py` | Menü-Tabellennamen, `SYS_PRENT_GUID`, Views `**SYSTEM`, Dropdowns, Dialoge |

Weitere dauerhaft genutzte Gruppen: `mandant_update_*`, `validate_*`, `audit_*`, `release_workflow_*`, `backup_pdvm_system_snapshot.py`, `smoke_test_dialog_api.py`.

## Historische Einmal-Skripte in diesem Ordner
`phase*`, `migrate_*`, `create_*`, `fix_*`, `import_*_from_sqlite`, `normalize_*`, `dialog_fix_*`, `dialog_migrate_*`, `setup_*` u. a. sind abgeschlossene Migrationen (Berichte siehe `backend/reports/`). Sie bleiben vorerst hier, weil Spezifikationen unter `docs/specs/` auf sie verweisen. Eine Verlagerung ins Archiv erfolgt, sobald diese Verweise angepasst sind.

## Konventionen
- Aufruf aus `backend/`: `..\.venv\Scripts\python.exe tools\<name>.py`
- Datenaendernde Werkzeuge: Standard ist Dry-Run, `--apply` nur mit Backup, Snapshot der betroffenen Zeilen und Protokoll.
- Reservierte Saetze (UID-Serien `0...`, `5...`, `6...`) nur mit ausdruecklicher Freigabe aendern.
- Windows-Konsole: `PYTHONUTF8=1` setzen (Emojis in Ausgaben).

# backend/tools

Einzige Ablage fuer Werkzeuge. Einmal-Skripte liegen in `backend/_archive_scripts/` und werden nicht mehr gepflegt.

## Aktive Werkzeuge (Phase 1/2, 06.11.2026)

| Werkzeug | Zweck | Schreibt? |
|---|---|---|
| `audit_system_data.py` | Audit der Systemdaten gegen `ARCHITECTURE_RULES.md` (Bericht als Markdown) | nein |
| `seed_base_records.py` | Seeder/Pruefung Basissaetze 000/555/666 (Dry-Run, `--check`, `--apply`) | nur mit `--apply --confirm-backup` |
| `measure_runtime.py` | Laufzeitmessung gegen laufendes Backend (Zugangsdaten per `PDVM_USER`/`PDVM_PASSWORD`) | nein |
| `profile_cold_path.py` | Login und Mandantenwahl im Prozess profilieren (zählt DB-Verbindungsaufbauten je Aufrufer) | nein |

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

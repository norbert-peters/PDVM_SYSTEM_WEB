"""
Standardsprache des Mandanten (`CONFIG.DEFAULT_LANGUAGE`) als Dropdown im Mandanten-Frame.

Spezifikation: docs/specs/PDVM_TEXTVORLAGEN_SPEC_V1.md (Sprachkette), Regel 2.16 (Dropdowns nur in sys_dropdowndaten).

Schritte (idempotent):
1. sys_dropdowndaten: `Sprachen::sprache` (Optionen DE-DE, EN-US, IT-IT; Beschriftung je Sprache).
2. sys_control_dict: `ASY_CONFIG_DEFAULT_LANGUAGE` (TABLE asy_mandanten, Gruppe CONFIG, Typ dropdown).
3. sys_framedaten: Control im Frame `Mandanten Edit` (Tab 1, nach den vorhandenen Feldern).

Aufruf aus backend/ (Standard ist Dry-Run):
  ..\\.venv\\Scripts\\python.exe tools\\seed_mandant_language_v1.py
  ..\\.venv\\Scripts\\python.exe tools\\seed_mandant_language_v1.py --apply --confirm-backup --snapshot <Pfad.json>
"""
from __future__ import annotations

import argparse
import asyncio
import copy
import json
import sys
import uuid
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.core.mandant_record_rules import MANDANT_FRAME_GUID, MANDANT_TABLE  # noqa: E402
from app.core.pdvm_datetime import now_pdvm_str  # noqa: E402
from audit_system_data import U666, as_dict, load_env_url  # noqa: E402
from seed_base_records import connect  # noqa: E402

NS = uuid.UUID("6f1a5b0e-2a0c-4d6b-9b3e-5d1f0c7a9e11")
DROPDOWN_UID = str(uuid.uuid5(NS, "dropdown:sprachen_sprache"))
DROPDOWN_NAME = "Sprachen::sprache"
CONTROL_NAME = "ASY_CONFIG_DEFAULT_LANGUAGE"
CONTROL_UID = str(uuid.uuid5(NS, f"control:{CONTROL_NAME}"))
FRAME_TAB = 1
FRAME_ORDER = 80
LANGUAGES = {
    "DE-DE": {"DE-DE": "Deutsch", "EN-US": "German", "IT-IT": "Tedesco"},
    "EN-US": {"DE-DE": "Englisch", "EN-US": "English", "IT-IT": "Inglese"},
    "IT-IT": {"DE-DE": "Italienisch", "EN-US": "Italian", "IT-IT": "Italiano"},
}
DROPDOWN_CONFIG = {"key": DROPDOWN_UID, "feld": "", "table": "sys_dropdowndaten", "gruppe": "", "label_language": "own"}


def root_block(table: str, uid: str, name: str, stamp: str, **extra) -> dict:
    return {
        "TABLE": table, "SELF_GUID": uid, "SELF_NAME": name, "SELF_LINK_UID": uid,
        "SELF_CREATED_AT": stamp, "SELF_MODIFIED_AT": stamp, "SELF_GILT_BIS": "9999365.99999",
        "STRUCT_VERSION_APPLIED": 1, **extra,
    }


def build_dropdown(stamp: str) -> dict:
    return {
        "ROOT": root_block("sys_dropdowndaten", DROPDOWN_UID, DROPDOWN_NAME, stamp, FIELD_KEY="sprachen_sprache",
                           RECORD_TYPE="dropdown_definition", DEFAULT_LANGUAGE="DE-DE",
                           SUPPORTED_LANGUAGES=["DE-DE", "EN-US"]),
        "OPTIONS": copy.deepcopy(LANGUAGES),
    }


def build_control(mother: dict, stamp: str) -> dict:
    ctrl = copy.deepcopy(mother)
    ctrl.pop("FELD", None)
    ctrl.update({
        "NAME": CONTROL_NAME, "FIELD": "DEFAULT_LANGUAGE", "TYPE": "dropdown", "LABEL": "Standardsprache (Texte)",
        "TABLE": MANDANT_TABLE, "GRUPPE": "CONFIG",
        "CONFIGS": {"dropdown": copy.deepcopy(DROPDOWN_CONFIG)},
    })
    return {"ROOT": root_block("sys_control_dict", CONTROL_UID, CONTROL_NAME, stamp), "CONTROL": ctrl}


async def run(args) -> int:
    stamp = now_pdvm_str()
    system = await connect(load_env_url(), "pdvm_system", read_only=not args.apply)
    try:
        writes: list[tuple[str, tuple]] = []
        log: list[str] = []
        before: dict = {}

        async def missing(table: str, uid: str) -> bool:
            return not await system.fetchval(f"select 1 from {table} where uid = $1::uuid", uid)

        if await missing("sys_dropdowndaten", DROPDOWN_UID):
            writes.append(("insert into sys_dropdowndaten (uid, name, daten, historisch, link_uid) "
                           "values ($1::uuid, $2, $3::jsonb, 0, $1::uuid)",
                           (DROPDOWN_UID, DROPDOWN_NAME, json.dumps(build_dropdown(stamp), ensure_ascii=False))))
            log.append(f"Dropdown {DROPDOWN_NAME}")
        else:
            # vorhandenen Satz nur ergaenzen: fehlende Sprachbezeichnungen (Eigennamen), nichts ueberschreiben
            dropdown = as_dict(await system.fetchval("select daten from sys_dropdowndaten where uid = $1::uuid", DROPDOWN_UID))
            options = dropdown.setdefault("OPTIONS", {})
            added = 0
            for code, labels in LANGUAGES.items():
                entry = options.setdefault(code, {})
                for lang, text in labels.items():
                    if lang not in entry:
                        entry[lang] = text
                        added += 1
            if added:
                before["dropdown"] = as_dict(await system.fetchval("select daten from sys_dropdowndaten where uid = $1::uuid", DROPDOWN_UID))
                dropdown["ROOT"]["SELF_MODIFIED_AT"] = stamp
                writes.append(("update sys_dropdowndaten set daten=$1::jsonb, modified_at=now() where uid=$2::uuid",
                               (json.dumps(dropdown, ensure_ascii=False), DROPDOWN_UID)))
                log.append(f"Dropdown {DROPDOWN_NAME}: {added} Sprachbezeichnung(en) ergaenzt")

        if await missing("sys_control_dict", CONTROL_UID):
            clash = await system.fetchval("select uid::text from sys_control_dict where name = $1", CONTROL_NAME)
            if clash:
                raise SystemExit(f"Controlname {CONTROL_NAME} ist bereits mit anderer UID vergeben")
            mother = as_dict(await system.fetchval("select daten from sys_control_dict where uid = $1::uuid", U666))["CONTROL"]
            writes.append(("insert into sys_control_dict (uid, name, daten, historisch, link_uid) "
                           "values ($1::uuid, $2, $3::jsonb, 0, $1::uuid)",
                           (CONTROL_UID, CONTROL_NAME, json.dumps(build_control(mother, stamp), ensure_ascii=False))))
            log.append(f"Control {CONTROL_NAME}")
        else:
            row = as_dict(await system.fetchval("select daten from sys_control_dict where uid = $1::uuid", CONTROL_UID))
            configs = as_dict(as_dict(row.get("CONTROL")).get("CONFIGS"))
            if as_dict(configs.get("dropdown")).get("label_language") != "own":
                before["control"] = copy.deepcopy(row)
                row["CONTROL"].setdefault("CONFIGS", {})["dropdown"] = copy.deepcopy(DROPDOWN_CONFIG)
                row["ROOT"]["SELF_MODIFIED_AT"] = stamp
                writes.append(("update sys_control_dict set daten=$1::jsonb, modified_at=now() where uid=$2::uuid",
                               (json.dumps(row, ensure_ascii=False), CONTROL_UID)))
                log.append(f"Control {CONTROL_NAME}: Eigenbezeichnung der Sprachen (label_language=own)")

        frame = as_dict(await system.fetchval("select daten from sys_framedaten where uid = $1::uuid", MANDANT_FRAME_GUID))
        if not frame:
            raise SystemExit("Frame 'Mandanten Edit' nicht gefunden (zuerst seed_mandant_frame_v1.py)")
        if CONTROL_UID not in frame.get("FIELDS", {}):
            before["frame"] = copy.deepcopy(frame)
            frame.setdefault("FIELDS", {})[CONTROL_UID] = {"TAB": FRAME_TAB, "DISPLAY_ORDER": FRAME_ORDER}
            frame["ROOT"]["SELF_MODIFIED_AT"] = stamp
            writes.append(("update sys_framedaten set daten=$1::jsonb, modified_at=now() where uid=$2::uuid",
                           (json.dumps(frame, ensure_ascii=False), MANDANT_FRAME_GUID)))
            log.append("Control im Frame 'Mandanten Edit'")

        print(f"{'APPLY' if args.apply else 'Dry-Run'}: {len(writes)} Schreibvorgang/-vorgaenge")
        for line in log:
            print(f"  {line}")
        if not args.apply or not writes:
            return 0
        Path(args.snapshot).write_text(json.dumps(before, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        async with system.transaction():
            for sql, params in writes:
                await system.execute(sql, *params)
        print(f"Snapshot: {args.snapshot}")
        return 0
    finally:
        await system.close()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--confirm-backup", action="store_true")
    ap.add_argument("--snapshot", help="Pfad fuer den Snapshot des Frames vor der Aenderung (ausserhalb des Repositorys)")
    args = ap.parse_args()
    if args.apply and not (args.confirm_backup and args.snapshot):
        raise SystemExit("--apply verlangt --confirm-backup und --snapshot")
    sys.exit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()

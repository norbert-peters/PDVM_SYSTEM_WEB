"""Legt das Standard-Info-Frame fuer Dialoge an (sys_framedaten) samt Controls (sys_control_dict).

Das Info-Fenster eines Dialogs (Button hinter der Ueberschrift) rendert dieses Frame mit schreibgeschuetzten
PdvmInputControls. Die Werte (Gruppe INFO) liefert der Dialog zur Laufzeit; Aufbau und Beschriftung stehen hier.

Aufruf (aus backend/, mit PYTHONUTF8=1):
    ..\\.venv\\Scripts\\python.exe tools\\seed_dialog_info_frame_v1.py                              # Dry-Run (Standard)
    ..\\.venv\\Scripts\\python.exe tools\\seed_dialog_info_frame_v1.py --apply --confirm-backup     # fehlende Zeilen anlegen
    ..\\.venv\\Scripts\\python.exe tools\\seed_dialog_info_frame_v1.py --apply --confirm-backup --force-update

- Alle UIDs sind deterministisch (uuid5); das Frame hat die feste UID `DIALOG_INFO_FRAME_GUID` (auch im Backend:
  `app.core.dialog_service.DIALOG_INFO_FRAME_GUID`).
- Bestehende Zeilen bleiben unveraendert, ausser mit --force-update (dann Snapshot nach backend/reports/).
- Controls folgen Regel 1.10 (Gruppen ROOT/CONTROL, FIELD gross, Name `SYS_<FIELD>`; bei Kollision `SYS_<GRUPPE>_<FIELD>`).
- Reservierte Saetze (UID-Serien 0/5/6) werden nicht angefasst.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple
from urllib.parse import unquote

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.core.dialog_info import (  # noqa: E402
    DIALOG_INFO_FRAME_GUID,
    DIALOG_INFO_GROUP as INFO_GROUP,
    dialog_info_control_uid,
)

FRAME_NAME = "Dialog Info"

# (Tab, Tab-Kopf, [(FIELD, Label, Name-Override)])
INFO_TABS: List[Tuple[int, str, List[Tuple[str, str, str | None]]]] = [
    (1, "Dialog", [
        ("DIALOG_NAME", "Dialog", None),
        ("DIALOG_GUID", "Dialog-GUID", None),
        ("DIALOG_TYPE", "Dialogtyp", "SYS_INFO_DIALOG_TYPE"),  # FIELD existiert mit anderer Semantik (sys_dialogdaten)
        ("DIALOG_TABLE", "Tabelle", None),
        ("DIALOG_EDIT_TYPE", "Edit-Typ", None),
        ("DIALOG_OPEN_EDIT_MODE", "Edit öffnen", None),
        ("DIALOG_VIEW_GUID", "View-GUID", None),
        ("DIALOG_FRAME_GUID", "Frame-GUID", None),
    ]),
    (2, "Datensatz", [
        ("RECORD_UID", "UID", None),
        ("RECORD_NAME", "Name", None),
        ("RECORD_STORAGE", "Speicherort", None),
    ]),
    (3, "Letzter Aufruf", [
        ("LAST_CALL", "last_call", None),
        ("LAST_CALL_KEY", "last_call_key", None),
        ("LAST_CALL_SCOPE", "last_call_scope", None),
        ("LAST_CALL_SCOPE_CLIENT", "last_call_scope_client", None),
        ("LAST_CALL_RUNTIME_STATE", "last_call_runtime_state", None),
    ]),
]


def frame_uid() -> uuid.UUID:
    return DIALOG_INFO_FRAME_GUID


def control_uid(field: str) -> uuid.UUID:
    return dialog_info_control_uid(field)


@dataclass(frozen=True)
class Spec:
    table: str
    uid: uuid.UUID
    name: str
    daten: Dict[str, Any]


def _control_daten(uid: uuid.UUID, field: str, label: str, name: str) -> Dict[str, Any]:
    return {
        "ROOT": {"TABLE": "sys_control_dict", "SELF_GUID": str(uid), "SELF_NAME": name, "SELF_LINK_UID": str(uid)},
        "CONTROL": {
            "TAB": 0,
            "NAME": name,
            "TYPE": "string",
            "FIELD": field,
            "LABEL": label,
            "TABLE": "",
            "GRUPPE": INFO_GROUP,
            "ABDATUM": False,
            "CONFIGS": {
                "help": {"key": "", "feld": "", "table": "", "gruppe": ""},
                "dropdown": {"key": "", "feld": "", "table": "", "gruppe": ""},
            },
            "DEFAULT": "",
            "SORTABLE": False,
            "READ_ONLY": True,
            "HISTORICAL": False,
            "MODUL_TYPE": "edit",
            "SEARCHABLE": False,
            "UPPER_CASE": False,
            "EXPERT_MODE": False,
            "FILTER_TYPE": "contains",
            "PARENT_GUID": None,
            "SOURCE_PATH": "root",
            "DISPLAY_SHOW": True,
            "EXPERT_ORDER": 0,
            "DISPLAY_ORDER": 0,
            "SORT_DIRECTION": "asc",
            "FIELDS_ELEMENTS": {},
            "CONFIGS_ELEMENTS": {},
            "SORT_BY_ORIGINAL": False,
        },
    }


def build_specs() -> List[Spec]:
    specs: List[Spec] = []
    fields: Dict[str, Any] = {}
    tab_elements: Dict[str, Any] = {}

    for tab, head, items in INFO_TABS:
        tab_elements[f"TAB_{tab:02d}"] = {"TAB": tab, "HEAD": head, "GRUPPE": INFO_GROUP}
        for order, (field, label, name_override) in enumerate(items, start=1):
            uid = control_uid(field)
            name = name_override or f"SYS_{field}"
            specs.append(Spec("sys_control_dict", uid, name, _control_daten(uid, field, label, name)))
            fields[str(uid)] = {"TAB": tab, "SOURCE_PATH": "root", "DISPLAY_ORDER": order * 10}

    frame = {
        "ROOT": {
            "TABS": len(INFO_TABS),
            "TABLE": "",
            "EDIT_TYPE": "pdvm_edit",
            "FRAME_TYPE": "popup",
            "SELF_GUID": str(frame_uid()),
            "SELF_LINK_UID": str(frame_uid()),
            "SELF_NAME": FRAME_NAME,
            "GO_NEW_SET": False,
            "TAB_ELEMENTS": tab_elements,
        },
        "FIELDS": fields,
    }
    specs.append(Spec("sys_framedaten", frame_uid(), FRAME_NAME, frame))
    return specs


async def main(apply: bool, force_update: bool) -> int:
    import asyncpg

    from audit_system_data import load_env_url

    url = load_env_url()
    conn = await asyncpg.connect(
        host="127.0.0.1" if url.hostname == "localhost" else url.hostname,
        port=url.port or 5432,
        user=url.username,
        password=unquote(url.password or ""),
        database="pdvm_system",
    )
    inserted: List[str] = []
    updated: List[str] = []
    skipped: List[str] = []
    snapshot: List[Dict[str, Any]] = []
    try:
        for spec in build_specs():
            existing = await conn.fetchrow(f"SELECT uid, name, daten FROM {spec.table} WHERE uid = $1", spec.uid)
            label = f"{spec.table}/{spec.name}"
            if existing:
                if not force_update:
                    skipped.append(label)
                    continue
                snapshot.append({"table": spec.table, "uid": str(spec.uid), "name": existing["name"], "daten": existing["daten"]})
                updated.append(label)
                if apply:
                    await conn.execute(
                        f"UPDATE {spec.table} SET daten = $2::jsonb, name = $3, link_uid = $1, modified_at = NOW() WHERE uid = $1",
                        spec.uid, json.dumps(spec.daten, ensure_ascii=False), spec.name,
                    )
                continue

            clash = await conn.fetchval(f"SELECT uid FROM {spec.table} WHERE name = $1 AND historisch = 0", spec.name)
            if clash:
                print(f"Namenskonflikt, uebersprungen: {label} (vorhanden als {clash})")
                skipped.append(label)
                continue
            inserted.append(label)
            if apply:
                await conn.execute(
                    f"INSERT INTO {spec.table} (uid, link_uid, daten, name, historisch, created_at, modified_at) "
                    "VALUES ($1, $1, $2::jsonb, $3, 0, NOW(), NOW())",
                    spec.uid, json.dumps(spec.daten, ensure_ascii=False), spec.name,
                )
    finally:
        await conn.close()

    mode = "APPLY" if apply else "DRY-RUN"
    print(f"=== Dialog-Info-Frame ({mode}) ===")
    print(f"Angelegt: {len(inserted)}  Aktualisiert: {len(updated)}  Unveraendert: {len(skipped)}")
    for item in inserted:
        print(f"  + {item}")
    for item in updated:
        print(f"  ~ {item}")
    if apply and snapshot:
        snap_dir = BACKEND_DIR / "reports"
        snap_dir.mkdir(exist_ok=True)
        path = snap_dir / f"dialog_info_frame_snapshot_{datetime.now().strftime('%Y-%m-%d_%H%M%S')}.json"
        path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        print(f"Snapshot: {path}")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="Schreiben (Standard: Dry-Run)")
    parser.add_argument("--confirm-backup", action="store_true", help="Bestaetigung, dass ein Backup existiert (Pflicht mit --apply)")
    parser.add_argument("--force-update", action="store_true", help="Bestehende Zeilen mit diesen UIDs ueberschreiben (mit Snapshot)")
    args = parser.parse_args()
    if args.apply and not args.confirm_backup:
        raise SystemExit("--apply verlangt --confirm-backup")
    raise SystemExit(asyncio.run(main(args.apply, args.force_update)))

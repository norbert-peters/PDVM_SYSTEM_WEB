"""
Fuehrt die Control-Eigenschaft IMMUTABLE ein und stellt das Bearbeiten von Mandanten auf das Frame um.

Spezifikation: docs/specs/PDVM_FRAME_INPUT_RENDERING_SPEC_V1.md (Abschnitt 8), Regel 2.15 / 1.10a.
Freigabe fuer das Muttercontrol (reservierter Satz 666 in sys_control_dict): 2026-11-13.

Schritte (idempotent):
1. Muttercontrol 666: CONTROL.IMMUTABLE=false (und gleich in TEMPLATES.CONTROL, Regel 1.10a).
2. Control SYS_IMMUTABLE und Eintrag im Frame `sys_control_dict Frame` (Control-Editor).
3. IMMUTABLE=true fuer die Mandanten-Felder (mandant_record_rules.IMMUTABLE_MANDANT_FIELDS).
4. View `Mandantendaten` und Dialog `Mandanten bearbeiten` (pdvm_edit, Frame `Mandanten Edit`).
5. Menue (sys_menudaten, Admin-Administration): Eintrag `Mandanten` oeffnet den neuen Dialog; der bisherige
   JSON-Dialog bleibt als `Mandanten (JSON)` erhalten.

Aufruf aus backend/ (Standard ist Dry-Run):
  ..\\.venv\\Scripts\\python.exe tools\\seed_mandant_dialog_v1.py
  ..\\.venv\\Scripts\\python.exe tools\\seed_mandant_dialog_v1.py --apply --confirm-backup --snapshot <Pfad.json>
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

from app.core.mandant_record_rules import (  # noqa: E402
    IMMUTABLE_MANDANT_FIELDS,
    MANDANT_DIALOG_GUID,
    MANDANT_FRAME_GUID,
    MANDANT_TABLE,
    MANDANT_VIEW_GUID,
)
from app.core.pdvm_datetime import now_pdvm_str  # noqa: E402
from audit_system_data import U666, as_dict, load_env_url  # noqa: E402
from seed_base_records import connect  # noqa: E402

NS = uuid.UUID("6f1a5b0e-2a0c-4d6b-9b3e-5d1f0c7a9e11")
CONTROL_FRAME_UID = "ebb4a327-6b3c-4fa8-8df8-e38b52072699"  # sys_control_dict Frame
BENUTZER_VIEW_UID = "a311c396-5408-485b-b188-a3e28be7679e"
MENU_UID = "4cfbf1ac-c7db-4a3a-ab37-c5b457b89440"  # Admin-Administration
MENU_ENTRY = "e4d93d76-099e-4dfd-9155-96e4cfb15043"
JSON_MENU_ENTRY = str(uuid.uuid5(NS, "menu:mandanten-json"))
SYS_IMMUTABLE_UID = str(uuid.uuid5(NS, "control:SYS_IMMUTABLE"))
VIEW_COLUMNS = [("MANDANT", "DESCRIPTION"), ("MANDANT", "DATABASE")]
VIEW_NAME_FIELD = ("ROOT", "NAME")


def root_block(table: str, uid: str, name: str, stamp: str, **extra) -> dict:
    return {
        "TABLE": table, "SELF_GUID": uid, "SELF_NAME": name, "SELF_LINK_UID": uid,
        "SELF_CREATED_AT": stamp, "SELF_MODIFIED_AT": stamp, "SELF_GILT_BIS": "9999365.99999",
        "STRUCT_VERSION_APPLIED": 1, **extra,
    }


def build_dialog(stamp: str) -> dict:
    tab = {"OPEN_EDIT": "double_click", "SELECTION_MODE": "single", "TABLE": MANDANT_TABLE, "EDIT_TYPE": "pdvm_edit"}
    return {"ROOT": {
        **root_block("sys_dialogdaten", MANDANT_DIALOG_GUID, "Mandanten bearbeiten", stamp),
        "TABS": 2, "TABLE": MANDANT_TABLE, "HEADER": "Mandanten bearbeiten", "EDIT_TYPE": "pdvm_edit",
        "OPEN_EDIT": "double_click", "GO_NEW_SET": False, "SHOW_TABLE": False, "DIALOG_TYPE": "norm",
        "SELECTION_MODE": "single",
        "TAB_ELEMENTS": {
            "TAB_01": {"TAB": 1, "GUID": MANDANT_VIEW_GUID, "HEAD": "Übersicht", "MODULE": "view", **tab},
            "TAB_02": {"TAB": 2, "GUID": MANDANT_FRAME_GUID, "HEAD": "Bearbeiten", "MODULE": "edit", **tab},
        },
    }}


def build_view(stamp: str, benutzer_view: dict, control_uids: dict) -> dict:
    columns = {}
    for order, key in enumerate([VIEW_NAME_FIELD] + VIEW_COLUMNS, start=1):
        columns[control_uids[key]] = {"show": True, "display_order": order * 10}
    return {
        "ROOT": {
            **root_block("sys_viewdaten", MANDANT_VIEW_GUID, "Mandantendaten", stamp),
            "TABLE": MANDANT_TABLE, "NO_DATA": False, "ALLOW_SORT": True, "ALLOW_FILTER": True,
            "HEADER_TEXT": "Übersicht Mandanten", "PROJECTION_MODE": "standard",
            "DEFAULT_SORT_COLUMN": "", "DEFAULT_SORT_REVERSE": False,
        },
        "**SYSTEM": copy.deepcopy(benutzer_view.get("**SYSTEM", {})),
        MANDANT_TABLE.upper(): columns,
    }


def find_menu_group(menu: dict) -> str | None:
    for group, content in menu.items():
        if isinstance(content, dict) and MENU_ENTRY in content:
            return group
    return None


async def run(args) -> int:
    env = load_env_url()
    stamp = now_pdvm_str()
    system = await connect(env, "pdvm_system", read_only=not args.apply)
    try:
        log: list[str] = []
        before: dict = {}
        writes: list[tuple[str, tuple]] = []

        # 1. Muttercontrol
        row = await system.fetchrow("select daten from sys_control_dict where uid = $1::uuid", U666)
        mother = as_dict(row["daten"])
        new_mother = copy.deepcopy(mother)
        changed = False
        for holder in (new_mother.get("CONTROL"), new_mother.get("TEMPLATES", {}).get("CONTROL")):
            if isinstance(holder, dict) and "IMMUTABLE" not in holder:
                holder["IMMUTABLE"] = False
                changed = True
        if changed:
            new_mother["ROOT"]["SELF_MODIFIED_AT"] = stamp
            before["mother_666"] = mother
            writes.append(("update sys_control_dict set daten=$1::jsonb, modified_at=now() where uid=$2::uuid",
                           (json.dumps(new_mother, ensure_ascii=False), U666)))
            log.append("Muttercontrol 666: IMMUTABLE=false ergaenzt (CONTROL und TEMPLATES.CONTROL)")

        # 2. Control SYS_IMMUTABLE + Control-Frame
        has_control = await system.fetchval("select 1 from sys_control_dict where uid = $1::uuid", SYS_IMMUTABLE_UID)
        if not has_control:
            ctrl = copy.deepcopy(new_mother["CONTROL"])
            ctrl.update({"NAME": "SYS_IMMUTABLE", "FIELD": "IMMUTABLE", "TYPE": "true_false",
                         "LABEL": "Nach Anlage unveränderlich", "TABLE": "sys_control_dict", "GRUPPE": "CONTROL",
                         "IMMUTABLE": False})
            daten = {"ROOT": root_block("sys_control_dict", SYS_IMMUTABLE_UID, "SYS_IMMUTABLE", stamp), "CONTROL": ctrl}
            writes.append(("insert into sys_control_dict (uid, name, daten, historisch, link_uid) "
                           "values ($1::uuid, 'SYS_IMMUTABLE', $2::jsonb, 0, $1::uuid)",
                           (SYS_IMMUTABLE_UID, json.dumps(daten, ensure_ascii=False))))
            log.append("Control SYS_IMMUTABLE angelegt")
        frame_row = await system.fetchrow("select daten from sys_framedaten where uid = $1::uuid", CONTROL_FRAME_UID)
        frame = as_dict(frame_row["daten"])
        if SYS_IMMUTABLE_UID not in frame.get("FIELDS", {}):
            before["control_frame"] = copy.deepcopy(frame)
            frame["FIELDS"][SYS_IMMUTABLE_UID] = {"TAB": 2, "DISPLAY_ORDER": 105}
            frame["ROOT"]["SELF_MODIFIED_AT"] = stamp
            writes.append(("update sys_framedaten set daten=$1::jsonb, modified_at=now() where uid=$2::uuid",
                           (json.dumps(frame, ensure_ascii=False), CONTROL_FRAME_UID)))
            log.append("Control-Frame: IMMUTABLE im Tab Control ergaenzt")

        # 3. IMMUTABLE an den Mandanten-Controls
        controls = await system.fetch(
            "select uid::text u, name, daten from sys_control_dict where lower(daten->'CONTROL'->>'TABLE') = $1", MANDANT_TABLE)
        control_uids = {}
        for r in controls:
            d = as_dict(r["daten"])
            key = (d["CONTROL"].get("GRUPPE"), d["CONTROL"].get("FIELD"))
            control_uids[key] = r["u"]
            if key in IMMUTABLE_MANDANT_FIELDS and d["CONTROL"].get("IMMUTABLE") is not True:
                before.setdefault("controls", {})[r["u"]] = copy.deepcopy(d)
                d["CONTROL"]["IMMUTABLE"] = True
                d["ROOT"]["SELF_MODIFIED_AT"] = stamp
                writes.append(("update sys_control_dict set daten=$1::jsonb, modified_at=now() where uid=$2::uuid",
                               (json.dumps(d, ensure_ascii=False), r["u"])))
                log.append(f"IMMUTABLE=true: {key[0]}.{key[1]} ({r['name']})")
        missing = [k for k in IMMUTABLE_MANDANT_FIELDS + [VIEW_NAME_FIELD] + VIEW_COLUMNS if k not in control_uids]
        if missing:
            raise SystemExit(f"Controls fehlen (zuerst seed_mandant_frame_v1.py ausfuehren): {missing}")

        # 4. View und Dialog
        if not await system.fetchval("select 1 from sys_viewdaten where uid = $1::uuid", MANDANT_VIEW_GUID):
            benutzer = as_dict(await system.fetchval("select daten from sys_viewdaten where uid = $1::uuid", BENUTZER_VIEW_UID))
            writes.append(("insert into sys_viewdaten (uid, name, daten, historisch, link_uid) "
                           "values ($1::uuid, 'Mandantendaten', $2::jsonb, 0, $1::uuid)",
                           (MANDANT_VIEW_GUID, json.dumps(build_view(stamp, benutzer, control_uids), ensure_ascii=False))))
            log.append("View Mandantendaten angelegt")
        if not await system.fetchval("select 1 from sys_dialogdaten where uid = $1::uuid", MANDANT_DIALOG_GUID):
            writes.append(("insert into sys_dialogdaten (uid, name, daten, historisch, link_uid) "
                           "values ($1::uuid, 'Mandanten bearbeiten', $2::jsonb, 0, $1::uuid)",
                           (MANDANT_DIALOG_GUID, json.dumps(build_dialog(stamp), ensure_ascii=False))))
            log.append("Dialog Mandanten bearbeiten angelegt")

        # 5. Menue
        menu = as_dict(await system.fetchval("select daten from sys_menudaten where uid = $1::uuid", MENU_UID))
        group = find_menu_group(menu)
        if group is None:
            raise SystemExit("Menueeintrag 'Mandanten' nicht gefunden")
        entry = menu[group][MENU_ENTRY]
        if entry["command"]["params"].get("dialog_guid") != MANDANT_DIALOG_GUID:
            before["menu"] = copy.deepcopy(menu)
            json_entry = copy.deepcopy(entry)
            json_entry.update({"label": "Mandanten (JSON)", "sort_order": entry.get("sort_order", 160) + 5})
            menu[group][JSON_MENU_ENTRY] = json_entry
            entry["command"]["params"]["dialog_guid"] = MANDANT_DIALOG_GUID
            entry["tooltip"] = "Hier können die Daten der Mandanten bearbeitet werden."
            menu["ROOT"]["SELF_MODIFIED_AT"] = stamp
            writes.append(("update sys_menudaten set daten=$1::jsonb, modified_at=now() where uid=$2::uuid",
                           (json.dumps(menu, ensure_ascii=False), MENU_UID)))
            log.append("Menue: Mandanten -> neuer Dialog, Mandanten (JSON) bleibt erhalten")

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
    ap.add_argument("--snapshot", help="Pfad fuer den Snapshot der Vorher-Staende (ausserhalb des Repositorys)")
    args = ap.parse_args()
    if args.apply and not (args.confirm_backup and args.snapshot):
        raise SystemExit("--apply verlangt --confirm-backup und --snapshot")
    sys.exit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()

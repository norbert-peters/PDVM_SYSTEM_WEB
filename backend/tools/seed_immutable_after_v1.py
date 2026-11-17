"""
Fuehrt die Control-Eigenschaft IMMUTABLE_AFTER ein (bedingte Sperre) und setzt sie an den Mandanten-Verbindungsfeldern.

`CONTROL.IMMUTABLE_AFTER` (Pfad GRUPPE.FELD): Ein IMMUTABLE-Feld bleibt aenderbar, bis dieses Feld im gespeicherten Satz
einen Wert hat. Fuer Mandanten: `ROOT.DB_CREATED_AT` - Tippfehler in Host/Datenbank/Port sind korrigierbar, solange die
Datenbank noch nicht eingerichtet ist (Aktion `mandant.setup`). Siehe immutable_fields_service und Regel 2.15.
Freigabe fuer das Muttercontrol (reservierter Satz 666 in sys_control_dict): 2026-11-16 (Anweisung des Nutzers).

1. Muttercontrol 666: CONTROL.IMMUTABLE_AFTER="" (und gleich in TEMPLATES.CONTROL, Regel 1.10a).
2. Control SYS_IMMUTABLE_AFTER und Eintrag im Frame `sys_control_dict Frame` (Control-Editor).
3. IMMUTABLE_AFTER=ROOT.DB_CREATED_AT an den Mandanten-Controls mit IMMUTABLE=true.

Aufruf aus backend/ (Standard ist Dry-Run):
  ..\\.venv\\Scripts\\python.exe tools\\seed_immutable_after_v1.py
  ..\\.venv\\Scripts\\python.exe tools\\seed_immutable_after_v1.py --apply --confirm-backup --snapshot <Pfad.json>
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

from app.core.mandant_record_rules import IMMUTABLE_MANDANT_FIELDS, MANDANT_TABLE  # noqa: E402
from app.core.pdvm_datetime import now_pdvm_str  # noqa: E402
from audit_system_data import U666, as_dict, load_env_url  # noqa: E402
from seed_base_records import connect  # noqa: E402
from seed_mandant_dialog_v1 import CONTROL_FRAME_UID, NS, root_block  # noqa: E402

CONDITION = "ROOT.DB_CREATED_AT"
SYS_IMMUTABLE_AFTER_UID = str(uuid.uuid5(NS, "control:SYS_IMMUTABLE_AFTER"))
UPDATE_CONTROL = "update sys_control_dict set daten=$1::jsonb, modified_at=now() where uid=$2::uuid"


async def run(args) -> int:
    stamp = now_pdvm_str()
    system = await connect(load_env_url(), "pdvm_system", read_only=not args.apply)
    try:
        log: list[str] = []
        before: dict = {}
        writes: list[tuple[str, tuple]] = []

        # 1. Muttercontrol
        mother = as_dict((await system.fetchrow("select daten from sys_control_dict where uid = $1::uuid", U666))["daten"])
        new_mother = copy.deepcopy(mother)
        changed = False
        for holder in (new_mother.get("CONTROL"), new_mother.get("TEMPLATES", {}).get("CONTROL")):
            if isinstance(holder, dict) and "IMMUTABLE_AFTER" not in holder:
                holder["IMMUTABLE_AFTER"] = ""
                changed = True
        if changed:
            new_mother["ROOT"]["SELF_MODIFIED_AT"] = stamp
            before["mother_666"] = mother
            writes.append((UPDATE_CONTROL, (json.dumps(new_mother, ensure_ascii=False), U666)))
            log.append("Muttercontrol 666: IMMUTABLE_AFTER ergaenzt (CONTROL und TEMPLATES.CONTROL)")

        # 2. Control SYS_IMMUTABLE_AFTER + Control-Frame
        if not await system.fetchval("select 1 from sys_control_dict where uid = $1::uuid", SYS_IMMUTABLE_AFTER_UID):
            ctrl = copy.deepcopy(new_mother["CONTROL"])
            ctrl.update({"NAME": "SYS_IMMUTABLE_AFTER", "FIELD": "IMMUTABLE_AFTER", "TYPE": "string",
                         "LABEL": "Unveränderlich erst wenn gefüllt (GRUPPE.FELD)", "TABLE": "sys_control_dict",
                         "GRUPPE": "CONTROL", "IMMUTABLE": False, "IMMUTABLE_AFTER": ""})
            daten = {"ROOT": root_block("sys_control_dict", SYS_IMMUTABLE_AFTER_UID, "SYS_IMMUTABLE_AFTER", stamp), "CONTROL": ctrl}
            writes.append(("insert into sys_control_dict (uid, name, daten, historisch, link_uid) "
                           "values ($1::uuid, 'SYS_IMMUTABLE_AFTER', $2::jsonb, 0, $1::uuid)",
                           (SYS_IMMUTABLE_AFTER_UID, json.dumps(daten, ensure_ascii=False))))
            log.append("Control SYS_IMMUTABLE_AFTER angelegt")
        frame = as_dict((await system.fetchrow("select daten from sys_framedaten where uid = $1::uuid", CONTROL_FRAME_UID))["daten"])
        if SYS_IMMUTABLE_AFTER_UID not in frame.get("FIELDS", {}):
            before["control_frame"] = copy.deepcopy(frame)
            frame["FIELDS"][SYS_IMMUTABLE_AFTER_UID] = {"TAB": 2, "DISPLAY_ORDER": 106}
            frame["ROOT"]["SELF_MODIFIED_AT"] = stamp
            writes.append(("update sys_framedaten set daten=$1::jsonb, modified_at=now() where uid=$2::uuid",
                           (json.dumps(frame, ensure_ascii=False), CONTROL_FRAME_UID)))
            log.append("Control-Frame: IMMUTABLE_AFTER im Tab Control ergaenzt")

        # 3. Bedingung an den Mandanten-Controls
        rows = await system.fetch(
            "select uid::text u, name, daten from sys_control_dict where lower(daten->'CONTROL'->>'TABLE') = $1", MANDANT_TABLE)
        found = set()
        for r in rows:
            d = as_dict(r["daten"])
            key = (d["CONTROL"].get("GRUPPE"), d["CONTROL"].get("FIELD"))
            if key not in IMMUTABLE_MANDANT_FIELDS:
                continue
            found.add(key)
            if d["CONTROL"].get("IMMUTABLE_AFTER") != CONDITION:
                before.setdefault("controls", {})[r["u"]] = copy.deepcopy(d)
                d["CONTROL"]["IMMUTABLE_AFTER"] = CONDITION
                d["ROOT"]["SELF_MODIFIED_AT"] = stamp
                writes.append((UPDATE_CONTROL, (json.dumps(d, ensure_ascii=False), r["u"])))
                log.append(f"IMMUTABLE_AFTER={CONDITION}: {key[0]}.{key[1]} ({r['name']})")
        missing = [k for k in IMMUTABLE_MANDANT_FIELDS if k not in found]
        if missing:
            raise SystemExit(f"Controls fehlen (zuerst seed_mandant_dialog_v1.py ausfuehren): {missing}")

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

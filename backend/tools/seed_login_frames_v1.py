"""
Legt die oeffentlichen Login-Frames und ihre Controls an (Anmeldung, Passwort vergessen, Passwort aendern).

Spezifikation: docs/specs/PDVM_LOGIN_FRAME_SPEC_V1.md. Die Frame-UIDs sind feste Konstanten im Code
(app.core.public_frame_service.LOGIN_FRAME_UIDS, Allowlist des oeffentlichen Endpunkts), die Control-UIDs
sind deterministisch (uuid5). Alle drei Frames haben FRAME_TYPE `public_form` (Voraussetzung fuer den Typ `password_input`).

- Control-Typ `password_input`: Passwort-Eingabe ohne Speicherung; `CONFIGS.input {name, autocomplete}` fuer Passwort-Manager.
- Die Controls gehoeren zur virtuellen Tabelle `auth_login` (keine Datenbanktabelle).
- Idempotent; zieht abweichende Konfigurationen nach.

Aufruf aus backend/ (Standard ist Dry-Run):
  ..\\.venv\\Scripts\\python.exe tools\\seed_login_frames_v1.py
  ..\\.venv\\Scripts\\python.exe tools\\seed_login_frames_v1.py --apply --confirm-backup --snapshot <Pfad.json>
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

from app.core.public_frame_service import LOGIN_FRAME_UIDS  # noqa: E402
from app.core.pdvm_datetime import now_pdvm_str  # noqa: E402
from audit_system_data import U666, as_dict, load_env_url  # noqa: E402
from seed_base_records import connect  # noqa: E402
from seed_mandant_dialog_v1 import NS, root_block  # noqa: E402

TABLE = "auth_login"
EMAIL_INPUT = {"input": {"name": "username", "autocomplete": "username"}}
NEW_PASSWORD_INPUT = {"input": {"autocomplete": "new-password"}, "password_input": {"reveal": True, "min_length": 12}}

# Frame -> (Name, Controls: (Controlname, Gruppe, Feld, Typ, Label, CONFIGS))
FRAMES = {
    "login": ("Login", [
        ("LOGIN_EMAIL", "LOGIN", "EMAIL", "string", "E-Mail", EMAIL_INPUT),
        ("LOGIN_PASSWORD", "LOGIN", "PASSWORD", "password_input", "Passwort",
         {"input": {"name": "password", "autocomplete": "current-password"}, "password_input": {"reveal": True}}),
    ]),
    "forgot": ("Passwort vergessen", [
        ("LOGIN_FORGOT_BENUTZER", "FORGOT", "BENUTZER", "string", "Benutzer", EMAIL_INPUT),
        ("LOGIN_FORGOT_EMAIL", "FORGOT", "EMAIL", "string", "Hinterlegte E-Mail-Adresse",
         {"input": {"name": "email", "autocomplete": "email"}}),
    ]),
    "change": ("Passwort ändern", [
        ("LOGIN_CHANGE_NEW_PASSWORD", "CHANGE", "NEW_PASSWORD", "password_input", "Neues Passwort",
         {**copy.deepcopy(NEW_PASSWORD_INPUT), "input": {"name": "new-password", "autocomplete": "new-password"}}),
        ("LOGIN_CHANGE_CONFIRM_PASSWORD", "CHANGE", "CONFIRM_PASSWORD", "password_input", "Passwort bestätigen",
         {"input": {"name": "confirm-password", "autocomplete": "new-password"},
          "password_input": {"reveal": True, "min_length": 12, "confirm_with": "NEW_PASSWORD"}}),
    ]),
}
CONTROL_KEYS = ("TYPE", "LABEL", "CONFIGS", "GRUPPE", "FIELD", "TABLE")


def control_uid(name: str) -> str:
    return str(uuid.uuid5(NS, f"control:{name}"))


def build_control(mother: dict, spec: tuple, uid: str, stamp: str) -> dict:
    name, gruppe, feld, typ, label, configs = spec
    ctrl = copy.deepcopy(mother)
    ctrl.pop("FELD", None)  # Alias-Verbot (Regel 1.12b)
    ctrl.update({"NAME": name, "FIELD": feld, "TYPE": typ, "LABEL": label, "TABLE": TABLE, "GRUPPE": gruppe,
                 "CONFIGS": copy.deepcopy(configs)})
    return {"ROOT": root_block("sys_control_dict", uid, name, stamp), "CONTROL": ctrl}


def build_frame(frame_uid: str, name: str, specs: list, stamp: str) -> dict:
    fields = {control_uid(spec[0]): {"TAB": 1, "DISPLAY_ORDER": order * 10} for order, spec in enumerate(specs, start=1)}
    return {
        "ROOT": {
            "TABS": 1, "TABLE": "", "FRAME_TYPE": "public_form", "GO_NEW_SET": False,
            "TAB_ELEMENTS": {str(uuid.uuid5(NS, f"frame-tab:{frame_uid}:1")): {"TAB": 1, "HEAD": name, "GRUPPE": "LOGIN"}},
            "SELF_GUID": frame_uid, "SELF_NAME": name, "SELF_LINK_UID": frame_uid,
            "SELF_CREATED_AT": stamp, "SELF_MODIFIED_AT": stamp, "SELF_GILT_BIS": "9999365.99999",
            "STRUCT_VERSION_APPLIED": 1,
        },
        "FIELDS": fields,
    }


async def run(args) -> int:
    stamp = now_pdvm_str()
    system = await connect(load_env_url(), "pdvm_system", read_only=not args.apply)
    try:
        writes: list[tuple[str, tuple]] = []
        log: list[str] = []
        before: dict = {}
        mother = as_dict(await system.fetchval("select daten from sys_control_dict where uid = $1::uuid", U666))["CONTROL"]
        existing = {r["name"]: str(r["uid"]) for r in await system.fetch("select uid, name from sys_control_dict")}

        for key, (frame_name, specs) in FRAMES.items():
            frame_uid = str(LOGIN_FRAME_UIDS[key])
            for spec in specs:
                name, uid = spec[0], control_uid(spec[0])
                if name in existing and existing[name] != uid:
                    raise SystemExit(f"Controlname {name} ist bereits mit anderer UID vergeben")
                wanted = build_control(mother, spec, uid, stamp)
                if name not in existing:
                    writes.append(("insert into sys_control_dict (uid, name, daten, historisch, link_uid) "
                                   "values ($1::uuid, $2, $3::jsonb, 0, $1::uuid)",
                                   (uid, name, json.dumps(wanted, ensure_ascii=False))))
                    log.append(f"Control {name}")
                    continue
                row = as_dict(await system.fetchval("select daten from sys_control_dict where uid = $1::uuid", uid))
                ctrl = as_dict(row.get("CONTROL"))
                if any(ctrl.get(k) != wanted["CONTROL"].get(k) for k in CONTROL_KEYS):
                    before.setdefault("controls", {})[uid] = copy.deepcopy(row)
                    for k in CONTROL_KEYS:
                        ctrl[k] = wanted["CONTROL"][k]
                    row["CONTROL"] = ctrl
                    row["ROOT"]["SELF_MODIFIED_AT"] = stamp
                    writes.append(("update sys_control_dict set daten=$1::jsonb, modified_at=now() where uid=$2::uuid",
                                   (json.dumps(row, ensure_ascii=False), uid)))
                    log.append(f"Control {name}: Konfiguration nachgezogen")

            wanted_frame = build_frame(frame_uid, frame_name, specs, stamp)
            row = await system.fetchrow("select daten from sys_framedaten where uid = $1::uuid", frame_uid)
            if not row:
                writes.append(("insert into sys_framedaten (uid, name, daten, historisch, link_uid) "
                               "values ($1::uuid, $2, $3::jsonb, 0, $1::uuid)",
                               (frame_uid, frame_name, json.dumps(wanted_frame, ensure_ascii=False))))
                log.append(f"Frame {frame_name} ({frame_uid})")
                continue
            frame = as_dict(row["daten"])
            if frame.get("FIELDS") != wanted_frame["FIELDS"] or as_dict(frame.get("ROOT")).get("FRAME_TYPE") != "public_form":
                before.setdefault("frames", {})[frame_uid] = copy.deepcopy(frame)
                frame["FIELDS"] = wanted_frame["FIELDS"]
                frame.setdefault("ROOT", {})["FRAME_TYPE"] = "public_form"
                frame["ROOT"]["SELF_MODIFIED_AT"] = stamp
                writes.append(("update sys_framedaten set daten=$1::jsonb, modified_at=now() where uid=$2::uuid",
                               (json.dumps(frame, ensure_ascii=False), frame_uid)))
                log.append(f"Frame {frame_name}: Felder nachgezogen")

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

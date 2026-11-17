"""
Legt die Frame-Aktionen und Hinweise (Control-Typen `action` und `info`) fuer `edit_user` und die Textvorlagen an.

Spezifikation: docs/specs/PDVM_FRAME_ACTIONS_SPEC_V1.md, Regel 2.17 (ARCHITECTURE_RULES.md).

Ersetzt die bisher fest im Komponentencode stehenden Schaltflaechen und Anzeigen:
- Frame `Benutzer Edit` (asy_benutzer): Maschinelles Passwort senden, Account sperren/entsperren, Anzeigen
  "Passwortwechsel erforderlich" und "Account gesperrt"; die zwei wirkungslosen Alt-Buttons "Klicks fuer Edit" (Typ action
  ohne Aktion) werden aus dem Frame entfernt.
- Frames `Textvorlagen Edit (Mandant/System)`: Kopie anlegen; nur Mandant: Hinweis "Systemvorlage ist neuer" mit
  "Neue Systemfassung uebernehmen".
- Frame `Mandanten Edit` (asy_mandanten): Hinweis "Datenbank noch nicht eingerichtet" und Schaltflaeche "Datenbank aufbauen"
  (Aktion mandant.setup, nur superadmin; ersetzt die Komponente MandantSetup).
- Workflow-Draft-Builder: die neun bestehenden Controls vom Typ action erhalten eine explizite Aktions-ID (workflow.*); die
  Aktion wird nicht mehr aus dem Label erraten.

Je Control ein Satz in sys_control_dict (TYPE action/info, CONFIGS.action/info), je Frame ein Eintrag in FIELDS.
Was eine Aktion tut und wer sie ausfuehren darf, steht im Backend (app/core/frame_action_service.py).
Idempotent; bestehende Controls werden nur bei abweichender Konfiguration nachgezogen.

Aufruf aus backend/ (Standard ist Dry-Run):
  ..\\.venv\\Scripts\\python.exe tools\\seed_frame_actions_v1.py
  ..\\.venv\\Scripts\\python.exe tools\\seed_frame_actions_v1.py --apply --confirm-backup --snapshot <Pfad.json>
"""
from __future__ import annotations

import argparse
import asyncio
import copy
import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.core.pdvm_datetime import now_pdvm_str  # noqa: E402
from app.core.text_template_service import MANDANT_TABLE, SYSTEM_TABLE  # noqa: E402
from audit_system_data import U666, as_dict, load_env_url  # noqa: E402
from seed_base_records import connect  # noqa: E402
from seed_text_template_dialogs_v1 import root_block, uid_for  # noqa: E402

USER_TABLE = "asy_benutzer"
USER_FRAME_UID = "0d024e06-e750-480d-b439-7241fbfc8886"  # Benutzer Edit
TEXT_FRAME_UIDS = {MANDANT_TABLE: uid_for("frame", MANDANT_TABLE), SYSTEM_TABLE: uid_for("frame", SYSTEM_TABLE)}
ADOPT_TOOLTIP = "Legt die aktuelle Systemfassung als neue, inaktive Kopie an. Diese Vorlage bleibt unverändert."


def control(name, table, feld, typ, label, configs, tooltip=None, gruppe="AKTIONEN"):
    return {"name": name, "table": table, "gruppe": gruppe, "feld": feld, "type": typ, "label": label,
            "tooltip": tooltip, "configs": configs}


USER_CONTROLS = [
    control("ASY_ACTION_USER_PASSWORD_RESET", USER_TABLE, "USER_PASSWORD_RESET", "action", "Maschinelles Passwort senden", {
        "action": {"id": "user.password_reset", "placement": "header", "modes": ["edit"], "confirm": {
            "title": "Maschinelles Passwort senden",
            "message": "Ein neues maschinelles Passwort wird erzeugt und per E-Mail versendet. Fortfahren?",
            "label": "Senden"}}}),
    control("ASY_ACTION_USER_LOCK", USER_TABLE, "USER_LOCK", "action", "Account sperren", {
        "action": {"id": "user.lock", "placement": "header", "modes": ["edit"],
                   "visible_when": {"path": "SECURITY.ACCOUNT_LOCKED", "not": True},
                   "confirm": {"title": "Account sperren", "message": "Bitte optionalen Sperrgrund angeben.", "label": "Sperren"},
                   "params": [{"name": "reason", "label": "Grund", "type": "text", "required": False}]}}),
    control("ASY_ACTION_USER_UNLOCK", USER_TABLE, "USER_UNLOCK", "action", "Account entsperren", {
        "action": {"id": "user.unlock", "placement": "header", "modes": ["edit"],
                   "visible_when": {"path": "SECURITY.ACCOUNT_LOCKED", "equals": True},
                   "confirm": {"title": "Account entsperren", "message": "Account wirklich entsperren?", "label": "Entsperren"}}}),
    control("ASY_INFO_USER_PASSWORD_CHANGE", USER_TABLE, "USER_PASSWORD_CHANGE_INFO", "info", "Passwortwechsel erforderlich", {
        "info": {"value_path": "SECURITY.PASSWORD_CHANGE_REQUIRED", "format": "yes_no", "placement": "header", "modes": ["edit"]}}),
    control("ASY_INFO_USER_LOCKED", USER_TABLE, "USER_LOCKED_INFO", "info", "Account gesperrt", {
        "info": {"value_path": "SECURITY.ACCOUNT_LOCKED", "format": "yes_no", "placement": "header", "modes": ["edit"]}}),
]

TEXT_COMMON = [
    control("MSY_ACTION_COPY", MANDANT_TABLE, "ACTION_COPY", "action", "Kopie anlegen", {
        "action": {"id": "texttemplate.copy", "placement": "header", "modes": ["edit"]}},
        tooltip="Legt eine Kopie dieser Vorlage an (inaktiv, Sprachen im Status „review“)."),
]
TEXT_MANDANT_ONLY = [
    control("MSY_ACTION_ADOPT_SOURCE", MANDANT_TABLE, "ACTION_ADOPT_SOURCE", "action", "Neue Systemfassung übernehmen", {
        "action": {"id": "texttemplate.adopt_source", "placement": "header", "modes": ["edit"],
                   "visible_when": {"path": "state.outdated", "equals": True}}}, tooltip=ADOPT_TOOLTIP),
    control("MSY_INFO_SOURCE_OUTDATED", MANDANT_TABLE, "INFO_SOURCE_OUTDATED", "info", "Systemvorlage", {
        "info": {"text": "„{{state.source_name}}“ ist neuer als diese Kopie.", "severity": "warning", "placement": "header",
                 "modes": ["edit"], "state": {"action": "texttemplate.adopt_source"},
                 "visible_when": {"path": "state.outdated", "equals": True}}}),
    control("MSY_INFO_SOURCE_MISSING", MANDANT_TABLE, "INFO_SOURCE_MISSING", "info", "Systemvorlage", {
        "info": {"text": "Die zugehörige Systemvorlage existiert nicht mehr.", "placement": "header", "modes": ["edit"],
                 "state": {"action": "texttemplate.adopt_source"},
                 "visible_when": {"path": "state.source_missing", "equals": True}}}),
]

MANDANT_TABLE_ASY = "asy_mandanten"
MANDANT_FRAME_UID = "b7f0c1a2-5d3e-4c8a-9a61-3e2d7c5f4a10"  # Mandanten Edit (app.core.mandant_record_rules.MANDANT_FRAME_GUID)
MANDANT_CONTROLS = [
    control("ASY_ACTION_MANDANT_SETUP", MANDANT_TABLE_ASY, "ACTION_MANDANT_SETUP", "action", "Datenbank aufbauen", {
        "action": {"id": "mandant.setup", "placement": "header", "modes": ["edit"],
                   "visible_when": {"path": "state.needs_setup", "equals": True},
                   "confirm": {"title": "Datenbank aufbauen",
                               "message": "Die Datenbank des Mandanten wird angelegt. Die Tabellen entstehen beim ersten Login des Mandanten. Fortfahren?",
                               "label": "Aufbauen"}}}),
    control("ASY_INFO_MANDANT_SETUP", MANDANT_TABLE_ASY, "INFO_MANDANT_SETUP", "info", "Datenbank", {
        "info": {"text": "„{{state.database}}“ ist noch nicht eingerichtet.", "severity": "warning", "placement": "header",
                 "modes": ["edit"], "state": {"action": "mandant.setup"},
                 "visible_when": {"path": "state.needs_setup", "equals": True}}}),
    control("ASY_ACTION_MANDANT_DELETE", MANDANT_TABLE_ASY, "ACTION_MANDANT_DELETE", "action", "Mandant löschen", {
        "action": {"id": "mandant.delete", "placement": "header", "modes": ["edit"],
                   "visible_when": {"path": "state.can_delete", "equals": True},
                   "confirm": {"title": "Mandant löschen",
                               "message": "Die Datenbank des Mandanten wird gesichert und danach gelöscht, der Mandant wird bei allen Benutzern "
                                          "entfernt und ist nicht mehr erreichbar. Der Mandantensatz bleibt erhalten. "
                                          "Zur Bestätigung den Namen des Mandanten eingeben.",
                               "label": "Endgültig löschen"},
                   "params": [{"name": "confirm_name", "label": "Mandantenname", "type": "string", "required": True}]}},
        tooltip="Nur mit den Rollen superadmin und delmand; der Mandant der aktuellen Sitzung kann nicht gelöscht werden."),
]

# Frame -> Controls
FRAMES = {
    USER_FRAME_UID: USER_CONTROLS,
    TEXT_FRAME_UIDS[MANDANT_TABLE]: TEXT_COMMON + TEXT_MANDANT_ONLY,
    TEXT_FRAME_UIDS[SYSTEM_TABLE]: TEXT_COMMON,
    MANDANT_FRAME_UID: MANDANT_CONTROLS,
}

# Workflow-Draft-Builder: bestehende Controls (Typ action) erhalten eine explizite Aktions-ID. Die Aktion wird nicht mehr
# aus dem Label erraten; der Dialog fuehrt sie selbst aus (executor "host"), Rechte kommen vom Server (frame_action_service).
WORKFLOW_ACTION_IDS = {
    "5d53c6ce-78ec-5e02-9904-2ef639874108": "workflow.validate",         # SYS_VALIDATE_ACTION
    "6f965a0d-8cb4-5883-baec-a4bd9d3c7a49": "workflow.build",            # SYS_BUILD_ACTION
    "ac1e2692-b97d-5116-9607-0d7222c73c98": "workflow.abort",            # SYS_ABORT_ACTION
    "6e5c5c95-03dc-52b1-afe1-13c822ec117f": "workflow.create_control",   # SYS_CREATE_CONTROL_ACTION
    "75defedf-1c4e-56d7-adbb-8b634800bb21": "workflow.save_view",        # SYS_SAVE_VIEW_ACTION
    "62c736b3-04d6-5d26-9392-78ee017a5182": "workflow.apply",            # SYS_APPLY_ACTION
    "d87d080f-65cd-5526-97df-58d7e848fd7e": "workflow.dry_run",          # SYS_DRY_RUN_ACTION
    "f7fbc9b9-e537-5ab9-b96f-ddfe3b4a0fef": "workflow.save_content",     # SYS_SAVE_CONTENT_ACTION
    "9a84d71a-776f-500e-b706-408f160cdf31": "workflow.create_property",  # SYS_CREATE_PROPERTY_ACTION
}

# Wirkungslose Alt-Buttons ("Klicks fuer Edit", Typ action ohne Aktion) im Frame `Benutzer Edit`; die Control-Saetze bleiben bestehen.
LEGACY_FRAME_FIELDS = {
    USER_FRAME_UID: ["f6f6b203-7cc0-49ff-8a0f-0d6a01220013", "a2b25f28-88a3-4d13-8a0f-0d6a01220012"],  # ASY_LOCK, ASY_PASSWORD
}


def build_control(mother: dict, spec: dict, uid: str, stamp: str) -> dict:
    ctrl = copy.deepcopy(mother)
    ctrl.pop("FELD", None)
    ctrl.update({"NAME": spec["name"], "FIELD": spec["feld"], "TYPE": spec["type"], "LABEL": spec["label"],
                 "TABLE": spec["table"], "GRUPPE": spec["gruppe"], "CONFIGS": copy.deepcopy(spec["configs"])})
    if spec["tooltip"]:
        ctrl["TOOLTIP"] = spec["tooltip"]
    return {"ROOT": root_block("sys_control_dict", uid, spec["name"], stamp), "CONTROL": ctrl}


async def run(args) -> int:
    stamp = now_pdvm_str()
    system = await connect(load_env_url(), "pdvm_system", read_only=not args.apply)
    try:
        writes: list[tuple[str, tuple]] = []
        log: list[str] = []
        before: dict = {}
        mother = as_dict(await system.fetchval("select daten from sys_control_dict where uid = $1::uuid", U666))["CONTROL"]

        specs = {s["name"]: s for controls in FRAMES.values() for s in controls}
        control_uids = {name: uid_for("control", name) for name in specs}
        existing = {r["name"]: str(r["uid"]) for r in await system.fetch("select uid, name from sys_control_dict")}
        for name, spec in specs.items():
            uid = control_uids[name]
            if name in existing and existing[name] != uid:
                raise SystemExit(f"Controlname {name} ist bereits mit anderer UID vergeben")
            if name not in existing:
                writes.append(("insert into sys_control_dict (uid, name, daten, historisch, link_uid) "
                               "values ($1::uuid, $2, $3::jsonb, 0, $1::uuid)",
                               (uid, name, json.dumps(build_control(mother, spec, uid, stamp), ensure_ascii=False))))
                log.append(f"Control {name}")
                continue
            row = as_dict(await system.fetchval("select daten from sys_control_dict where uid = $1::uuid", uid))
            ctrl = as_dict(row.get("CONTROL"))
            wanted = build_control(mother, spec, uid, stamp)["CONTROL"]
            if any(ctrl.get(k) != wanted.get(k) for k in ("TYPE", "LABEL", "CONFIGS", "TOOLTIP")):
                before.setdefault("controls", {})[uid] = copy.deepcopy(row)
                for key in ("TYPE", "LABEL", "CONFIGS", "TOOLTIP"):
                    if key in wanted:
                        ctrl[key] = wanted[key]
                row["CONTROL"] = ctrl
                row["ROOT"]["SELF_MODIFIED_AT"] = stamp
                writes.append(("update sys_control_dict set daten=$1::jsonb, modified_at=now() where uid=$2::uuid",
                               (json.dumps(row, ensure_ascii=False), uid)))
                log.append(f"Control {name}: Konfiguration nachgezogen")

        for frame_uid, controls in FRAMES.items():
            row = await system.fetchrow("select name, daten from sys_framedaten where uid = $1::uuid", frame_uid)
            if not row:
                log.append(f"Frame {frame_uid} nicht vorhanden (zuerst das zugehoerige Seed-Tool ausfuehren) - uebersprungen")
                continue
            frame = as_dict(row["daten"])
            fields = frame.setdefault("FIELDS", {})
            added = []
            for order, spec in enumerate(controls, start=1):
                uid = control_uids[spec["name"]]
                if uid not in fields:
                    fields[uid] = {"TAB": 1, "DISPLAY_ORDER": 900 + order * 10}
                    added.append(spec["name"])
            legacy = set(LEGACY_FRAME_FIELDS.get(frame_uid, []))
            removed = [k for k, v in list(fields.items()) if k in legacy or str(as_dict(v).get("dict_ref")) in legacy]
            for key in removed:
                del fields[key]
            if added or removed:
                before.setdefault("frames", {})[frame_uid] = as_dict(row["daten"])
                frame["ROOT"]["SELF_MODIFIED_AT"] = stamp
                writes.append(("update sys_framedaten set daten=$1::jsonb, modified_at=now() where uid=$2::uuid",
                               (json.dumps(frame, ensure_ascii=False), frame_uid)))
                if added:
                    log.append(f"Frame {row['name']}: {', '.join(added)}")
                if removed:
                    log.append(f"Frame {row['name']}: {len(removed)} wirkungslose Alt-Buttons entfernt")

        for uid, action_id in WORKFLOW_ACTION_IDS.items():
            row = as_dict(await system.fetchval("select daten from sys_control_dict where uid = $1::uuid", uid))
            if not row:
                log.append(f"Workflow-Control {uid} nicht vorhanden - uebersprungen")
                continue
            ctrl = as_dict(row.get("CONTROL"))
            configs = as_dict(ctrl.get("CONFIGS"))
            wanted = {"id": action_id, "modes": ["create", "edit"]}
            if as_dict(configs.get("action")) != wanted:
                before.setdefault("controls", {})[uid] = copy.deepcopy(row)
                configs["action"] = wanted
                ctrl["CONFIGS"] = configs
                row["CONTROL"] = ctrl
                row["ROOT"]["SELF_MODIFIED_AT"] = stamp
                writes.append(("update sys_control_dict set daten=$1::jsonb, modified_at=now() where uid=$2::uuid",
                               (json.dumps(row, ensure_ascii=False), uid)))
                log.append(f"Workflow-Control {ctrl.get('NAME') or uid}: Aktion {action_id}")

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
    ap.add_argument("--snapshot", help="Pfad fuer den Snapshot der Frames/Controls vor der Aenderung (ausserhalb des Repositorys)")
    args = ap.parse_args()
    if args.apply and not (args.confirm_backup and args.snapshot):
        raise SystemExit("--apply verlangt --confirm-backup und --snapshot")
    sys.exit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()

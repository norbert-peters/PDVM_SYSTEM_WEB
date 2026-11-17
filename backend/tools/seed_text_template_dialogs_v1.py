"""
Legt die Verwaltung der Textvorlagen an: Controls, Frames, Views, Dialoge, Status-Dropdown und Menueeintraege.

Spezifikation: docs/specs/PDVM_TEXTVORLAGEN_SPEC_V1.md, Regel 1.24 / 2.15.

- Controls `MSY_*` (TABLE msy_textvorlagen), je Sprache `MSY_<SPRACHE>_<FELD>`; ein Control-Satz, zwei Frames
  (`Textvorlagen Edit (Mandant)` mit ACTIVE/Herkunft, `Textvorlagen Edit (System)`).
- Je Tabelle View und Dialog (`pdvm_edit`); Menueeintraege in Admin-Administration.
- Unveraenderlich nach der Anlage: Schluessel, Kanal, Variablen (CONTROL.IMMUTABLE).

Aufruf aus backend/ (Standard ist Dry-Run):
  ..\\.venv\\Scripts\\python.exe tools\\seed_text_template_dialogs_v1.py
  ..\\.venv\\Scripts\\python.exe tools\\seed_text_template_dialogs_v1.py --apply --confirm-backup --snapshot <Pfad.json>
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

from app.core.pdvm_datetime import now_pdvm_str  # noqa: E402
from app.core.text_template_service import MANDANT_TABLE, SYSTEM_TABLE  # noqa: E402
from audit_system_data import U666, as_dict, load_env_url  # noqa: E402
from seed_base_records import connect  # noqa: E402

NS = uuid.UUID("6f1a5b0e-2a0c-4d6b-9b3e-5d1f0c7a9e11")
BENUTZER_VIEW_UID = "a311c396-5408-485b-b188-a3e28be7679e"
MENU_UID = "4cfbf1ac-c7db-4a3a-ab37-c5b457b89440"  # Admin-Administration
MENU_PARENT = "58ebd97e-d2cd-4e36-b933-6ec0a2f9dfc2"
CONTROL_PREFIX = "MSY"
LANGUAGES = [("DE-DE", "Deutsch"), ("EN-US", "English")]
STATUS_DROPDOWN_UID = str(uuid.uuid5(NS, "dropdown:textvorlagen_status"))


def uid_for(kind: str, key: str) -> str:
    return str(uuid.uuid5(NS, f"{kind}:{key}"))


# (Gruppe, Feld, Typ, Label, Eigenschaften)
GENERAL = [
    ("ROOT", "SELF_NAME", "string", "Name", {}),
    ("ROOT", "TEMPLATE_KEY", "string", "Schlüssel", {"IMMUTABLE": True}),
    ("ROOT", "CHANNEL", "string", "Kanal (z. B. email)", {"IMMUTABLE": True}),
    ("ROOT", "DESCRIPTION", "text", "Beschreibung", {}),
    ("ROOT", "VARIABLES", "string", "Variablen (Komma-getrennt)", {"IMMUTABLE": True}),
    ("ROOT", "REQUIRED_VARIABLES", "string", "Pflichtvariablen (Komma-getrennt)", {"IMMUTABLE": True}),
    ("ROOT", "ACTIVE", "true_false", "Aktiv (wird verwendet)", {}),
    ("ROOT", "SOURCE_UID", "string", "Herkunft (Systemvorlage)", {"READ_ONLY": True}),
    ("ROOT", "SOURCE_HASH", "string", "Stand der Herkunft", {"READ_ONLY": True}),
]
MANDANT_ONLY = {"ACTIVE", "SOURCE_UID", "SOURCE_HASH"}
PER_LANGUAGE = [
    ("SUBJECT", "string", "Betreff", {}),
    ("BODY", "text", "Text", {"CONFIGS": {"text": {"rows": 8, "title": "Text"}}}),
    ("BODY_HTML", "text", "Text (HTML, optional)", {
        "CONFIGS": {"text": {"rows": 6, "title": "Text (HTML)", "mono": True, "html_preview": True}}}),
    ("STATUS", "dropdown", "Freigabestatus", {
        "CONFIGS": {"dropdown": {"key": STATUS_DROPDOWN_UID, "feld": "", "table": "sys_dropdowndaten", "gruppe": ""}}}),
    ("VERSION", "string", "Version", {"READ_ONLY": True}),
    ("APPROVED_BY", "string", "Freigegeben von", {"READ_ONLY": True}),
    ("APPROVED_AT", "string", "Freigegeben am", {"READ_ONLY": True}),
]


def control_specs() -> list[dict]:
    """Alle Controls mit Name, Gruppe, Feld, Typ, Label, Eigenschaften, Tab und Reihenfolge."""
    out = []
    for order, (gruppe, feld, typ, label, props) in enumerate(GENERAL, start=1):
        out.append({"name": f"{CONTROL_PREFIX}_{feld}", "gruppe": gruppe, "feld": feld, "type": typ, "label": label,
                    "props": props, "tab": 1, "order": order * 10})
    for tab, (lang, _head) in enumerate(LANGUAGES, start=2):
        for order, (feld, typ, label, props) in enumerate(PER_LANGUAGE, start=1):
            out.append({"name": f"{CONTROL_PREFIX}_{lang.replace('-', '_')}_{feld}", "gruppe": lang, "feld": feld,
                        "type": typ, "label": label, "props": props, "tab": tab, "order": order * 10})
    return out


def root_block(table: str, uid: str, name: str, stamp: str, **extra) -> dict:
    return {
        "TABLE": table, "SELF_GUID": uid, "SELF_NAME": name, "SELF_LINK_UID": uid,
        "SELF_CREATED_AT": stamp, "SELF_MODIFIED_AT": stamp, "SELF_GILT_BIS": "9999365.99999",
        "STRUCT_VERSION_APPLIED": 1, **extra,
    }


def build_control(mother: dict, spec: dict, uid: str, stamp: str) -> dict:
    ctrl = copy.deepcopy(mother)
    ctrl.pop("FELD", None)
    ctrl.update({"NAME": spec["name"], "FIELD": spec["feld"], "TYPE": spec["type"], "LABEL": spec["label"],
                 "TABLE": MANDANT_TABLE, "GRUPPE": spec["gruppe"]})
    ctrl.update(copy.deepcopy(spec["props"]))
    return {"ROOT": root_block("sys_control_dict", uid, spec["name"], stamp), "CONTROL": ctrl}


def build_status_dropdown(stamp: str) -> dict:
    labels = {
        "new": ("Neu", "new"), "machine": ("Maschinell", "machine"),
        "review": ("In Prüfung", "in review"), "approved": ("Freigegeben", "approved"),
    }
    return {
        "ROOT": root_block("sys_dropdowndaten", STATUS_DROPDOWN_UID, "Textvorlagen::status",
                           stamp, FIELD_KEY="textvorlagen_status", RECORD_TYPE="dropdown_definition",
                           DEFAULT_LANGUAGE="DE-DE", SUPPORTED_LANGUAGES=["DE-DE", "EN-US"]),
        "OPTIONS": {k: {"DE-DE": de, "EN-US": en} for k, (de, en) in labels.items()},
    }


def build_frame(table: str, frame_uid: str, name: str, control_uids: dict, stamp: str) -> dict:
    fields = {}
    for spec in control_specs():
        if table == SYSTEM_TABLE and spec["feld"] in MANDANT_ONLY and spec["gruppe"] == "ROOT":
            continue
        fields[control_uids[spec["name"]]] = {"TAB": spec["tab"], "DISPLAY_ORDER": spec["order"]}
    heads = [(1, "Vorlage", "ROOT")] + [(i, head, lang) for i, (lang, head) in enumerate(LANGUAGES, start=2)]
    return {
        "ROOT": {
            **root_block("sys_framedaten", frame_uid, name, stamp),
            "TABS": len(heads), "TABLE": "", "EDIT_TYPE": "pdvm_edit", "FRAME_TYPE": "standard", "GO_NEW_SET": True,
            "ROOT_TABLE": table,
            "TAB_ELEMENTS": {uid_for("frame-tab", f"{frame_uid}:{no}"): {"TAB": no, "HEAD": head, "GRUPPE": grp}
                             for no, head, grp in heads},
        },
        "FIELDS": fields,
    }


def build_view(table: str, view_uid: str, name: str, control_uids: dict, benutzer_view: dict, stamp: str) -> dict:
    columns = [("SELF_NAME", "Name"), ("TEMPLATE_KEY", "Schlüssel"), ("CHANNEL", "Kanal")]
    if table == MANDANT_TABLE:
        columns.append(("ACTIVE", "Aktiv"))
    group = {control_uids[f"{CONTROL_PREFIX}_{feld}"]: {"show": True, "display_order": order * 10}
             for order, (feld, _label) in enumerate(columns, start=1)}
    return {
        "ROOT": {
            **root_block("sys_viewdaten", view_uid, name, stamp),
            "TABLE": table, "NO_DATA": False, "ALLOW_SORT": True, "ALLOW_FILTER": True,
            "HEADER_TEXT": name, "PROJECTION_MODE": "standard", "DEFAULT_SORT_COLUMN": "", "DEFAULT_SORT_REVERSE": False,
        },
        "**SYSTEM": copy.deepcopy(benutzer_view.get("**SYSTEM", {})),
        table.upper(): group,
    }


def build_dialog(table: str, dialog_uid: str, view_uid: str, frame_uid: str, name: str, stamp: str) -> dict:
    tab = {"OPEN_EDIT": "double_click", "SELECTION_MODE": "single", "TABLE": table, "EDIT_TYPE": "pdvm_edit"}
    return {"ROOT": {
        **root_block("sys_dialogdaten", dialog_uid, name, stamp),
        "TABS": 2, "TABLE": table, "HEADER": name, "EDIT_TYPE": "pdvm_edit", "OPEN_EDIT": "double_click",
        "GO_NEW_SET": True, "SHOW_TABLE": False, "DIALOG_TYPE": "norm", "SELECTION_MODE": "single",
        "TAB_ELEMENTS": {
            "TAB_01": {"TAB": 1, "GUID": view_uid, "HEAD": "Übersicht", "MODULE": "view", **tab},
            "TAB_02": {"TAB": 2, "GUID": frame_uid, "HEAD": "Bearbeiten", "MODULE": "edit", **tab},
        },
    }}


TARGETS = [
    (MANDANT_TABLE, "Textvorlagen (Mandant)", 170),
    (SYSTEM_TABLE, "Textvorlagen (System)", 175),
]


async def run(args) -> int:
    stamp = now_pdvm_str()
    system = await connect(load_env_url(), "pdvm_system", read_only=not args.apply)
    try:
        writes: list[tuple[str, tuple]] = []
        log: list[str] = []
        before: dict = {}

        mother = as_dict(await system.fetchval("select daten from sys_control_dict where uid = $1::uuid", U666))["CONTROL"]
        existing = {r["name"]: str(r["uid"]) for r in await system.fetch("select uid, name from sys_control_dict")}
        control_uids: dict[str, str] = {}
        for spec in control_specs():
            uid = uid_for("control", spec["name"])
            control_uids[spec["name"]] = uid
            if spec["name"] in existing and existing[spec["name"]] != uid:
                raise SystemExit(f"Controlname {spec['name']} ist bereits mit anderer UID vergeben")
            if spec["name"] not in existing:
                writes.append(("insert into sys_control_dict (uid, name, daten, historisch, link_uid) "
                               "values ($1::uuid, $2, $3::jsonb, 0, $1::uuid)",
                               (uid, spec["name"], json.dumps(build_control(mother, spec, uid, stamp), ensure_ascii=False))))
                log.append(f"Control {spec['name']}")
            elif "text" in as_dict(spec["props"].get("CONFIGS")):
                # bestehende Text-Controls: Konfiguration des grossen Textfensters nachziehen
                row = as_dict(await system.fetchval("select daten from sys_control_dict where uid = $1::uuid", uid))
                configs = as_dict(as_dict(row.get("CONTROL")).get("CONFIGS"))
                wanted = spec["props"]["CONFIGS"]["text"]
                if configs.get("text") != wanted:
                    before.setdefault("controls", {})[uid] = copy.deepcopy(row)
                    row.setdefault("CONTROL", {}).setdefault("CONFIGS", {})["text"] = wanted
                    row.setdefault("ROOT", {})["SELF_MODIFIED_AT"] = stamp
                    writes.append(("update sys_control_dict set daten=$1::jsonb, modified_at=now() where uid=$2::uuid",
                                   (json.dumps(row, ensure_ascii=False), uid)))
                    log.append(f"Control {spec['name']}: Textfenster konfiguriert")

        async def missing(table: str, uid: str) -> bool:
            return not await system.fetchval(f"select 1 from {table} where uid = $1::uuid", uid)

        if await missing("sys_dropdowndaten", STATUS_DROPDOWN_UID):
            writes.append(("insert into sys_dropdowndaten (uid, name, daten, historisch, link_uid) "
                           "values ($1::uuid, 'Textvorlagen::status', $2::jsonb, 0, $1::uuid)",
                           (STATUS_DROPDOWN_UID, json.dumps(build_status_dropdown(stamp), ensure_ascii=False))))
            log.append("Dropdown Textvorlagen::status")

        benutzer_view = as_dict(await system.fetchval("select daten from sys_viewdaten where uid = $1::uuid", BENUTZER_VIEW_UID))
        menu = as_dict(await system.fetchval("select daten from sys_menudaten where uid = $1::uuid", MENU_UID))
        menu_before = copy.deepcopy(menu)
        for table, title, sort_order in TARGETS:
            key = table.split("_", 1)[0]
            frame_uid, view_uid, dialog_uid = (uid_for(k, table) for k in ("frame", "view", "dialog"))
            menu_uid = uid_for("menu", table)
            if await missing("sys_framedaten", frame_uid):
                name = f"Textvorlagen Edit ({'Mandant' if key == 'msy' else 'System'})"
                writes.append(("insert into sys_framedaten (uid, name, daten, historisch, link_uid) "
                               "values ($1::uuid, $2, $3::jsonb, 0, $1::uuid)",
                               (frame_uid, name, json.dumps(build_frame(table, frame_uid, name, control_uids, stamp), ensure_ascii=False))))
                log.append(f"Frame {name}")
            if await missing("sys_viewdaten", view_uid):
                writes.append(("insert into sys_viewdaten (uid, name, daten, historisch, link_uid) "
                               "values ($1::uuid, $2, $3::jsonb, 0, $1::uuid)",
                               (view_uid, title, json.dumps(build_view(table, view_uid, title, control_uids, benutzer_view, stamp), ensure_ascii=False))))
                log.append(f"View {title}")
            if await missing("sys_dialogdaten", dialog_uid):
                writes.append(("insert into sys_dialogdaten (uid, name, daten, historisch, link_uid) "
                               "values ($1::uuid, $2, $3::jsonb, 0, $1::uuid)",
                               (dialog_uid, title, json.dumps(build_dialog(table, dialog_uid, view_uid, frame_uid, title, stamp), ensure_ascii=False))))
                log.append(f"Dialog {title}")
            if menu_uid not in menu.get("GRUND", {}):
                menu.setdefault("GRUND", {})[menu_uid] = {
                    "icon": "FileText", "type": "BUTTON", "label": title,
                    "command": {"params": {"table": table, "dialog_guid": dialog_uid}, "handler": "go_pdvm_dialog"},
                    "enabled": True, "visible": True, "sort_order": sort_order, "parent_guid": MENU_PARENT,
                    "tooltip": "Textvorlagen für Nachrichten (z. B. E-Mails) pflegen.",
                }
                log.append(f"Menü {title}")
        if menu != menu_before:
            menu["ROOT"]["SELF_MODIFIED_AT"] = stamp
            before["menu"] = menu_before
            writes.append(("update sys_menudaten set daten=$1::jsonb, modified_at=now() where uid=$2::uuid",
                           (json.dumps(menu, ensure_ascii=False), MENU_UID)))

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
    ap.add_argument("--snapshot", help="Pfad fuer den Snapshot des Menues vor der Aenderung (ausserhalb des Repositorys)")
    args = ap.parse_args()
    if args.apply and not (args.confirm_backup and args.snapshot):
        raise SystemExit("--apply verlangt --confirm-backup und --snapshot")
    sys.exit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()

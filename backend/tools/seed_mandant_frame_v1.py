"""
Legt die Maske fuer Mandantendaten (asy_mandanten) als Frame an und bereinigt die 666-Vorlage.

Spezifikation: docs/specs/PDVM_FRAME_INPUT_RENDERING_SPEC_V1.md, Regel 2.15 (ARCHITECTURE_RULES.md)

Schritte (idempotent):
1. sys_control_dict: ein Control je Feld (TABLE asy_mandanten, Name ASY_<FELD>, bei Kollision ASY_<GRUPPE>_<FELD>).
2. sys_framedaten: Frame `Mandanten Edit` (UID = app.core.mandant_record_rules.MANDANT_FRAME_GUID) mit Tabs/Layout.
3. asy_mandanten 666 (reservierter Satz, ausdrueckliche Freigabe 2026-11-13): TEMPLATES.MANDANT.PASSWORD und
   TEMPLATES.SEND_EMAIL.SMTP_PASS entfernen, Credential-Verweise (CREDENTIAL, SYSTEM_CREDENTIAL) ergaenzen,
   Testdaten (Datenbank, Adresse, Kontakt, Mail-Zugang, ROOT.DB_CREATED_AT) auf neutrale Vorgaben setzen.

Aufruf aus backend/ (Standard ist Dry-Run):
  ..\\.venv\\Scripts\\python.exe tools\\seed_mandant_frame_v1.py
  ..\\.venv\\Scripts\\python.exe tools\\seed_mandant_frame_v1.py --apply --confirm-backup --snapshot <Pfad.json>

Der Snapshot enthaelt die entfernten Passwoerter im Klartext: ausserhalb des Repositorys ablegen.
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
    FORBIDDEN_SECRET_FIELDS,
    MANDANT_FRAME_GUID,
    MANDANT_TABLE,
    MANDANT_TEMPLATE_UID,
)
from app.core.pdvm_datetime import now_pdvm_str  # noqa: E402
from audit_system_data import U666, as_dict, load_env_url  # noqa: E402
from seed_base_records import connect  # noqa: E402

PREFIX = "ASY"
NS = uuid.UUID("6f1a5b0e-2a0c-4d6b-9b3e-5d1f0c7a9e11")
FRAME_NAME = "Mandanten Edit"

# Tab -> (Kopf, [(Gruppe, Feld, Typ, Label)]); Reihenfolge = DISPLAY_ORDER (10er-Schritte).
TABS = [
    ("Mandant", [
        ("ROOT", "NAME", "string", "Bezeichnung"),
        ("MANDANT", "DESCRIPTION", "string", "Beschreibung"),
        ("MANDANT", "IS_ACTIVE", "true_false", "Aktiv"),
        ("MANDANT", "IS_ALLOWED", "true_false", "Zugelassen"),
        ("CONFIG", "MAX_USERS", "number", "Maximale Benutzerzahl"),
        ("ROOT", "IDLE_TIMEOUT", "number", "Inaktivität bis Abmeldung (Sekunden)"),
        ("ROOT", "IDLE_WARNING", "number", "Warnung vor Abmeldung (Sekunden)"),
    ]),
    ("Verbindung", [
        ("MANDANT", "DATABASE", "string", "Mandanten-Datenbank"),
        ("MANDANT", "HOST", "string", "Server (Host)"),
        ("MANDANT", "PORT", "number", "Port"),
        ("MANDANT", "USER", "string", "Datenbank-Benutzer"),
        ("MANDANT", "CREDENTIAL", "string", "Zugangsdaten (Credential-Name)"),
        ("MANDANT", "SYSTEM_DB", "string", "System-Datenbank"),
        ("MANDANT", "SYSTEM_HOST", "string", "System-Server (Host)"),
        ("MANDANT", "SYSTEM_PORT", "number", "System-Port"),
        ("MANDANT", "SYSTEM_USER", "string", "System-Datenbank-Benutzer"),
        ("MANDANT", "SYSTEM_CREDENTIAL", "string", "System-Zugangsdaten (Credential-Name)"),
    ]),
    ("Kontakt", [
        ("CONTACT", "LABEL", "string", "Bezeichnung"),
        ("CONTACT", "STREET", "string", "Straße"),
        ("CONTACT", "TOWN", "string", "Ort"),
        ("CONTACT", "FON", "string", "Telefon"),
        ("CONTACT", "EMAIL", "string", "E-Mail"),
    ]),
    ("E-Mail-Versand", [
        ("SEND_EMAIL", "MAIL", "string", "Absenderadresse"),
        ("SEND_EMAIL", "SENDER_NAME", "string", "Absendername"),
        ("SEND_EMAIL", "REPLY_TO", "string", "Antwortadresse"),
        ("SEND_EMAIL", "SMTP_HOST", "string", "SMTP-Server"),
        ("SEND_EMAIL", "SMTP_PORT", "number", "SMTP-Port"),
        ("SEND_EMAIL", "SMTP_USER", "string", "SMTP-Benutzer"),
        ("SEND_EMAIL", "CREDENTIAL", "string", "Zugangsdaten (Credential-Name)"),
        ("SEND_EMAIL", "SMTP_SSL", "true_false", "SSL verwenden"),
        ("SEND_EMAIL", "SMTP_STARTTLS", "true_false", "STARTTLS verwenden"),
        ("SEND_EMAIL", "OTP_RATE_LIMIT", "number", "OTP-Limit"),
    ]),
]

# Neue Felder in der 666-Vorlage (leer = Standard bzw. kein Credential).
TEMPLATE_ADDITIONS = {("MANDANT", "CREDENTIAL"): "", ("MANDANT", "SYSTEM_CREDENTIAL"): "", ("SEND_EMAIL", "CREDENTIAL"): ""}
for _field in ("SYSTEM_HOST", "SYSTEM_PORT", "SYSTEM_USER"):
    TEMPLATE_ADDITIONS[("MANDANT", _field)] = ""

# Neutrale Vorgaben statt Testdaten eines Einzelmandanten (Datenbank, Adresse, Kontakt, Mail-Zugang).
# Leere Adress-/Benutzerwerte bedeuten: AUTH-Instanz bzw. Credential (Spec PDVM_DB_VERBINDUNGEN, 3.1/3.2).
TEMPLATE_RESET = {
    ("MANDANT", "HOST"): "", ("MANDANT", "PORT"): "", ("MANDANT", "USER"): "",
    ("MANDANT", "DATABASE"): "", ("MANDANT", "DESCRIPTION"): "",
    ("CONTACT", "LABEL"): "", ("CONTACT", "STREET"): "", ("CONTACT", "TOWN"): "",
    ("CONTACT", "FON"): "", ("CONTACT", "EMAIL"): "",
    ("SEND_EMAIL", "MAIL"): "", ("SEND_EMAIL", "REPLY_TO"): "", ("SEND_EMAIL", "SENDER_NAME"): "",
    ("SEND_EMAIL", "SMTP_HOST"): "", ("SEND_EMAIL", "SMTP_USER"): "",
}
# Altfelder ohne Funktion im Neuanlage-Satz (SYSTEM_DATABASE doppelt SYSTEM_DB; MODIFIED ist ein Testwert).
TEMPLATE_REMOVE = [("MANDANT", "SYSTEM_DATABASE"), ("MANDANT", "MODIFIED")]
# ROOT-Werte, die in einem neuen Satz nicht vorbelegt sein duerfen (sonst gilt die DB als bereits eingerichtet).
TEMPLATE_ROOT_REMOVE = ["DB_CREATED_AT"]


def control_names(existing: dict[str, str]) -> dict[tuple[str, str], str]:
    """Name je (Gruppe, Feld): ASY_<FELD>; bei Kollision (auch mit vorhandenen Controls) ASY_<GRUPPE>_<FELD>."""
    all_specs = [(g, f) for _, rows in TABS for g, f, _, _ in rows]
    names: dict[tuple[str, str], str] = {}
    for gruppe, feld in all_specs:
        short = f"{PREFIX}_{feld}"
        clash = sum(1 for _, f in all_specs if f == feld) > 1
        owner = existing.get(short)
        if clash or (owner is not None and owner != MANDANT_TABLE):
            names[(gruppe, feld)] = f"{PREFIX}_{gruppe}_{feld}"
        else:
            names[(gruppe, feld)] = short
    return names


def build_control(mother: dict, name: str, uid: str, stamp: str, gruppe: str, feld: str, typ: str, label: str) -> dict:
    ctrl = copy.deepcopy(mother)
    ctrl.pop("FELD", None)  # Alias-Verbot (Regel 1.12b)
    ctrl.update({"NAME": name, "FIELD": feld, "TYPE": typ, "LABEL": label, "TABLE": MANDANT_TABLE, "GRUPPE": gruppe})
    return {
        "ROOT": {
            "TABLE": "sys_control_dict", "SELF_GUID": uid, "SELF_NAME": name, "SELF_LINK_UID": uid,
            "SELF_CREATED_AT": stamp, "SELF_MODIFIED_AT": stamp, "SELF_GILT_BIS": "9999365.99999",
            "STRUCT_VERSION_APPLIED": 1,
        },
        "CONTROL": ctrl,
    }


def build_frame(uids: list[list[str]], stamp: str) -> dict:
    fields, tab_elements = {}, {}
    for tab_no, ((head, rows), tab_uids) in enumerate(zip(TABS, uids), start=1):
        tab_elements[str(uuid.uuid5(NS, f"frame-tab:{MANDANT_FRAME_GUID}:{tab_no}"))] = {"TAB": tab_no, "HEAD": head, "GRUPPE": head.upper()}
        for order, uid in enumerate(tab_uids, start=1):
            fields[uid] = {"TAB": tab_no, "DISPLAY_ORDER": order * 10}
    return {
        "ROOT": {
            "TABS": len(TABS), "TABLE": "", "EDIT_TYPE": "pdvm_edit", "FRAME_TYPE": "standard", "GO_NEW_SET": True,
            "ROOT_TABLE": MANDANT_TABLE, "TAB_ELEMENTS": tab_elements,
            "SELF_GUID": MANDANT_FRAME_GUID, "SELF_NAME": FRAME_NAME, "SELF_LINK_UID": MANDANT_FRAME_GUID,
            "SELF_CREATED_AT": stamp, "SELF_MODIFIED_AT": stamp, "SELF_GILT_BIS": "9999365.99999",
            "STRUCT_VERSION_APPLIED": 1,
        },
        "FIELDS": fields,
    }


def clean_template(daten: dict, stamp: str) -> tuple[dict, list[str], dict]:
    """Liefert (neue Daten, Aenderungsliste, entfernte Geheimnisse)."""
    out = copy.deepcopy(daten)
    templates = out.setdefault("TEMPLATES", {})
    changes: list[str] = []
    removed: dict = {}
    for (group, field) in FORBIDDEN_SECRET_FIELDS:
        content = templates.get(group)
        if isinstance(content, dict) and field in content:
            removed[f"{group}.{field}"] = content.pop(field)
            changes.append(f"entfernt: TEMPLATES.{group}.{field}")
    for (group, field), default in TEMPLATE_ADDITIONS.items():
        content = templates.setdefault(group, {})
        if field not in content:
            content[field] = default
            changes.append(f"ergaenzt: TEMPLATES.{group}.{field}")
    for (group, field), value in TEMPLATE_RESET.items():
        content = templates.setdefault(group, {})
        if content.get(field) != value:
            content[field] = value
            changes.append(f"zurueckgesetzt: TEMPLATES.{group}.{field}")
    for group, field in TEMPLATE_REMOVE:
        if isinstance(templates.get(group), dict) and field in templates[group]:
            del templates[group][field]
            changes.append(f"entfernt: TEMPLATES.{group}.{field}")
    for field in TEMPLATE_ROOT_REMOVE:
        if field in out.get("ROOT", {}):
            del out["ROOT"][field]
            changes.append(f"entfernt: ROOT.{field}")
    if changes:
        out.setdefault("ROOT", {})["SELF_MODIFIED_AT"] = stamp
    return out, changes, removed


async def run(args) -> int:
    env = load_env_url()
    stamp = now_pdvm_str()
    system = await connect(env, "pdvm_system", read_only=not args.apply)
    auth = await connect(env, "auth", read_only=not args.apply)
    try:
        existing_rows = await system.fetch("select uid, name, daten from sys_control_dict")
        existing = {r["name"]: as_dict(r["daten"]).get("CONTROL", {}).get("TABLE", "") for r in existing_rows}
        existing_uids = {r["name"]: str(r["uid"]) for r in existing_rows}
        mother = as_dict(next(r["daten"] for r in existing_rows if str(r["uid"]) == U666)).get("CONTROL", {})
        names = control_names(existing)

        new_controls, uids = {}, []
        for head, rows in TABS:
            tab_uids = []
            for gruppe, feld, typ, label in rows:
                name = names[(gruppe, feld)]
                if name in existing and existing[name] == MANDANT_TABLE:
                    tab_uids.append(existing_uids[name])
                    continue
                uid = str(uuid.uuid5(NS, f"control:{name}"))
                new_controls[uid] = (name, build_control(mother, name, uid, stamp, gruppe, feld, typ, label))
                tab_uids.append(uid)
            uids.append(tab_uids)

        frame_exists = await system.fetchval("select 1 from sys_framedaten where uid = $1::uuid", MANDANT_FRAME_GUID)
        frame_daten = build_frame(uids, stamp)

        tmpl = await auth.fetchrow(f"select daten from {MANDANT_TABLE} where uid = $1::uuid", MANDANT_TEMPLATE_UID)
        old_tmpl = as_dict(tmpl["daten"]) if tmpl else {}
        new_tmpl, tmpl_changes, removed = clean_template(old_tmpl, stamp)

        print(f"{'APPLY' if args.apply else 'Dry-Run'}: {len(new_controls)} neue Controls, "
              f"Frame {'vorhanden (bleibt)' if frame_exists else 'wird angelegt'}, "
              f"666-Vorlage: {len(tmpl_changes)} Aenderung(en)")
        for name, _ in new_controls.values():
            print(f"  Control {name}")
        for line in tmpl_changes:
            print(f"  666: {line}")
        if not args.apply:
            return 0

        Path(args.snapshot).write_text(json.dumps(
            {"template_666_before": old_tmpl, "removed_secrets": removed,
             "created_controls": list(new_controls), "created_frame": None if frame_exists else MANDANT_FRAME_GUID},
            ensure_ascii=False, indent=1, default=str), encoding="utf-8")

        async with system.transaction():
            for uid, (name, daten) in new_controls.items():
                await system.execute(
                    "insert into sys_control_dict (uid, name, daten, historisch, link_uid) "
                    "values ($1::uuid, $2, $3::jsonb, 0, $1::uuid)",
                    uid, name, json.dumps(daten, ensure_ascii=False),
                )
            if not frame_exists:
                await system.execute(
                    "insert into sys_framedaten (uid, name, daten, historisch, link_uid) "
                    "values ($1::uuid, $2, $3::jsonb, 0, $1::uuid)",
                    MANDANT_FRAME_GUID, FRAME_NAME, json.dumps(frame_daten, ensure_ascii=False),
                )
        if tmpl_changes:
            await auth.execute(
                f"update {MANDANT_TABLE} set daten = $1::jsonb, modified_at = now() where uid = $2::uuid",
                json.dumps(new_tmpl, ensure_ascii=False), MANDANT_TEMPLATE_UID,
            )
        print(f"Snapshot: {args.snapshot}")
        return 0
    finally:
        await system.close()
        await auth.close()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--confirm-backup", action="store_true")
    ap.add_argument("--snapshot", help="Pfad fuer den Snapshot (Pflicht mit --apply, ausserhalb des Repositorys)")
    args = ap.parse_args()
    if args.apply and not (args.confirm_backup and args.snapshot):
        raise SystemExit("--apply verlangt --confirm-backup und --snapshot")
    sys.exit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()

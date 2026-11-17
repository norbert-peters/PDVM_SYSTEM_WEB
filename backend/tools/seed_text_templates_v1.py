"""
Legt die Tabelle sys_textvorlagen an und seedet die System-Textvorlagen (derzeit PASSWORD_RESET, DE-DE und EN-US).

Spezifikation: docs/specs/PDVM_TEXTVORLAGEN_SPEC_V1.md, Regel 1.24.

Idempotent: vorhandene Vorlagen werden nie ueberschrieben (Aenderungen laufen ueber den Editor). Die Basissaetze
000/555/666 der neuen Tabelle legt anschliessend `seed_base_records.py --db pdvm_system --apply` an.

Aufruf aus backend/ (Standard ist Dry-Run):
  ..\\.venv\\Scripts\\python.exe tools\\seed_text_templates_v1.py
  ..\\.venv\\Scripts\\python.exe tools\\seed_text_templates_v1.py --apply --confirm-backup
"""
from __future__ import annotations

import argparse
import asyncio
import copy
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.core.i18n_policy import normalize_language  # noqa: E402
from app.core.mandant_db_maintenance import MandantDatabaseMaintenance  # noqa: E402
from app.core.pdvm_datetime import now_pdvm_str  # noqa: E402
from app.core.text_template_service import SYSTEM_TABLE, language_groups, source_hash, validate_template  # noqa: E402
from audit_system_data import as_dict, load_env_url  # noqa: E402
from seed_base_records import connect  # noqa: E402

NS = uuid.UUID("6f1a5b0e-2a0c-4d6b-9b3e-5d1f0c7a9e11")

TEMPLATES = [
    {
        "key": "PASSWORD_RESET",
        "name": "Passwort zurücksetzen (E-Mail)",
        "description": "Einmalpasswort nach „Passwort vergessen“ bzw. maschinellem Passwort durch den Administrator.",
        "channel": "email",
        "variables": ["otp", "expires_minutes", "user_email"],
        "required": ["otp"],
        "languages": {
            "DE-DE": {
                "SUBJECT": "PDVM Passwort zurücksetzen",
                "BODY": (
                    "Ihr neues einmaliges Passwort wurde erzeugt.\n\n"
                    "Passwort: {{otp}}\n"
                    "Gültigkeit: {{expires_minutes}} Minuten\n\n"
                    "Bitte melden Sie sich an und ändern Sie Ihr Passwort sofort."
                ),
            },
            "EN-US": {
                "SUBJECT": "PDVM password reset",
                "BODY": (
                    "Your new one-time password has been generated.\n\n"
                    "Password: {{otp}}\n"
                    "Valid for: {{expires_minutes}} minutes\n\n"
                    "Please sign in and change your password immediately."
                ),
            },
        },
    },
]


def build_daten(tpl: dict, uid: str, stamp: str) -> dict:
    approved_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    release = {"STATUS": "approved", "VERSION": "v1.0.0", "APPROVED_BY": "system", "APPROVED_AT": approved_at}
    daten = {
        "ROOT": {
            "TABLE": SYSTEM_TABLE, "SELF_GUID": uid, "SELF_NAME": tpl["name"], "SELF_LINK_UID": uid,
            "SELF_CREATED_AT": stamp, "SELF_MODIFIED_AT": stamp, "SELF_GILT_BIS": "9999365.99999",
            "STRUCT_VERSION_APPLIED": 1,
            "TEMPLATE_KEY": tpl["key"], "CHANNEL": tpl["channel"], "DESCRIPTION": tpl["description"],
            "VARIABLES": tpl["variables"], "REQUIRED_VARIABLES": tpl["required"],
        },
        **{lang: {**texts, **release} for lang, texts in tpl["languages"].items()},
    }
    errors = validate_template(daten)
    if errors:
        raise SystemExit(f"Vorlage {tpl['key']} ungültig: {errors}")
    return daten


def add_missing_release_fields(daten: dict) -> tuple[dict, list[str]]:
    """Ergaenzt Freigabefelder in Sprachgruppen ohne STATUS (Vorlagen aus der Zeit vor dem Freigabemodell)."""
    out, changed = copy.deepcopy(daten), []
    approved_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    for lang in language_groups(out):
        group = next(g for k, g in out.items() if k != "ROOT" and normalize_language(k) == lang)
        if not group.get("STATUS"):
            group.update({"STATUS": "approved", "VERSION": "v1.0.0", "APPROVED_BY": "system", "APPROVED_AT": approved_at})
            changed.append(lang)
    return out, changed


async def run(args) -> int:
    stamp = now_pdvm_str()
    conn = await connect(load_env_url(), "pdvm_system", read_only=not args.apply)
    try:
        has_table = await conn.fetchval("select to_regclass('public.' || $1) is not null", SYSTEM_TABLE)
        print(f"{'APPLY' if args.apply else 'Dry-Run'}: Tabelle {SYSTEM_TABLE} {'vorhanden' if has_table else 'wird angelegt'}")
        todo, upgrades = [], []
        for tpl in TEMPLATES:
            uid = str(uuid.uuid5(NS, f"textvorlage:{tpl['key']}"))
            row = await conn.fetchrow(f"select daten from {SYSTEM_TABLE} where uid = $1::uuid", uid) if has_table else None
            daten = build_daten(tpl, uid, stamp)
            if row is None:
                print(f"  {tpl['key']} ({uid[:8]}): wird angelegt, Stand {source_hash(daten)[:8]}")
                todo.append((uid, tpl["name"], daten))
                continue
            upgraded, langs = add_missing_release_fields(as_dict(row["daten"]))
            print(f"  {tpl['key']} ({uid[:8]}): vorhanden (Texte bleiben)"
                  + (f", Freigabefelder ergänzen: {langs}" if langs else ""))
            if langs:
                upgrades.append((uid, upgraded))
        if not args.apply:
            return 0
        async with conn.transaction():
            if not has_table:
                await MandantDatabaseMaintenance(None, "", {})._create_pdvm_table(conn, SYSTEM_TABLE)
            for uid, name, daten in todo:
                await conn.execute(
                    f"insert into {SYSTEM_TABLE} (uid, name, daten, historisch, link_uid) "
                    "values ($1::uuid, $2, $3::jsonb, 0, $1::uuid)",
                    uid, name, json.dumps(daten, ensure_ascii=False))
            for uid, daten in upgrades:
                await conn.execute(
                    f"update {SYSTEM_TABLE} set daten = $1::jsonb, modified_at = now() where uid = $2::uuid",
                    json.dumps(daten, ensure_ascii=False), uid)
        print(f"{len(todo)} Vorlage(n) angelegt, {len(upgrades)} ergänzt")
        return 0
    finally:
        await conn.close()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--confirm-backup", action="store_true")
    args = ap.parse_args()
    if args.apply and not args.confirm_backup:
        raise SystemExit("--apply verlangt --confirm-backup")
    sys.exit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()

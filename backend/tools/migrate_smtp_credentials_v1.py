"""
Ueberfuehrt SMTP-Passwoerter aus asy_mandanten in den Credential-Store (Tabelle asy_credentials, verschluesselt).

Spezifikation: docs/specs/PDVM_FRAME_INPUT_RENDERING_SPEC_V1.md (Abschnitt 9), Regel 2.15.

Je Mandant mit SEND_EMAIL.SMTP_PASS:
1. Zugangsdatensatz `mail-<erste 8 Zeichen der Mandanten-UID>` mit dem Passwort anlegen (Chiffretext).
2. Pruefen, dass der Store dasselbe Passwort liefert.
3. SEND_EMAIL.CREDENTIAL setzen, SEND_EMAIL.SMTP_PASS aus daten UND daten_backup entfernen.
Ausserdem: Control ASY_SEND_EMAIL_CREDENTIAL auf Typ `password` (Label `SMTP-Passwort`) umstellen.

Voraussetzung: PDVM_SECRET_KEY ist in der .env gesetzt. Es entsteht kein Klartext-Snapshot; das Passwort liegt
danach verschluesselt in asy_credentials (Wiederherstellung nur mit dem Schluessel).

Aufruf aus backend/ (Standard ist Dry-Run):
  ..\\.venv\\Scripts\\python.exe tools\\migrate_smtp_credentials_v1.py
  ..\\.venv\\Scripts\\python.exe tools\\migrate_smtp_credentials_v1.py --apply --confirm-backup
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

from app.core import credential_service, credential_store  # noqa: E402
from app.core.central_write_service import update_record_central  # noqa: E402
from app.core.database import DatabasePool  # noqa: E402
from app.core.pdvm_datetime import now_pdvm_str  # noqa: E402
from audit_system_data import as_dict, load_env_url  # noqa: E402
from seed_base_records import connect  # noqa: E402

NS = uuid.UUID("6f1a5b0e-2a0c-4d6b-9b3e-5d1f0c7a9e11")
CONTROL_UID = str(uuid.uuid5(NS, "control:ASY_SEND_EMAIL_CREDENTIAL"))
RESERVED_PREFIXES = ("0000", "5555", "6666")


def credential_name(mandant_uid: str) -> str:
    return f"mail-{str(mandant_uid)[:8]}"


async def run(args) -> int:
    await DatabasePool.create_pool()
    system = await connect(load_env_url(), "pdvm_system", read_only=not args.apply)
    try:
        pool = DatabasePool._pool_auth
        rows = await pool.fetch("select uid::text u, name, daten::text dt, daten_backup::text bk from asy_mandanten order by name")
        todo = []
        for r in rows:
            if r["u"].startswith(RESERVED_PREFIXES):
                continue
            send = as_dict(as_dict(r["dt"]).get("SEND_EMAIL"))
            backup_has = "SMTP_PASS" in (r["bk"] or "")
            if send.get("SMTP_PASS") or backup_has:
                todo.append((r, send, backup_has))

        control_row = await system.fetchrow("select daten from sys_control_dict where uid = $1::uuid", CONTROL_UID)
        control = as_dict(control_row["daten"]) if control_row else {}
        control_change = bool(control) and control["CONTROL"].get("TYPE") != "password"

        print(f"{'APPLY' if args.apply else 'Dry-Run'}: {len(todo)} Mandant(en), Control-Umstellung: {control_change}")
        for r, send, backup_has in todo:
            cred = credential_name(r["u"])
            print(f"  {r['name']}: SMTP_PASS -> Credential '{cred}'"
                  f"{' (Klartext auch in daten_backup)' if backup_has else ''}"
                  f"{'' if send.get('SMTP_PASS') else ' [nur noch Backup bereinigen]'}")
        if not args.apply:
            return 0

        for r, send, backup_has in todo:
            cred = credential_name(r["u"])
            legacy = str(send.get("SMTP_PASS") or "")
            if legacy:
                await credential_service.set_credential(cred, legacy, user=None)
                stored = credential_store.get_credential(cred)
                if stored is None or stored.password != legacy:
                    raise SystemExit(f"Abbruch: Store liefert für '{cred}' nicht dasselbe Passwort (nichts entfernt)")
                daten = as_dict(r["dt"])
                daten["SEND_EMAIL"]["CREDENTIAL"] = cred
                daten["SEND_EMAIL"].pop("SMTP_PASS", None)
                daten.setdefault("ROOT", {})["SELF_MODIFIED_AT"] = now_pdvm_str()
                await update_record_central(table_name="asy_mandanten", uid=r["u"], daten=daten, name=r["name"])
            # Klartext auch aus der Sicherungsspalte entfernen
            await pool.execute(
                "update asy_mandanten set daten_backup = daten_backup #- '{SEND_EMAIL,SMTP_PASS}' where uid = $1::uuid", r["u"])
            print(f"  {r['name']}: überführt")

        if control_change:
            new_control = copy.deepcopy(control)
            new_control["CONTROL"].update(
                {"TYPE": "password", "LABEL": "SMTP-Passwort", "CONFIGS": {"password": {"name_prefix": "mail"}}}
            )
            new_control["ROOT"]["SELF_MODIFIED_AT"] = now_pdvm_str()
            await system.execute(
                "update sys_control_dict set daten=$1::jsonb, modified_at=now() where uid=$2::uuid",
                json.dumps(new_control, ensure_ascii=False), CONTROL_UID)
            print("  Control ASY_SEND_EMAIL_CREDENTIAL: Typ password")
        return 0
    finally:
        await system.close()
        await DatabasePool.close_pool()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--confirm-backup", action="store_true", help="Bestaetigt, dass ein Backup der AUTH-DB existiert")
    args = ap.parse_args()
    if args.apply and not args.confirm_backup:
        raise SystemExit("--apply verlangt --confirm-backup")
    sys.exit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()

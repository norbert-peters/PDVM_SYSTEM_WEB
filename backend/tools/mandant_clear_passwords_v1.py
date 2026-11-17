"""
Entfernt das veraltete Feld MANDANT.PASSWORD aus asy_mandanten.

Spezifikation: docs/specs/PDVM_DB_VERBINDUNGEN_UND_ZUGANGSDATEN_SPEC_V1.md (Abschnitt 4, Schritt 3)

Ein Passwort wird nur entfernt, wenn die Aufloesung ohne das Feld (CREDENTIAL, Credential 'default' oder
AUTH-Zugangsdaten auf derselben Instanz) dasselbe Passwort liefert. Sonst bleibt es stehen und wird gemeldet.

Aufruf aus backend/ (Standard ist Dry-Run, es wird nichts geschrieben):
  ..\\.venv\\Scripts\\python.exe tools\\mandant_clear_passwords_v1.py
  ..\\.venv\\Scripts\\python.exe tools\\mandant_clear_passwords_v1.py --apply --confirm-backup --snapshot <Pfad.json>

Der Snapshot enthaelt die entfernten Passwoerter im Klartext: ausserhalb des Repositorys ablegen.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

import asyncpg

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings  # noqa: E402
from app.core.connection_manager import ConnectionManager  # noqa: E402
from app.core.pdvm_datetime import PdvmDateTime  # noqa: E402


def _as_dict(value) -> dict:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except ValueError:
            return {}
    return {}


def check(mandant_info: dict) -> tuple[bool, str]:
    legacy = str(mandant_info.get("PASSWORD") or "")
    without = {k: v for k, v in mandant_info.items() if k != "PASSWORD"}
    try:
        system, mandant = ConnectionManager.resolve_mandant_connections(without)
    except ValueError as exc:
        return False, f"Aufloesung ohne PASSWORD scheitert: {exc}"
    if mandant.password != legacy:
        return False, "Aufloesung ohne PASSWORD liefert ein anderes Passwort (Credential/.env anpassen)"
    if system.password != legacy:
        return False, "System-DB loest ohne PASSWORD ein anderes Passwort auf (SYSTEM_CREDENTIAL pruefen)"
    return True, "bereit"


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="Passwoerter wirklich entfernen")
    parser.add_argument("--confirm-backup", action="store_true", help="Bestaetigt, dass ein Backup der AUTH-DB existiert")
    parser.add_argument("--snapshot", help="Pfad fuer den Snapshot der entfernten Passwoerter (Pflicht mit --apply)")
    args = parser.parse_args()

    if args.apply and not (args.confirm_backup and args.snapshot):
        parser.error("--apply verlangt --confirm-backup und --snapshot")

    conn = await asyncpg.connect(settings.DATABASE_URL_AUTH)
    try:
        rows = await conn.fetch("SELECT uid, name, daten FROM asy_mandanten ORDER BY name")
        ready, snapshot = [], []
        for row in rows:
            info = _as_dict(_as_dict(row["daten"]).get("MANDANT"))
            if not info.get("PASSWORD"):
                continue
            ok, reason = check(info)
            print(f"{'OK  ' if ok else 'SKIP'} {row['name']} ({row['uid']}): {reason}")
            if ok:
                ready.append(row["uid"])
                snapshot.append({"uid": str(row["uid"]), "name": row["name"], "PASSWORD": info["PASSWORD"]})

        print(f"\n{len(ready)} Mandant(en) bereit zum Leeren.")
        if not args.apply:
            print("Dry-Run: nichts geschrieben.")
            return 0

        Path(args.snapshot).write_text(json.dumps(snapshot, indent=1), encoding="utf-8")
        now_pdvm = PdvmDateTime().now().pdvm_datetime_str
        async with conn.transaction():
            for uid in ready:
                await conn.execute(
                    """
                    UPDATE asy_mandanten
                       SET daten = jsonb_set(daten #- '{MANDANT,PASSWORD}', '{ROOT,SELF_MODIFIED_AT}', to_jsonb($2::text), false),
                           modified_at = now()
                     WHERE uid = $1
                    """,
                    uid, now_pdvm,
                )
        print(f"{len(ready)} Passwort(e) entfernt, Snapshot: {args.snapshot}")
        return 0
    finally:
        await conn.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

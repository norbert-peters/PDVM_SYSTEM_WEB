"""
DATA_UPDATE-Schritt `textvorlagen`: liefert Textvorlagen in bestehende Mandanten-DBs nach (Regel 1.20, Regel 1.24).

Je Mandant (asy_mandanten, ohne reservierte Saetze):
1. Tabelle `msy_textvorlagen` muss existieren (Struktur ist DATABASE_UPDATE bzw. die Mandanten-Wartung beim Login);
   fehlt sie, wird der Mandant mit Hinweis uebersprungen. Mit `--with-maintenance` (nur zusammen mit `--apply`) laeuft
   dieselbe Mandanten-Wartung wie beim Login und legt sie an.
2. Fehlende Basissaetze 000/555/666 werden angelegt (nur Ergaenzen, nichts wird veraendert).
3. Fehlende Systemvorlagen werden als Mandantenvorlage kopiert (`text_template_service.ensure_mandant_templates`,
   neue UID, SOURCE_UID/SOURCE_HASH, aktiv). Bereits uebernommene Vorlagen bleiben unberuehrt.

Ausschliesslich Inserts: nichts wird ueberschrieben oder geloescht; Wiederholung erzeugt keine Seiteneffekte.
Die Versionsachsen (`msy_update_state`) fuehrt weiterhin `mandant_update_apply_v1.py`.

Aufruf aus backend/ (Standard ist Dry-Run, mit PYTHONUTF8=1):
  ..\\.venv\\Scripts\\python.exe tools\\mandant_textvorlagen_update_v1.py
  ..\\.venv\\Scripts\\python.exe tools\\mandant_textvorlagen_update_v1.py --apply --confirm-backup
  ..\\.venv\\Scripts\\python.exe tools\\mandant_textvorlagen_update_v1.py --mandant <UID> [--mandant <UID> ...]
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

import asyncpg

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.core import credential_service, text_template_service as texts  # noqa: E402
from app.core.connection_manager import ConnectionManager  # noqa: E402
from app.core.database import DatabasePool  # noqa: E402
from app.core.mandant_db_maintenance import run_mandant_maintenance  # noqa: E402
from audit_system_data import as_dict  # noqa: E402
from seed_base_records import apply_work, plan_table  # noqa: E402

RESERVED_PREFIXES = ("0000", "5555", "6666")


async def base_records(conn: asyncpg.Connection, apply: bool) -> list[str]:
    """Fehlende Basissaetze 000/555/666 von msy_textvorlagen (nur Anlage)."""
    cols = {
        r["column_name"]: r["data_type"]
        for r in await conn.fetch(
            "select column_name, data_type from information_schema.columns where table_schema='public' and table_name=$1",
            texts.MANDANT_TABLE,
        )
    }
    sel = "uid, name, daten, " + ("gilt_bis" if "gilt_bis" in cols else "null as gilt_bis") + ", " + (
        "link_uid" if "link_uid" in cols else "null::uuid as link_uid")
    rows = await conn.fetch(f"select {sel} from {texts.MANDANT_TABLE}")
    created = [w for w in plan_table(texts.MANDANT_TABLE, rows, "link_uid" in cols) if w.created]
    if apply:
        async with conn.transaction():
            for w in created:
                await apply_work(conn, texts.MANDANT_TABLE, cols, w, allow_reserved=False)
    return [w.uid for w in created]


async def update_mandant(row, args) -> int:
    """Gibt die Zahl der (geplanten oder ausgefuehrten) Anlagen zurueck."""
    apply = args.apply
    daten = as_dict(row["daten"])
    info = as_dict(daten.get("MANDANT"))
    system_cfg, mandant_cfg = ConnectionManager.resolve_mandant_connections(info)
    mandant_pool = system_pool = None
    try:
        mandant_pool = await asyncpg.create_pool(**mandant_cfg.to_dict(), min_size=1, max_size=2)
        system_pool = await asyncpg.create_pool(**system_cfg.to_dict(), min_size=1, max_size=2)
        async with mandant_pool.acquire() as conn:
            exists = await conn.fetchval("select to_regclass('public.' || $1) is not null", texts.MANDANT_TABLE)
        if not exists and args.with_maintenance and apply:
            # dieselbe Wartung wie beim Mandanten-Login (DATABASE_UPDATE: legt fehlende Standardtabellen an)
            stats = await run_mandant_maintenance(mandant_pool, row["uid"], daten)
            print(f"  {row['name']}: Mandanten-Wartung ausgefuehrt (Tabellen angelegt: {stats.get('tables_created') or 0}, "
                  f"Fehler: {stats.get('errors') or 0})")
            async with mandant_pool.acquire() as conn:
                exists = await conn.fetchval("select to_regclass('public.' || $1) is not null", texts.MANDANT_TABLE)
        if not exists:
            hint = "--with-maintenance legt sie an" if not args.with_maintenance else "wuerde von der Mandanten-Wartung angelegt"
            print(f"  {row['name']} ({mandant_cfg.database}): Tabelle {texts.MANDANT_TABLE} fehlt ({hint}; sonst beim naechsten Login) - uebersprungen")
            return 0
        async with mandant_pool.acquire() as conn:
            base = await base_records(conn, apply)
        templates = await texts.ensure_mandant_templates(
            system_pool=system_pool, mandant_pool=mandant_pool, force=True, dry_run=not apply
        )
        verb = "angelegt" if apply else "wuerden angelegt"
        print(f"  {row['name']} ({mandant_cfg.database}): Basissaetze {verb}: {len(base)}; Vorlagen {verb}: "
              f"{', '.join(templates) if templates else '0'}")
        return len(base) + len(templates)
    finally:
        for pool in (mandant_pool, system_pool):
            if pool is not None:
                await pool.close()


async def run(args) -> int:
    await DatabasePool.create_pool()
    try:
        await credential_service.ensure_fresh()
        rows = await DatabasePool._pool_auth.fetch(
            "select uid::text as uid, name, daten from asy_mandanten where COALESCE(historisch, 0) = 0 order by name"
        )
        wanted = {m.lower() for m in (args.mandant or [])}
        total = failed = 0
        print(f"{'APPLY' if args.apply else 'Dry-Run'}: Textvorlagen in Mandanten-DBs nachliefern")
        for row in rows:
            if row["uid"].startswith(RESERVED_PREFIXES) or (wanted and row["uid"].lower() not in wanted):
                continue
            try:
                total += await update_mandant(row, args)
            except Exception as exc:  # ein nicht erreichbarer Mandant stoppt die uebrigen nicht
                failed += 1
                print(f"  {row['name']}: FEHLER {exc}")
        print(f"Ergebnis: {total} Anlage(n) {'ausgefuehrt' if args.apply else 'geplant'}, {failed} Mandant(en) mit Fehler")
        return 1 if failed else 0
    finally:
        await DatabasePool.close_pool()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="Anlagen ausfuehren (sonst Dry-Run)")
    ap.add_argument("--confirm-backup", action="store_true", help="Bestaetigt, dass ein Backup vorliegt (Pflicht fuer --apply)")
    ap.add_argument("--mandant", action="append", help="Nur diese Mandanten-UID (mehrfach moeglich)")
    ap.add_argument("--with-maintenance", action="store_true",
                    help="Fehlt msy_textvorlagen, die Mandanten-Wartung (wie beim Login) ausfuehren; nur mit --apply")
    args = ap.parse_args()
    if args.apply and not args.confirm_backup:
        raise SystemExit("--apply verlangt --confirm-backup (Backup muss vorher vorliegen).")
    sys.exit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()

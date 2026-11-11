"""Korrigiert Kontrastverstoesse in den Theme-Paketen (``sys_layout`` und die Kopien in ``msy_layout``).

Aufruf (aus backend/, mit PYTHONUTF8=1):
    ..\\.venv\\Scripts\\python.exe tools\\fix_theme_contrast_v1.py                            # Dry-Run (Standard)
    ..\\.venv\\Scripts\\python.exe tools\\fix_theme_contrast_v1.py --apply --confirm-backup   # schreibt

Vorgehen (theme_service.repair_contrast): Zuerst werden Hex-Farben ohne '#' korrigiert (normalize_package_values), danach
wird je verletztem Pflicht-Kontrastpaar die Farbe angepasst, die sich
am wenigsten aendern muss (Helligkeit in OKLab, Farbton bleibt); Textfarben werden bevorzugt, Flaechenfarben
nur bei deutlich kleinerer Aenderung. Es werden nur ausdrueckliche Werte der Variantengruppen veraendert.

- Betroffen: Zeilen mit Variantengruppen (``light``/``dark``/...) in ``pdvm_system.sys_layout`` und in
  ``msy_layout`` jeder Mandanten-DB (Paketkopien; Overlay-Zeilen mit ``ROOT.LAYER = "OVERLAY"`` bleiben unberuehrt).
- Reservierte Basissaetze (000/555/666) werden nicht angefasst (ARCHITECTURE_RULES 1.11).
- --apply verlangt --confirm-backup und schreibt vorher einen Snapshot der betroffenen Zeilen nach backend/reports/.
- Das Ergebnis wird als Bericht nach docs/reports/ geschrieben.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote

import asyncpg

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.core import theme_service  # noqa: E402
from audit_system_data import RESERVED, as_dict, load_env_url  # noqa: E402

META_GROUPS = {"ROOT", "info", "TEMPLATES", "TABLE_INFO"}


async def connect(url, database: str) -> asyncpg.Connection:
    return await asyncpg.connect(
        host="127.0.0.1" if url.hostname == "localhost" else url.hostname,
        port=url.port or 5432,
        user=url.username,
        password=unquote(url.password or ""),
        database=database,
    )


def variant_groups(daten: dict) -> list[str]:
    return [name for name, value in daten.items() if isinstance(value, dict) and name not in META_GROUPS]


def is_overlay(daten: dict) -> bool:
    return (as_dict(daten.get("ROOT")) or {}).get("LAYER") == "OVERLAY"


async def collect_targets(auth_conn: asyncpg.Connection, url) -> list[tuple[str, str]]:
    """(Datenbank, Tabelle) fuer sys_layout und alle Mandanten-DBs mit msy_layout."""
    targets = [("pdvm_system", "sys_layout")]
    seen = {"pdvm_system"}
    for row in await auth_conn.fetch("SELECT daten FROM asy_mandanten WHERE historisch = 0"):
        database = (as_dict(row["daten"]).get("MANDANT") or {}).get("DATABASE")
        if database and database not in seen:
            seen.add(database)
            targets.append((database, "msy_layout"))
    return targets


async def main(apply: bool) -> int:
    url = load_env_url()
    auth_db = url.path.lstrip("/")
    auth = await connect(url, auth_db)
    report: list[str] = []
    snapshot: list[dict] = []
    pending: list[tuple[str, str, str, dict]] = []  # (db, table, uid, neue daten)
    try:
        for database, table in await collect_targets(auth, url):
            try:
                conn = await connect(url, database)
            except Exception as exc:  # Mandanten-DB nicht erreichbar
                report.append(f"- {database}: uebersprungen ({exc})")
                continue
            try:
                exists = await conn.fetchval("SELECT to_regclass($1)", f"public.{table}")
                if not exists:
                    continue
                for row in await conn.fetch(f"SELECT uid, name, daten FROM {table} WHERE historisch = 0"):
                    uid = str(row["uid"])
                    daten = as_dict(row["daten"])
                    groups = variant_groups(daten)
                    if uid in RESERVED or not groups or is_overlay(daten):
                        continue
                    new = json.loads(json.dumps(daten))
                    row_changes = []
                    for group in groups:
                        # 1. Rohdaten: Hex-Farben ohne '#' ergaenzen (z. B. text_color "000000")
                        normalized, value_changes = theme_service.normalize_package_values(daten[group])
                        # 2. Kontrast auf den bereinigten Werten
                        fixed, changes = theme_service.repair_contrast(normalized, comfort=7.0)
                        remaining = [c for c in theme_service.check_contrast(fixed) if not c["ok"]]
                        _, invalid = theme_service.sanitize_package_variant(fixed)
                        if changes or value_changes or invalid:
                            new[group] = fixed
                            row_changes.append((group, value_changes, changes, remaining, invalid))
                    if not any(vc or ch or inv for _, vc, ch, _, inv in row_changes):
                        continue
                    report.append(f"### {database}.{table} `{uid}` {row['name']}")
                    for group, value_changes, changes, remaining, invalid in row_changes:
                        if not (value_changes or changes or invalid):
                            continue
                        report.append(
                            f"- Variante `{group}`: {len(value_changes)} Wertkorrektur(en), {len(changes)} Kontrastaenderung(en)"
                            + (f", **{len(remaining)} offen**" if remaining else "")
                        )
                        for vc in value_changes:
                            report.append(f"  - `{vc['ref']}` {vc['old']!r} -> {vc['new']!r} (fehlendes '#')")
                        for ch in changes:
                            report.append(f"  - `{ch['ref']}` {ch['old']} -> {ch['new']} (Paar `{ch['pair']}`, vorher {ch['ratio_before']}:1)")
                        for msg in invalid:
                            report.append(f"  - **nicht automatisch behebbar:** {msg}")
                    snapshot.append({"db": database, "table": table, "uid": uid, "daten": daten})
                    pending.append((database, table, uid, new))
            finally:
                await conn.close()

        if not pending:
            print("Keine Kontrastverstoesse oder ungueltigen Werte in den Theme-Paketen.")
            return 0

        print("\n".join(report))
        print(f"\n{len(pending)} Zeile(n) {'werden geschrieben' if apply else 'wuerden geaendert (Dry-Run)'}")

        stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        report_path = BACKEND_DIR.parent / "docs" / "reports" / f"THEME_CONTRAST_REPAIR_{'APPLY' if apply else 'DRYRUN'}_{stamp}.md"
        report_path.write_text("# Theme-Kontrast-Korrektur\n\n" + "\n".join(report) + "\n", encoding="utf-8")
        print(f"Bericht: {report_path}")

        if apply:
            snap_dir = BACKEND_DIR / "reports"
            snap_dir.mkdir(exist_ok=True)
            snap_path = snap_dir / f"theme_contrast_snapshot_{stamp}.json"
            snap_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
            print(f"Snapshot: {snap_path}")
            for database, table, uid, new in pending:
                conn = await connect(url, database)
                try:
                    await conn.execute(
                        f"UPDATE {table} SET daten = $1::jsonb, modified_at = NOW() WHERE uid = $2::uuid",
                        json.dumps(new),
                        uid,
                    )
                finally:
                    await conn.close()
            print("Geschrieben.")
    finally:
        await auth.close()
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="Aenderungen schreiben (Standard: Dry-Run)")
    parser.add_argument("--confirm-backup", action="store_true", help="Bestaetigung, dass ein Backup existiert (Pflicht mit --apply)")
    args = parser.parse_args()
    if args.apply and not args.confirm_backup:
        raise SystemExit("--apply verlangt --confirm-backup")
    raise SystemExit(asyncio.run(main(args.apply)))

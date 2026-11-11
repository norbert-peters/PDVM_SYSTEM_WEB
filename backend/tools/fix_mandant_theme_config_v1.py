"""Korrigiert vertauschte THEME_LIGHT/THEME_DARK in asy_mandanten.CONFIG.

Aufruf (aus backend/, mit PYTHONUTF8=1):
    ..\\.venv\\Scripts\\python.exe tools\\fix_mandant_theme_config_v1.py            # Dry-Run (Standard)
    ..\\.venv\\Scripts\\python.exe tools\\fix_mandant_theme_config_v1.py --apply

Eine Zeile gilt als vertauscht, wenn THEME_LIGHT den Namen 'dark' und THEME_DARK den Namen 'light' enthaelt.
Reservierte Basissaetze (000/555/666) werden nicht angefasst (ARCHITECTURE_RULES 1.11).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from urllib.parse import unquote

import asyncpg

sys.path.insert(0, str(Path(__file__).resolve().parent))
from audit_system_data import RESERVED, as_dict, load_env_url  # noqa: E402


def is_swapped(cfg: dict) -> bool:
    light = str(cfg.get("THEME_LIGHT") or "").lower()
    dark = str(cfg.get("THEME_DARK") or "").lower()
    return "dark" in light and "light" in dark


async def main(apply: bool) -> int:
    url = load_env_url()
    conn = await asyncpg.connect(
        host="127.0.0.1" if url.hostname == "localhost" else url.hostname,
        port=url.port or 5432,
        user=url.username,
        password=unquote(url.password or ""),
        database=url.path.lstrip("/"),
    )
    try:
        rows = await conn.fetch("SELECT uid, name, daten FROM asy_mandanten WHERE historisch = 0")
        changed = 0
        for row in rows:
            uid = str(row["uid"])
            if uid in RESERVED:
                continue
            daten = as_dict(row["daten"])
            cfg = daten.get("CONFIG")
            if not isinstance(cfg, dict) or not is_swapped(cfg):
                continue
            old = (cfg.get("THEME_LIGHT"), cfg.get("THEME_DARK"))
            cfg["THEME_LIGHT"], cfg["THEME_DARK"] = cfg["THEME_DARK"], cfg["THEME_LIGHT"]
            print(f"{'APPLY' if apply else 'DRY  '} {uid} {row['name']}: THEME_LIGHT/DARK {old} -> "
                  f"{(cfg['THEME_LIGHT'], cfg['THEME_DARK'])}")
            if apply:
                await conn.execute(
                    "UPDATE asy_mandanten SET daten = $1::jsonb, modified_at = NOW() WHERE uid = $2::uuid",
                    json.dumps(daten),
                    uid,
                )
            changed += 1
        print(f"{changed} Mandant(en) {'korrigiert' if apply else 'wuerden korrigiert (Dry-Run)'}")
    finally:
        await conn.close()
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="Aenderungen schreiben (Standard: Dry-Run)")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(main(args.apply)))

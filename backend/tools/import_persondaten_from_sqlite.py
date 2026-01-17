import argparse
import asyncio
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import sys

# Allow running this script from repo root (adds `backend/` to sys.path)
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import asyncpg

from app.core.database import get_database_url


@dataclass(frozen=True)
class PersonRow:
    uid: str
    daten: dict[str, Any]
    name: str
    historisch: int


def _pick_latest_value(stichtag_map: Any) -> Any:
    if not isinstance(stichtag_map, dict) or not stichtag_map:
        return None

    def _key_to_float(k: Any) -> float:
        try:
            return float(k)
        except Exception:
            return float("-inf")

    best_key = max(stichtag_map.keys(), key=_key_to_float)
    return stichtag_map.get(best_key)


def _derive_name_from_daten(daten: dict[str, Any]) -> str:
    pers = daten.get("PERSDATEN")
    if not isinstance(pers, dict):
        # Some DBs may include ROOT wrapper or other variants; keep it minimal.
        pers = daten.get("persdaten") if isinstance(daten.get("persdaten"), dict) else None

    if not isinstance(pers, dict):
        return ""

    vorname = _pick_latest_value(pers.get("VORNAME"))
    familienname = _pick_latest_value(pers.get("FAMILIENNAME"))

    parts = [p for p in [vorname, familienname] if isinstance(p, str) and p.strip()]
    return " ".join(parts).strip()


def _load_from_sqlite(db_path: Path) -> list[PersonRow]:
    con = sqlite3.connect(str(db_path))
    try:
        cur = con.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='persondaten'")
        if cur.fetchone() is None:
            raise SystemExit(f"SQLite table 'persondaten' not found in: {db_path}")

        cur.execute("SELECT uid, daten, name, historisch FROM persondaten")
        rows: list[PersonRow] = []
        for uid, daten_raw, name_raw, historisch in cur.fetchall():
            if not uid or not daten_raw:
                continue
            try:
                daten = json.loads(daten_raw) if isinstance(daten_raw, str) else daten_raw
            except Exception:
                continue

            derived_name = _derive_name_from_daten(daten)
            name = derived_name or (str(name_raw) if name_raw is not None else "")
            hist = int(historisch) if historisch is not None else 0
            rows.append(PersonRow(uid=str(uid), daten=daten, name=name, historisch=hist))
        return rows
    finally:
        con.close()


async def _upsert_to_postgres(rows: list[PersonRow], *, dry_run: bool) -> None:
    db_url = get_database_url("mandant")

    if dry_run:
        print(f"dry_run=True postgres_url={db_url}")
        print(f"rows_to_import={len(rows)}")
        if rows:
            print(f"sample_uid={rows[0].uid} sample_name={rows[0].name}")
        return

    pool = await asyncpg.create_pool(db_url, min_size=1, max_size=4)
    try:
        query = """
            INSERT INTO persondaten (uid, daten, name, historisch)
            VALUES ($1::uuid, $2::jsonb, $3, $4)
            ON CONFLICT (uid) DO UPDATE SET
                daten = EXCLUDED.daten,
                name = EXCLUDED.name,
                historisch = EXCLUDED.historisch,
                modified_at = NOW()
        """

        batch_size = 250
        imported = 0
        async with pool.acquire() as conn:
            for i in range(0, len(rows), batch_size):
                batch = rows[i : i + batch_size]
                args = [(r.uid, json.dumps(r.daten), r.name, r.historisch) for r in batch]
                await conn.executemany(query, args)
                imported += len(batch)
                print(f"imported={imported}/{len(rows)}")

        print(f"done imported={imported}")
    finally:
        await pool.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Import Desktop SQLite persondaten into Postgres mandant.persondaten (upsert by uid)"
    )
    parser.add_argument("sqlite_db", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not args.sqlite_db.exists():
        raise SystemExit(f"SQLite DB not found: {args.sqlite_db}")

    rows = _load_from_sqlite(args.sqlite_db)
    asyncio.run(_upsert_to_postgres(rows, dry_run=args.dry_run))


if __name__ == "__main__":
    main()

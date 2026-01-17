import argparse
import asyncio
import json
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import asyncpg

# Allow running this script from repo root (adds `backend/` to sys.path)
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.database import get_database_url


@dataclass(frozen=True)
class SQLiteRow:
    uid: str
    daten_raw: str
    name: str
    historisch: int


def _looks_like_uuid(text: str) -> bool:
    import uuid

    try:
        uuid.UUID(str(text))
        return True
    except Exception:
        return False


def _safe_json_loads(raw: str) -> Optional[dict[str, Any]]:
    try:
        value = json.loads(raw)
        return value if isinstance(value, dict) else None
    except Exception:
        return None


def _load_finanzdaten_rows(sqlite_db_path: Path) -> list[SQLiteRow]:
    con = sqlite3.connect(str(sqlite_db_path))
    try:
        cur = con.cursor()
        cur.execute("SELECT uid, daten, name, historisch FROM finanzdaten")
        rows: list[SQLiteRow] = []
        for uid, daten, name, historisch in cur.fetchall():
            rows.append(
                SQLiteRow(
                    uid=str(uid or "").strip(),
                    daten_raw=str(daten or "").strip(),
                    name=str(name or "").strip(),
                    historisch=int(historisch or 0),
                )
            )
        return rows
    finally:
        con.close()


def _normalize_rows(rows: list[SQLiteRow]) -> list[dict[str, Any]]:
    """Return rows ready for Postgres upsert."""
    out: list[dict[str, Any]] = []
    for row in rows:
        if row.historisch != 0:
            continue
        if not row.uid or not _looks_like_uuid(row.uid):
            continue
        data = _safe_json_loads(row.daten_raw)
        if data is None:
            continue

        # Keep desktop 'name' as-is. If missing, try a simple derivation.
        name = row.name
        if not name:
            fin = data.get("FINANZDATEN")
            if isinstance(fin, dict):
                name = str(fin.get("KONTOBEZEICHNUNG") or fin.get("KONTONUMMER") or "")

        out.append({"uid": row.uid, "daten": data, "name": name})

    return out


async def _upsert_finanzdaten(rows: list[dict[str, Any]], url: str, *, batch_size: int = 250) -> int:
    if not rows:
        return 0

    conn = await asyncpg.connect(url)
    try:
        upsert_sql = """
            INSERT INTO finanzdaten (uid, daten, name, modified_at)
            VALUES ($1::uuid, $2::jsonb, $3, NOW())
            ON CONFLICT (uid) DO UPDATE
            SET daten = EXCLUDED.daten,
                name = EXCLUDED.name,
                modified_at = NOW()
        """

        imported = 0
        for i in range(0, len(rows), batch_size):
            batch = rows[i : i + batch_size]
            async with conn.transaction():
                for r in batch:
                    await conn.execute(upsert_sql, r["uid"], json.dumps(r["daten"]), r["name"])
                    imported += 1
        return imported
    finally:
        await conn.close()


async def main_async() -> int:
    parser = argparse.ArgumentParser(
        description="Import finanzdaten from Desktop SQLite into Postgres mandant.finanzdaten (upsert by uid)"
    )
    parser.add_argument("sqlite_db", type=Path, help="Path to Desktop SQLite datenbank.db")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not args.sqlite_db.exists():
        print(f"ERROR sqlite_db_not_found={args.sqlite_db}")
        return 2

    rows_raw = _load_finanzdaten_rows(args.sqlite_db)
    rows = _normalize_rows(rows_raw)

    pg_url = get_database_url("mandant")
    print(f"dry_run={args.dry_run} postgres_url={pg_url}")
    print(f"rows_to_import={len(rows)}")

    if rows:
        print(f"sample_uid={rows[0]['uid']} sample_name={rows[0]['name']}")

    if args.dry_run:
        return 0

    imported = await _upsert_finanzdaten(rows, pg_url)
    print(f"imported={imported}/{len(rows)}")
    print(f"done imported={imported}")
    return 0


def main() -> None:
    raise SystemExit(asyncio.run(main_async()))


if __name__ == "__main__":
    main()

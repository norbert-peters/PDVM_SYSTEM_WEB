import argparse
import asyncio
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlsplit, urlunsplit

import sys

# Allow running this script from repo root (adds `backend/` to sys.path)
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import asyncpg

from app.core.database import get_database_url
from app.core.pdvm_datetime import pdvm_to_datetime


@dataclass(frozen=True)
class DropdownRow:
    uid: str
    daten: dict[str, Any]
    name: str
    historisch: int
    source_hash: str
    sec_id: Optional[str]
    gilt_bis: Optional[datetime]
    created_at: Optional[datetime]
    modified_at: Optional[datetime]


def _parse_pdvm_ts(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    s = str(value).strip()
    if not s:
        return None
    try:
        return pdvm_to_datetime(float(s))
    except Exception:
        return None


def _load_from_sqlite(db_path: Path) -> list[DropdownRow]:
    con = sqlite3.connect(str(db_path))
    try:
        cur = con.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='sys_dropdowndaten'")
        if cur.fetchone() is None:
            raise SystemExit(f"SQLite table 'sys_dropdowndaten' not found in: {db_path}")

        cur.execute(
            "SELECT uid, daten, name, historisch, source_hash, sec_id, gilt_bis, created_at, modified_at FROM sys_dropdowndaten"
        )

        rows: list[DropdownRow] = []
        for uid, daten_raw, name_raw, historisch, source_hash, sec_id, gilt_bis, created_at, modified_at in cur.fetchall():
            if not uid or not daten_raw:
                continue

            try:
                daten = json.loads(daten_raw) if isinstance(daten_raw, str) else daten_raw
            except Exception:
                continue

            if not isinstance(daten, dict):
                continue

            gilt_bis_dt = _parse_pdvm_ts(gilt_bis) or _parse_pdvm_ts("9999365.00000")

            rows.append(
                DropdownRow(
                    uid=str(uid),
                    daten=daten,
                    name=str(name_raw) if name_raw is not None else "",
                    historisch=int(historisch) if historisch is not None else 0,
                    source_hash=str(source_hash) if source_hash is not None else "",
                    sec_id=str(sec_id) if sec_id is not None else None,
                    gilt_bis=gilt_bis_dt,
                    created_at=_parse_pdvm_ts(created_at),
                    modified_at=_parse_pdvm_ts(modified_at),
                )
            )

        return rows
    finally:
        con.close()


async def _upsert_to_postgres(rows: list[DropdownRow], *, dry_run: bool) -> None:
    db_url = get_database_url("system")  # -> pdvm_system

    def _redact_url(url: str) -> str:
        try:
            parts = urlsplit(url)
            if not parts.password:
                return url
            username = parts.username or ""
            hostname = parts.hostname or ""
            port = f":{parts.port}" if parts.port else ""
            netloc = f"{username}:***@{hostname}{port}" if username else f"***@{hostname}{port}"
            return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))
        except Exception:
            return "<redacted>"

    if dry_run:
        print(f"dry_run=True postgres_url={_redact_url(db_url)}")
        print(f"rows_to_import={len(rows)}")
        if rows:
            print(f"sample_uid={rows[0].uid} sample_top_keys={list(rows[0].daten.keys())[:5]}")
        return

    pool = await asyncpg.create_pool(db_url, min_size=1, max_size=4)
    try:
        query = """
            INSERT INTO sys_dropdowndaten
                (uid, daten, name, historisch, source_hash, sec_id, gilt_bis, created_at, modified_at)
            VALUES
                ($1::uuid, $2::jsonb, $3, $4, $5, $6::uuid, $7::timestamp, COALESCE($8, NOW()), COALESCE($9, NOW()))
            ON CONFLICT (uid) DO UPDATE SET
                daten = EXCLUDED.daten,
                name = EXCLUDED.name,
                historisch = EXCLUDED.historisch,
                source_hash = EXCLUDED.source_hash,
                sec_id = EXCLUDED.sec_id,
                gilt_bis = EXCLUDED.gilt_bis,
                modified_at = COALESCE(EXCLUDED.modified_at, NOW())
        """

        batch_size = 250
        imported = 0
        async with pool.acquire() as conn:
            for i in range(0, len(rows), batch_size):
                batch = rows[i : i + batch_size]
                args = [
                    (
                        r.uid,
                        json.dumps(r.daten, ensure_ascii=False),
                        r.name,
                        r.historisch,
                        r.source_hash,
                        r.sec_id,
                        r.gilt_bis,
                        r.created_at,
                        r.modified_at,
                    )
                    for r in batch
                ]
                await conn.executemany(query, args)
                imported += len(batch)
                print(f"imported={imported}/{len(rows)}")

        print(f"done imported={imported}")
    finally:
        await pool.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Import Desktop SQLite pdvm_system.db sys_dropdowndaten into Postgres pdvm_system.sys_dropdowndaten (upsert by uid)"
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

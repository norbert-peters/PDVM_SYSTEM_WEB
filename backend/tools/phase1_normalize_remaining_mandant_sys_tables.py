"""
Normalize remaining sys_* mandant tables after prefix migration.

Handles cases where both old sys_* and new msy_* tables exist:
- merge rows from old table into new table (upsert by uid)
- drop old table
- optionally create compatibility view old->new

Default mode is dry-run.

Usage:
  python backend/tools/phase1_normalize_remaining_mandant_sys_tables.py
  python backend/tools/phase1_normalize_remaining_mandant_sys_tables.py --apply
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import asyncpg

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.connection_manager import ConnectionConfig, ConnectionManager

RESERVED_BASE_UIDS = {
    "00000000-0000-0000-0000-000000000000",
    "55555555-5555-5555-5555-555555555555",
    "66666666-6666-6666-6666-666666666666",
}

MANDANT_RENAMES = {
    "sys_systemsteuerung": "msy_systemsteuerung",
    "sys_anwendungsdaten": "msy_anwendungsdaten",
    "sys_layout": "msy_layout",
    "sys_security": "msy_security",
    "sys_error_log": "msy_error_log",
    "sys_error_acknowledgements": "msy_error_acknowledgments",
    "sys_error_acknowledgments": "msy_error_acknowledgments",
    "sys_contr_dict_man": "msy_control_dict",
    "sys_contr_dict_man_audit": "msy_control_dict_audit",
    "sys_ext_table_man": "msy_ext_table",
    "sys_feld_aenderungshistorie": "msy_feld_aenderungshistorie",
}


def _cfg_key(cfg: ConnectionConfig) -> Tuple[str, int, str, str, str]:
    return (cfg.host, int(cfg.port), cfg.user, cfg.password, cfg.database)


def _to_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            return {}
    return {}


async def _relation_kind(conn: asyncpg.Connection, relation_name: str) -> Optional[str]:
    kind = await conn.fetchval(
        """
        SELECT c.relkind
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public' AND c.relname = $1
        """,
        relation_name,
    )
    if isinstance(kind, (bytes, bytearray)):
        return kind.decode("utf-8", errors="ignore")
    return kind


async def _fetch_columns(conn: asyncpg.Connection, table_name: str) -> List[str]:
    rows = await conn.fetch(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema='public' AND table_name = $1
        ORDER BY ordinal_position
        """,
        table_name,
    )
    return [str(r["column_name"]) for r in rows]


async def _collect_mandant_configs(auth_cfg: ConnectionConfig) -> List[ConnectionConfig]:
    conn = await asyncpg.connect(auth_cfg.to_url())
    try:
        rows = await conn.fetch(
            """
            SELECT uid::text AS uid, historisch, daten
            FROM asy_mandanten
            ORDER BY created_at ASC NULLS LAST
            """
        )
    except Exception:
        rows = await conn.fetch(
            """
            SELECT uid::text AS uid, historisch, daten
            FROM sys_mandanten
            ORDER BY created_at ASC NULLS LAST
            """
        )
    finally:
        await conn.close()

    excluded_db_names: Set[str] = set()
    parsed_rows: List[Dict[str, Any]] = []
    for row in rows:
        rec = {
            "uid": str(row["uid"]),
            "historisch": int(row["historisch"] or 0),
            "daten": _to_dict(row["daten"]),
        }
        parsed_rows.append(rec)

    for rec in parsed_rows:
        if rec["uid"] not in RESERVED_BASE_UIDS:
            continue
        mandant = rec.get("daten", {}).get("MANDANT")
        if isinstance(mandant, dict):
            db_name = str(mandant.get("DATABASE") or "").strip().lower()
            if db_name:
                excluded_db_names.add(db_name)

    seen: Set[Tuple[str, int, str, str, str]] = set()
    configs: List[ConnectionConfig] = []

    for rec in parsed_rows:
        if rec["historisch"] == 1:
            continue
        mandant = rec.get("daten", {}).get("MANDANT")
        if not isinstance(mandant, dict):
            continue

        host = mandant.get("HOST")
        port = mandant.get("PORT")
        user = mandant.get("USER")
        password = mandant.get("PASSWORD")
        database = mandant.get("DATABASE")
        if any(v in (None, "") for v in [host, port, user, password, database]):
            continue

        db_norm = str(database).strip().lower()
        if db_norm in excluded_db_names:
            continue

        cfg = ConnectionConfig(
            host=str(host),
            port=int(port),
            user=str(user),
            password=str(password),
            database=str(database),
        )
        key = _cfg_key(cfg)
        if key in seen:
            continue
        seen.add(key)
        configs.append(cfg)

    return configs


async def _merge_table_rows(conn: asyncpg.Connection, source: str, target: str, apply_changes: bool) -> int:
    source_cols = await _fetch_columns(conn, source)
    target_cols = await _fetch_columns(conn, target)

    common_cols = [c for c in source_cols if c in target_cols]
    if "uid" not in common_cols:
        return 0

    update_cols = [c for c in common_cols if c != "uid"]
    if not common_cols:
        return 0

    col_list = ", ".join(f'"{c}"' for c in common_cols)
    set_list = ", ".join(f'"{c}" = EXCLUDED."{c}"' for c in update_cols)

    sql = (
        f'INSERT INTO "{target}" ({col_list}) '
        f'SELECT {col_list} FROM "{source}" '
        f'ON CONFLICT ("uid") DO UPDATE SET {set_list}'
    )

    if not apply_changes:
        count = await conn.fetchval(f'SELECT COUNT(*) FROM "{source}"')
        return int(count or 0)

    await conn.execute(sql)
    count = await conn.fetchval(f'SELECT COUNT(*) FROM "{source}"')
    return int(count or 0)


async def _normalize_db(cfg: ConnectionConfig, apply_changes: bool, create_compat_views: bool) -> Dict[str, Any]:
    result = {
        "database": cfg.database,
        "pairs_processed": 0,
        "rows_merged": 0,
        "tables_dropped": 0,
        "views_created": 0,
        "errors": [],
    }

    conn = await asyncpg.connect(cfg.to_url())
    try:
        for old_name, new_name in MANDANT_RENAMES.items():
            old_kind = await _relation_kind(conn, old_name)
            new_kind = await _relation_kind(conn, new_name)

            if old_kind is None and new_kind is None:
                continue

            result["pairs_processed"] += 1

            # Case 1: old table exists and new does not -> rename
            if old_kind == "r" and new_kind is None:
                if apply_changes:
                    await conn.execute(f'ALTER TABLE "{old_name}" RENAME TO "{new_name}"')

            # Refresh kinds after potential rename in apply mode
            old_kind = await _relation_kind(conn, old_name)
            new_kind = await _relation_kind(conn, new_name)

            # Case 2: both are tables -> merge and drop old
            if old_kind == "r" and new_kind == "r":
                try:
                    merged = await _merge_table_rows(conn, old_name, new_name, apply_changes)
                    result["rows_merged"] += merged
                    if apply_changes:
                        await conn.execute(f'DROP TABLE "{old_name}"')
                        result["tables_dropped"] += 1
                        old_kind = None
                except Exception as exc:
                    result["errors"].append(f"{old_name}->{new_name}: {exc}")
                    continue

            # Case 3: compatibility view creation
            if create_compat_views:
                old_kind = await _relation_kind(conn, old_name)
                new_kind = await _relation_kind(conn, new_name)
                if old_kind is None and new_kind == "r":
                    if apply_changes:
                        try:
                            await conn.execute(f'CREATE VIEW "{old_name}" AS SELECT * FROM "{new_name}"')
                            result["views_created"] += 1
                        except Exception as exc:
                            result["errors"].append(f"view {old_name}->{new_name}: {exc}")
    finally:
        await conn.close()

    return result


async def main() -> None:
    parser = argparse.ArgumentParser(description="Normalize remaining sys_* tables in mandant DBs")
    parser.add_argument("--apply", action="store_true", help="Execute normalization (default dry-run)")
    parser.add_argument("--no-compat-views", action="store_true", help="Do not create legacy views")
    args = parser.parse_args()

    auth_cfg = await ConnectionManager.get_auth_config()
    mandant_cfgs = await _collect_mandant_configs(auth_cfg)

    print(f"mode={'APPLY' if args.apply else 'DRY-RUN'}")
    print(f"mandant_databases={len(mandant_cfgs)}")

    total_pairs = 0
    total_merged = 0
    total_dropped = 0
    total_views = 0
    total_errors = 0

    for cfg in mandant_cfgs:
        r = await _normalize_db(cfg, args.apply, create_compat_views=not args.no_compat_views)
        total_pairs += r["pairs_processed"]
        total_merged += r["rows_merged"]
        total_dropped += r["tables_dropped"]
        total_views += r["views_created"]
        total_errors += len(r["errors"])
        print(
            f"mandant_db={cfg.database} pairs={r['pairs_processed']} merged={r['rows_merged']} "
            f"dropped={r['tables_dropped']} views={r['views_created']} errors={len(r['errors'])}"
        )

    print(f"total_pairs={total_pairs}")
    print(f"total_merged={total_merged}")
    print(f"total_dropped={total_dropped}")
    print(f"total_views={total_views}")
    print(f"total_errors={total_errors}")


if __name__ == "__main__":
    asyncio.run(main())

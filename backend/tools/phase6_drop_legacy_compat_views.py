"""
Phase 6 runner: drop legacy compatibility views in mandant DBs.

Goal:
- Remove old sys_* compatibility views introduced during Phase 1
- Keep only canonical msy_* tables in mandant DBs

This tool only drops objects when they are VIEWS.
It does not drop physical tables.

Usage:
  python backend/tools/phase6_drop_legacy_compat_views.py
  python backend/tools/phase6_drop_legacy_compat_views.py --apply
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

import asyncpg

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.connection_manager import ConnectionConfig, ConnectionManager

MANDANT_LEGACY_VIEWS = [
    "sys_systemsteuerung",
    "sys_anwendungsdaten",
    "sys_layout",
    "sys_security",
    "sys_error_log",
    "sys_error_acknowledgements",
    "sys_error_acknowledgments",
    "sys_contr_dict_man",
    "sys_contr_dict_man_audit",
    "sys_ext_table_man",
    "sys_feld_aenderungshistorie",
]


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


async def _collect_mandant_configs_from_auth(auth_cfg: ConnectionConfig) -> List[ConnectionConfig]:
    conn = await asyncpg.connect(auth_cfg.to_url())
    try:
        rows = await conn.fetch("SELECT historisch, daten FROM asy_mandanten ORDER BY created_at ASC NULLS LAST")
    except Exception:
        rows = await conn.fetch("SELECT historisch, daten FROM sys_mandanten ORDER BY created_at ASC NULLS LAST")
    finally:
        await conn.close()

    seen: Set[Tuple[str, int, str, str, str]] = set()
    configs: List[ConnectionConfig] = []

    for row in rows:
        if int(row["historisch"] or 0) == 1:
            continue
        daten = _to_dict(row["daten"])
        mandant = daten.get("MANDANT") if isinstance(daten, dict) else {}
        if not isinstance(mandant, dict):
            continue

        host = mandant.get("HOST")
        port = mandant.get("PORT")
        user = mandant.get("USER")
        password = mandant.get("PASSWORD")
        database = mandant.get("DATABASE")

        if any(v in (None, "") for v in [host, port, user, password, database]):
            continue

        cfg = ConnectionConfig(str(host), int(port), str(user), str(password), str(database))
        key = _cfg_key(cfg)
        if key in seen:
            continue
        seen.add(key)
        configs.append(cfg)

    return configs


async def _relation_kind(conn: asyncpg.Connection, name: str) -> str:
    kind = await conn.fetchval(
        """
        SELECT c.relkind
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public' AND c.relname = $1
        """,
        name,
    )
    if isinstance(kind, (bytes, bytearray)):
        return kind.decode("utf-8", errors="ignore")
    return str(kind or "")


async def _process_db(cfg: ConnectionConfig, *, apply_changes: bool) -> Dict[str, Any]:
    result = {
        "database": cfg.database,
        "views_found": 0,
        "views_dropped": 0,
        "tables_skipped": 0,
        "missing": 0,
        "errors": [],
    }

    conn = await asyncpg.connect(cfg.to_url())
    try:
        for name in MANDANT_LEGACY_VIEWS:
            kind = await _relation_kind(conn, name)
            if not kind:
                result["missing"] += 1
                continue
            if kind == "v":
                result["views_found"] += 1
                if apply_changes:
                    try:
                        await conn.execute(f'DROP VIEW IF EXISTS "{name}"')
                        result["views_dropped"] += 1
                    except Exception as exc:
                        result["errors"].append(f"drop {name}: {exc}")
                continue
            if kind == "r":
                result["tables_skipped"] += 1
                continue
    finally:
        await conn.close()

    return result


async def main() -> None:
    parser = argparse.ArgumentParser(description="Drop mandant legacy compatibility views")
    parser.add_argument("--apply", action="store_true", help="Execute DROP VIEW statements")
    args = parser.parse_args()

    auth_cfg = await ConnectionManager.get_auth_config()
    mandant_cfgs = await _collect_mandant_configs_from_auth(auth_cfg)

    print(f"mode={'APPLY' if args.apply else 'DRY-RUN'}")
    print(f"mandant_databases={len(mandant_cfgs)}")

    total_found = 0
    total_dropped = 0
    total_tables_skipped = 0
    total_missing = 0
    total_errors = 0
    total_db_errors = 0

    for cfg in mandant_cfgs:
        try:
            r = await _process_db(cfg, apply_changes=args.apply)
        except Exception as exc:
            total_db_errors += 1
            print(
                f"db={cfg.database} views_found=0 views_dropped=0 "
                f"tables_skipped=0 missing=0 errors=1 db_error={exc}"
            )
            continue
        total_found += int(r["views_found"])
        total_dropped += int(r["views_dropped"])
        total_tables_skipped += int(r["tables_skipped"])
        total_missing += int(r["missing"])
        total_errors += len(r["errors"])
        print(
            f"db={cfg.database} views_found={r['views_found']} views_dropped={r['views_dropped']} "
            f"tables_skipped={r['tables_skipped']} missing={r['missing']} errors={len(r['errors'])}"
        )

    print(f"total_views_found={total_found}")
    print(f"total_views_dropped={total_dropped}")
    print(f"total_tables_skipped={total_tables_skipped}")
    print(f"total_missing={total_missing}")
    print(f"total_errors={total_errors}")
    print(f"total_db_errors={total_db_errors}")


if __name__ == "__main__":
    asyncio.run(main())

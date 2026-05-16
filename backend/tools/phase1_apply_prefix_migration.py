"""
Phase 1 runner: apply prefix migration renames in auth and mandant DBs.

Default mode is dry-run.
Use --apply to execute.

Order:
1) collect mandant DB targets from auth.sys_mandanten (before auth rename)
2) process mandant DB renames (sys_ -> msy_)
3) process auth DB renames (sys_ -> asy_)

Usage:
  python backend/tools/phase1_apply_prefix_migration.py
  python backend/tools/phase1_apply_prefix_migration.py --apply
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

AUTH_RENAMES = {
    "sys_benutzer": "asy_benutzer",
    "sys_mandanten": "asy_mandanten",
    "sys_feld_aenderungshistorie": "asy_feld_aenderungshistorie",
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


async def _table_exists(conn: asyncpg.Connection, table_name: str) -> bool:
    return bool(await conn.fetchval("SELECT to_regclass($1)", f"public.{table_name}"))


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


async def _collect_mandant_configs_from_auth(auth_cfg: ConnectionConfig) -> List[ConnectionConfig]:
    conn = await asyncpg.connect(auth_cfg.to_url())
    try:
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


async def _process_renames(
    cfg: ConnectionConfig,
    renames: Dict[str, str],
    *,
    apply_changes: bool,
    create_compat_views: bool,
) -> Dict[str, Any]:
    result = {
        "database": cfg.database,
        "planned": 0,
        "renamed": 0,
        "compat_views_planned": 0,
        "compat_views_created": 0,
        "skipped_missing_source": 0,
        "skipped_target_exists": 0,
        "errors": [],
    }

    conn = await asyncpg.connect(cfg.to_url())
    try:
        for src, dst in renames.items():
            source_exists = await _table_exists(conn, src)
            target_exists = await _table_exists(conn, dst)

            if not source_exists:
                result["skipped_missing_source"] += 1
                if create_compat_views and target_exists:
                    src_kind = await _relation_kind(conn, src)
                    if src_kind is None:
                        result["compat_views_planned"] += 1
                        if apply_changes:
                            try:
                                await conn.execute(f'CREATE VIEW "{src}" AS SELECT * FROM "{dst}"')
                                result["compat_views_created"] += 1
                            except Exception as exc:
                                result["errors"].append(f"view {src}->{dst}: {exc}")
                continue
            if target_exists:
                result["skipped_target_exists"] += 1
                continue

            result["planned"] += 1
            if apply_changes:
                try:
                    await conn.execute(f'ALTER TABLE "{src}" RENAME TO "{dst}"')
                    result["renamed"] += 1
                except Exception as exc:
                    result["errors"].append(f"{src}->{dst}: {exc}")

            if create_compat_views:
                src_kind_after = await _relation_kind(conn, src)
                dst_exists_after = await _table_exists(conn, dst)
                if dst_exists_after and src_kind_after is None:
                    result["compat_views_planned"] += 1
                    if apply_changes:
                        try:
                            await conn.execute(f'CREATE VIEW "{src}" AS SELECT * FROM "{dst}"')
                            result["compat_views_created"] += 1
                        except Exception as exc:
                            result["errors"].append(f"view {src}->{dst}: {exc}")
                elif src_kind_after == "v":
                    # View already exists - nothing to do
                    pass
    finally:
        await conn.close()

    return result


async def main() -> None:
    parser = argparse.ArgumentParser(description="Apply Phase 1 prefix migration")
    parser.add_argument("--apply", action="store_true", help="Execute renames (default is dry-run)")
    parser.add_argument(
        "--no-compat-views",
        action="store_true",
        help="Do not create legacy compatibility views after rename",
    )
    args = parser.parse_args()

    auth_cfg = await ConnectionManager.get_auth_config()
    mandant_cfgs = await _collect_mandant_configs_from_auth(auth_cfg)

    print(f"mode={'APPLY' if args.apply else 'DRY-RUN'}")
    print(f"mandant_databases={len(mandant_cfgs)}")

    mandant_results: List[Dict[str, Any]] = []
    for cfg in mandant_cfgs:
        r = await _process_renames(
            cfg,
            MANDANT_RENAMES,
            apply_changes=args.apply,
            create_compat_views=not args.no_compat_views,
        )
        mandant_results.append(r)
        print(
            f"mandant_db={cfg.database} planned={r['planned']} renamed={r['renamed']} "
            f"compat_plan={r['compat_views_planned']} compat_created={r['compat_views_created']} "
            f"skip_src={r['skipped_missing_source']} skip_dst={r['skipped_target_exists']} errors={len(r['errors'])}"
        )

    auth_result = await _process_renames(
        auth_cfg,
        AUTH_RENAMES,
        apply_changes=args.apply,
        create_compat_views=not args.no_compat_views,
    )
    print(
        f"auth_db={auth_cfg.database} planned={auth_result['planned']} renamed={auth_result['renamed']} "
        f"compat_plan={auth_result['compat_views_planned']} compat_created={auth_result['compat_views_created']} "
        f"skip_src={auth_result['skipped_missing_source']} skip_dst={auth_result['skipped_target_exists']} errors={len(auth_result['errors'])}"
    )

    total_planned = auth_result["planned"] + sum(r["planned"] for r in mandant_results)
    total_renamed = auth_result["renamed"] + sum(r["renamed"] for r in mandant_results)
    total_compat_planned = auth_result["compat_views_planned"] + sum(r["compat_views_planned"] for r in mandant_results)
    total_compat_created = auth_result["compat_views_created"] + sum(r["compat_views_created"] for r in mandant_results)
    total_errors = len(auth_result["errors"]) + sum(len(r["errors"]) for r in mandant_results)

    print(f"total_planned={total_planned}")
    print(f"total_renamed={total_renamed}")
    print(f"total_compat_planned={total_compat_planned}")
    print(f"total_compat_created={total_compat_created}")
    print(f"total_errors={total_errors}")


if __name__ == "__main__":
    asyncio.run(main())

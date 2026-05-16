"""
Local helper to enforce table-prefix policy across PDVM databases.

What this script does:
1. Renames legacy test tables in mandant DBs:
   - persondaten -> tst_persondaten
   - finanzdaten -> tst_finanzdaten
2. Updates auth.sys_mandanten CONFIG/CONFIGS.FEATURES entries accordingly.
3. Scans auth/system/mandant DBs and reports tables without an allowed prefix.

Default allowed prefixes:
- sys_
- dev_
- tst_

Usage:
  python backend/tools/enforce_table_prefixes_local.py
  python backend/tools/enforce_table_prefixes_local.py --apply
  python backend/tools/enforce_table_prefixes_local.py --apply --allow-prefix app_
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

import asyncpg

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.connection_manager import ConnectionConfig, ConnectionManager
from app.core.database import DatabasePool

logger = logging.getLogger("enforce_table_prefixes_local")
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

RESERVED_BASE_UIDS = {
    "00000000-0000-0000-0000-000000000000",
    "55555555-5555-5555-5555-555555555555",
    "66666666-6666-6666-6666-666666666666",
}

TABLE_RENAMES = {
    "persondaten": "tst_persondaten",
    "finanzdaten": "tst_finanzdaten",
}

DEFAULT_ALLOWED_PREFIXES = ["sys_", "dev_", "tst_"]


@dataclass(frozen=True)
class DbTarget:
    role: str
    cfg: ConnectionConfig


def _cfg_key(cfg: ConnectionConfig) -> Tuple[str, int, str, str, str]:
    return (cfg.host, int(cfg.port), cfg.user, cfg.password, cfg.database)


def _parse_json_dict(value: Any) -> Dict[str, Any]:
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


def _collect_unique_prefixes(prefixes: Iterable[str]) -> List[str]:
    normalized: List[str] = []
    seen: Set[str] = set()
    for prefix in prefixes:
        p = str(prefix or "").strip().lower()
        if not p:
            continue
        if not p.endswith("_"):
            p = f"{p}_"
        if p in seen:
            continue
        seen.add(p)
        normalized.append(p)
    return normalized


def _extract_mandant_cfg(record_daten: Dict[str, Any]) -> Optional[Tuple[ConnectionConfig, ConnectionConfig]]:
    mandant_info = record_daten.get("MANDANT")
    if not isinstance(mandant_info, dict):
        return None

    host = mandant_info.get("HOST")
    port = mandant_info.get("PORT")
    user = mandant_info.get("USER")
    password = mandant_info.get("PASSWORD")
    database = mandant_info.get("DATABASE")
    system_db = mandant_info.get("SYSTEM_DB") or mandant_info.get("SYSTEM_DATABASE") or "pdvm_system"

    required = [host, port, user, password, database]
    if any(v in (None, "") for v in required):
        return None

    system_cfg = ConnectionConfig(
        host=str(host),
        port=int(port),
        user=str(user),
        password=str(password),
        database=str(system_db),
    )
    mandant_cfg = ConnectionConfig(
        host=str(host),
        port=int(port),
        user=str(user),
        password=str(password),
        database=str(database),
    )
    return system_cfg, mandant_cfg


async def _load_mandanten(auth_pool: asyncpg.Pool) -> List[Dict[str, Any]]:
    async with auth_pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT uid::text AS uid, daten, historisch
            FROM sys_mandanten
            ORDER BY created_at ASC NULLS LAST
            """
        )

    out: List[Dict[str, Any]] = []
    for row in rows:
        out.append(
            {
                "uid": str(row["uid"]),
                "historisch": int(row["historisch"] or 0),
                "daten": _parse_json_dict(row["daten"]),
            }
        )
    return out


def _replace_feature_tables(daten: Dict[str, Any]) -> Tuple[Dict[str, Any], bool]:
    changed = False
    updated = dict(daten)

    for cfg_key in ("CONFIG", "CONFIGS"):
        cfg = updated.get(cfg_key)
        if not isinstance(cfg, dict):
            continue

        features = cfg.get("FEATURES")
        if not isinstance(features, list):
            continue

        new_features: List[Any] = []
        for item in features:
            if isinstance(item, str) and item in TABLE_RENAMES:
                new_features.append(TABLE_RENAMES[item])
                changed = True
            else:
                new_features.append(item)

        deduped: List[Any] = []
        seen: Set[Any] = set()
        for item in new_features:
            marker = item if isinstance(item, (str, int, float, bool, type(None))) else repr(item)
            if marker in seen:
                continue
            seen.add(marker)
            deduped.append(item)

        cfg = dict(cfg)
        cfg["FEATURES"] = deduped
        updated[cfg_key] = cfg

    return updated, changed


async def _update_auth_feature_configs(auth_pool: asyncpg.Pool, apply_changes: bool) -> Dict[str, int]:
    stats = {"rows_updated": 0, "rows_planned": 0}

    async with auth_pool.acquire() as conn:
        rows = await conn.fetch("SELECT uid::text AS uid, daten FROM sys_mandanten")

        for row in rows:
            uid = str(row["uid"])
            daten = _parse_json_dict(row["daten"])
            if not daten:
                continue

            updated_daten, changed = _replace_feature_tables(daten)
            if not changed:
                continue

            stats["rows_planned"] += 1
            logger.info("📝 sys_mandanten FEATURES update geplant: uid=%s", uid)

            if apply_changes:
                await conn.execute(
                    """
                    UPDATE sys_mandanten
                    SET daten = $2::jsonb,
                        modified_at = NOW()
                    WHERE uid = $1::uuid
                    """,
                    uid,
                    json.dumps(updated_daten, ensure_ascii=False),
                )
                stats["rows_updated"] += 1

    return stats


async def _list_public_tables(pool: asyncpg.Pool) -> List[str]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT tablename
            FROM pg_tables
            WHERE schemaname = 'public'
            ORDER BY tablename
            """
        )
    return [str(r["tablename"]) for r in rows]


async def _rename_tables(pool: asyncpg.Pool, apply_changes: bool) -> Dict[str, int]:
    stats = {
        "planned": 0,
        "renamed": 0,
        "skipped_missing_source": 0,
        "skipped_target_exists": 0,
    }

    async with pool.acquire() as conn:
        for source, target in TABLE_RENAMES.items():
            source_exists = bool(await conn.fetchval("SELECT to_regclass($1)", f"public.{source}"))
            target_exists = bool(await conn.fetchval("SELECT to_regclass($1)", f"public.{target}"))

            if not source_exists:
                stats["skipped_missing_source"] += 1
                continue

            if target_exists:
                stats["skipped_target_exists"] += 1
                logger.warning("⚠️ Zieltabelle bereits vorhanden, Rename übersprungen: %s -> %s", source, target)
                continue

            stats["planned"] += 1
            logger.info("🔁 Rename geplant: %s -> %s", source, target)

            if apply_changes:
                await conn.execute(f'ALTER TABLE "{source}" RENAME TO "{target}"')
                stats["renamed"] += 1

    return stats


def _find_unprefixed_tables(tables: Iterable[str], allowed_prefixes: Iterable[str]) -> List[str]:
    prefixes = tuple(str(p).lower() for p in allowed_prefixes)
    violations: List[str] = []
    for table in tables:
        name = str(table).lower()
        if name.startswith(prefixes):
            continue
        violations.append(str(table))
    return violations


async def _scan_and_optionally_rename(
    target: DbTarget,
    *,
    allowed_prefixes: List[str],
    apply_changes: bool,
    do_rename: bool,
) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "role": target.role,
        "database": target.cfg.database,
        "rename": {},
        "unprefixed_tables": [],
        "error": None,
    }

    pool = await asyncpg.create_pool(target.cfg.to_url(), min_size=1, max_size=2)
    try:
        if do_rename:
            result["rename"] = await _rename_tables(pool, apply_changes)

        tables = await _list_public_tables(pool)
        result["unprefixed_tables"] = _find_unprefixed_tables(tables, allowed_prefixes)
    except Exception as exc:
        result["error"] = str(exc)
    finally:
        await pool.close()

    return result


async def main() -> None:
    parser = argparse.ArgumentParser(description="Rename legacy test tables and report prefix violations")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply changes (without this flag, script only reports planned changes)",
    )
    parser.add_argument(
        "--allow-prefix",
        action="append",
        default=[],
        help="Additional allowed table prefix (can be used multiple times)",
    )
    args = parser.parse_args()

    allowed_prefixes = _collect_unique_prefixes([*DEFAULT_ALLOWED_PREFIXES, *args.allow_prefix])
    logger.info("📐 Erlaubte Praefixe: %s", allowed_prefixes)
    logger.info("🛠️ Modus: %s", "APPLY" if args.apply else "DRY-RUN")

    await DatabasePool.create_pool()
    try:
        auth_cfg = await ConnectionManager.get_auth_config()
        auth_pool = await asyncpg.create_pool(auth_cfg.to_url(), min_size=1, max_size=2)
        try:
            mandanten = await _load_mandanten(auth_pool)
            logger.info("📋 Geladene sys_mandanten Datensaetze: %s", len(mandanten))

            cfg_stats = await _update_auth_feature_configs(auth_pool, args.apply)
        finally:
            await auth_pool.close()

        targets: List[DbTarget] = [DbTarget(role="auth", cfg=auth_cfg)]

        seen_system: Set[Tuple[str, int, str, str, str]] = set()
        seen_mandant: Set[Tuple[str, int, str, str, str]] = set()

        try:
            default_system_cfg = await ConnectionManager.get_system_config("pdvm_system")
            targets.append(DbTarget(role="system", cfg=default_system_cfg))
            seen_system.add(_cfg_key(default_system_cfg))
        except Exception as exc:
            logger.warning("⚠️ Standard-System-DB konnte nicht geladen werden: %s", exc)

        excluded_db_names: Set[str] = set()
        for rec in mandanten:
            if rec.get("uid") not in RESERVED_BASE_UIDS:
                continue
            mandant_info = rec.get("daten", {}).get("MANDANT")
            if isinstance(mandant_info, dict):
                db_name = str(mandant_info.get("DATABASE") or "").strip().lower()
                if db_name:
                    excluded_db_names.add(db_name)

        for rec in mandanten:
            if int(rec.get("historisch") or 0) == 1:
                continue

            parsed = _extract_mandant_cfg(rec.get("daten") or {})
            if not parsed:
                continue

            system_cfg, mandant_cfg = parsed
            mandant_db_norm = str(mandant_cfg.database).strip().lower()
            if mandant_db_norm in excluded_db_names:
                continue

            system_key = _cfg_key(system_cfg)
            if system_key not in seen_system:
                seen_system.add(system_key)
                targets.append(DbTarget(role="system", cfg=system_cfg))

            mandant_key = _cfg_key(mandant_cfg)
            if mandant_key not in seen_mandant:
                seen_mandant.add(mandant_key)
                targets.append(DbTarget(role="mandant", cfg=mandant_cfg))

        results: List[Dict[str, Any]] = []
        for target in targets:
            do_rename = target.role == "mandant"
            logger.info("🔎 Pruefe DB: role=%s db=%s", target.role, target.cfg.database)
            result = await _scan_and_optionally_rename(
                target,
                allowed_prefixes=allowed_prefixes,
                apply_changes=args.apply,
                do_rename=do_rename,
            )
            results.append(result)

        print("\n=== PREFIX ENFORCEMENT REPORT ===")
        print(f"mode={'APPLY' if args.apply else 'DRY-RUN'}")
        print(f"allowed_prefixes={allowed_prefixes}")
        print(f"sys_mandanten_feature_rows_planned={cfg_stats['rows_planned']}")
        print(f"sys_mandanten_feature_rows_updated={cfg_stats['rows_updated']}")

        total_unprefixed = 0
        total_renamed = 0
        for result in results:
            role = result.get("role")
            db_name = result.get("database")
            error = result.get("error")
            print(f"\n[{role}] {db_name}")
            if error:
                print(f"  error: {error}")
                continue

            rename = result.get("rename") or {}
            if rename:
                print(f"  rename_planned={rename.get('planned', 0)}")
                print(f"  renamed={rename.get('renamed', 0)}")
                print(f"  skipped_missing_source={rename.get('skipped_missing_source', 0)}")
                print(f"  skipped_target_exists={rename.get('skipped_target_exists', 0)}")
                total_renamed += int(rename.get("renamed", 0))

            unprefixed_tables = result.get("unprefixed_tables") or []
            total_unprefixed += len(unprefixed_tables)
            print(f"  unprefixed_count={len(unprefixed_tables)}")
            for table in unprefixed_tables:
                print(f"  - {table}")

        print("\n--- SUMMARY ---")
        print(f"total_databases={len(results)}")
        print(f"total_tables_renamed={total_renamed}")
        print(f"total_unprefixed_tables={total_unprefixed}")

    finally:
        await DatabasePool.close_pool()


if __name__ == "__main__":
    asyncio.run(main())

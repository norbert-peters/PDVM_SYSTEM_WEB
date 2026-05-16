"""
Phase 2 runner: build TABLE_META catalogs in auth/system/mandant DB contexts.

Default mode is dry-run.
Use --apply to execute inserts/updates.

Scope implemented:
- auth DB: asy_* tables -> asy_systemdaten (TABLE_META)
- system DB: sys_* and dev_* tables -> sys_systemdaten (TABLE_META)
- mandant DBs: msy_*, tst_ and app-specific prefixes -> msy_systemdaten (TABLE_META)

Usage:
  python backend/tools/phase2_apply_metadata_catalog.py
  python backend/tools/phase2_apply_metadata_catalog.py --apply
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

import asyncpg

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.connection_manager import ConnectionConfig, ConnectionManager

PDVM_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS {table_name} (
    uid UUID PRIMARY KEY,
    link_uid UUID,
    daten JSONB NOT NULL,
    name TEXT,
    historisch INTEGER DEFAULT 0,
    source_hash TEXT,
    sec_id UUID,
    gilt_bis TIMESTAMP DEFAULT '9999-12-31 23:59:59',
    created_at TIMESTAMP DEFAULT NOW(),
    modified_at TIMESTAMP DEFAULT NOW(),
    backup_daten JSONB DEFAULT '{{}}'::jsonb
)
"""

TARGET_PREFIXES = ("asy_", "sys_", "dev_", "msy_", "tst_")


@dataclass(frozen=True)
class DbTarget:
    role: str
    config: ConnectionConfig
    catalog_table: str


def _cfg_key(cfg: ConnectionConfig) -> Tuple[str, int, str, str]:
    return (str(cfg.host), int(cfg.port), str(cfg.user), str(cfg.database))


def _extract_prefix(table_name: str) -> str:
    name = str(table_name).lower().strip()
    for prefix in TARGET_PREFIXES:
        if name.startswith(prefix):
            return prefix
    if "_" in name:
        return name.split("_", 1)[0] + "_"
    return "<none>"


def _is_mandant_table(table_name: str) -> bool:
    prefix = _extract_prefix(table_name)
    if prefix in {"asy_", "sys_", "dev_", "<none>"}:
        return False
    return True


def _app_key_for_table(table_name: str) -> str:
    if "_" in table_name:
        return table_name.split("_", 1)[0].lower()
    return "core"


def _dict_tables_for_role(role: str, table_name: str) -> Tuple[Optional[str], Optional[str]]:
    prefix = _extract_prefix(table_name)

    if role == "auth":
        # Auth tables have no control dict in current architecture.
        return None, None

    if role == "system":
        return "sys_control_dict", "sys_control_dict_audit"

    # mandant
    if prefix in {"msy_", "tst_"} or _is_mandant_table(table_name):
        return "msy_control_dict", "msy_control_dict_audit"

    return None, None


def _table_uid(role: str, database: str, table_name: str) -> str:
    base = f"pdvm.table_meta::{role}::{database.lower()}::{table_name.lower()}"
    return str(uuid.uuid5(uuid.NAMESPACE_URL, base))


def _meta_payload(role: str, database: str, table_name: str) -> Dict[str, Any]:
    prefix = _extract_prefix(table_name)
    dict_table, dict_audit_table = _dict_tables_for_role(role, table_name)

    return {
        "gruppe": "TABLE_META",
        "ROOT": {
            "TABLE": table_name,
            "PREFIX": prefix,
            "DOMAIN": role,
            "CONTROL_DICT_TABLE": dict_table,
            "DICT_AUDIT_TABLE": dict_audit_table,
            "APP_KEY": _app_key_for_table(table_name),
            "IS_ACTIVE": True,
            "SOURCE_DB": database,
        },
    }


async def _ensure_pdvm_table(conn: asyncpg.Connection, table_name: str) -> bool:
    exists = await conn.fetchval("SELECT to_regclass($1)", f"public.{table_name}")
    if exists:
        return False

    await conn.execute(PDVM_TABLE_SQL.format(table_name=f'"{table_name}"'))

    index_specs = [
        (f"idx_{table_name}_link_uid", f'"{table_name}"(link_uid)'),
        (f"idx_{table_name}_created_at", f'"{table_name}"(created_at)'),
        (f"idx_{table_name}_sec_id", f'"{table_name}"(sec_id)'),
        (f"idx_{table_name}_historisch", f'"{table_name}"(historisch)'),
        (f"idx_{table_name}_name", f'"{table_name}"(name)'),
        (f"idx_{table_name}_modified_at", f'"{table_name}"(modified_at)'),
        (f"idx_{table_name}_daten", f'"{table_name}" USING GIN(daten)'),
    ]

    for idx_name, idx_target in index_specs:
        await conn.execute(f'CREATE INDEX IF NOT EXISTS "{idx_name}" ON {idx_target}')

    return True


async def _fetch_public_tables(conn: asyncpg.Connection) -> List[str]:
    rows = await conn.fetch(
        """
        SELECT tablename
        FROM pg_tables
        WHERE schemaname = 'public'
        ORDER BY tablename
        """
    )
    return [str(r["tablename"]) for r in rows]


async def _upsert_table_meta(
    conn: asyncpg.Connection,
    *,
    catalog_table: str,
    role: str,
    database: str,
    table_name: str,
    apply_changes: bool,
) -> Tuple[str, Optional[str]]:
    payload = _meta_payload(role, database, table_name)
    payload_json = json.dumps(payload, ensure_ascii=False)
    table_uid = _table_uid(role, database, table_name)

    existing = await conn.fetchrow(
        f'''
        SELECT uid::text AS uid, link_uid::text AS link_uid, daten
        FROM "{catalog_table}"
        WHERE COALESCE(daten->>'gruppe', daten->>'GRUPPE', '') = 'TABLE_META'
          AND (
              name = $1
              OR COALESCE(daten->'ROOT'->>'TABLE', '') = $1
          )
        ORDER BY modified_at DESC NULLS LAST
        LIMIT 1
        ''',
        table_name,
    )

    if not existing:
        if apply_changes:
            await conn.execute(
                f'''
                INSERT INTO "{catalog_table}" (uid, link_uid, daten, name, historisch, created_at, modified_at)
                VALUES ($1::uuid, $2::uuid, $3::jsonb, $4, 0, NOW(), NOW())
                ''',
                table_uid,
                table_uid,
                payload_json,
                table_name,
            )
        return "insert", table_uid

    existing_uid = str(existing["uid"])
    if apply_changes:
        await conn.execute(
            f'''
            UPDATE "{catalog_table}"
            SET link_uid = $1::uuid,
                daten = $2::jsonb,
                name = $3,
                historisch = 0,
                modified_at = NOW()
            WHERE uid = $4::uuid
            ''',
            table_uid,
            payload_json,
            table_name,
            existing_uid,
        )
    return "update", existing_uid


async def _collect_db_targets() -> List[DbTarget]:
    auth_cfg = await ConnectionManager.get_auth_config()
    auth_conn = await asyncpg.connect(**auth_cfg.to_dict())
    try:
        rows = await auth_conn.fetch(
            """
            SELECT datname
            FROM pg_database
            WHERE datistemplate = false
              AND datname NOT IN ('postgres')
            ORDER BY datname
            """
        )
        db_names = [str(r["datname"]) for r in rows]
    finally:
        await auth_conn.close()

    targets: List[DbTarget] = [DbTarget("auth", auth_cfg, "asy_systemdaten")]

    seen: Set[Tuple[str, int, str, str]] = {_cfg_key(auth_cfg)}

    for db_name in db_names:
        cfg = ConnectionConfig(
            host=auth_cfg.host,
            port=auth_cfg.port,
            user=auth_cfg.user,
            password=auth_cfg.password,
            database=db_name,
        )
        key = _cfg_key(cfg)
        if key in seen:
            continue
        seen.add(key)

        db_name_l = db_name.lower()
        if db_name_l == "auth":
            continue
        if db_name_l == "pdvm_system":
            targets.append(DbTarget("system", cfg, "sys_systemdaten"))
            continue

        # all remaining business DBs are treated as mandant DBs
        targets.append(DbTarget("mandant", cfg, "msy_systemdaten"))

    return targets


def _select_candidate_tables(role: str, tables: Sequence[str]) -> List[str]:
    result: List[str] = []
    for table in tables:
        t = str(table)
        prefix = _extract_prefix(t)

        if role == "auth":
            if prefix == "asy_":
                result.append(t)
            continue

        if role == "system":
            if prefix in {"sys_", "dev_"}:
                result.append(t)
            continue

        # mandant
        if _is_mandant_table(t):
            result.append(t)

    # catalog table itself should not be represented inside itself
    return sorted(dict.fromkeys(result))


async def _process_target(target: DbTarget, apply_changes: bool) -> Dict[str, Any]:
    conn = await asyncpg.connect(**target.config.to_dict())
    result: Dict[str, Any] = {
        "role": target.role,
        "database": target.config.database,
        "catalog_table": target.catalog_table,
        "catalog_created": 0,
        "tables_total": 0,
        "meta_candidates": 0,
        "inserted": 0,
        "updated": 0,
        "errors": [],
    }

    try:
        catalog_exists = bool(await conn.fetchval("SELECT to_regclass($1)", f"public.{target.catalog_table}"))
        if apply_changes:
            created = await _ensure_pdvm_table(conn, target.catalog_table)
            result["catalog_created"] = 1 if created else 0
            catalog_exists = True

        tables = await _fetch_public_tables(conn)
        result["tables_total"] = len(tables)

        candidates = _select_candidate_tables(target.role, tables)
        candidates = [t for t in candidates if t != target.catalog_table]
        result["meta_candidates"] = len(candidates)

        for table_name in candidates:
            try:
                if not catalog_exists and not apply_changes:
                    result["inserted"] += 1
                    continue
                action, _ = await _upsert_table_meta(
                    conn,
                    catalog_table=target.catalog_table,
                    role=target.role,
                    database=target.config.database,
                    table_name=table_name,
                    apply_changes=apply_changes,
                )
                if action == "insert":
                    result["inserted"] += 1
                else:
                    result["updated"] += 1
            except Exception as exc:
                result["errors"].append(f"{table_name}: {exc}")
    finally:
        await conn.close()

    return result


async def main() -> None:
    parser = argparse.ArgumentParser(description="Apply Phase 2 TABLE_META catalog rollout")
    parser.add_argument("--apply", action="store_true", help="Execute inserts/updates (default: dry-run)")
    args = parser.parse_args()

    targets = await _collect_db_targets()

    print(f"mode={'APPLY' if args.apply else 'DRY-RUN'}")
    print(f"targets={len(targets)}")

    results: List[Dict[str, Any]] = []
    for target in targets:
        try:
            r = await _process_target(target, apply_changes=args.apply)
            results.append(r)
            print(
                f"role={r['role']} db={r['database']} catalog={r['catalog_table']} "
                f"created={r['catalog_created']} candidates={r['meta_candidates']} "
                f"inserted={r['inserted']} updated={r['updated']} errors={len(r['errors'])}"
            )
        except Exception as exc:
            results.append(
                {
                    "role": target.role,
                    "database": target.config.database,
                    "catalog_table": target.catalog_table,
                    "catalog_created": 0,
                    "tables_total": 0,
                    "meta_candidates": 0,
                    "inserted": 0,
                    "updated": 0,
                    "errors": [str(exc)],
                }
            )
            print(
                f"role={target.role} db={target.config.database} catalog={target.catalog_table} "
                f"created=0 candidates=0 inserted=0 updated=0 errors=1"
            )

    total_inserted = sum(int(r.get("inserted", 0)) for r in results)
    total_updated = sum(int(r.get("updated", 0)) for r in results)
    total_errors = sum(len(r.get("errors", [])) for r in results)

    print(f"total_inserted={total_inserted}")
    print(f"total_updated={total_updated}")
    print(f"total_errors={total_errors}")


if __name__ == "__main__":
    asyncio.run(main())

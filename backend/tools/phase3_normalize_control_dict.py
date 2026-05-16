"""
Phase 3 runner: normalize control dictionaries to ROOT+CONTROL model.

Implements spec requirements:
- enforce only ROOT + CONTROL top-level groups
- enforce CONTROL.FIELD uppercase
- enforce name and ROOT.SELF_NAME = <TABLE_PREFIX>_<FIELD_UPPER>
- enforce link_uid = table_uid from TABLE_META catalogs

Scope:
- system DB: sys_control_dict using sys_systemdaten
- mandant DBs: msy_control_dict using msy_systemdaten

Usage:
  python backend/tools/phase3_normalize_control_dict.py --dry-run
  python backend/tools/phase3_normalize_control_dict.py --apply
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import asyncpg

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.connection_manager import ConnectionConfig, ConnectionManager

TEMPLATE_555_UID = "55555555-5555-5555-5555-555555555555"


@dataclass(frozen=True)
class Target:
    role: str
    cfg: ConnectionConfig
    control_table: str
    catalog_table: str


def _as_dict(value: Any) -> Dict[str, Any]:
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


def _pick_ci(d: Dict[str, Any], *keys: str) -> Any:
    if not isinstance(d, dict):
        return None
    for key in keys:
        if key in d:
            return d[key]
        up = key.upper()
        if up in d:
            return d[up]
        low = key.lower()
        if low in d:
            return d[low]
    return None


def _table_prefix(table_name: str) -> str:
    table = str(table_name or "").strip().lower()
    if not table:
        return "SYS"
    if "_" in table:
        return table.split("_", 1)[0].upper()
    return (table[:3] or "CTL").upper()


def _to_upper_text(value: Any) -> str:
    return str(value or "").strip().upper()


def _canonical_name(table_name: str, field_upper: str) -> str:
    prefix = _table_prefix(table_name)
    return f"{prefix}_{field_upper}" if field_upper else prefix


def _normalize_control_keys(control_in: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for key, value in control_in.items():
        out[str(key).upper()] = value
    return out


async def _list_databases(auth_cfg: ConnectionConfig) -> List[str]:
    conn = await asyncpg.connect(**auth_cfg.to_dict())
    try:
        rows = await conn.fetch(
            """
            SELECT datname
            FROM pg_database
            WHERE datistemplate = false
              AND datname NOT IN ('postgres')
            ORDER BY datname
            """
        )
    finally:
        await conn.close()
    return [str(r["datname"]) for r in rows]


async def _build_targets() -> List[Target]:
    auth_cfg = await ConnectionManager.get_auth_config()
    dbs = await _list_databases(auth_cfg)

    targets: List[Target] = []
    for db in dbs:
        cfg = ConnectionConfig(auth_cfg.host, auth_cfg.port, auth_cfg.user, auth_cfg.password, db)
        db_l = db.lower()
        if db_l == "pdvm_system":
            targets.append(Target("system", cfg, "sys_control_dict", "sys_systemdaten"))
        elif db_l == "auth":
            continue
        else:
            targets.append(Target("mandant", cfg, "msy_control_dict", "msy_systemdaten"))
    return targets


async def _table_exists(conn: asyncpg.Connection, table_name: str) -> bool:
    return bool(await conn.fetchval("SELECT to_regclass($1)", f"public.{table_name}"))


async def _load_table_uid_map(conn: asyncpg.Connection, catalog_table: str) -> Dict[str, str]:
    rows = await conn.fetch(
        f'''
        SELECT
            uid::text AS uid,
            link_uid::text AS link_uid,
            name,
            daten
        FROM "{catalog_table}"
        WHERE COALESCE(daten->>'gruppe', daten->>'GRUPPE', '') = 'TABLE_META'
          AND historisch = 0
        '''
    )

    mapping: Dict[str, str] = {}
    for row in rows:
        daten = _as_dict(row.get("daten"))
        root = _as_dict(daten.get("ROOT"))
        table_name = str(_pick_ci(root, "TABLE") or row.get("name") or "").strip().lower()
        table_uid = str(row.get("link_uid") or row.get("uid") or "").strip().lower()
        if not table_name or not table_uid:
            continue
        mapping[table_name] = table_uid
    return mapping


def _extract_table_name(row_name: str, root_in: Dict[str, Any], control_in: Dict[str, Any], fallback_table: str) -> str:
    table = str(
        _pick_ci(control_in, "TABLE")
        or _pick_ci(root_in, "TABLE")
        or ""
    ).strip().lower()
    if table:
        return table

    # best effort from canonical name prefix
    if row_name and "_" in row_name:
        prefix = row_name.split("_", 1)[0].strip().lower()
        if prefix in {"sys", "dev"}:
            return "sys_control_dict"
        if prefix in {"msy", "tst"}:
            return fallback_table

    return fallback_table


def _extract_field(row_name: str, root_in: Dict[str, Any], control_in: Dict[str, Any]) -> str:
    field = str(
        _pick_ci(control_in, "FIELD", "FELD")
        or _pick_ci(root_in, "FIELD", "FELD")
        or _pick_ci(control_in, "NAME")
        or row_name
        or ""
    ).strip()

    # if NAME already canonical (PREFIX_FIELD), cut prefix
    if "_" in field:
        parts = field.split("_", 1)
        if len(parts) == 2 and parts[0].isalpha():
            field = parts[1]

    return _to_upper_text(field)


def _needs_update(
    *,
    original_daten: Dict[str, Any],
    new_daten: Dict[str, Any],
    row_name: str,
    canonical_name: str,
    row_link_uid: Optional[str],
    target_link_uid: Optional[str],
) -> bool:
    if str(row_name or "") != str(canonical_name or ""):
        return True

    old = json.dumps(original_daten, ensure_ascii=False, sort_keys=True)
    new = json.dumps(new_daten, ensure_ascii=False, sort_keys=True)
    if old != new:
        return True

    if target_link_uid and str(row_link_uid or "").lower() != str(target_link_uid).lower():
        return True

    return False


async def _normalize_target(target: Target, apply_changes: bool) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "role": target.role,
        "database": target.cfg.database,
        "control_table": target.control_table,
        "catalog_table": target.catalog_table,
        "rows_total": 0,
        "rows_changed": 0,
        "rows_skipped_no_table_uid": 0,
        "errors": [],
    }

    conn = await asyncpg.connect(**target.cfg.to_dict())
    try:
        if not await _table_exists(conn, target.control_table):
            return result
        if not await _table_exists(conn, target.catalog_table):
            result["errors"].append(f"catalog missing: {target.catalog_table}")
            return result

        table_uid_map = await _load_table_uid_map(conn, target.catalog_table)

        rows = await conn.fetch(
            f'''
            SELECT uid::text AS uid, link_uid::text AS link_uid, name, daten
            FROM "{target.control_table}"
            WHERE historisch = 0
            '''
        )

        result["rows_total"] = len(rows)

        fallback_table = "sys_control_dict" if target.role == "system" else "msy_control_dict"

        for row in rows:
            uid = str(row.get("uid"))
            if uid.lower() == TEMPLATE_555_UID:
                continue
            row_name = str(row.get("name") or "")
            row_link_uid = str(row.get("link_uid") or "")
            original_daten = _as_dict(row.get("daten"))
            if not original_daten:
                continue

            root_in = _as_dict(original_daten.get("ROOT"))
            control_in = _as_dict(original_daten.get("CONTROL"))
            if not control_in:
                control_in = {
                    k: v
                    for k, v in original_daten.items()
                    if str(k).upper() not in {"ROOT", "CONTROL"}
                }

            control = _normalize_control_keys(control_in)
            table_name = _extract_table_name(row_name, root_in, control, fallback_table)
            field_upper = _extract_field(row_name, root_in, control)
            canonical_name = _canonical_name(table_name, field_upper)

            if field_upper:
                control["FIELD"] = field_upper
                control["FELD"] = field_upper
            control["NAME"] = canonical_name
            control["TABLE"] = table_name

            gruppe = _pick_ci(control, "GRUPPE")
            if gruppe is not None:
                control["GRUPPE"] = _to_upper_text(gruppe)

            root = dict(root_in)
            root["SELF_GUID"] = uid
            root["SELF_NAME"] = canonical_name
            root["NAME"] = canonical_name
            root["TABLE"] = table_name
            root["FIELD"] = field_upper

            new_daten = {"ROOT": root, "CONTROL": control}

            table_uid = table_uid_map.get(table_name)
            if not table_uid:
                result["rows_skipped_no_table_uid"] += 1
                continue

            root["SELF_LINK_UID"] = table_uid

            if not _needs_update(
                original_daten=original_daten,
                new_daten=new_daten,
                row_name=row_name,
                canonical_name=canonical_name,
                row_link_uid=row_link_uid,
                target_link_uid=table_uid,
            ):
                continue

            result["rows_changed"] += 1
            if apply_changes:
                await conn.execute(
                    f'''
                    UPDATE "{target.control_table}"
                    SET name = $1,
                        link_uid = $2::uuid,
                        daten = $3::jsonb,
                        modified_at = NOW()
                    WHERE uid = $4::uuid
                    ''',
                    canonical_name,
                    table_uid,
                    json.dumps(new_daten, ensure_ascii=False),
                    uid,
                )
    except Exception as exc:
        result["errors"].append(str(exc))
    finally:
        await conn.close()

    return result


def _change_reasons(
    *,
    original_daten: Dict[str, Any],
    new_daten: Dict[str, Any],
    row_name: str,
    canonical_name: str,
    row_link_uid: Optional[str],
    target_link_uid: Optional[str],
) -> Dict[str, bool]:
    old = json.dumps(original_daten, ensure_ascii=False, sort_keys=True)
    new = json.dumps(new_daten, ensure_ascii=False, sort_keys=True)
    return {
        "name_diff": str(row_name or "") != str(canonical_name or ""),
        "daten_diff": old != new,
        "link_uid_diff": bool(target_link_uid)
        and str(row_link_uid or "").lower() != str(target_link_uid).lower(),
    }


async def main() -> None:
    parser = argparse.ArgumentParser(description="Apply Phase 3 control dict normalization")
    parser.add_argument("--dry-run", action="store_true", help="Analyze only")
    parser.add_argument("--apply", action="store_true", help="Execute updates")
    parser.add_argument("--debug-sample", type=int, default=0, help="Print up to N changed rows with reason flags")
    args = parser.parse_args()

    if args.apply and args.dry_run:
        raise SystemExit("--apply und --dry-run gleichzeitig nicht erlaubt")

    apply_changes = bool(args.apply) and not bool(args.dry_run)

    targets = await _build_targets()

    print(f"mode={'APPLY' if apply_changes else 'DRY-RUN'}")
    print(f"targets={len(targets)}")

    results: List[Dict[str, Any]] = []
    printed_debug = 0
    for target in targets:
        r = await _normalize_target(target, apply_changes)
        results.append(r)
        print(
            f"role={r['role']} db={r['database']} table={r['control_table']} "
            f"rows={r['rows_total']} changed={r['rows_changed']} "
            f"skip_no_table_uid={r['rows_skipped_no_table_uid']} errors={len(r['errors'])}"
        )

        if args.debug_sample > 0 and printed_debug < args.debug_sample and target.role == "system":
            conn = await asyncpg.connect(**target.cfg.to_dict())
            try:
                table_uid_map = await _load_table_uid_map(conn, target.catalog_table)
                rows = await conn.fetch(
                    f'''
                    SELECT uid::text AS uid, link_uid::text AS link_uid, name, daten
                    FROM "{target.control_table}"
                    WHERE historisch = 0
                    '''
                )
                for row in rows:
                    if printed_debug >= args.debug_sample:
                        break
                    uid = str(row.get("uid"))
                    if uid.lower() == TEMPLATE_555_UID:
                        continue
                    row_name = str(row.get("name") or "")
                    row_link_uid = str(row.get("link_uid") or "")
                    original_daten = _as_dict(row.get("daten"))
                    if not original_daten:
                        continue

                    root_in = _as_dict(original_daten.get("ROOT"))
                    control_in = _as_dict(original_daten.get("CONTROL"))
                    if not control_in:
                        control_in = {
                            k: v
                            for k, v in original_daten.items()
                            if str(k).upper() not in {"ROOT", "CONTROL"}
                        }

                    control = _normalize_control_keys(control_in)
                    table_name = _extract_table_name(row_name, root_in, control, "sys_control_dict")
                    field_upper = _extract_field(row_name, root_in, control)
                    canonical_name = _canonical_name(table_name, field_upper)

                    control["FIELD"] = field_upper
                    control["FELD"] = field_upper
                    control["NAME"] = canonical_name
                    control["TABLE"] = table_name

                    gruppe = _pick_ci(control, "GRUPPE")
                    if gruppe is not None:
                        control["GRUPPE"] = _to_upper_text(gruppe)

                    root_new = dict(root_in)
                    root_new["SELF_GUID"] = uid
                    root_new["SELF_NAME"] = canonical_name
                    root_new["NAME"] = canonical_name
                    root_new["TABLE"] = table_name
                    root_new["FIELD"] = field_upper
                    table_uid = table_uid_map.get(table_name)
                    if table_uid:
                        root_new["SELF_LINK_UID"] = table_uid

                    new_daten = {"ROOT": root_new, "CONTROL": control}

                    table_uid = table_uid_map.get(table_name)
                    if not table_uid:
                        continue

                    if not _needs_update(
                        original_daten=original_daten,
                        new_daten=new_daten,
                        row_name=row_name,
                        canonical_name=canonical_name,
                        row_link_uid=row_link_uid,
                        target_link_uid=table_uid,
                    ):
                        continue

                    reasons = _change_reasons(
                        original_daten=original_daten,
                        new_daten=new_daten,
                        row_name=row_name,
                        canonical_name=canonical_name,
                        row_link_uid=row_link_uid,
                        target_link_uid=table_uid,
                    )
                    print(
                        "debug_changed "
                        f"uid={uid} name={row_name} canonical={canonical_name} "
                        f"table={table_name} reasons={reasons}"
                    )
                    printed_debug += 1
            finally:
                await conn.close()

    total_changed = sum(int(r.get("rows_changed", 0)) for r in results)
    total_rows = sum(int(r.get("rows_total", 0)) for r in results)
    total_skipped = sum(int(r.get("rows_skipped_no_table_uid", 0)) for r in results)
    total_errors = sum(len(r.get("errors", [])) for r in results)

    print(f"total_rows={total_rows}")
    print(f"total_changed={total_changed}")
    print(f"total_skipped_no_table_uid={total_skipped}")
    print(f"total_errors={total_errors}")


if __name__ == "__main__":
    asyncio.run(main())

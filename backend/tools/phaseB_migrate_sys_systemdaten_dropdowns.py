"""
Phase B.2: Big-Bang Migration von Dropdown-Strukturen aus sys_systemdaten nach sys_dropdowndaten.

Ziel:
1. Pro Dropdown ein eigener Datensatz in sys_dropdowndaten.
2. RECORD_TYPE in Ziel- und Quellsatz setzen.
3. Migrierte Dropdown-Container aus sys_systemdaten entfernen.
4. Harte Referenzprüfung: verbleibende Verweise auf sys_systemdaten-Dropdowns sind Fehler.

Usage:
  python backend/tools/phaseB_migrate_sys_systemdaten_dropdowns.py
  python backend/tools/phaseB_migrate_sys_systemdaten_dropdowns.py --apply
  python backend/tools/phaseB_migrate_sys_systemdaten_dropdowns.py --output backend/reports/phaseB_migrate_sys_systemdaten_dropdowns_report.json
"""

from __future__ import annotations

import argparse
import asyncio
import copy
import json
import re
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import asyncpg

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.connection_manager import ConnectionConfig, ConnectionManager

UID_555 = "55555555-5555-5555-5555-555555555555"
UID_666 = "66666666-6666-6666-6666-666666666666"
SYSTEM_MANDANT_UIDS = {UID_555, UID_666, "00000000-0000-0000-0000-000000000000"}
MIGRATION_TAG = "phaseB_sys_systemdaten_to_dropdowndaten_v1"
DEFAULT_LANG = "DE-DE"


@dataclass
class TableMeta:
    table_name: str
    columns: List[str] = field(default_factory=list)

    @property
    def has_uid(self) -> bool:
        return "uid" in self.columns

    @property
    def has_daten(self) -> bool:
        return "daten" in self.columns

    @property
    def has_name(self) -> bool:
        return "name" in self.columns

    @property
    def has_historisch(self) -> bool:
        return "historisch" in self.columns


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


def _is_lang_key(value: str) -> bool:
    s = str(value or "").strip()
    if not s:
        return False
    if re.fullmatch(r"[A-Za-z]{2}[-_][A-Za-z]{2}", s):
        return True
    if re.fullmatch(r"[A-Za-z]{4}", s):
        return True
    return False


def _norm_lang(value: Any) -> str:
    s = str(value or "").strip().upper()
    return s if s else DEFAULT_LANG


def _norm_field(value: Any) -> str:
    return str(value or "").strip().lower()


def _deep_walk_find_refs(obj: Any, path: Tuple[str, ...], hits: List[Dict[str, Any]]) -> None:
    if isinstance(obj, dict):
        table_val = str(obj.get("table") or "").strip().lower()
        if table_val == "sys_systemdaten":
            path_text = ".".join(path).lower()
            is_dropdown_ref = (
                "dropdown" in path_text
                or "dropdown" in [str(k).lower() for k in obj.keys()]
                or str(obj.get("type") or "").strip().lower() == "dropdown"
            )
            if is_dropdown_ref:
                hits.append({"path": ".".join(path), "context": "dropdown", "node": obj})
        for k, v in obj.items():
            _deep_walk_find_refs(v, (*path, str(k)), hits)
    elif isinstance(obj, list):
        for idx, item in enumerate(obj):
            _deep_walk_find_refs(item, (*path, str(idx)), hits)


def _build_dropdown_dataset(
    *,
    db_label: str,
    source_uid: str,
    field_key: str,
    source_name: str,
    default_lang: str,
    lang_items: Dict[str, Dict[str, Any]],
) -> Tuple[str, str, Dict[str, Any]]:
    stable_uid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{MIGRATION_TAG}:{db_label}:{source_uid}:{field_key}"))
    stable_name = f"MIGRATED_DROPDOWN::{field_key}"

    lang_payload: Dict[str, Any] = {}
    for lang, item in sorted(lang_items.items(), key=lambda kv: kv[0]):
        lang_payload[_norm_lang(lang)] = {
            str(uuid.uuid5(uuid.NAMESPACE_URL, f"{stable_uid}:{lang}:{field_key}")): item
        }

    payload = {
        "ROOT": {
            "SELF_GUID": stable_uid,
            "SELF_NAME": stable_name,
            "TABLE": "sys_dropdowndaten",
            "RECORD_TYPE": "dropdown_definition",
            "FIELD_KEY": field_key,
            "DEFAULT_LANGUAGE": _norm_lang(default_lang),
            "SOURCE_TABLE": "sys_systemdaten",
            "SOURCE_UID": source_uid,
            "SOURCE_NAME": source_name,
            "MIGRATION_TAG": MIGRATION_TAG,
            "UPDATED_AT_UTC": datetime.now(timezone.utc).isoformat(),
        },
        **lang_payload,
    }
    return stable_uid, stable_name, payload


async def _get_table_meta(conn: asyncpg.Connection) -> Dict[str, TableMeta]:
    rows = await conn.fetch(
        """
        SELECT table_name, column_name
        FROM information_schema.columns
        WHERE table_schema = 'public'
        ORDER BY table_name, ordinal_position
        """
    )
    by_table: Dict[str, List[str]] = {}
    for row in rows:
        t = str(row.get("table_name"))
        c = str(row.get("column_name"))
        by_table.setdefault(t, []).append(c)
    return {t: TableMeta(table_name=t, columns=cols) for t, cols in by_table.items()}


async def _resolve_main_mandant_config() -> Tuple[Optional[ConnectionConfig], Optional[Dict[str, Any]]]:
    auth_cfg = await ConnectionManager.get_auth_config()
    conn = await asyncpg.connect(**auth_cfg.to_dict())
    try:
        source_table: Optional[str] = None
        for table_name in ("asy_mandanten", "sys_mandanten"):
            exists = await conn.fetchval("SELECT to_regclass($1) IS NOT NULL", f"public.{table_name}")
            if exists:
                source_table = table_name
                break

        if not source_table:
            return None, None

        rows = await conn.fetch(
            f'''
            SELECT uid::text AS uid, name, daten
            FROM "{source_table}"
            WHERE COALESCE(historisch, 0) = 0
            '''
        )

        candidates: List[Dict[str, Any]] = []
        for row in rows:
            uid = str(row.get("uid") or "")
            if uid in SYSTEM_MANDANT_UIDS:
                continue
            daten = _as_dict(row.get("daten"))
            mandant = _as_dict(daten.get("MANDANT"))
            host = str(mandant.get("HOST") or auth_cfg.host or "").strip()
            user = str(mandant.get("USER") or auth_cfg.user or "").strip()
            password = str(mandant.get("PASSWORD") or "").strip()
            if not password or password in {"postgres", "Polari$55"}:
                password = str(auth_cfg.password or "")
            database = str(mandant.get("DATABASE") or "").strip()
            port_raw = mandant.get("PORT") or auth_cfg.port
            try:
                port = int(port_raw)
            except Exception:
                continue

            if not (host and user and database):
                continue

            candidates.append(
                {
                    "uid": uid,
                    "name": str(row.get("name") or ""),
                    "database": database,
                    "host": host,
                    "port": port,
                    "user": user,
                    "password": password,
                    "source_table": source_table,
                }
            )

        if not candidates:
            return None, None

        chosen = sorted(candidates, key=lambda x: (x.get("name") or "").lower())[0]
        cfg = ConnectionConfig(
            host=chosen["host"],
            port=int(chosen["port"]),
            user=chosen["user"],
            password=chosen["password"],
            database=chosen["database"],
        )
        return cfg, chosen
    finally:
        await conn.close()


async def _load_active_rows(conn: asyncpg.Connection, table_name: str, has_historisch: bool) -> List[Dict[str, Any]]:
    where_hist = "WHERE COALESCE(historisch, 0) = 0" if has_historisch else ""
    rows = await conn.fetch(
        f'''
        SELECT uid::text AS uid, name, daten
        FROM "{table_name}"
        {where_hist}
        '''
    )
    out: List[Dict[str, Any]] = []
    for row in rows:
        uid = str(row.get("uid") or "")
        if uid in {UID_555, UID_666}:
            continue
        out.append({"uid": uid, "name": str(row.get("name") or ""), "daten": _as_dict(row.get("daten"))})
    return out


async def _upsert_row(
    conn: asyncpg.Connection,
    meta: TableMeta,
    *,
    row_uid: str,
    row_name: str,
    daten: Dict[str, Any],
) -> str:
    exists = await conn.fetchval(
        f'SELECT COUNT(*) FROM "{meta.table_name}" WHERE uid::text = $1',
        row_uid,
    )
    if int(exists or 0) > 0:
        await conn.execute(
            f'UPDATE "{meta.table_name}" SET daten = $1::jsonb, name = $2 WHERE uid::text = $3',
            json.dumps(daten, ensure_ascii=False),
            row_name,
            row_uid,
        )
        return "updated"

    cols: List[str] = ["uid", "daten"]
    vals: List[Any] = [uuid.UUID(row_uid), json.dumps(daten, ensure_ascii=False)]
    if meta.has_name:
        cols.append("name")
        vals.append(row_name)
    if meta.has_historisch:
        cols.append("historisch")
        vals.append(0)

    placeholders = ", ".join(f"${i+1}" for i in range(len(cols)))
    col_sql = ", ".join(f'"{c}"' for c in cols)
    await conn.execute(f'INSERT INTO "{meta.table_name}" ({col_sql}) VALUES ({placeholders})', *vals)
    return "inserted"


def _extract_dropdowns_from_system_row(row: Dict[str, Any]) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, Any], Dict[str, Any]]:
    """
    Returns:
    1) by_field: {field_key: {lang: item_dict}}
    2) mutated_data (sys_systemdaten without migrated dropdown item containers)
    3) stats
    """
    daten = copy.deepcopy(_as_dict(row.get("daten")))
    root = _as_dict(daten.get("ROOT"))
    default_lang = _norm_lang(root.get("DEFAULT_LANGUAGE") or DEFAULT_LANG)

    by_field: Dict[str, Dict[str, Any]] = {}
    migrated_items: List[Dict[str, Any]] = []

    lang_groups = [k for k in daten.keys() if _is_lang_key(str(k)) and isinstance(daten.get(k), dict)]
    for lang in lang_groups:
        group_obj = _as_dict(daten.get(lang))
        to_remove_keys: List[str] = []

        for item_key, item_value in group_obj.items():
            item = _as_dict(item_value)
            edit_list = item.get("edit_list")
            if not isinstance(edit_list, list) or not edit_list:
                continue

            field_key = _norm_field(item.get("list_name") or item.get("name") or item_key)
            if not field_key:
                continue

            by_field.setdefault(field_key, {})[_norm_lang(lang)] = item
            migrated_items.append({"lang": _norm_lang(lang), "field_key": field_key, "item_key": str(item_key)})
            to_remove_keys.append(str(item_key))

        for key in to_remove_keys:
            group_obj.pop(key, None)

        if group_obj:
            daten[lang] = group_obj
        else:
            daten.pop(lang, None)

    root["RECORD_TYPE"] = "mixed_system_config"
    root["UPDATED_AT_UTC"] = datetime.now(timezone.utc).isoformat()
    daten["ROOT"] = root

    stats = {
        "default_language": default_lang,
        "migrated_items": migrated_items,
        "migrated_count": len(migrated_items),
        "fields_count": len(by_field),
    }
    return by_field, daten, stats


def _rewrite_dropdown_refs_in_source(
    daten: Dict[str, Any],
    *,
    source_uid: str,
    field_to_uid: Dict[str, str],
) -> Tuple[int, List[Dict[str, Any]]]:
    rewired_count = 0
    unresolved: List[Dict[str, Any]] = []

    def _walk(node: Any, path: Tuple[str, ...]) -> None:
        nonlocal rewired_count
        if isinstance(node, dict):
            for key, value in list(node.items()):
                next_path = (*path, str(key))

                if str(key).lower() == "dropdown" and isinstance(value, dict):
                    table_val = str(value.get("table") or "").strip().lower()
                    if table_val == "sys_systemdaten":
                        candidates = [
                            _norm_field(value.get("field_name")),
                            _norm_field(value.get("list_name")),
                            _norm_field(value.get("name")),
                            _norm_field(value.get("field")),
                        ]
                        mapped_uid: Optional[str] = None
                        for c in candidates:
                            if c and c in field_to_uid:
                                mapped_uid = field_to_uid[c]
                                break

                        if mapped_uid:
                            value["table"] = "sys_dropdowndaten"
                            value["key"] = mapped_uid
                            value["source_uid"] = source_uid
                            value["migration_tag"] = MIGRATION_TAG
                            rewired_count += 1
                        else:
                            unresolved.append(
                                {
                                    "path": ".".join(next_path),
                                    "table": "sys_systemdaten",
                                    "candidates": [c for c in candidates if c],
                                }
                            )

                _walk(value, next_path)

        elif isinstance(node, list):
            for idx, item in enumerate(node):
                _walk(item, (*path, str(idx)))

    _walk(daten, tuple())
    return rewired_count, unresolved


async def _process_db(db_label: str, cfg: ConnectionConfig, apply: bool, strict_refs: bool) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "db_label": db_label,
        "database": cfg.database,
        "skipped": False,
        "skip_reason": None,
        "dropdown_records_planned": 0,
        "dropdown_records_inserted": 0,
        "dropdown_records_updated": 0,
        "system_rows_touched": 0,
        "hard_ref_errors": 0,
        "hard_ref_findings": [],
        "details": [],
        "error": None,
    }

    try:
        conn = await asyncpg.connect(**cfg.to_dict())
    except Exception as exc:
        out["error"] = f"connect_failed: {exc}"
        return out

    try:
        metas = await _get_table_meta(conn)
        sys_meta = metas.get("sys_systemdaten")
        dd_meta = metas.get("sys_dropdowndaten")
        if not sys_meta or not dd_meta:
            out["skipped"] = True
            out["skip_reason"] = "sys_systemdaten oder sys_dropdowndaten fehlt"
            return out
        if not (sys_meta.has_uid and sys_meta.has_daten and dd_meta.has_uid and dd_meta.has_daten):
            out["skipped"] = True
            out["skip_reason"] = "uid/daten Spalten fehlen in sys_systemdaten oder sys_dropdowndaten"
            return out

        rows = await _load_active_rows(conn, "sys_systemdaten", sys_meta.has_historisch)

        planned_dropdown_rows: List[Tuple[str, str, Dict[str, Any]]] = []
        planned_system_updates: List[Tuple[str, str, Dict[str, Any]]] = []
        planned_system_data_by_uid: Dict[str, Dict[str, Any]] = {}

        for row in rows:
            by_field, mutated_data, stats = _extract_dropdowns_from_system_row(row)
            if not by_field:
                continue

            source_uid = str(row.get("uid") or "")
            source_name = str(row.get("name") or "")
            default_lang = stats.get("default_language") or DEFAULT_LANG

            field_to_uid: Dict[str, str] = {}

            for field_key, lang_items in sorted(by_field.items(), key=lambda kv: kv[0]):
                rec_uid, rec_name, payload = _build_dropdown_dataset(
                    db_label=db_label,
                    source_uid=source_uid,
                    field_key=field_key,
                    source_name=source_name,
                    default_lang=str(default_lang),
                    lang_items=lang_items,
                )
                field_to_uid[field_key] = rec_uid
                planned_dropdown_rows.append((rec_uid, rec_name, payload))

            rewired_count, unresolved = _rewrite_dropdown_refs_in_source(
                mutated_data,
                source_uid=source_uid,
                field_to_uid=field_to_uid,
            )

            planned_system_updates.append((source_uid, source_name, mutated_data))
            planned_system_data_by_uid[source_uid] = mutated_data
            out["details"].append(
                {
                    "source_uid": source_uid,
                    "source_name": source_name,
                    "fields": sorted(by_field.keys()),
                    "migrated_count": int(stats.get("migrated_count", 0)),
                    "rewired_refs": rewired_count,
                    "unresolved_refs": unresolved,
                }
            )

        out["dropdown_records_planned"] = len(planned_dropdown_rows)
        out["system_rows_touched"] = len(planned_system_updates)

        # Harte Referenzprüfung: verbleibende sys_systemdaten-Verweise sind ein Fehler.
        ref_hits: List[Dict[str, Any]] = []
        for table_name, meta in metas.items():
            if not (meta.has_uid and meta.has_daten):
                continue
            table_rows = await _load_active_rows(conn, table_name, meta.has_historisch)
            for table_row in table_rows:
                hits: List[Dict[str, Any]] = []
                row_uid = str(table_row.get("uid") or "")
                effective_data = _as_dict(table_row.get("daten"))
                if table_name == "sys_systemdaten" and row_uid in planned_system_data_by_uid:
                    effective_data = planned_system_data_by_uid[row_uid]

                _deep_walk_find_refs(effective_data, (table_name, row_uid, "daten"), hits)
                for hit in hits:
                    ref_hits.append(
                        {
                            "table": table_name,
                            "uid": row_uid,
                            "path": hit.get("path"),
                            "context": hit.get("context"),
                        }
                    )

        out["hard_ref_findings"] = ref_hits
        out["hard_ref_errors"] = len(ref_hits)

        if apply and strict_refs and ref_hits:
            out["error"] = f"hard_reference_check_failed: {len(ref_hits)} sys_systemdaten references detected"
            return out

        if apply:
            for rec_uid, rec_name, payload in planned_dropdown_rows:
                action = await _upsert_row(conn, dd_meta, row_uid=rec_uid, row_name=rec_name, daten=payload)
                if action == "inserted":
                    out["dropdown_records_inserted"] += 1
                elif action == "updated":
                    out["dropdown_records_updated"] += 1

            for src_uid, src_name, src_payload in planned_system_updates:
                await _upsert_row(conn, sys_meta, row_uid=src_uid, row_name=src_name, daten=src_payload)

    except Exception as exc:
        out["error"] = f"process_failed: {exc}"
    finally:
        await conn.close()

    return out


async def build_report(*, apply: bool, strict_refs: bool) -> Dict[str, Any]:
    db_targets: List[Tuple[str, ConnectionConfig]] = []

    system_cfg = await ConnectionManager.get_system_config()
    auth_cfg = await ConnectionManager.get_auth_config()
    db_targets.append(("system", system_cfg))
    db_targets.append(("auth", auth_cfg))

    main_cfg, main_info = await _resolve_main_mandant_config()
    if main_cfg:
        db_targets.append(("main_mandant", main_cfg))

    report: Dict[str, Any] = {
        "phase": "phaseB",
        "title": "Migrate sys_systemdaten dropdown containers to sys_dropdowndaten",
        "mode": "apply" if apply else "dry-run",
        "strict_references": strict_refs,
        "main_mandant": main_info,
        "databases": [],
        "summary": {
            "db_count": 0,
            "db_skipped": 0,
            "db_errors": 0,
            "dropdown_records_planned": 0,
            "dropdown_records_inserted": 0,
            "dropdown_records_updated": 0,
            "system_rows_touched": 0,
            "hard_ref_errors": 0,
        },
    }

    for db_label, cfg in db_targets:
        entry = await _process_db(db_label, cfg, apply=apply, strict_refs=strict_refs)
        report["databases"].append(entry)
        report["summary"]["db_count"] += 1
        report["summary"]["dropdown_records_planned"] += int(entry.get("dropdown_records_planned", 0))
        report["summary"]["dropdown_records_inserted"] += int(entry.get("dropdown_records_inserted", 0))
        report["summary"]["dropdown_records_updated"] += int(entry.get("dropdown_records_updated", 0))
        report["summary"]["system_rows_touched"] += int(entry.get("system_rows_touched", 0))
        report["summary"]["hard_ref_errors"] += int(entry.get("hard_ref_errors", 0))
        if entry.get("skipped"):
            report["summary"]["db_skipped"] += 1
        if entry.get("error"):
            report["summary"]["db_errors"] += 1

    return report


def _default_output_path() -> Path:
    return BACKEND_DIR / "reports" / "phaseB_migrate_sys_systemdaten_dropdowns_report.json"


def _print_summary(report: Dict[str, Any]) -> None:
    s = report.get("summary", {})
    print("\n=== Phase B.2 sys_systemdaten -> sys_dropdowndaten ===")
    print(f"Mode: {report.get('mode')}")
    print(f"DB count: {s.get('db_count', 0)}")
    print(f"DB skipped: {s.get('db_skipped', 0)}")
    print(f"DB errors: {s.get('db_errors', 0)}")
    print(f"Planned dropdown rows: {s.get('dropdown_records_planned', 0)}")
    print(f"Inserted dropdown rows: {s.get('dropdown_records_inserted', 0)}")
    print(f"Updated dropdown rows: {s.get('dropdown_records_updated', 0)}")
    print(f"System rows touched: {s.get('system_rows_touched', 0)}")
    print(f"Hard reference findings: {s.get('hard_ref_errors', 0)}")


async def _run(args: argparse.Namespace) -> int:
    report = await build_report(apply=bool(args.apply), strict_refs=bool(args.strict_refs))
    _print_summary(report)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nReport geschrieben: {output_path}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase B.2 migrate sys_systemdaten dropdowns to sys_dropdowndaten")
    parser.add_argument("--apply", action="store_true", help="Änderungen schreiben")
    parser.add_argument("--strict-refs", action="store_true", default=True, help="Harte Fehler bei verbleibenden sys_systemdaten Referenzen")
    parser.add_argument("--output", default=str(_default_output_path()), help="Pfad für JSON-Report")
    args = parser.parse_args()
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())

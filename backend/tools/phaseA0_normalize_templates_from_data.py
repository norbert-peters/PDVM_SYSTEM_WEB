"""
Phase A.0: 555/666 Normalisierung aus vorhandenen Datensaetzen.

Regelbild:
- 555: ROOT + leere Gruppen (je Tabelle)
- 666: ROOT + TEMPLATES (je Gruppe aus realen Datensaetzen)
- ROOT-Struktur 555 und 666 identisch (abgesehen von SELF_GUID/SELF_NAME Werten)

Scope:
- System-DB
- Auth-DB
- Hauptmandant-DB

Usage:
  python backend/tools/phaseA0_normalize_templates_from_data.py
  python backend/tools/phaseA0_normalize_templates_from_data.py --apply
  python backend/tools/phaseA0_normalize_templates_from_data.py --output backend/reports/phaseA0_normalize_templates_from_data.json
"""

from __future__ import annotations

import argparse
import asyncio
import copy
import json
import re
import sys
import uuid
from collections import Counter
from dataclasses import dataclass, field
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

EXPLICIT_EXCLUDED = {
    "dev_workflow_draft",
    "dev_workflow_draft_item",
}

EXPLICIT_PARTIAL = {
    "asy_benutzer",
}

INFOS_TABLES = {
    "sys_dropdowndaten",
    "sys_beschreibungen",
    "sys_systemdaten",
}

LANG_TEMPLATE_GROUP = "LANG_CONTENT"


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


def _parse_uid(uid_value: str) -> uuid.UUID:
    return uuid.UUID(str(uid_value))


def _table_mode(table_name: str, has_uid: bool, has_daten: bool, columns: Sequence[str]) -> str:
    if not (has_uid and has_daten):
        return "nicht_im_scope"

    cols = {str(c).lower() for c in columns}
    if {"benutzer", "passwort"}.issubset(cols):
        return "teiltemplatefaehig"

    if table_name in EXPLICIT_EXCLUDED:
        return "ausgenommen"

    if table_name in EXPLICIT_PARTIAL:
        return "teiltemplatefaehig"

    if "historie" in table_name or "history" in table_name or "audit" in table_name or table_name.startswith("log_"):
        return "ausgenommen"

    return "voll_templatefaehig"


def _to_hashable_scalar(value: Any) -> Optional[str]:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return None


def _is_language_group_key(value: str) -> bool:
    s = str(value or "").strip()
    if not s:
        return False
    if re.fullmatch(r"[A-Za-z]{2}[-_][A-Za-z]{2}", s):
        return True
    if re.fullmatch(r"[A-Za-z]{4}", s):
        return True
    return False


def _merge_template_value(current: Any, incoming: Any) -> Any:
    if current is None:
        return copy.deepcopy(incoming)

    if isinstance(current, dict) and isinstance(incoming, dict):
        out = copy.deepcopy(current)
        for key, value in incoming.items():
            if key not in out:
                out[key] = copy.deepcopy(value)
            else:
                out[key] = _merge_template_value(out[key], value)
        return out

    # linear/pragmatic: keep first concrete value
    return current


async def _get_table_meta(conn: asyncpg.Connection) -> List[TableMeta]:
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

    return [TableMeta(table_name=t, columns=cols) for t, cols in sorted(by_table.items(), key=lambda kv: kv[0])]


async def _fetch_template_row(conn: asyncpg.Connection, meta: TableMeta, uid_value: str) -> Optional[Dict[str, Any]]:
    where_hist = "AND COALESCE(historisch, 0) = 0" if meta.has_historisch else ""
    row = await conn.fetchrow(
        f'''
        SELECT uid::text AS uid, name, daten
        FROM "{meta.table_name}"
        WHERE uid::text = $1
        {where_hist}
        LIMIT 1
        ''',
        uid_value,
    )
    return dict(row) if row else None


async def _fetch_active_rows(conn: asyncpg.Connection, meta: TableMeta) -> List[Dict[str, Any]]:
    where_hist = "WHERE COALESCE(historisch, 0) = 0" if meta.has_historisch else ""
    rows = await conn.fetch(
        f'''
        SELECT uid::text AS uid, name, daten
        FROM "{meta.table_name}"
        {where_hist}
        '''
    )
    out: List[Dict[str, Any]] = []
    for row in rows:
        uid = str(row.get("uid") or "")
        if uid in {UID_555, UID_666}:
            continue
        out.append(
            {
                "uid": uid,
                "name": str(row.get("name") or ""),
                "daten": _as_dict(row.get("daten")),
            }
        )
    return out


async def _required_columns_without_default(conn: asyncpg.Connection, table_name: str) -> List[str]:
    rows = await conn.fetch(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = $1
          AND is_nullable = 'NO'
          AND COALESCE(column_default, '') = ''
          AND COALESCE(identity_generation, '') = ''
          AND COALESCE(is_generated, 'NEVER') = 'NEVER'
        ORDER BY ordinal_position
        """,
        table_name,
    )
    return [str(r.get("column_name")) for r in rows]


def _build_normalized_templates(
    table_name: str,
    rows: List[Dict[str, Any]],
    existing_555: Dict[str, Any],
    existing_666: Dict[str, Any],
) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    root_555 = _as_dict(existing_555.get("ROOT"))
    root_666 = _as_dict(existing_666.get("ROOT"))

    root_key_counter: Counter[str] = Counter()
    root_value_counter: Dict[str, Counter[str]] = {}
    group_templates: Dict[str, Any] = {}
    lang_templates: Dict[str, Any] = {}

    for row in rows:
        daten = _as_dict(row.get("daten"))
        root = _as_dict(daten.get("ROOT"))

        for k, v in root.items():
            root_key_counter[str(k)] += 1
            hv = _to_hashable_scalar(v)
            if hv is not None:
                root_value_counter.setdefault(str(k), Counter())[hv] += 1

        for top_key, top_value in daten.items():
            if top_key in {"ROOT", "TEMPLATES"}:
                continue

            if table_name in INFOS_TABLES and _is_language_group_key(str(top_key)):
                lang_templates[str(top_key)] = _merge_template_value(lang_templates.get(str(top_key)), top_value)
                continue

            if top_key not in group_templates:
                group_templates[top_key] = None
            group_templates[top_key] = _merge_template_value(group_templates[top_key], top_value)

    if lang_templates:
        group_templates[LANG_TEMPLATE_GROUP] = _merge_template_value(group_templates.get(LANG_TEMPLATE_GROUP), lang_templates)

    base_root_keys: List[str] = []
    for k in [*root_555.keys(), *root_666.keys(), *root_key_counter.keys()]:
        ks = str(k)
        if ks not in base_root_keys:
            base_root_keys.append(ks)

    for required in ("SELF_GUID", "SELF_NAME", "TABLE"):
        if required not in base_root_keys:
            base_root_keys.append(required)

    # keep only keys that are either mandatory or seen in data/templates
    final_root: Dict[str, Any] = {}
    for key in base_root_keys:
        if key == "SELF_GUID":
            final_root[key] = None
            continue
        if key == "SELF_NAME":
            final_root[key] = None
            continue
        if key == "TABLE":
            final_root[key] = table_name
            continue

        if key in root_555:
            final_root[key] = root_555.get(key)
            continue
        if key in root_666:
            final_root[key] = root_666.get(key)
            continue

        if key in root_value_counter and root_value_counter[key]:
            best = root_value_counter[key].most_common(1)[0][0]
            final_root[key] = json.loads(best)
        else:
            final_root[key] = None

    normalized_555: Dict[str, Any] = {
        "ROOT": {
            **final_root,
            "SELF_GUID": UID_555,
            "SELF_NAME": "TEMPLATE_555",
            "TABLE": table_name,
        }
    }

    for g in sorted(group_templates.keys()):
        normalized_555[g] = {}

    normalized_666: Dict[str, Any] = {
        "ROOT": {
            **final_root,
            "SELF_GUID": UID_666,
            "SELF_NAME": "TEMPLATE_666",
            "TABLE": table_name,
        },
        "TEMPLATES": {},
    }

    for g in sorted(group_templates.keys()):
        value = group_templates[g]
        if value is None:
            value = {}
        normalized_666["TEMPLATES"][g] = value

    diagnostics = {
        "source_row_count": len(rows),
        "group_count": len(group_templates),
        "root_keys": sorted(final_root.keys()),
        "groups": sorted(group_templates.keys()),
        "language_groups_folded": sorted(lang_templates.keys()),
    }

    return normalized_555, normalized_666, diagnostics


async def _insert_template_row(conn: asyncpg.Connection, meta: TableMeta, uid_value: str, name_value: str, payload: Dict[str, Any]) -> None:
    cols: List[str] = ["uid", "daten"]
    vals: List[Any] = [_parse_uid(uid_value), json.dumps(payload, ensure_ascii=False)]
    if meta.has_name:
        cols.append("name")
        vals.append(name_value)
    if meta.has_historisch:
        cols.append("historisch")
        vals.append(0)

    placeholders = [f"${i+1}" for i in range(len(cols))]
    col_sql = ", ".join(f'"{c}"' for c in cols)
    val_sql = ", ".join(placeholders)
    await conn.execute(f'INSERT INTO "{meta.table_name}" ({col_sql}) VALUES ({val_sql})', *vals)


async def _update_template_row(conn: asyncpg.Connection, meta: TableMeta, uid_value: str, payload: Dict[str, Any]) -> None:
    await conn.execute(
        f'UPDATE "{meta.table_name}" SET daten = $1::jsonb WHERE uid::text = $2',
        json.dumps(payload, ensure_ascii=False),
        uid_value,
    )


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

        candidates = sorted(candidates, key=lambda x: (x.get("name") or "").lower())
        chosen = candidates[0]
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


async def _process_db(db_label: str, cfg: ConnectionConfig, apply: bool) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "db_label": db_label,
        "database": cfg.database,
        "summary": {
            "tables_total": 0,
            "tables_considered": 0,
            "tables_normalized": 0,
            "rows_inserted": 0,
            "rows_updated": 0,
            "rows_skipped_blocked": 0,
        },
        "tables": [],
        "error": None,
    }

    try:
        conn = await asyncpg.connect(**cfg.to_dict())
    except Exception as exc:
        out["error"] = f"connect_failed: {exc}"
        return out

    try:
        metas = await _get_table_meta(conn)
        out["summary"]["tables_total"] = len(metas)

        for meta in metas:
            mode = _table_mode(meta.table_name, meta.has_uid, meta.has_daten, meta.columns)
            table_entry: Dict[str, Any] = {
                "table": meta.table_name,
                "mode": mode,
                "action": "skip",
                "notes": [],
                "diagnostics": {},
            }

            if not (meta.has_uid and meta.has_daten):
                table_entry["notes"].append("not_in_scope_uid_daten_missing")
                out["tables"].append(table_entry)
                continue

            out["summary"]["tables_considered"] += 1

            if mode == "ausgenommen":
                table_entry["notes"].append("mode_ausgenommen")
                out["tables"].append(table_entry)
                continue

            rows = await _fetch_active_rows(conn, meta)
            row_555 = await _fetch_template_row(conn, meta, UID_555)
            row_666 = await _fetch_template_row(conn, meta, UID_666)
            data_555 = _as_dict(row_555.get("daten")) if row_555 else {}
            data_666 = _as_dict(row_666.get("daten")) if row_666 else {}

            normalized_555, normalized_666, diagnostics = _build_normalized_templates(
                meta.table_name,
                rows,
                data_555,
                data_666,
            )
            table_entry["diagnostics"] = diagnostics

            required_no_default = await _required_columns_without_default(conn, meta.table_name)
            insert_cols = {"uid", "daten"}
            if meta.has_name:
                insert_cols.add("name")
            if meta.has_historisch:
                insert_cols.add("historisch")
            blocking_cols = [c for c in required_no_default if c not in insert_cols]

            if blocking_cols:
                table_entry["notes"].append(f"insert_blocking_columns={blocking_cols}")

            changed = False

            if row_555:
                if data_555 != normalized_555:
                    changed = True
                    if apply:
                        await _update_template_row(conn, meta, UID_555, normalized_555)
                        out["summary"]["rows_updated"] += 1
            else:
                if blocking_cols:
                    out["summary"]["rows_skipped_blocked"] += 1
                    table_entry["notes"].append("skip_create_555_blocked")
                elif mode == "teiltemplatefaehig":
                    table_entry["notes"].append("skip_create_555_partial")
                else:
                    changed = True
                    if apply:
                        await _insert_template_row(conn, meta, UID_555, "TEMPLATE_555", normalized_555)
                        out["summary"]["rows_inserted"] += 1

            if row_666:
                if data_666 != normalized_666:
                    changed = True
                    if apply:
                        await _update_template_row(conn, meta, UID_666, normalized_666)
                        out["summary"]["rows_updated"] += 1
            else:
                if blocking_cols:
                    out["summary"]["rows_skipped_blocked"] += 1
                    table_entry["notes"].append("skip_create_666_blocked")
                elif mode == "teiltemplatefaehig":
                    table_entry["notes"].append("skip_create_666_partial")
                else:
                    changed = True
                    if apply:
                        await _insert_template_row(conn, meta, UID_666, "TEMPLATE_666", normalized_666)
                        out["summary"]["rows_inserted"] += 1

            table_entry["action"] = "normalized" if changed else "already_normal"
            if changed:
                out["summary"]["tables_normalized"] += 1

            out["tables"].append(table_entry)

    except Exception as exc:
        out["error"] = f"process_failed: {exc}"
    finally:
        await conn.close()

    return out


async def build_report(apply: bool) -> Dict[str, Any]:
    system_cfg = await ConnectionManager.get_system_config()
    auth_cfg = await ConnectionManager.get_auth_config()
    mandant_cfg, mandant_info = await _resolve_main_mandant_config()

    targets: List[Tuple[str, ConnectionConfig]] = [
        ("system", system_cfg),
        ("auth", auth_cfg),
    ]
    if mandant_cfg:
        targets.append(("mandant_main", mandant_cfg))

    report: Dict[str, Any] = {
        "phase": "phaseA0_normalize_templates_from_data",
        "apply": bool(apply),
        "main_mandant": mandant_info,
        "databases": [],
        "summary": {
            "db_count": 0,
            "db_errors": 0,
            "tables_total": 0,
            "tables_considered": 0,
            "tables_normalized": 0,
            "rows_inserted": 0,
            "rows_updated": 0,
            "rows_skipped_blocked": 0,
        },
    }

    for db_label, cfg in targets:
        entry = await _process_db(db_label, cfg, apply=apply)
        report["databases"].append(entry)

    report["summary"]["db_count"] = len(report["databases"])

    for db in report["databases"]:
        if db.get("error"):
            report["summary"]["db_errors"] += 1
        s = db.get("summary", {})
        report["summary"]["tables_total"] += int(s.get("tables_total", 0))
        report["summary"]["tables_considered"] += int(s.get("tables_considered", 0))
        report["summary"]["tables_normalized"] += int(s.get("tables_normalized", 0))
        report["summary"]["rows_inserted"] += int(s.get("rows_inserted", 0))
        report["summary"]["rows_updated"] += int(s.get("rows_updated", 0))
        report["summary"]["rows_skipped_blocked"] += int(s.get("rows_skipped_blocked", 0))

    return report


def _default_output_path() -> Path:
    return BACKEND_DIR / "reports" / "phaseA0_normalize_templates_from_data_report.json"


def _print_summary(report: Dict[str, Any]) -> None:
    s = report.get("summary", {})
    print("\n=== Phase A.0 Normalize Templates ===")
    print(f"DBs: {s.get('db_count', 0)}")
    print(f"DB errors: {s.get('db_errors', 0)}")
    print(f"Tables total/considered/normalized: {s.get('tables_total', 0)}/{s.get('tables_considered', 0)}/{s.get('tables_normalized', 0)}")
    print(f"Rows inserted/updated/skipped_blocked: {s.get('rows_inserted', 0)}/{s.get('rows_updated', 0)}/{s.get('rows_skipped_blocked', 0)}")


async def _run(output_path: Path, apply: bool) -> int:
    report = await build_report(apply=apply)
    _print_summary(report)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nReport geschrieben: {output_path}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase A.0 normalize 555/666 from data")
    parser.add_argument("--apply", action="store_true", help="Schreibt normalisierte 555/666 in die Tabellen")
    parser.add_argument(
        "--output",
        default=str(_default_output_path()),
        help="Pfad fuer JSON-Report",
    )
    args = parser.parse_args()

    return asyncio.run(_run(Path(args.output), apply=bool(args.apply)))


if __name__ == "__main__":
    raise SystemExit(main())

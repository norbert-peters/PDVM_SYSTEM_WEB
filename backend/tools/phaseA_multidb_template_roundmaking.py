"""
Phase A Multi-DB: Tabellenklassifizierung + 555/666 Template-Roundmaking

Scope:
- System-DB
- Auth-DB
- Hauptmandant-DB (ein Mandant)

Funktionen:
1. Alle Tabellen klassifizieren (voll/teil/ausgenommen/nicht-im-scope).
2. 555/666 Health-Analyse pro Tabelle (wenn uid+daten vorhanden).
3. Optionales Roundmaking (555/666 anlegen/angleichen).

Usage:
  python backend/tools/phaseA_multidb_template_roundmaking.py
  python backend/tools/phaseA_multidb_template_roundmaking.py --apply
  python backend/tools/phaseA_multidb_template_roundmaking.py --output backend/reports/phaseA_multidb_template_roundmaking_report.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
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
SYSTEM_MANDANT_UIDS = {
    UID_555,
    UID_666,
    "00000000-0000-0000-0000-000000000000",
}

EXPLICIT_EXCLUDED = {
    "dev_workflow_draft",
    "dev_workflow_draft_item",
}

EXPLICIT_PARTIAL = {
    "asy_benutzer",
}


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


def _default_root(table_name: str, uid_value: str, self_name: str) -> Dict[str, Any]:
    return {
        "SELF_GUID": uid_value,
        "SELF_NAME": self_name,
        "TABLE": table_name,
    }


def _ensure_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _normalize_group_payload(payload: Any) -> Dict[str, Any]:
    if isinstance(payload, dict):
        return payload
    return {}


def _build_555_data(table_name: str, existing_555: Dict[str, Any], existing_666: Dict[str, Any]) -> Dict[str, Any]:
    root_555 = _as_dict(existing_555.get("ROOT"))
    root_666 = _as_dict(existing_666.get("ROOT"))

    root_keys: List[str] = []
    for key in list(root_555.keys()) + list(root_666.keys()):
        if key not in root_keys:
            root_keys.append(key)

    if not root_keys:
        root_keys = ["SELF_GUID", "SELF_NAME", "TABLE"]

    root_out: Dict[str, Any] = {}
    for key in root_keys:
        if key == "SELF_GUID":
            root_out[key] = UID_555
        elif key == "SELF_NAME":
            root_out[key] = "TEMPLATE_555"
        elif key == "TABLE":
            root_out[key] = table_name
        elif key in root_555:
            root_out[key] = root_555.get(key)
        elif key in root_666:
            root_out[key] = root_666.get(key)
        else:
            root_out[key] = None

    out: Dict[str, Any] = {"ROOT": root_out}

    for key, value in existing_555.items():
        if key in {"ROOT", "TEMPLATES"}:
            continue
        out[key] = _normalize_group_payload(value)

    return out


def _build_666_data(table_name: str, normalized_555: Dict[str, Any], existing_666: Dict[str, Any]) -> Dict[str, Any]:
    root_555 = _as_dict(normalized_555.get("ROOT"))
    root_666 = _as_dict(existing_666.get("ROOT"))

    root_out: Dict[str, Any] = {}
    for key in root_555.keys():
        if key == "SELF_GUID":
            root_out[key] = UID_666
        elif key == "SELF_NAME":
            root_out[key] = "TEMPLATE_666"
        elif key == "TABLE":
            root_out[key] = table_name
        elif key in root_666:
            root_out[key] = root_666.get(key)
        else:
            root_out[key] = root_555.get(key)

    templates = _as_dict(existing_666.get("TEMPLATES"))
    for group_key in normalized_555.keys():
        if group_key == "ROOT":
            continue
        if group_key not in templates or not isinstance(templates.get(group_key), dict):
            templates[group_key] = {}

    out: Dict[str, Any] = dict(existing_666)
    out["ROOT"] = root_out
    out["TEMPLATES"] = templates

    return out


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


async def _insert_template_row(
    conn: asyncpg.Connection,
    meta: TableMeta,
    uid_value: str,
    name_value: str,
    daten_value: Dict[str, Any],
) -> None:
    cols: List[str] = ["uid", "daten"]
    vals: List[Any] = [_parse_uid(uid_value), json.dumps(daten_value, ensure_ascii=False)]

    if meta.has_name:
        cols.append("name")
        vals.append(name_value)
    if meta.has_historisch:
        cols.append("historisch")
        vals.append(0)

    placeholders = [f"${i+1}" for i in range(len(cols))]
    col_sql = ", ".join(f'"{c}"' for c in cols)
    val_sql = ", ".join(placeholders)

    await conn.execute(
        f'INSERT INTO "{meta.table_name}" ({col_sql}) VALUES ({val_sql})',
        *vals,
    )


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


async def _update_template_row(conn: asyncpg.Connection, meta: TableMeta, uid_value: str, daten_value: Dict[str, Any]) -> None:
    await conn.execute(
        f'UPDATE "{meta.table_name}" SET daten = $1::jsonb WHERE uid::text = $2',
        json.dumps(daten_value, ensure_ascii=False),
        uid_value,
    )


def _health_errors(data_555: Dict[str, Any], data_666: Dict[str, Any]) -> List[str]:
    errors: List[str] = []

    root_555 = _as_dict(data_555.get("ROOT"))
    root_666 = _as_dict(data_666.get("ROOT"))
    has_templates_key = "TEMPLATES" in data_666
    templates_raw = data_666.get("TEMPLATES")
    templates_is_dict = isinstance(templates_raw, dict)

    if not root_555:
        errors.append("555.ROOT fehlt oder ist kein Objekt")
    if not root_666:
        errors.append("666.ROOT fehlt oder ist kein Objekt")
    if not has_templates_key or not templates_is_dict:
        errors.append("666.TEMPLATES fehlt oder ist kein Objekt")

    if root_555 and root_666:
        keys_555 = set(root_555.keys())
        keys_666 = set(root_666.keys())
        if keys_555 != keys_666:
            only_555 = sorted(keys_555 - keys_666)
            only_666 = sorted(keys_666 - keys_555)
            errors.append(f"ROOT-Struktur ungleich (nur in 555: {only_555}, nur in 666: {only_666})")

    return errors


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


async def _process_db(
    db_label: str,
    cfg: ConnectionConfig,
    apply: bool,
) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "db_label": db_label,
        "database": cfg.database,
        "host": cfg.host,
        "port": cfg.port,
        "tables": [],
        "summary": {
            "tables_total": 0,
            "tables_scope_uid_daten": 0,
            "mode_voll": 0,
            "mode_teil": 0,
            "mode_ausgenommen": 0,
            "mode_nicht_im_scope": 0,
            "health_error_count": 0,
            "roundmaking_actions": 0,
        },
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
            if mode == "voll_templatefaehig":
                out["summary"]["mode_voll"] += 1
            elif mode == "teiltemplatefaehig":
                out["summary"]["mode_teil"] += 1
            elif mode == "ausgenommen":
                out["summary"]["mode_ausgenommen"] += 1
            else:
                out["summary"]["mode_nicht_im_scope"] += 1

            table_entry: Dict[str, Any] = {
                "table": meta.table_name,
                "columns": meta.columns,
                "mode": mode,
                "has_uid": meta.has_uid,
                "has_daten": meta.has_daten,
                "has_name": meta.has_name,
                "has_historisch": meta.has_historisch,
                "has_555": False,
                "has_666": False,
                "health_errors": [],
                "roundmaking": [],
            }

            try:
                if not (meta.has_uid and meta.has_daten):
                    out["tables"].append(table_entry)
                    continue

                out["summary"]["tables_scope_uid_daten"] += 1

                row_555 = await _fetch_template_row(conn, meta, UID_555)
                row_666 = await _fetch_template_row(conn, meta, UID_666)

                data_555_raw = _as_dict(row_555.get("daten")) if row_555 else {}
                data_666_raw = _as_dict(row_666.get("daten")) if row_666 else {}

                table_entry["has_555"] = row_555 is not None
                table_entry["has_666"] = row_666 is not None

                normalized_555 = _build_555_data(meta.table_name, data_555_raw, data_666_raw)
                normalized_666 = _build_666_data(meta.table_name, normalized_555, data_666_raw)

                create_blocking_columns: List[str] = []
                required_no_default = await _required_columns_without_default(conn, meta.table_name)
                insert_cols = {"uid", "daten"}
                if meta.has_name:
                    insert_cols.add("name")
                if meta.has_historisch:
                    insert_cols.add("historisch")
                create_blocking_columns = [c for c in required_no_default if c not in insert_cols]
                can_create_templates = len(create_blocking_columns) == 0

                if not can_create_templates:
                    table_entry["roundmaking"].append(
                        f"create_blocked_non_nullable_columns:{create_blocking_columns}"
                    )

                is_partial_mode = mode == "teiltemplatefaehig"

                if mode != "ausgenommen":
                    if is_partial_mode and (not row_555 or not row_666):
                        table_entry["roundmaking"].append("skip_partial_create")
                    elif not can_create_templates and (not row_555 or not row_666):
                        table_entry["roundmaking"].append("skip_writes_blocked")
                    else:
                        if not row_555:
                            if can_create_templates:
                                table_entry["roundmaking"].append("create_555")
                                if apply:
                                    await _insert_template_row(conn, meta, UID_555, "TEMPLATE_555", normalized_555)
                            else:
                                table_entry["roundmaking"].append("skip_create_555")
                        else:
                            if data_555_raw != normalized_555:
                                table_entry["roundmaking"].append("update_555")
                                if apply:
                                    await _update_template_row(conn, meta, UID_555, normalized_555)

                        if not row_666:
                            if can_create_templates:
                                table_entry["roundmaking"].append("create_666")
                                if apply:
                                    await _insert_template_row(conn, meta, UID_666, "TEMPLATE_666", normalized_666)
                            else:
                                table_entry["roundmaking"].append("skip_create_666")
                        else:
                            if data_666_raw != normalized_666:
                                table_entry["roundmaking"].append("update_666")
                                if apply:
                                    await _update_template_row(conn, meta, UID_666, normalized_666)
                else:
                    table_entry["roundmaking"].append("skip_ausgenommen")

                # Re-read for final health (after optional apply)
                row_555_after = await _fetch_template_row(conn, meta, UID_555)
                row_666_after = await _fetch_template_row(conn, meta, UID_666)
                data_555_after = _as_dict(row_555_after.get("daten")) if row_555_after else {}
                data_666_after = _as_dict(row_666_after.get("daten")) if row_666_after else {}

                errors = []
                if mode != "ausgenommen":
                    partial_missing_allowed = is_partial_mode and (not can_create_templates)
                    if not row_555_after and not partial_missing_allowed:
                        errors.append("Template 555 fehlt")
                    if not row_666_after and not partial_missing_allowed:
                        errors.append("Template 666 fehlt")
                    if row_555_after and row_666_after:
                        errors.extend(_health_errors(data_555_after, data_666_after))

                table_entry["has_555"] = row_555_after is not None
                table_entry["has_666"] = row_666_after is not None
                table_entry["health_errors"] = errors

                out["summary"]["health_error_count"] += len(errors)
                out["summary"]["roundmaking_actions"] += len([x for x in table_entry["roundmaking"] if x.startswith("create_") or x.startswith("update_")])
            except Exception as table_exc:
                table_entry["health_errors"].append(f"table_error: {table_exc}")
                out["summary"]["health_error_count"] += 1

            out["tables"].append(table_entry)
    except Exception as exc:
        out["error"] = f"analyze_failed: {exc}"
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
        "phase": "phaseA_multidb",
        "title": "Multi-DB Tabellenklassifizierung + Template-Roundmaking",
        "apply": bool(apply),
        "main_mandant": mandant_info,
        "databases": [],
        "summary": {
            "db_count": 0,
            "tables_total": 0,
            "tables_scope_uid_daten": 0,
            "mode_voll": 0,
            "mode_teil": 0,
            "mode_ausgenommen": 0,
            "mode_nicht_im_scope": 0,
            "health_error_count": 0,
            "roundmaking_actions": 0,
            "db_errors": 0,
        },
    }

    for label, cfg in targets:
        entry = await _process_db(label, cfg, apply=apply)
        report["databases"].append(entry)

    report["summary"]["db_count"] = len(report["databases"])

    for db_entry in report["databases"]:
        if db_entry.get("error"):
            report["summary"]["db_errors"] += 1
            continue

        s = db_entry.get("summary", {})
        report["summary"]["tables_total"] += int(s.get("tables_total", 0))
        report["summary"]["tables_scope_uid_daten"] += int(s.get("tables_scope_uid_daten", 0))
        report["summary"]["mode_voll"] += int(s.get("mode_voll", 0))
        report["summary"]["mode_teil"] += int(s.get("mode_teil", 0))
        report["summary"]["mode_ausgenommen"] += int(s.get("mode_ausgenommen", 0))
        report["summary"]["mode_nicht_im_scope"] += int(s.get("mode_nicht_im_scope", 0))
        report["summary"]["health_error_count"] += int(s.get("health_error_count", 0))
        report["summary"]["roundmaking_actions"] += int(s.get("roundmaking_actions", 0))

    return report


def _default_output_path() -> Path:
    return BACKEND_DIR / "reports" / "phaseA_multidb_template_roundmaking_report.json"


def _print_summary(report: Dict[str, Any]) -> None:
    s = report.get("summary", {})
    print("\n=== Phase A Multi-DB ===")
    print(f"DBs: {s.get('db_count', 0)}")
    print(f"Tabellen gesamt: {s.get('tables_total', 0)}")
    print(f"Tabellen im Scope (uid+daten): {s.get('tables_scope_uid_daten', 0)}")
    print(f"Mode voll/teil/ausgenommen/nicht-im-scope: {s.get('mode_voll', 0)}/{s.get('mode_teil', 0)}/{s.get('mode_ausgenommen', 0)}/{s.get('mode_nicht_im_scope', 0)}")
    print(f"Health-Errors: {s.get('health_error_count', 0)}")
    print(f"Roundmaking-Actions: {s.get('roundmaking_actions', 0)}")
    print(f"DB-Errors: {s.get('db_errors', 0)}")


async def _run(output_path: Path, apply: bool) -> int:
    report = await build_report(apply=apply)
    _print_summary(report)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nReport geschrieben: {output_path}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase A Multi-DB Template Roundmaking")
    parser.add_argument("--apply", action="store_true", help="Roundmaking schreiben (create/update 555/666)")
    parser.add_argument(
        "--output",
        default=str(_default_output_path()),
        help="Pfad fuer den JSON-Report",
    )
    args = parser.parse_args()

    return asyncio.run(_run(Path(args.output), apply=bool(args.apply)))


if __name__ == "__main__":
    raise SystemExit(main())

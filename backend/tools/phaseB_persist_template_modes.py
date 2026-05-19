"""
Phase B V1: Persistiert Tabellenklassifizierung in *systemdaten Tabellen.

Ziel:
- Pro Tabelle einen Metadata-Satz ablegen mit:
  - TEMPLATE_MODE
    - TABLE_TYPE
  - STRUCT_VERSION_TARGET

Scope:
- System-DB
- Auth-DB
- Hauptmandant-DB

Usage:
  python backend/tools/phaseB_persist_template_modes.py
  python backend/tools/phaseB_persist_template_modes.py --apply
  python backend/tools/phaseB_persist_template_modes.py --output backend/reports/phaseB_persist_template_modes_report.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
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

SYSTEM_MANDANT_UIDS = {
    "55555555-5555-5555-5555-555555555555",
    "66666666-6666-6666-6666-666666666666",
    "00000000-0000-0000-0000-000000000000",
}

EXPLICIT_EXCLUDED = {
    "dev_workflow_draft",
    "dev_workflow_draft_item",
}

EXPLICIT_PARTIAL = {
    "asy_benutzer",
}

STRUCT_VERSION_TARGET = 1
STRUCT_META_GROUP = "TEMPLATE_META"
SOURCE_TAG = "phaseB_persist_template_modes_v1"

# TabellenTyp Taxonomie V1
TABLE_TYPE_EXPLICIT: Dict[str, str] = {
    "sys_dropdowndaten": "infos_dropdown",
    "sys_beschreibungen": "infos_text",
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


def _table_type(table_name: str, mode: str) -> Tuple[str, str]:
    """Liefert (table_type, source) mit source=explicit|heuristic."""
    t = str(table_name or "").strip().lower()

    explicit = TABLE_TYPE_EXPLICIT.get(t)
    if explicit:
        return explicit, "explicit"

    if mode == "nicht_im_scope":
        return "technical", "heuristic"

    if any(k in t for k in ("historie", "history", "audit", "acknowledg")):
        return "audit_history", "heuristic"

    if any(k in t for k in ("dropdown",)):
        return "infos_dropdown", "heuristic"

    if any(k in t for k in ("beschreibung", "text", "tooltip", "help", "label", "menu")):
        return "infos_text", "heuristic"

    if any(k in t for k in ("workflow", "queue", "import", "job", "process")):
        return "process", "heuristic"

    if t.startswith("sys_"):
        return "config", "heuristic"

    if t.startswith("dev_"):
        return "process", "heuristic"

    if t.startswith(("msy_", "tst_", "asy_")):
        return "master_data", "heuristic"

    return "master_data", "heuristic"


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


async def _table_exists(conn: asyncpg.Connection, table_name: str) -> bool:
    exists = await conn.fetchval("SELECT to_regclass($1) IS NOT NULL", f"public.{table_name}")
    return bool(exists)


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


async def _resolve_main_mandant_config() -> Tuple[Optional[ConnectionConfig], Optional[Dict[str, Any]]]:
    auth_cfg = await ConnectionManager.get_auth_config()
    conn = await asyncpg.connect(**auth_cfg.to_dict())
    try:
        source_table: Optional[str] = None
        for table_name in ("asy_mandanten", "sys_mandanten"):
            if await _table_exists(conn, table_name):
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


def _build_meta_payload(
    *,
    db_label: str,
    target_table: str,
    mode: str,
    table_type: str,
    table_type_source: str,
    record_uid: str,
    record_name: str,
    meta_table: str,
) -> Dict[str, Any]:
    now_iso = datetime.now(timezone.utc).isoformat()
    return {
        "ROOT": {
            "SELF_GUID": record_uid,
            "SELF_NAME": record_name,
            "TABLE": meta_table,
        },
        STRUCT_META_GROUP: {
            "TARGET_TABLE": target_table,
            "TEMPLATE_MODE": mode,
            "TABLE_TYPE": table_type,
            "TABLE_TYPE_SOURCE": table_type_source,
            "STRUCT_VERSION_TARGET": STRUCT_VERSION_TARGET,
            "SOURCE_DB_LABEL": db_label,
            "UPDATED_AT_UTC": now_iso,
            "SOURCE": SOURCE_TAG,
        },
    }


async def _resolve_meta_table(conn: asyncpg.Connection) -> Optional[str]:
    for t in ("sys_systemdaten", "asy_systemdaten", "msy_systemdaten"):
        if await _table_exists(conn, t):
            return t
    return None


async def _find_existing_meta_row(conn: asyncpg.Connection, meta_table: str, record_uid: str, record_name: str) -> Optional[Dict[str, Any]]:
    row = await conn.fetchrow(
        f'''
        SELECT uid::text AS uid, name, daten
        FROM "{meta_table}"
        WHERE uid::text = $1
        LIMIT 1
        ''',
        record_uid,
    )
    if row:
        return dict(row)

    has_name = await conn.fetchval(
        """
        SELECT COUNT(*)
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = $1 AND column_name = 'name'
        """,
        meta_table,
    )
    if int(has_name or 0) > 0:
        row = await conn.fetchrow(
            f'''
            SELECT uid::text AS uid, name, daten
            FROM "{meta_table}"
            WHERE name = $1
            ORDER BY modified_at DESC NULLS LAST
            LIMIT 1
            ''',
            record_name,
        )
        if row:
            return dict(row)

    return None


async def _insert_meta_row(
    conn: asyncpg.Connection,
    *,
    meta_table: str,
    meta_meta: TableMeta,
    record_uid: str,
    record_name: str,
    payload: Dict[str, Any],
) -> None:
    cols: List[str] = ["uid", "daten"]
    vals: List[Any] = [_parse_uid(record_uid), json.dumps(payload, ensure_ascii=False)]

    if meta_meta.has_name:
        cols.append("name")
        vals.append(record_name)
    if meta_meta.has_historisch:
        cols.append("historisch")
        vals.append(0)

    placeholders = [f"${i+1}" for i in range(len(cols))]
    col_sql = ", ".join(f'"{c}"' for c in cols)
    val_sql = ", ".join(placeholders)

    await conn.execute(
        f'INSERT INTO "{meta_table}" ({col_sql}) VALUES ({val_sql})',
        *vals,
    )


async def _update_meta_row(conn: asyncpg.Connection, *, meta_table: str, where_uid: str, payload: Dict[str, Any], record_name: str, has_name: bool) -> None:
    if has_name:
        await conn.execute(
            f'UPDATE "{meta_table}" SET daten = $1::jsonb, name = $2 WHERE uid::text = $3',
            json.dumps(payload, ensure_ascii=False),
            record_name,
            where_uid,
        )
    else:
        await conn.execute(
            f'UPDATE "{meta_table}" SET daten = $1::jsonb WHERE uid::text = $2',
            json.dumps(payload, ensure_ascii=False),
            where_uid,
        )


async def _process_db(db_label: str, cfg: ConnectionConfig, apply: bool) -> Dict[str, Any]:
    entry: Dict[str, Any] = {
        "db_label": db_label,
        "database": cfg.database,
        "meta_table": None,
        "summary": {
            "tables_total": 0,
            "meta_rows_planned": 0,
            "meta_rows_inserted": 0,
            "meta_rows_updated": 0,
            "meta_rows_skipped_blocked": 0,
            "table_type_counts": {},
        },
        "tables": [],
        "error": None,
    }

    try:
        conn = await asyncpg.connect(**cfg.to_dict())
    except Exception as exc:
        entry["error"] = f"connect_failed: {exc}"
        return entry

    try:
        metas = await _get_table_meta(conn)
        entry["summary"]["tables_total"] = len(metas)

        meta_table = await _resolve_meta_table(conn)
        entry["meta_table"] = meta_table
        if not meta_table:
            entry["error"] = "no_systemdaten_table_found"
            return entry

        meta_meta = next((m for m in metas if m.table_name == meta_table), None)
        if not meta_meta:
            entry["error"] = f"meta_table_not_in_information_schema:{meta_table}"
            return entry

        required_no_default = await _required_columns_without_default(conn, meta_table)
        insert_cols = {"uid", "daten"}
        if meta_meta.has_name:
            insert_cols.add("name")
        if meta_meta.has_historisch:
            insert_cols.add("historisch")
        blocking_insert_cols = [c for c in required_no_default if c not in insert_cols]

        for t in metas:
            mode = _table_mode(t.table_name, t.has_uid, t.has_daten, t.columns)
            table_type, table_type_source = _table_type(t.table_name, mode)
            record_name = f"TEMPLATE_META::{t.table_name}"
            record_uid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{SOURCE_TAG}:{db_label}:{t.table_name}"))

            payload = _build_meta_payload(
                db_label=db_label,
                target_table=t.table_name,
                mode=mode,
                table_type=table_type,
                table_type_source=table_type_source,
                record_uid=record_uid,
                record_name=record_name,
                meta_table=meta_table,
            )

            table_entry = {
                "table": t.table_name,
                "mode": mode,
                "table_type": table_type,
                "table_type_source": table_type_source,
                "record_uid": record_uid,
                "record_name": record_name,
                "action": "none",
                "note": None,
            }

            entry["summary"]["meta_rows_planned"] += 1
            type_counts = entry["summary"].setdefault("table_type_counts", {})
            type_counts[table_type] = int(type_counts.get(table_type, 0)) + 1

            existing = await _find_existing_meta_row(conn, meta_table, record_uid, record_name)

            if existing:
                table_entry["action"] = "update"
                if apply:
                    await _update_meta_row(
                        conn,
                        meta_table=meta_table,
                        where_uid=str(existing.get("uid") or record_uid),
                        payload=payload,
                        record_name=record_name,
                        has_name=meta_meta.has_name,
                    )
                    entry["summary"]["meta_rows_updated"] += 1
            else:
                table_entry["action"] = "insert"
                if blocking_insert_cols:
                    table_entry["action"] = "skip_blocked"
                    table_entry["note"] = f"blocking_columns={blocking_insert_cols}"
                    entry["summary"]["meta_rows_skipped_blocked"] += 1
                elif apply:
                    await _insert_meta_row(
                        conn,
                        meta_table=meta_table,
                        meta_meta=meta_meta,
                        record_uid=record_uid,
                        record_name=record_name,
                        payload=payload,
                    )
                    entry["summary"]["meta_rows_inserted"] += 1

            entry["tables"].append(table_entry)

    except Exception as exc:
        entry["error"] = f"process_failed: {exc}"
    finally:
        await conn.close()

    return entry


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
        "phase": "phaseB_persist_template_modes",
        "apply": bool(apply),
        "main_mandant": mandant_info,
        "databases": [],
        "summary": {
            "db_count": 0,
            "db_errors": 0,
            "tables_total": 0,
            "meta_rows_planned": 0,
            "meta_rows_inserted": 0,
            "meta_rows_updated": 0,
            "meta_rows_skipped_blocked": 0,
            "table_type_counts": {},
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
        report["summary"]["meta_rows_planned"] += int(s.get("meta_rows_planned", 0))
        report["summary"]["meta_rows_inserted"] += int(s.get("meta_rows_inserted", 0))
        report["summary"]["meta_rows_updated"] += int(s.get("meta_rows_updated", 0))
        report["summary"]["meta_rows_skipped_blocked"] += int(s.get("meta_rows_skipped_blocked", 0))
        for k, v in (s.get("table_type_counts", {}) or {}).items():
            counts = report["summary"].setdefault("table_type_counts", {})
            counts[k] = int(counts.get(k, 0)) + int(v)

    return report


def _default_output_path() -> Path:
    return BACKEND_DIR / "reports" / "phaseB_persist_template_modes_report.json"


def _print_summary(report: Dict[str, Any]) -> None:
    s = report.get("summary", {})
    print("\n=== Phase B Persist Template Modes ===")
    print(f"DBs: {s.get('db_count', 0)}")
    print(f"DB errors: {s.get('db_errors', 0)}")
    print(f"Tabellen gesamt: {s.get('tables_total', 0)}")
    print(f"Meta planned/inserted/updated/skipped: {s.get('meta_rows_planned', 0)}/{s.get('meta_rows_inserted', 0)}/{s.get('meta_rows_updated', 0)}/{s.get('meta_rows_skipped_blocked', 0)}")


async def _run(output_path: Path, apply: bool) -> int:
    report = await build_report(apply=apply)
    _print_summary(report)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nReport geschrieben: {output_path}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase B persist template modes")
    parser.add_argument("--apply", action="store_true", help="Persistiert Metadata in *systemdaten Tabellen")
    parser.add_argument(
        "--output",
        default=str(_default_output_path()),
        help="Pfad fuer JSON-Report",
    )
    args = parser.parse_args()

    return asyncio.run(_run(Path(args.output), apply=bool(args.apply)))


if __name__ == "__main__":
    raise SystemExit(main())

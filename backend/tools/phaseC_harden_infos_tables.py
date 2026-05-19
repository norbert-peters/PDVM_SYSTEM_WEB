"""
Phase C: Finale Verhaertung fuer infos-Tabellen.

Scope:
- sys_dropdowndaten
- sys_beschreibungen

Regeln:
1. 555 (UID_555): ROOT + leere Gruppen, kein TEMPLATES Top-Level.
2. 666 (UID_666): nur ROOT + TEMPLATES, TEMPLATES-Felder sind Objekte.
3. Datenzeilen:
   - ROOT.TABLE wird auf Zieltabelle korrigiert.
   - ROOT.RECORD_TYPE wird gesetzt:
     - sys_dropdowndaten: dropdown_definition
     - sys_beschreibungen: text_definition
   - ROOT.DEFAULT_LANGUAGE wird auf DE-DE gesetzt, wenn leer.
   - sys_dropdowndaten: ROOT.FIELD_KEY wird gesetzt, wenn leer.

Usage:
  python backend/tools/phaseC_harden_infos_tables.py
  python backend/tools/phaseC_harden_infos_tables.py --apply
  python backend/tools/phaseC_harden_infos_tables.py --output backend/reports/phaseC_harden_infos_tables_report.json
"""

from __future__ import annotations

import argparse
import asyncio
import copy
import json
import sys
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import asyncpg

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.connection_manager import ConnectionManager

UID_555 = "55555555-5555-5555-5555-555555555555"
UID_666 = "66666666-6666-6666-6666-666666666666"
TARGET_TABLES = {
    "sys_dropdowndaten": "dropdown_definition",
    "sys_beschreibungen": "text_definition",
}
DEFAULT_LANGUAGE = "DE-DE"


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


def _norm_field(value: Any) -> str:
    return str(value or "").strip().lower()


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


async def _load_row(conn: asyncpg.Connection, table_name: str, uid: str, has_historisch: bool) -> Optional[Dict[str, Any]]:
    where_hist = "AND COALESCE(historisch, 0) = 0" if has_historisch else ""
    row = await conn.fetchrow(
        f'''
        SELECT uid::text AS uid, name, daten
        FROM "{table_name}"
        WHERE uid::text = $1
        {where_hist}
        LIMIT 1
        ''',
        uid,
    )
    return dict(row) if row else None


async def _load_active_rows(conn: asyncpg.Connection, meta: TableMeta) -> List[Dict[str, Any]]:
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
        out.append({
            "uid": uid,
            "name": str(row.get("name") or ""),
            "daten": _as_dict(row.get("daten")),
        })
    return out


async def _update_row(conn: asyncpg.Connection, table_name: str, uid: str, payload: Dict[str, Any]) -> None:
    await conn.execute(
        f'UPDATE "{table_name}" SET daten = $1::jsonb WHERE uid::text = $2',
        json.dumps(payload, ensure_ascii=False),
        uid,
    )


def _build_strict_555(table_name: str, data_555: Dict[str, Any], data_666: Dict[str, Any]) -> Dict[str, Any]:
    root_555 = _as_dict(data_555.get("ROOT"))
    root_666 = _as_dict(data_666.get("ROOT"))
    root_keys: List[str] = []
    for k in [*root_555.keys(), *root_666.keys(), "SELF_GUID", "SELF_NAME", "TABLE", "RECORD_TYPE"]:
        ks = str(k)
        if ks not in root_keys:
            root_keys.append(ks)

    root_out: Dict[str, Any] = {}
    for key in root_keys:
        if key == "SELF_GUID":
            root_out[key] = UID_555
        elif key == "SELF_NAME":
            root_out[key] = "TEMPLATE_555"
        elif key == "TABLE":
            root_out[key] = table_name
        elif key == "RECORD_TYPE":
            root_out[key] = TARGET_TABLES.get(table_name)
        elif key in root_555:
            root_out[key] = root_555.get(key)
        elif key in root_666:
            root_out[key] = root_666.get(key)
        else:
            root_out[key] = None

    template_groups = _as_dict(data_666.get("TEMPLATES"))
    out: Dict[str, Any] = {"ROOT": root_out}
    for g in sorted(str(k) for k in template_groups.keys()):
        out[g] = {}
    return out


def _build_strict_666(table_name: str, strict_555: Dict[str, Any], data_666: Dict[str, Any]) -> Dict[str, Any]:
    root_base = _as_dict(strict_555.get("ROOT"))
    root_666_old = _as_dict(data_666.get("ROOT"))
    templates_old = _as_dict(data_666.get("TEMPLATES"))

    root_out: Dict[str, Any] = {}
    for key in root_base.keys():
        if key == "SELF_GUID":
            root_out[key] = UID_666
        elif key == "SELF_NAME":
            root_out[key] = "TEMPLATE_666"
        elif key == "TABLE":
            root_out[key] = table_name
        elif key == "RECORD_TYPE":
            root_out[key] = TARGET_TABLES.get(table_name)
        elif key in root_666_old:
            root_out[key] = root_666_old.get(key)
        else:
            root_out[key] = root_base.get(key)

    templates_out: Dict[str, Any] = {}
    for g in [k for k in strict_555.keys() if k != "ROOT"]:
        v = templates_old.get(g)
        templates_out[g] = v if isinstance(v, dict) else {}

    return {
        "ROOT": root_out,
        "TEMPLATES": templates_out,
    }


def _harden_data_row(table_name: str, row_uid: str, row_name: str, data: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    out = copy.deepcopy(_as_dict(data))
    notes: List[str] = []

    root = _as_dict(out.get("ROOT"))
    root["SELF_GUID"] = row_uid
    root["SELF_NAME"] = row_name or row_uid
    root["TABLE"] = table_name

    record_type = TARGET_TABLES.get(table_name)
    if root.get("RECORD_TYPE") != record_type:
        root["RECORD_TYPE"] = record_type
        notes.append("set_root_record_type")

    if not str(root.get("DEFAULT_LANGUAGE") or "").strip():
        root["DEFAULT_LANGUAGE"] = DEFAULT_LANGUAGE
        notes.append("set_default_language")

    if table_name == "sys_dropdowndaten":
        field_key = _norm_field(root.get("FIELD_KEY"))
        if not field_key:
            field_key = _norm_field(row_name)
            if not field_key:
                field_key = _norm_field(row_uid)
            root["FIELD_KEY"] = field_key
            notes.append("set_field_key")

    out["ROOT"] = root
    out.pop("TEMPLATES", None)

    return out, notes


async def build_report(apply: bool) -> Dict[str, Any]:
    cfg = await ConnectionManager.get_system_config()
    conn = await asyncpg.connect(**cfg.to_dict())

    report: Dict[str, Any] = {
        "phase": "phaseC",
        "title": "Harden infos tables",
        "mode": "apply" if apply else "dry-run",
        "database": cfg.database,
        "tables": [],
        "summary": {
            "tables_total": 0,
            "rows_scanned": 0,
            "rows_changed": 0,
            "template_rows_changed": 0,
            "db_errors": 0,
        },
    }

    try:
        metas = await _get_table_meta(conn)
        for table_name, record_type in TARGET_TABLES.items():
            meta = metas.get(table_name)
            entry = {
                "table": table_name,
                "record_type": record_type,
                "rows_scanned": 0,
                "rows_changed": 0,
                "template_rows_changed": 0,
                "notes": [],
                "error": None,
            }
            report["summary"]["tables_total"] += 1

            if not meta or not (meta.has_uid and meta.has_daten):
                entry["error"] = "table_missing_or_not_uid_daten"
                report["summary"]["db_errors"] += 1
                report["tables"].append(entry)
                continue

            row_555 = await _load_row(conn, table_name, UID_555, meta.has_historisch)
            row_666 = await _load_row(conn, table_name, UID_666, meta.has_historisch)

            data_555 = _as_dict((row_555 or {}).get("daten"))
            data_666 = _as_dict((row_666 or {}).get("daten"))
            strict_555 = _build_strict_555(table_name, data_555, data_666)
            strict_666 = _build_strict_666(table_name, strict_555, data_666)

            if row_555 and data_555 != strict_555:
                entry["template_rows_changed"] += 1
                report["summary"]["template_rows_changed"] += 1
                if apply:
                    await _update_row(conn, table_name, UID_555, strict_555)
            if row_666 and data_666 != strict_666:
                entry["template_rows_changed"] += 1
                report["summary"]["template_rows_changed"] += 1
                if apply:
                    await _update_row(conn, table_name, UID_666, strict_666)

            rows = await _load_active_rows(conn, meta)
            for row in rows:
                row_uid = str(row.get("uid") or "")
                if row_uid in {UID_555, UID_666}:
                    continue

                entry["rows_scanned"] += 1
                report["summary"]["rows_scanned"] += 1

                hardened, notes = _harden_data_row(
                    table_name,
                    row_uid,
                    str(row.get("name") or ""),
                    _as_dict(row.get("daten")),
                )
                if hardened != _as_dict(row.get("daten")):
                    entry["rows_changed"] += 1
                    report["summary"]["rows_changed"] += 1
                    if apply:
                        await _update_row(conn, table_name, row_uid, hardened)
                if notes:
                    entry["notes"].append({"uid": row_uid, "changes": notes})

            report["tables"].append(entry)

    except Exception as exc:
        report["summary"]["db_errors"] += 1
        report["error"] = f"process_failed: {exc}"
    finally:
        await conn.close()

    return report


def _default_output() -> Path:
    return BACKEND_DIR / "reports" / "phaseC_harden_infos_tables_report.json"


def _print_summary(report: Dict[str, Any]) -> None:
    s = report.get("summary", {})
    print("\n=== Phase C Harden Infos Tables ===")
    print(f"Mode: {report.get('mode')}")
    print(f"Tables: {s.get('tables_total', 0)}")
    print(f"Rows scanned: {s.get('rows_scanned', 0)}")
    print(f"Rows changed: {s.get('rows_changed', 0)}")
    print(f"Template rows changed: {s.get('template_rows_changed', 0)}")
    print(f"DB errors: {s.get('db_errors', 0)}")


async def _run(args: argparse.Namespace) -> int:
    report = await build_report(apply=bool(args.apply))
    _print_summary(report)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nReport geschrieben: {output_path}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase C harden infos tables")
    parser.add_argument("--apply", action="store_true", help="Änderungen schreiben")
    parser.add_argument("--output", default=str(_default_output()), help="Pfad für JSON-Report")
    args = parser.parse_args()
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())

"""
Phase 7: Control Dict Konsistenz-Report

Prueft fuer die System-DB:
- Duplikate in aktiven Control-Referenznamen
- Referenzierte Control-UIDs aus sys_framedaten/sys_viewdaten/sys_dialogdaten
- Referenzierte Control-Namen aus sys_framedaten/sys_viewdaten/sys_dialogdaten
- Fehlende Referenzen gegen sys_control_dict

Usage:
  python backend/tools/phase7_control_dict_consistency_report.py
  python backend/tools/phase7_control_dict_consistency_report.py --output backend/reports/phase7_control_dict_consistency_report.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import uuid
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

import asyncpg

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.connection_manager import ConnectionManager

UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
CONTROL_UID_KEYS = {
    "control_uid",
    "control_guid",
    "controlid",
    "control_id",
    "uid_control",
    "guid_control",
}
CONTROL_NAME_KEYS = {
    "control_name",
    "control",
    "field",
    "feld",
}
TEMPLATE_UIDS = {
    "55555555-5555-5555-5555-555555555555",
    "66666666-6666-6666-6666-666666666666",
}


@dataclass(frozen=True)
class SourceRow:
    source_table: str
    row_uid: str
    row_name: str
    daten: Dict[str, Any]


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


def _as_list(value: Any) -> List[Any]:
    if isinstance(value, list):
        return value
    return []


def _is_uuid(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    return bool(UUID_RE.match(value.strip()))


def _norm_name(value: Any) -> str:
    return str(value or "").strip().lower()


def _collect_control_references_from_node(
    node: Any,
    *,
    path: str,
    source_table: str,
    row_uid: str,
    row_name: str,
    out_uid_refs: List[Dict[str, str]],
    out_name_refs: List[Dict[str, str]],
) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            key_s = str(key)
            key_l = key_s.strip().lower()
            next_path = f"{path}.{key_s}" if path else key_s
            path_l = next_path.lower()

            looks_control_context = ("control" in path_l) or ("controls" in path_l)

            if key_l in CONTROL_UID_KEYS and _is_uuid(value):
                out_uid_refs.append(
                    {
                        "source_table": source_table,
                        "row_uid": row_uid,
                        "row_name": row_name,
                        "path": next_path,
                        "control_uid": str(value).strip().lower(),
                    }
                )
            elif looks_control_context and key_l in {"uid", "guid"} and _is_uuid(value):
                out_uid_refs.append(
                    {
                        "source_table": source_table,
                        "row_uid": row_uid,
                        "row_name": row_name,
                        "path": next_path,
                        "control_uid": str(value).strip().lower(),
                    }
                )

            if key_l in CONTROL_NAME_KEYS:
                value_s = str(value or "").strip()
                if value_s and not _is_uuid(value_s):
                    out_name_refs.append(
                        {
                            "source_table": source_table,
                            "row_uid": row_uid,
                            "row_name": row_name,
                            "path": next_path,
                            "control_name": value_s,
                        }
                    )

            _collect_control_references_from_node(
                value,
                path=next_path,
                source_table=source_table,
                row_uid=row_uid,
                row_name=row_name,
                out_uid_refs=out_uid_refs,
                out_name_refs=out_name_refs,
            )
    elif isinstance(node, list):
        for idx, value in enumerate(node):
            next_path = f"{path}[{idx}]"
            _collect_control_references_from_node(
                value,
                path=next_path,
                source_table=source_table,
                row_uid=row_uid,
                row_name=row_name,
                out_uid_refs=out_uid_refs,
                out_name_refs=out_name_refs,
            )


def _extract_control_references(rows: Iterable[SourceRow]) -> Tuple[List[Dict[str, str]], List[Dict[str, str]]]:
    uid_refs: List[Dict[str, str]] = []
    name_refs: List[Dict[str, str]] = []
    for row in rows:
        _collect_control_references_from_node(
            row.daten,
            path="daten",
            source_table=row.source_table,
            row_uid=row.row_uid,
            row_name=row.row_name,
            out_uid_refs=uid_refs,
            out_name_refs=name_refs,
        )
    return uid_refs, name_refs


async def _fetch_source_rows(conn: asyncpg.Connection, table_name: str) -> List[SourceRow]:
    exists = await conn.fetchval("SELECT to_regclass($1)", f"public.{table_name}")
    if not exists:
        return []

    rows = await conn.fetch(
        f'''
        SELECT uid::text AS uid, name, daten
        FROM "{table_name}"
        WHERE historisch = 0
        '''
    )

    out: List[SourceRow] = []
    for row in rows:
        out.append(
            SourceRow(
                source_table=table_name,
                row_uid=str(row.get("uid") or ""),
                row_name=str(row.get("name") or ""),
                daten=_as_dict(row.get("daten")),
            )
        )
    return out


async def _fetch_controls(conn: asyncpg.Connection) -> Tuple[List[Dict[str, Any]], Dict[str, Dict[str, Any]], Dict[str, List[str]]]:
    rows = await conn.fetch(
        '''
        SELECT uid::text AS uid, name, daten
        FROM sys_control_dict
        WHERE historisch = 0
        '''
    )

    controls: List[Dict[str, Any]] = []
    by_uid: Dict[str, Dict[str, Any]] = {}
    by_ref_name: Dict[str, List[str]] = defaultdict(list)

    for row in rows:
        uid = str(row.get("uid") or "").strip().lower()
        name = str(row.get("name") or "").strip()
        daten = _as_dict(row.get("daten"))

        root = _as_dict(daten.get("ROOT"))
        control = _as_dict(daten.get("CONTROL"))

        ref_name = (
            str(root.get("SELF_NAME") or "").strip()
            or str(control.get("FIELD") or control.get("FELD") or "").strip()
            or name
        )

        entry = {
            "uid": uid,
            "name": name,
            "ref_name": ref_name,
        }
        controls.append(entry)
        by_uid[uid] = entry

        if ref_name:
            by_ref_name[_norm_name(ref_name)].append(uid)

    return controls, by_uid, by_ref_name


async def build_report() -> Dict[str, Any]:
    cfg = await ConnectionManager.get_system_config()
    conn = await asyncpg.connect(**cfg.to_dict())
    try:
        controls, controls_by_uid, controls_by_ref_name = await _fetch_controls(conn)

        duplicates_by_ref_name = [
            {
                "ref_name": ref_name,
                "uids": uids,
                "count": len(uids),
            }
            for ref_name, uids in controls_by_ref_name.items()
            if len(uids) > 1
        ]
        duplicates_by_ref_name.sort(key=lambda x: (-x["count"], x["ref_name"]))

        source_tables = ["sys_framedaten", "sys_viewdaten", "sys_dialogdaten"]
        source_rows: List[SourceRow] = []
        rows_per_table: Dict[str, int] = {}

        for table in source_tables:
            rows = await _fetch_source_rows(conn, table)
            source_rows.extend(rows)
            rows_per_table[table] = len(rows)

        uid_refs, name_refs = _extract_control_references(source_rows)

        referenced_uids: Set[str] = {str(r["control_uid"]).lower() for r in uid_refs}
        referenced_names: Set[str] = {_norm_name(r["control_name"]) for r in name_refs if str(r.get("control_name") or "").strip()}

        missing_uid_refs = [
            ref for ref in uid_refs
            if ref["control_uid"] not in controls_by_uid
            and ref["control_uid"] not in TEMPLATE_UIDS
        ]

        missing_name_refs = [
            ref for ref in name_refs
            if _norm_name(ref["control_name"]) not in controls_by_ref_name
        ]

        report: Dict[str, Any] = {
            "phase": "phase7",
            "title": "Control Dict Konsistenzreport",
            "database": cfg.database,
            "summary": {
                "controls_active": len(controls),
                "controls_duplicate_ref_names": len(duplicates_by_ref_name),
                "source_rows_total": len(source_rows),
                "source_rows_by_table": rows_per_table,
                "referenced_control_uids": len(referenced_uids),
                "referenced_control_names": len(referenced_names),
                "missing_uid_references": len(missing_uid_refs),
                "missing_name_references": len(missing_name_refs),
            },
            "duplicates_by_ref_name": duplicates_by_ref_name,
            "missing_uid_references": missing_uid_refs,
            "missing_name_references": missing_name_refs,
            "sample": {
                "uid_refs": uid_refs[:100],
                "name_refs": name_refs[:100],
            },
        }

        return report
    finally:
        await conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 7 Control-Dict Konsistenzreport")
    parser.add_argument(
        "--output",
        default=str(BACKEND_DIR / "reports" / "phase7_control_dict_consistency_report.json"),
        help="Ausgabedatei fuer JSON-Report",
    )
    args = parser.parse_args()

    report = asyncio.run(build_report())

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    summary = report.get("summary", {})
    print("PHASE7_CONTROL_DICT_REPORT")
    print(f"output={output_path}")
    for key in [
        "controls_active",
        "controls_duplicate_ref_names",
        "source_rows_total",
        "referenced_control_uids",
        "referenced_control_names",
        "missing_uid_references",
        "missing_name_references",
    ]:
        print(f"{key}={summary.get(key)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

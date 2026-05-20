"""
Phase E: Retarget von Dropdown-UID-Referenzen in Frame/Viewdaten.

Ziele:
1. Referenzen auf gesplittete Dropdown-Datensaetze auf neue target_uids umstellen.
2. sys_viewdaten und sys_framedaten rekursiv scannen.
3. Mehrdeutige Referenzen hart reporten (optional strict-exit).

Quelle fuer Mapping:
- backend/reports/phaseD_migrate_infos_to_values_model_apply_v1.json

Usage:
  python backend/tools/phaseE_retarget_frame_view_dropdown_uids.py
  python backend/tools/phaseE_retarget_frame_view_dropdown_uids.py --apply
  python backend/tools/phaseE_retarget_frame_view_dropdown_uids.py --strict
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

import asyncpg

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.connection_manager import ConnectionManager

UID_555 = "55555555-5555-5555-5555-555555555555"
UID_666 = "66666666-6666-6666-6666-666666666666"
RESERVED_UIDS = {UID_555, UID_666}


@dataclass
class TargetCandidate:
    target_uid: str
    field_key: str


@dataclass
class TableMeta:
    table_name: str
    columns: List[str]

    @property
    def has_uid(self) -> bool:
        return "uid" in self.columns

    @property
    def has_name(self) -> bool:
        return "name" in self.columns

    @property
    def has_daten(self) -> bool:
        return "daten" in self.columns

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


def _norm_text(value: Any) -> str:
    s = str(value or "").strip().lower()
    return re.sub(r"[^a-z0-9_\-]", "", s)


def _is_uuid(value: Any) -> bool:
    token = str(value or "").strip()
    if not token:
        return False
    try:
        uuid.UUID(token)
        return True
    except Exception:
        return False


def _collect_hints_from_dict(node: Dict[str, Any], control_field_map: Dict[str, str]) -> Set[str]:
    hints: Set[str] = set()
    for key in ("FIELD_KEY", "field_key", "FELD", "feld", "FIELD", "field", "NAME", "name", "list_name", "field_name"):
        value = node.get(key)
        norm = _norm_text(value)
        if norm:
            hints.add(norm)

    field_ref = str(node.get("field") or "").strip()
    if _is_uuid(field_ref):
        norm = _norm_text(control_field_map.get(field_ref, ""))
        if norm:
            hints.add(norm)
    return hints


def _resolve_target_uid(
    old_uid: str,
    node: Dict[str, Any],
    inherited_hints: Set[str],
    mapping: Dict[str, List[TargetCandidate]],
    control_field_map: Dict[str, str],
) -> Tuple[Optional[str], List[str], List[str]]:
    candidates = mapping.get(old_uid, [])
    if not candidates:
        return None, [], []
    if len(candidates) == 1:
        only = candidates[0]
        return only.target_uid, [only.field_key], []

    hints = set(inherited_hints)
    hints.update(_collect_hints_from_dict(node, control_field_map))
    candidate_fields = [_norm_text(c.field_key) for c in candidates]

    hits = [c for c in candidates if _norm_text(c.field_key) in hints]
    if len(hits) == 1:
        chosen = hits[0]
        return chosen.target_uid, [h.field_key for h in candidates], sorted(hints)

    return None, [h.field_key for h in candidates], sorted(hints)


def _walk_and_retarget(
    node: Any,
    *,
    path: str,
    inherited_hints: Set[str],
    mapping: Dict[str, List[TargetCandidate]],
    control_field_map: Dict[str, str],
    findings: List[Dict[str, Any]],
    unresolved: List[Dict[str, Any]],
) -> Tuple[Any, bool]:
    changed = False

    if isinstance(node, dict):
        local_hints = set(inherited_hints)
        local_hints.update(_collect_hints_from_dict(node, control_field_map))

        table_value = _norm_text(node.get("table"))
        key_value = str(node.get("key") or "").strip()
        if table_value == "sys_dropdowndaten" and _is_uuid(key_value) and key_value in mapping:
            target_uid, candidate_fields, used_hints = _resolve_target_uid(
                key_value,
                node,
                local_hints,
                mapping,
                control_field_map,
            )
            if target_uid and target_uid != key_value:
                node["key"] = target_uid
                changed = True
                findings.append(
                    {
                        "path": path,
                        "old_key": key_value,
                        "new_key": target_uid,
                        "candidate_fields": candidate_fields,
                        "used_hints": used_hints,
                    }
                )
            elif target_uid is None:
                unresolved.append(
                    {
                        "path": path,
                        "old_key": key_value,
                        "candidate_fields": candidate_fields,
                        "used_hints": used_hints,
                    }
                )

        for key, value in list(node.items()):
            child_path = f"{path}.{key}" if path else str(key)
            new_value, child_changed = _walk_and_retarget(
                value,
                path=child_path,
                inherited_hints=local_hints,
                mapping=mapping,
                control_field_map=control_field_map,
                findings=findings,
                unresolved=unresolved,
            )
            if child_changed:
                node[key] = new_value
                changed = True
        return node, changed

    if isinstance(node, list):
        out = []
        for idx, value in enumerate(node):
            child_path = f"{path}[{idx}]"
            new_value, child_changed = _walk_and_retarget(
                value,
                path=child_path,
                inherited_hints=inherited_hints,
                mapping=mapping,
                control_field_map=control_field_map,
                findings=findings,
                unresolved=unresolved,
            )
            out.append(new_value)
            if child_changed:
                changed = True
        return out, changed

    return node, False


def _default_mapping_path() -> Path:
    return BACKEND_DIR / "reports" / "phaseD_migrate_infos_to_values_model_apply_v1.json"


def _default_output_path() -> Path:
    return BACKEND_DIR / "reports" / "phaseE_retarget_frame_view_dropdown_uids_report.json"


def _load_mapping(mapping_path: Path) -> Dict[str, List[TargetCandidate]]:
    data = json.loads(mapping_path.read_text(encoding="utf-8"))
    tables = data.get("tables") if isinstance(data, dict) else []
    dd_table = None
    for t in tables if isinstance(tables, list) else []:
        if isinstance(t, dict) and str(t.get("table")) == "sys_dropdowndaten":
            dd_table = t
            break
    if not isinstance(dd_table, dict):
        return {}

    out: Dict[str, List[TargetCandidate]] = {}
    for m in dd_table.get("mappings", []):
        if not isinstance(m, dict):
            continue
        source_uid = str(m.get("source_uid") or "").strip()
        target_uid = str(m.get("target_uid") or "").strip()
        field_key = _norm_text(m.get("field_key"))
        if not (_is_uuid(source_uid) and _is_uuid(target_uid)):
            continue
        out.setdefault(source_uid, []).append(TargetCandidate(target_uid=target_uid, field_key=field_key))
    return out


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
        if uid in RESERVED_UIDS:
            continue
        out.append(
            {
                "uid": uid,
                "name": str(row.get("name") or ""),
                "daten": _as_dict(row.get("daten")),
            }
        )
    return out


async def _update_row(conn: asyncpg.Connection, table_name: str, uid: str, daten: Dict[str, Any]) -> None:
    await conn.execute(
        f'UPDATE "{table_name}" SET daten = $1::jsonb WHERE uid::text = $2',
        json.dumps(daten, ensure_ascii=False),
        uid,
    )


async def _build_control_field_map(conn: asyncpg.Connection, metas: Dict[str, TableMeta]) -> Dict[str, str]:
    meta = metas.get("sys_control_dict")
    if not meta or not (meta.has_uid and meta.has_daten):
        return {}

    rows = await _load_active_rows(conn, meta)
    out: Dict[str, str] = {}
    for row in rows:
        uid = str(row.get("uid") or "")
        data = _as_dict(row.get("daten"))
        root = _as_dict(data.get("ROOT"))
        candidate = root.get("FELD") or root.get("FIELD") or root.get("NAME")
        norm = _norm_text(candidate)
        if norm:
            out[uid] = norm
    return out


async def build_report(*, apply: bool, strict: bool, mapping_path: Path) -> Tuple[Dict[str, Any], int]:
    mapping = _load_mapping(mapping_path)
    cfg = await ConnectionManager.get_system_config()
    conn = await asyncpg.connect(**cfg.to_dict())

    report: Dict[str, Any] = {
        "phase": "phaseE",
        "title": "Retarget frame/view dropdown uid references",
        "mode": "apply" if apply else "dry-run",
        "database": cfg.database,
        "mapping_file": str(mapping_path),
        "summary": {
            "tables_total": 2,
            "rows_scanned": 0,
            "rows_updated": 0,
            "ref_updates": 0,
            "unresolved_refs": 0,
            "db_errors": 0,
        },
        "tables": [],
    }

    exit_code = 0
    try:
        metas = await _get_table_meta(conn)
        control_field_map = await _build_control_field_map(conn, metas)

        for table_name in ("sys_viewdaten", "sys_framedaten"):
            entry: Dict[str, Any] = {
                "table": table_name,
                "rows_scanned": 0,
                "rows_updated": 0,
                "ref_updates": 0,
                "unresolved_refs": 0,
                "changes": [],
                "unresolved": [],
                "error": None,
            }

            meta = metas.get(table_name)
            if not meta or not (meta.has_uid and meta.has_daten):
                entry["error"] = "table_missing_or_invalid"
                report["summary"]["db_errors"] += 1
                report["tables"].append(entry)
                continue

            rows = await _load_active_rows(conn, meta)
            for row in rows:
                entry["rows_scanned"] += 1
                report["summary"]["rows_scanned"] += 1

                data = _as_dict(row.get("daten"))
                findings: List[Dict[str, Any]] = []
                unresolved: List[Dict[str, Any]] = []

                new_data, changed = _walk_and_retarget(
                    data,
                    path="",
                    inherited_hints=set(),
                    mapping=mapping,
                    control_field_map=control_field_map,
                    findings=findings,
                    unresolved=unresolved,
                )

                if findings:
                    entry["ref_updates"] += len(findings)
                    report["summary"]["ref_updates"] += len(findings)
                    entry["changes"].append(
                        {
                            "row_uid": row["uid"],
                            "row_name": row["name"],
                            "updates": findings,
                        }
                    )

                if unresolved:
                    entry["unresolved_refs"] += len(unresolved)
                    report["summary"]["unresolved_refs"] += len(unresolved)
                    entry["unresolved"].append(
                        {
                            "row_uid": row["uid"],
                            "row_name": row["name"],
                            "refs": unresolved,
                        }
                    )

                if changed:
                    entry["rows_updated"] += 1
                    report["summary"]["rows_updated"] += 1
                    if apply:
                        await _update_row(conn, table_name, row["uid"], new_data)

            report["tables"].append(entry)

        if strict and int(report["summary"].get("unresolved_refs", 0)) > 0:
            exit_code = 2
            report["strict_error"] = "unresolved_dropdown_refs_found"

    except Exception as exc:
        report["summary"]["db_errors"] += 1
        report["error"] = f"process_failed: {exc}"
        exit_code = 1
    finally:
        await conn.close()

    return report, exit_code


def _print_summary(report: Dict[str, Any]) -> None:
    summary = report.get("summary", {})
    print("\n=== Phase E Retarget Dropdown UIDs ===")
    print(f"Mode: {report.get('mode')}")
    print(f"Rows scanned: {summary.get('rows_scanned', 0)}")
    print(f"Rows updated: {summary.get('rows_updated', 0)}")
    print(f"Ref updates: {summary.get('ref_updates', 0)}")
    print(f"Unresolved refs: {summary.get('unresolved_refs', 0)}")
    print(f"DB errors: {summary.get('db_errors', 0)}")


async def _run(args: argparse.Namespace) -> int:
    report, exit_code = await build_report(
        apply=bool(args.apply),
        strict=bool(args.strict),
        mapping_path=Path(args.mapping),
    )
    _print_summary(report)

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nReport geschrieben: {output}")
    return exit_code


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Phase E retarget frame/view dropdown uid references")
    parser.add_argument("--apply", action="store_true", help="Änderungen schreiben")
    parser.add_argument("--strict", action="store_true", help="Exit Code 2 bei unresolved refs")
    parser.add_argument("--mapping", default=str(_default_mapping_path()), help="Pfad zum Phase-D-Apply-Report")
    parser.add_argument("--output", default=str(_default_output_path()), help="Pfad für JSON-Report")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())

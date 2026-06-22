"""
Hard migration V1 for sys_control_dict.

Rules enforced:
1) SELF_NAME must be unique (case-insensitive).
2) SELF_NAME must start with table prefix; generic controls use XXX_.
3) CONTROL structure of each row must match mother control structure.
   - Structure is copied from mother control keys.
   - Missing row values can be filled from mother values.
   - Values that would be lost are moved into backup_daten.
4) Duplicate controls are merged hard:
   - Keep one UID per canonical SELF_NAME.
   - Update references in sys_framedaten/sys_viewdaten from old UID/name to keep UID.
   - Retired rows are marked with DEL_ then hard deleted.

Usage:
  python backend/tools/hard_migrate_sys_control_dict_v1.py --dry-run
  python backend/tools/hard_migrate_sys_control_dict_v1.py --apply
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

import asyncpg

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.connection_manager import ConnectionManager

TEMPLATE_UIDS: Set[str] = {
    "00000000-0000-0000-0000-000000000000",
    "55555555-5555-5555-5555-555555555555",
    "66666666-6666-6666-6666-666666666666",
}

UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
SAFE_CHARS_RE = re.compile(r"[^A-Z0-9_]+")

UID_REF_KEYS = {
    "control_uid",
    "control_guid",
    "controlid",
    "control_id",
    "uid_control",
    "guid_control",
    "field",  # in sys_framedaten FIELDS.*.FIELD is control uid reference
}
NAME_REF_KEYS = {
    "control_name",
    "control",
    "field",  # can still contain legacy name in some rows
}


@dataclass
class ControlRow:
    uid: str
    name: str
    modified_at: str
    daten: Dict[str, Any]
    backup_daten: Dict[str, Any]
    root: Dict[str, Any]
    control: Dict[str, Any]
    self_name: str
    table_name: str
    field_name: str
    canonical_self_name: str
    is_template_uid: bool = False


@dataclass
class MigrationStats:
    controls_total: int = 0
    controls_template_skipped: int = 0
    duplicate_groups: int = 0
    duplicate_retire_candidates: int = 0
    references_rows_checked: int = 0
    references_rows_changed: int = 0
    reference_values_rewritten: int = 0
    controls_updated: int = 0
    controls_deleted: int = 0
    controls_del_marked: int = 0
    controls_structure_synced: int = 0
    controls_backup_written: int = 0
    controls_other_groups_removed: int = 0
    controls_root_synced: int = 0


@dataclass
class MigrationResult:
    stats: MigrationStats = field(default_factory=MigrationStats)
    mother_uid: str = ""
    mother_self_name: str = ""
    mother_key_count: int = 0
    root_mother_uid: str = ""
    root_mother_self_name: str = ""
    root_mother_key_count: int = 0
    keep_map: Dict[str, str] = field(default_factory=dict)
    retire_map: Dict[str, str] = field(default_factory=dict)
    duplicate_groups: List[Dict[str, Any]] = field(default_factory=list)
    changed_reference_rows: List[Dict[str, str]] = field(default_factory=list)
    updated_control_uids: List[str] = field(default_factory=list)
    del_marked_uids: List[str] = field(default_factory=list)
    deleted_control_uids: List[str] = field(default_factory=list)


def _as_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _norm_low(value: Any) -> str:
    return _norm(value).lower()


def _is_uuid_text(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    return bool(UUID_RE.match(value.strip()))


def _json_deep_copy(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False))


def _is_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ""
    if isinstance(value, (list, dict, tuple, set)):
        return len(value) == 0
    return False


def _normalize_key_name(value: Any) -> str:
    txt = _norm(value).upper()
    txt = txt.replace(" ", "_").replace("-", "_").replace(".", "_")
    txt = SAFE_CHARS_RE.sub("_", txt)
    txt = re.sub(r"_+", "_", txt).strip("_")
    return txt


def _table_prefix(table_name: str) -> str:
    table = _norm_low(table_name)
    if not table:
        return "XXX"
    base = table.split("_", 1)[0].strip()
    if not base:
        return "XXX"
    return _normalize_key_name(base) or "XXX"


def _pick_ci(d: Dict[str, Any], *keys: str) -> Any:
    if not isinstance(d, dict):
        return None
    for k in keys:
        if k in d:
            return d[k]
        up = k.upper()
        if up in d:
            return d[up]
        low = k.lower()
        if low in d:
            return d[low]
    return None


def _extract_table_name(root: Dict[str, Any], control: Dict[str, Any]) -> str:
    table = _norm(_pick_ci(control, "TABLE") or _pick_ci(root, "TABLE"))
    return table.lower()


def _extract_field_name(row_name: str, root: Dict[str, Any], control: Dict[str, Any]) -> str:
    field = _norm(
        _pick_ci(control, "FIELD", "FELD")
        or _pick_ci(root, "FIELD", "FELD")
        or _pick_ci(control, "NAME")
        or _pick_ci(root, "SELF_NAME")
        or row_name
    )
    field_norm = _normalize_key_name(field)
    if "_" in field_norm:
        parts = field_norm.split("_", 1)
        if len(parts) == 2 and parts[0] and parts[1]:
            # Handle legacy canonical names like SYS_TYPE -> TYPE
            field_norm = parts[1]
    return field_norm


def _canonical_self_name(table_name: str, field_name: str) -> str:
    prefix = _table_prefix(table_name)
    field = _normalize_key_name(field_name)
    if not field:
        return prefix
    return f"{prefix}_{field}"


def _control_non_empty_count(control: Dict[str, Any]) -> int:
    count = 0
    for value in control.values():
        if not _is_empty(value):
            count += 1
    return count


def _normalize_control_dict(control: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for key, value in control.items():
        key_n = _normalize_key_name(key)
        if not key_n:
            continue
        out[key_n] = value
    return out


def _select_mother_control(controls: List[ControlRow], target_table: str) -> ControlRow:
    # Absolute architecture rule priority:
    # CONTROL mother is the reserved 666 template row.
    uid_666 = "66666666-6666-6666-6666-666666666666"
    uid_666_candidates = [c for c in controls if c.uid == uid_666]
    if uid_666_candidates:
        return uid_666_candidates[0]

    target_table_n = _norm_low(target_table)

    # Strong preference: non-template row in target table with FIELD=666 or SELF_NAME SYS_666.
    candidates = [
        c
        for c in controls
        if (not c.is_template_uid)
        and _norm_low(c.table_name) == target_table_n
        and (
            _norm_low(c.self_name) == "sys_666"
            or _normalize_key_name(c.field_name) == "666"
        )
    ]

    # Fallback: non-template controls in target table.
    if not candidates:
        candidates = [c for c in controls if (not c.is_template_uid) and _norm_low(c.table_name) == target_table_n]

    # Last fallback: any non-template controls.
    if not candidates:
        candidates = [c for c in controls if not c.is_template_uid]

    if not candidates:
        raise RuntimeError("No non-template control rows found for mother control selection")

    def rank(c: ControlRow) -> Tuple[int, int, str, str]:
        score_sys_666 = 1 if _norm_low(c.self_name) == "sys_666" else 0
        return (
            score_sys_666,
            len(c.control.keys()),
            _norm(c.modified_at),
            c.uid,
        )

    return sorted(candidates, key=rank, reverse=True)[0]


def _select_root_mother_555(controls: List[ControlRow], target_table: str) -> ControlRow:
    target_table_n = _norm_low(target_table)

    # Absolute priority: dedicated 555 template row.
    uid_555 = "55555555-5555-5555-5555-555555555555"
    uid_555_candidates = [c for c in controls if c.uid == uid_555]
    if uid_555_candidates:
        return uid_555_candidates[0]

    # First try: explicit FIELD=555 or SELF_NAME *_555 in target table.
    candidates = [
        c
        for c in controls
        if _norm_low(c.table_name) == target_table_n
        and (
            _normalize_key_name(c.field_name) == "555"
            or _norm_low(c.self_name).endswith("_555")
        )
    ]

    # Fallback: any *_555 row for target table.
    if not candidates:
        candidates = [
            c
            for c in controls
            if _norm_low(c.table_name) == target_table_n and _norm_low(c.self_name).endswith("_555")
        ]

    # Last fallback: template 555 UID row.
    if not candidates:
        candidates = [c for c in controls if c.uid == "55555555-5555-5555-5555-555555555555"]

    if not candidates:
        raise RuntimeError(f"No 555 root mother found for target table '{target_table}'")

    def rank(c: ControlRow) -> Tuple[int, int, str, str]:
        score_555 = 1 if (_normalize_key_name(c.field_name) == "555" or _norm_low(c.self_name).endswith("_555")) else 0
        return (
            score_555,
            len(c.root.keys()),
            _norm(c.modified_at),
            c.uid,
        )

    return sorted(candidates, key=rank, reverse=True)[0]


def _build_control_rows(rows: Iterable[asyncpg.Record]) -> List[ControlRow]:
    out: List[ControlRow] = []
    for row in rows:
        uid = _norm(row.get("uid")).lower()
        name = _norm(row.get("name"))
        daten = _as_dict(row.get("daten"))
        backup_daten = _as_dict(row.get("backup_daten"))

        root = _as_dict(daten.get("ROOT"))

        # Canonical source for control payload:
        # 1) daten.CONTROL (normal rows)
        # 2) daten.TEMPLATES.CONTROL (reserved 666 template row)
        control_src = _as_dict(daten.get("CONTROL"))
        if not control_src:
            templates = _as_dict(daten.get("TEMPLATES"))
            control_src = _as_dict(_pick_ci(templates, "CONTROL"))

        control = _normalize_control_dict(control_src)

        if not control:
            # Legacy fallback: top-level keys except ROOT/CONTROL are interpreted as CONTROL.
            fallback = {
                _normalize_key_name(k): v
                for k, v in daten.items()
                if _normalize_key_name(k) not in {"ROOT", "CONTROL", "TEMPLATES"}
            }
            control = {k: v for k, v in fallback.items() if k}

        self_name = _norm(_pick_ci(root, "SELF_NAME") or _pick_ci(root, "NAME") or _pick_ci(control, "NAME") or name)
        table_name = _extract_table_name(root, control)
        field_name = _extract_field_name(name, root, control)
        canonical_self_name = _canonical_self_name(table_name, field_name)

        out.append(
            ControlRow(
                uid=uid,
                name=name,
                modified_at=_norm(row.get("modified_at")),
                daten=daten,
                backup_daten=backup_daten,
                root=root,
                control=control,
                self_name=self_name,
                table_name=table_name,
                field_name=field_name,
                canonical_self_name=canonical_self_name,
                is_template_uid=uid in TEMPLATE_UIDS,
            )
        )

    return out


def _rank_keep_candidate(row: ControlRow, reference_count: int) -> Tuple[int, int, int, str, str]:
    return (
        1 if not row.is_template_uid else 0,
        int(reference_count),
        _control_non_empty_count(row.control),
        _norm(row.modified_at),
        row.uid,
    )


def _merge_control_into_keep(
    keep_control: Dict[str, Any],
    donor_control: Dict[str, Any],
) -> Dict[str, List[Any]]:
    conflicts: Dict[str, List[Any]] = {}
    for key, donor_value in donor_control.items():
        key_u = _normalize_key_name(key)
        if not key_u:
            continue

        keep_has = key_u in keep_control
        keep_value = keep_control.get(key_u)

        if (not keep_has) or _is_empty(keep_value):
            if not _is_empty(donor_value):
                keep_control[key_u] = donor_value
            continue

        if _is_empty(donor_value):
            continue

        if keep_value != donor_value:
            conflicts.setdefault(key_u, []).append(donor_value)

    return conflicts


def _enforce_mother_structure(
    row: ControlRow,
    mother_control: Dict[str, Any],
    mother_root: Dict[str, Any],
    canonical_self_name: str,
) -> Tuple[Dict[str, Any], Dict[str, Any], bool, bool]:
    # Returns: new_daten, new_backup_daten, changed, backup_changed
    old_daten = _json_deep_copy(row.daten)
    old_backup = _json_deep_copy(row.backup_daten)

    current_root = _as_dict(old_daten.get("ROOT"))
    current_control_raw = _normalize_control_dict(_as_dict(old_daten.get("CONTROL")))

    if not current_control_raw:
        current_control_raw = _normalize_control_dict(row.control)

    new_control: Dict[str, Any] = {}
    removed_non_empty: Dict[str, Any] = {}

    # Track removed keys that are not part of mother structure.
    mother_keys = {_normalize_key_name(k) for k in mother_control.keys()}
    for key, value in current_control_raw.items():
        if key not in mother_keys and not _is_empty(value):
            removed_non_empty[key] = value

    for m_key_raw, mother_value in mother_control.items():
        m_key = _normalize_key_name(m_key_raw)
        row_value = current_control_raw.get(m_key)
        if _is_empty(row_value):
            new_control[m_key] = mother_value
        else:
            new_control[m_key] = row_value

    # Ensure key business fields are aligned and deterministic.
    table_name = _extract_table_name(current_root, new_control) or row.table_name
    field_name = _extract_field_name(row.name, current_root, new_control) or row.field_name
    if _is_empty(field_name):
        field_name = _extract_field_name(canonical_self_name, current_root, new_control)

    field_name = _normalize_key_name(field_name)
    table_name = _norm_low(table_name)

    new_control["FIELD"] = field_name
    new_control["FELD"] = field_name
    new_control["NAME"] = canonical_self_name
    new_control["TABLE"] = table_name

    gruppe = _pick_ci(new_control, "GRUPPE")
    if gruppe is not None:
        new_control["GRUPPE"] = _normalize_key_name(gruppe)

    # ROOT is normalized from 555 mother, then deterministic row identity fields are set.
    new_root = dict(mother_root)
    new_root["SELF_GUID"] = row.uid
    new_root["SELF_NAME"] = canonical_self_name
    new_root["NAME"] = canonical_self_name
    new_root["TABLE"] = table_name
    new_root["FIELD"] = field_name

    # Hard rule: only ROOT and CONTROL are kept at top-level.
    removed_groups_non_empty: Dict[str, Any] = {}
    for key, value in old_daten.items():
        key_n = _normalize_key_name(key)
        if key_n not in {"ROOT", "CONTROL"} and not _is_empty(value):
            removed_groups_non_empty[key_n] = value

    new_daten: Dict[str, Any] = {}
    new_daten["ROOT"] = new_root
    new_daten["CONTROL"] = new_control

    new_backup = dict(old_backup)
    if removed_non_empty:
        existing = _as_dict(new_backup.get("control_removed_keys"))
        merged = dict(existing)
        merged.update(removed_non_empty)
        new_backup["control_removed_keys"] = merged

    if removed_groups_non_empty:
        existing_groups = _as_dict(new_backup.get("removed_top_groups"))
        merged_groups = dict(existing_groups)
        merged_groups.update(removed_groups_non_empty)
        new_backup["removed_top_groups"] = merged_groups

    changed = (
        json.dumps(old_daten, ensure_ascii=False, sort_keys=True)
        != json.dumps(new_daten, ensure_ascii=False, sort_keys=True)
        or _norm(row.name) != canonical_self_name
    )
    backup_changed = json.dumps(old_backup, ensure_ascii=False, sort_keys=True) != json.dumps(new_backup, ensure_ascii=False, sort_keys=True)

    return new_daten, new_backup, changed, backup_changed


def _collect_reference_counts_from_node(node: Any, counter: Dict[str, int]) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            key_l = _norm_low(key)
            if key_l in UID_REF_KEYS and isinstance(value, str) and _is_uuid_text(value):
                counter[_norm_low(value)] = int(counter.get(_norm_low(value), 0)) + 1
            _collect_reference_counts_from_node(value, counter)
    elif isinstance(node, list):
        for value in node:
            _collect_reference_counts_from_node(value, counter)


def _rewrite_references_in_node(
    node: Any,
    uid_remap: Dict[str, str],
    name_to_uid: Dict[str, str],
) -> Tuple[Any, int]:
    changed = 0

    if isinstance(node, dict):
        out: Dict[str, Any] = {}
        for key, value in node.items():
            key_l = _norm_low(key)

            # Global exact UID rewrite catches embedded control snapshots
            # (for example ROOT.SELF_GUID nested in framedaten/viewdaten payloads).
            if isinstance(value, str):
                value_l = _norm_low(value)
                if _is_uuid_text(value_l) and value_l in uid_remap:
                    out[key] = uid_remap[value_l]
                    changed += 1
                    continue

            if key_l in UID_REF_KEYS and isinstance(value, str):
                value_l = _norm_low(value)
                if _is_uuid_text(value_l) and value_l in uid_remap:
                    out[key] = uid_remap[value_l]
                    changed += 1
                    continue
                if (not _is_uuid_text(value_l)) and key_l in NAME_REF_KEYS and value_l in name_to_uid:
                    out[key] = name_to_uid[value_l]
                    changed += 1
                    continue

            if key_l in NAME_REF_KEYS and isinstance(value, str):
                value_l = _norm_low(value)
                if value_l in name_to_uid:
                    out[key] = name_to_uid[value_l]
                    changed += 1
                    continue

            new_child, child_changed = _rewrite_references_in_node(value, uid_remap, name_to_uid)
            out[key] = new_child
            changed += child_changed

        return out, changed

    if isinstance(node, list):
        out_list: List[Any] = []
        for value in node:
            new_child, child_changed = _rewrite_references_in_node(value, uid_remap, name_to_uid)
            out_list.append(new_child)
            changed += child_changed
        return out_list, changed

    return node, 0


async def _load_source_rows(conn: asyncpg.Connection, table_name: str) -> List[asyncpg.Record]:
    exists = await conn.fetchval("SELECT to_regclass($1)", f"public.{table_name}")
    if not exists:
        return []

    return await conn.fetch(
        f'''
        SELECT uid::text AS uid, name, daten
        FROM "{table_name}"
        WHERE historisch = 0
        '''
    )


async def _run(apply_changes: bool, output_path: Path, target_table: str) -> MigrationResult:
    result = MigrationResult()

    cfg = await ConnectionManager.get_system_config()
    conn = await asyncpg.connect(**cfg.to_dict())

    try:
        tx = conn.transaction()
        await tx.start()

        control_rows_raw = await conn.fetch(
            '''
            SELECT uid::text AS uid, name, daten, backup_daten, modified_at
            FROM sys_control_dict
            WHERE historisch = 0
            '''
        )
        controls = _build_control_rows(control_rows_raw)
        result.stats.controls_total = len(controls)

        if not controls:
            raise RuntimeError("sys_control_dict has no active rows")

        mother = _select_mother_control(controls, target_table)
        mother_control = _normalize_control_dict(mother.control)
        if not mother_control:
            raise RuntimeError("Selected mother control has empty CONTROL structure")

        root_mother = _select_root_mother_555(controls, target_table)
        mother_root = _as_dict(root_mother.root)
        if not mother_root:
            raise RuntimeError("Selected 555 ROOT mother has empty ROOT structure")

        result.mother_uid = mother.uid
        result.mother_self_name = mother.self_name
        result.mother_key_count = len(mother_control.keys())
        result.root_mother_uid = root_mother.uid
        result.root_mother_self_name = root_mother.self_name
        result.root_mother_key_count = len(mother_root.keys())

        source_rows = []
        for table_name in ("sys_framedaten", "sys_viewdaten"):
            source_rows.extend([(table_name, r) for r in await _load_source_rows(conn, table_name)])
        result.stats.references_rows_checked = len(source_rows)

        ref_counts: Dict[str, int] = {}
        for _, row in source_rows:
            _collect_reference_counts_from_node(_as_dict(row.get("daten")), ref_counts)

        target_table_n = _norm_low(target_table)
        scoped_controls = [
            r for r in controls if (not r.is_template_uid) and _norm_low(r.table_name) == target_table_n
        ]

        # Group controls by canonical SELF_NAME (excluding reserved template UIDs).
        by_canonical: Dict[str, List[ControlRow]] = defaultdict(list)
        for row in controls:
            if row.is_template_uid:
                result.stats.controls_template_skipped += 1
                continue
            if _norm_low(row.table_name) != target_table_n:
                continue
            canonical = _norm_low(row.canonical_self_name)
            if not canonical:
                canonical = _norm_low(row.self_name)
            by_canonical[canonical].append(row)

        duplicate_groups: List[Tuple[str, List[ControlRow], ControlRow, List[ControlRow]]] = []

        for canonical, group in by_canonical.items():
            if not canonical or len(group) <= 1:
                continue

            ranked = sorted(
                group,
                key=lambda x: _rank_keep_candidate(x, int(ref_counts.get(x.uid, 0))),
                reverse=True,
            )
            keep = ranked[0]
            retires = ranked[1:]
            duplicate_groups.append((canonical, group, keep, retires))

            result.stats.duplicate_groups += 1
            result.stats.duplicate_retire_candidates += len(retires)

            result.duplicate_groups.append(
                {
                    "canonical_self_name": canonical,
                    "keep_uid": keep.uid,
                    "retire_uids": [r.uid for r in retires],
                }
            )

            result.keep_map[canonical] = keep.uid
            for r in retires:
                result.retire_map[r.uid] = keep.uid

        # Build map for legacy name-based references -> keep UID.
        name_to_uid: Dict[str, str] = {}
        for row in scoped_controls:
            key_names = {
                _norm_low(row.self_name),
                _norm_low(row.name),
                _norm_low(row.canonical_self_name),
                _norm_low(_pick_ci(row.control, "NAME")),
                _norm_low(_pick_ci(row.control, "FIELD", "FELD")),
            }
            target_uid = result.retire_map.get(row.uid, row.uid)
            for name_key in key_names:
                if name_key:
                    name_to_uid[name_key] = target_uid

        # Merge retire controls into keep controls before structure enforcement.
        controls_by_uid: Dict[str, ControlRow] = {c.uid: c for c in controls}
        keep_conflicts: Dict[str, Dict[str, List[Any]]] = defaultdict(lambda: defaultdict(list))

        for _, _, keep, retires in duplicate_groups:
            keep_row = controls_by_uid.get(keep.uid)
            if not keep_row:
                continue
            keep_control_work = dict(keep_row.control)

            for retire_row in retires:
                conflicts = _merge_control_into_keep(keep_control_work, retire_row.control)
                if conflicts:
                    for key, values in conflicts.items():
                        keep_conflicts[keep.uid][key].extend(values)

            keep_row.control = keep_control_work
            keep_row.daten = dict(keep_row.daten)
            keep_row.daten["CONTROL"] = keep_control_work

        # Rewrite references in sys_framedaten and sys_viewdaten.
        for table_name, row in source_rows:
            row_uid = _norm(row.get("uid")).lower()
            daten = _as_dict(row.get("daten"))
            if not daten:
                continue

            rewritten, changed_count = _rewrite_references_in_node(daten, result.retire_map, name_to_uid)
            if changed_count <= 0:
                continue

            result.stats.reference_values_rewritten += changed_count
            result.stats.references_rows_changed += 1
            result.changed_reference_rows.append({"table": table_name, "uid": row_uid})

            if apply_changes:
                await conn.execute(
                    f'''
                    UPDATE "{table_name}"
                    SET daten = $1::jsonb,
                        modified_at = NOW()
                    WHERE uid = $2::uuid
                    ''',
                    json.dumps(rewritten, ensure_ascii=False),
                    row_uid,
                )

        # Apply structural sync for all non-template rows.
        canonical_usage: Dict[str, int] = defaultdict(int)

        for row in scoped_controls:

            base_canonical = row.canonical_self_name
            if row.uid in result.retire_map:
                keep_uid = result.retire_map[row.uid]
                keep_row = controls_by_uid.get(keep_uid)
                if keep_row:
                    base_canonical = keep_row.canonical_self_name

            canonical_usage[_norm_low(base_canonical)] += 1
            if canonical_usage[_norm_low(base_canonical)] > 1:
                # Hard-unique fallback suffix to satisfy unique SELF_NAME rule.
                suffix = canonical_usage[_norm_low(base_canonical)]
                canonical_name = f"{base_canonical}_{suffix}"
            else:
                canonical_name = base_canonical

            row.canonical_self_name = canonical_name

            # Merge duplicate conflict backups if row is keep-row.
            if row.uid in keep_conflicts and keep_conflicts[row.uid]:
                backup_map = _as_dict(row.backup_daten)
                existing = _as_dict(backup_map.get("duplicate_merge_conflicts"))
                merged = dict(existing)
                for key, values in keep_conflicts[row.uid].items():
                    if not values:
                        continue
                    existing_vals = merged.get(key)
                    if not isinstance(existing_vals, list):
                        existing_vals = []
                    existing_vals.extend(values)
                    merged[key] = existing_vals
                backup_map["duplicate_merge_conflicts"] = merged
                row.backup_daten = backup_map

            old_top_level_keys = set(_as_dict(row.daten).keys())

            new_daten, new_backup, changed, backup_changed = _enforce_mother_structure(
                row,
                mother_control,
                mother_root,
                canonical_name,
            )

            if any(_normalize_key_name(k) not in {"ROOT", "CONTROL"} for k in old_top_level_keys):
                result.stats.controls_other_groups_removed += 1

            if _as_dict(new_daten.get("ROOT")):
                result.stats.controls_root_synced += 1

            if changed or backup_changed:
                result.updated_control_uids.append(row.uid)
                result.stats.controls_updated += 1
                if backup_changed:
                    result.stats.controls_backup_written += 1
                result.stats.controls_structure_synced += 1

                if apply_changes:
                    await conn.execute(
                        '''
                        UPDATE sys_control_dict
                        SET name = $1,
                            daten = $2::jsonb,
                            backup_daten = $3::jsonb,
                            modified_at = NOW()
                        WHERE uid = $4::uuid
                        ''',
                        canonical_name,
                        json.dumps(new_daten, ensure_ascii=False),
                        json.dumps(new_backup, ensure_ascii=False),
                        row.uid,
                    )

        # DEL mark and hard delete duplicates.
        for retire_uid, keep_uid in result.retire_map.items():
            retire_row = controls_by_uid.get(retire_uid)
            if not retire_row:
                continue

            del_name = f"DEL_{_normalize_key_name(retire_row.name or retire_row.self_name or retire_uid)}"
            del_self_name = f"DEL_{_normalize_key_name(retire_row.self_name or retire_row.name or retire_uid)}"

            if apply_changes:
                retire_data = _as_dict(retire_row.daten)
                retire_root = _as_dict(retire_data.get("ROOT"))
                retire_root["SELF_NAME"] = del_self_name
                retire_root["NAME"] = del_self_name
                retire_data["ROOT"] = retire_root

                await conn.execute(
                    '''
                    UPDATE sys_control_dict
                    SET name = $1,
                        daten = $2::jsonb,
                        modified_at = NOW()
                    WHERE uid = $3::uuid
                    ''',
                    del_name,
                    json.dumps(retire_data, ensure_ascii=False),
                    retire_uid,
                )
                result.stats.controls_del_marked += 1

                await conn.execute(
                    "DELETE FROM sys_control_dict WHERE uid = $1::uuid",
                    retire_uid,
                )
                result.stats.controls_deleted += 1

            result.del_marked_uids.append(retire_uid)
            result.deleted_control_uids.append(retire_uid)

        if apply_changes:
            await tx.commit()
        else:
            await tx.rollback()

    finally:
        await conn.close()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_payload = {
        "phase": "hard_migration_v1",
        "title": "Hard migration sys_control_dict",
        "mode": "apply" if apply_changes else "dry-run",
        "target_table": target_table,
        "mother": {
            "uid": result.mother_uid,
            "self_name": result.mother_self_name,
            "control_key_count": result.mother_key_count,
        },
        "root_mother": {
            "uid": result.root_mother_uid,
            "self_name": result.root_mother_self_name,
            "root_key_count": result.root_mother_key_count,
        },
        "stats": result.stats.__dict__,
        "duplicate_groups": result.duplicate_groups,
        "retire_map": result.retire_map,
        "changed_reference_rows": result.changed_reference_rows,
        "updated_control_uids": result.updated_control_uids,
        "del_marked_uids": result.del_marked_uids,
        "deleted_control_uids": result.deleted_control_uids,
    }
    output_path.write_text(json.dumps(output_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Hard migrate sys_control_dict with strict normalization")
    parser.add_argument("--apply", action="store_true", help="Write changes to database")
    parser.add_argument("--dry-run", action="store_true", help="Analyze only and rollback")
    parser.add_argument(
        "--output",
        default=str(BACKEND_DIR / "reports" / "hard_migrate_sys_control_dict_v1.json"),
        help="Result report JSON path",
    )
    parser.add_argument(
        "--target-table",
        default="sys_control_dict",
        help="Normalize only controls whose CONTROL.TABLE matches this table",
    )
    args = parser.parse_args()

    if args.apply and args.dry_run:
        print("ERROR: use only one of --apply or --dry-run")
        return 2

    apply_changes = bool(args.apply) and not bool(args.dry_run)

    result = asyncio.run(
        _run(
            apply_changes=apply_changes,
            output_path=Path(args.output),
            target_table=args.target_table,
        )
    )

    print("HARD_MIGRATE_SYS_CONTROL_DICT_V1")
    print(f"mode={'apply' if apply_changes else 'dry-run'}")
    print(f"output={args.output}")
    print(f"mother_uid={result.mother_uid}")
    print(f"mother_self_name={result.mother_self_name}")
    print(f"root_mother_uid={result.root_mother_uid}")
    print(f"root_mother_self_name={result.root_mother_self_name}")
    for key, value in result.stats.__dict__.items():
        print(f"{key}={value}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

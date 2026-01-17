"""View Matrix Service

ARCHITECTURE_RULES: keine SQL in Routern.

Ziel: Server-seitige, lineare View-Pipeline (BASIS → STICHTAG → EXCLUDE → FILTER → SORT → GROUP → PROJECT).
Der Browser ist nur Darsteller + Rücksender von State.

Hinweis (aktueller Stand):
- Für sehr große Datenmengen muss Filter/Sort perspektivisch DB-näher umgesetzt werden (Pagination/Indices).
- Diese Implementierung arbeitet deterministisch und linear, mit einem konfigurierten Max-Limit für Base-Rows.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
import hashlib
import json
import time

from app.core.pdvm_central_systemsteuerung import PdvmCentralSystemsteuerung
from app.core.dropdown_service import get_dropdown_mapping_for_field, get_user_language
from app.core.view_service import load_view_definition, load_view_base_rows
from app.core.view_state_service import (
    effective_controls_as_list,
    extract_controls_origin,
    merge_controls,
    normalize_controls_source,
)
from app.core.view_table_state_service import merge_table_state, normalize_table_state_source
from app.core.config import settings
from app.core.pdvm_datetime import now_pdvm


MAX_BASE_ROWS_DEFAULT = int(getattr(settings, "VIEW_TABLE_CACHE_MAX_ROWS", 20000) or 20000)


def _stable_json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _normalize_type(control: Dict[str, Any]) -> str:
    t = str(control.get("type") or control.get("control_type") or "").strip().lower()
    if not t:
        return "string"
    if t == "text":
        return "string"
    if t == "base":
        return "string"
    return t


def _get_value_from_row(row: Dict[str, Any], control: Dict[str, Any]) -> Any:
    daten = row.get("daten") or {}
    if not isinstance(daten, dict):
        return None

    gruppe = str(control.get("gruppe") or "")
    feld = str(control.get("feld") or "")
    if not gruppe or not feld:
        return None

    group_obj = daten.get(gruppe)
    raw = None
    try:
        raw = group_obj.get(feld) if isinstance(group_obj, dict) else None
    except Exception:
        raw = None

    # SYSTEM special-case: tolerate case variants (frontend does this too)
    if gruppe.upper() == "SYSTEM" and raw is None and isinstance(group_obj, dict):
        raw = group_obj.get(str(feld).lower())
        if raw is None:
            raw = group_obj.get(str(feld).upper())

    return raw


def _is_empty_for_type(type_norm: str, raw: Any) -> bool:
    if raw is None:
        return True

    if isinstance(raw, str) and raw.strip() == "":
        return True

    if type_norm in ("string", "dropdown"):
        return False

    if type_norm in ("date", "datetime"):
        # PDVM-Konvention: 1001.0 = Default/leer
        try:
            n = float(raw)
            return n == 1001.0
        except Exception:
            return False

    if type_norm in ("number", "float", "int"):
        try:
            n = float(raw)
            return n != n  # NaN
        except Exception:
            return True

    if type_norm in ("bool", "boolean"):
        return False

    # Fallback
    if isinstance(raw, list):
        return len(raw) == 0
    if isinstance(raw, dict):
        return len(raw.keys()) == 0
    return False


def _row_has_any_value(row: Dict[str, Any], controls_origin: Dict[str, Dict[str, Any]]) -> bool:
    # SYSTEM-Spalten nicht berücksichtigen (haben immer Werte)
    for c in controls_origin.values():
        if str(c.get("gruppe") or "").upper() == "SYSTEM":
            continue
        raw = _get_value_from_row(row, c)
        type_norm = _normalize_type(c)
        if not _is_empty_for_type(type_norm, raw):
            return True
    return False


def _apply_filters(rows: List[Dict[str, Any]], filters: Dict[str, str], controls_origin: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not filters:
        return rows

    normalized_filters = {k: str(v or "").strip() for k, v in filters.items() if str(v or "").strip()}
    if not normalized_filters:
        return rows

    out: List[Dict[str, Any]] = []
    for r in rows:
        ok = True
        for control_guid, needle_raw in normalized_filters.items():
            control = controls_origin.get(control_guid)
            if not control:
                continue

            needle = needle_raw.lower()
            raw = _get_value_from_row(r, control)
            hay = "" if raw is None else str(raw)
            if needle not in hay.lower():
                ok = False
                break
        if ok:
            out.append(r)
    return out


def _apply_sort(rows: List[Dict[str, Any]], sort_control_guid: Optional[str], direction: Optional[str], controls_origin: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not sort_control_guid or not direction:
        return rows

    control = controls_origin.get(sort_control_guid)
    if not control:
        return rows

    sign = 1 if str(direction) == "asc" else -1

    def key_fn(r: Dict[str, Any]):
        v = _get_value_from_row(r, control)
        # numeric if possible
        try:
            n = float(v)
            if n == n:
                return (0, n)
        except Exception:
            pass
        s = "" if v is None else str(v)
        return (1, s)

    return sorted(rows, key=key_fn, reverse=(sign == -1))


def _apply_group(
    rows: List[Dict[str, Any]],
    group_by_guid: str,
    sum_guid: Optional[str],
    controls_origin: Dict[str, Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], Optional[Dict[str, Any]]]:
    group_control = controls_origin.get(group_by_guid)
    if not group_control:
        return ([{"kind": "data", **r} for r in rows], None)

    sum_control = controls_origin.get(sum_guid) if sum_guid else None

    buckets: Dict[str, Dict[str, Any]] = {}
    order: List[str] = []

    for r in rows:
        raw = _get_value_from_row(r, group_control)
        key = "" if raw is None else str(raw)
        if key not in buckets:
            buckets[key] = {"raw": raw, "items": []}
            order.append(key)
        buckets[key]["items"].append(r)

    out: List[Dict[str, Any]] = []

    total_sum: Optional[float] = None
    total_count = 0
    any_sum = False

    for key in order:
        bucket = buckets[key]
        items: List[Dict[str, Any]] = bucket["items"]

        group_sum: Optional[float] = None
        if sum_control:
            s = 0.0
            any_local = False
            for it in items:
                v = _get_value_from_row(it, sum_control)
                try:
                    n = float(v)
                    if n == n:
                        s += n
                        any_local = True
                except Exception:
                    continue
            group_sum = s if any_local else None

        out.append({"kind": "group", "key": key, "raw": bucket["raw"], "count": len(items), "sum": group_sum})
        for it in items:
            out.append({"kind": "data", "group_key": key, **it})

        total_count += len(items)
        if group_sum is not None:
            total_sum = (total_sum or 0.0) + float(group_sum)
            any_sum = True

    totals = {"count": total_count, "sum": total_sum if any_sum else None}
    return out, totals


async def build_view_matrix(
    gcs: PdvmCentralSystemsteuerung,
    view_guid: str,
    *,
    controls_source: Optional[Dict[str, Any]] = None,
    table_state_source: Optional[Dict[str, Any]] = None,
    include_historisch: bool = True,
    limit: int = 200,
    offset: int = 0,
    max_base_rows: int = MAX_BASE_ROWS_DEFAULT,
) -> Dict[str, Any]:
    """Erstellt eine projektierte Matrix für eine View (serverseitig)."""

    view_uuid = __import__("uuid").UUID(view_guid)
    definition = await load_view_definition(gcs, view_uuid)

    table = str((definition.get("root") or {}).get("TABLE") or "").strip()
    if not table:
        raise ValueError("View ROOT.TABLE ist leer")

    origin = extract_controls_origin(definition.get("daten") or {})

    # State: source overrides (optional) or persisted
    src_controls = controls_source if controls_source is not None else (gcs.get_view_controls(view_guid) or {})
    if not isinstance(src_controls, dict):
        src_controls = {}

    src_table_state = table_state_source if table_state_source is not None else (gcs.get_view_table_state(view_guid) or {})
    if not isinstance(src_table_state, dict):
        src_table_state = {}

    effective, meta = merge_controls(origin=origin, source=src_controls)
    normalized_controls_source = normalize_controls_source(source=src_controls, effective=effective)

    # Dropdown resolver data (for rendering + filters)
    dropdowns: Dict[str, Any] = {}
    try:
        user_lang = get_user_language(gcs)
        for c in effective_controls_as_list(effective):
            control_guid = str((c or {}).get("control_guid") or "")
            if not control_guid:
                continue
            if _normalize_type(c) != "dropdown":
                continue

            cfg = (c or {}).get("configs") or {}
            dd = cfg.get("dropdown") if isinstance(cfg, dict) else None
            if not isinstance(dd, dict):
                continue

            dataset_uid = dd.get("key")
            field = dd.get("feld")
            table_name = dd.get("table") or "sys_dropdowndaten"
            if not dataset_uid or not field:
                continue

            resolved = await get_dropdown_mapping_for_field(
                gcs,
                table=str(table_name),
                dataset_uid=str(dataset_uid),
                field=str(field),
                language=user_lang,
            )
            dropdowns[control_guid] = {
                "table": str(table_name),
                "key": str(dataset_uid),
                "feld": str(field),
                **(resolved or {}),
            }
    except Exception:
        dropdowns = {}

    table_state_effective, table_state_meta = merge_table_state(src_table_state)
    table_state_normalized = normalize_table_state_source(table_state_effective)
    meta["table_state"] = table_state_meta

    # Paging sanitize
    try:
        page_limit = max(1, int(limit))
    except Exception:
        page_limit = 200
    try:
        page_offset = max(0, int(offset))
    except Exception:
        page_offset = 0

    # Stichtag-Projektion nur für Felder, die die View nutzt
    control_fields: List[tuple[str, str]] = []
    for c in origin.values():
        gruppe = str((c or {}).get("gruppe") or "").strip()
        feld = str((c or {}).get("feld") or "").strip()
        if gruppe and feld:
            control_fields.append((gruppe, feld))

    # Für Skalierung: Table-Cache kann größer sein als die aktuell angefragte Seite.
    # max_base_rows dient als RAM-Schutz und ist konfigurierbar.
    configured_max = int(getattr(settings, "VIEW_TABLE_CACHE_MAX_ROWS", max_base_rows) or max_base_rows)
    effective_max_base_rows = int(max(1, min(int(max_base_rows), configured_max)))

    base_rows = await load_view_base_rows(
        gcs,
        table_name=table,
        limit=effective_max_base_rows,
        include_historisch=include_historisch,
        control_fields=control_fields,
    )

    # Table cache version (for result cache invalidation)
    table_version = 0
    table_truncated = False
    try:
        cache_entry = getattr(gcs, "_pdvm_table_cache", {}).get((str(table), bool(include_historisch)))
        if isinstance(cache_entry, dict):
            table_version = int(cache_entry.get("version") or 0)
            table_truncated = bool(cache_entry.get("truncated"))
    except Exception:
        pass

    # Empty-row exclusion
    base_rows = [r for r in base_rows if _row_has_any_value(r, origin)]
    base_loaded = len(base_rows)

    # Result cache: sorted UID order (state + stichtag + current-day for gilt_bis semantics)
    current_day = int(float(now_pdvm()))
    state_blob = {
        "controls_source": normalized_controls_source,
        "table_state_source": table_state_normalized,
        "include_historisch": bool(include_historisch),
        "stichtag": float(gcs.stichtag),
        "current_day": current_day,
    }
    state_hash = hashlib.sha1(_stable_json(state_blob).encode("utf-8")).hexdigest()
    cache_key = f"{view_guid}:{table}:{table_version}:{state_hash}"

    sorted_uids: Optional[List[str]] = None
    cached_total_after_filter: Optional[int] = None
    cached_global_totals: Optional[Dict[str, Any]] = None
    cache_hit = False
    try:
        cache_map = getattr(gcs, "_view_matrix_result_cache", {})
        entry = cache_map.get(cache_key) if isinstance(cache_map, dict) else None
        if isinstance(entry, dict) and int(entry.get("table_version") or 0) == table_version:
            sorted_uids = entry.get("sorted_uids")
            cached_total_after_filter = entry.get("total_after_filter")
            cached_global_totals = entry.get("global_totals")
            if isinstance(sorted_uids, list):
                cache_hit = True
    except Exception:
        cache_hit = False

    base_by_uid = {str(r.get("uid")): r for r in base_rows if r.get("uid")}

    if not cache_hit:
        # Filter
        filters = (table_state_effective.get("filters") or {}) if isinstance(table_state_effective, dict) else {}
        if not isinstance(filters, dict):
            filters = {}
        filtered = _apply_filters(base_rows, filters, origin)

        # Sort
        sort_obj = table_state_effective.get("sort") if isinstance(table_state_effective, dict) else None
        sort_guid = None
        sort_dir = None
        if isinstance(sort_obj, dict):
            sort_guid = sort_obj.get("control_guid")
            sort_dir = sort_obj.get("direction")
        sorted_rows = _apply_sort(filtered, sort_guid, sort_dir, origin)

        sorted_uids = [str(r.get("uid")) for r in sorted_rows if r.get("uid")]
        cached_total_after_filter = len(sorted_uids)

        # Global totals (über alle Treffer) – aktuell nur relevant wenn Grouping aktiv ist.
        group_obj = table_state_effective.get("group") if isinstance(table_state_effective, dict) else None
        global_totals: Optional[Dict[str, Any]] = None
        if isinstance(group_obj, dict) and bool(group_obj.get("enabled")):
            sum_guid = group_obj.get("sum_control_guid")
            sum_control = origin.get(sum_guid) if isinstance(sum_guid, str) and sum_guid else None

            total_sum: Optional[float] = None
            any_sum = False
            if sum_control:
                s = 0.0
                for uid in sorted_uids:
                    r = base_by_uid.get(uid)
                    if not r:
                        continue
                    v = _get_value_from_row(r, sum_control)
                    try:
                        n = float(v)
                        if n == n:
                            s += n
                            any_sum = True
                    except Exception:
                        continue
                total_sum = s if any_sum else None

            global_totals = {"count": int(cached_total_after_filter), "sum": total_sum}

        cached_global_totals = global_totals

        # Store cache + basic eviction
        try:
            cache_map = getattr(gcs, "_view_matrix_result_cache", None)
            if isinstance(cache_map, dict):
                cache_map[cache_key] = {
                    "ts": float(time.time()),
                    "table_version": int(table_version),
                    "sorted_uids": sorted_uids,
                    "total_after_filter": int(cached_total_after_filter),
                    "global_totals": cached_global_totals,
                }

                max_entries = int(getattr(settings, "VIEW_MATRIX_RESULT_CACHE_MAX_ENTRIES", 200) or 200)
                if len(cache_map) > max_entries:
                    # evict oldest
                    oldest_key = None
                    oldest_ts = None
                    for k, v in list(cache_map.items()):
                        if not isinstance(v, dict):
                            continue
                        t = v.get("ts")
                        try:
                            t = float(t)
                        except Exception:
                            continue
                        if oldest_ts is None or t < oldest_ts:
                            oldest_ts = t
                            oldest_key = k
                    if oldest_key:
                        cache_map.pop(oldest_key, None)
        except Exception:
            pass

    total_after_filter = int(cached_total_after_filter or 0)

    # Page slice
    start = page_offset
    end = start + page_limit
    page_uids = (sorted_uids or [])[start:end] if end > start else []
    page_rows = [base_by_uid[uid] for uid in page_uids if uid in base_by_uid]
    has_more = end < total_after_filter

    # Group (page-scope rows), Totals (global-scope)
    group_obj = table_state_effective.get("group") if isinstance(table_state_effective, dict) else None
    grouped_rows: List[Dict[str, Any]] = [{"kind": "data", **r} for r in page_rows]
    totals: Optional[Dict[str, Any]] = None

    if isinstance(group_obj, dict) and bool(group_obj.get("enabled")):
        by_guid = group_obj.get("by")
        sum_guid = group_obj.get("sum_control_guid")
        if isinstance(by_guid, str) and by_guid:
            grouped_rows, _page_totals = _apply_group(page_rows, by_guid, sum_guid, origin)
        # totals are global-scope (cached)
        totals = cached_global_totals

    response = {
        "view_guid": view_guid,
        "table": table,
        "stichtag": float(gcs.stichtag),
        "controls_source": normalized_controls_source,
        "controls_effective": effective_controls_as_list(effective),
        "table_state_source": table_state_normalized,
        "table_state_effective": table_state_effective,
        "rows": grouped_rows,
        "totals": totals,
        "dropdowns": dropdowns,
        "meta": {
            "max_base_rows": int(effective_max_base_rows),
            "base_loaded": int(base_loaded),
            "total_after_filter": total_after_filter,
            "offset": int(page_offset),
            "limit": int(page_limit),
            "returned_data": int(len(page_rows)),
            "returned_rows": int(len(grouped_rows)),
            "has_more": bool(has_more),
            "cache_hit": bool(cache_hit),
            "table_version": int(table_version),
            "table_truncated": bool(table_truncated),
            "totals_scope": "global",
        },
    }

    return response

"""View Table State Service

Phase 1 (erweitert):
- Persistiert Sort- und Filter-Zustand pro View in sys_systemsteuerung

Wichtig:
- Niemals nach sys_viewdaten zurückschreiben.
- Router bleibt SQL-frei.

Shape (minimal, bewusst simpel):
{
  "sort": {"control_guid": <str|null>, "direction": "asc"|"desc"|null},
    "filters": {"<control_guid>": <str>},
    "group": {"enabled": <bool>, "by": <str|null>, "sum_control_guid": <str|null>}
}
"""

from __future__ import annotations

from typing import Any, Dict, Tuple


ALLOWED_SORT_DIRECTIONS = {"asc", "desc", None}


def _is_plain_object(value: Any) -> bool:
    return isinstance(value, dict)


def default_table_state() -> Dict[str, Any]:
    return {
        "sort": {"control_guid": None, "direction": None},
        "filters": {},
        "group": {"enabled": False, "by": None, "sum_control_guid": None},
    }


def merge_table_state(source: Dict[str, Any] | None) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Merges source auf Default und normalisiert Werte."""

    effective = default_table_state()
    meta: Dict[str, Any] = {}

    if not _is_plain_object(source):
        meta["source_ok"] = False
        return effective, meta

    meta["source_ok"] = True

    # sort
    sort_in = source.get("sort")
    if _is_plain_object(sort_in):
        cg = sort_in.get("control_guid")
        if cg is None or isinstance(cg, str):
            effective["sort"]["control_guid"] = cg

        direction = sort_in.get("direction")
        if direction is None or direction in ("asc", "desc"):
            effective["sort"]["direction"] = direction

    # filters
    filters_in = source.get("filters")
    if _is_plain_object(filters_in):
        out: Dict[str, str] = {}
        for k, v in filters_in.items():
            if not isinstance(k, str):
                continue
            if v is None:
                continue
            if not isinstance(v, str):
                v = str(v)
            v = v.strip()
            if not v:
                continue
            out[k] = v
        effective["filters"] = out

    # group
    group_in = source.get("group")
    if _is_plain_object(group_in):
        enabled = group_in.get("enabled")
        if isinstance(enabled, bool):
            effective["group"]["enabled"] = enabled

        by = group_in.get("by")
        if by is None or isinstance(by, str):
            effective["group"]["by"] = by

        sum_cg = group_in.get("sum_control_guid")
        if sum_cg is None or isinstance(sum_cg, str):
            effective["group"]["sum_control_guid"] = sum_cg

    return effective, meta


def normalize_table_state_source(effective: Dict[str, Any]) -> Dict[str, Any]:
    """Persistiert nur die minimalen Keys in stabiler Form."""
    # Für Phase 1 speichern wir bewusst effektiv -> source (bereits normalisiert)
    if not _is_plain_object(effective):
        return default_table_state()

    sort = effective.get("sort")
    filters = effective.get("filters")
    group = effective.get("group")

    out = {
        "sort": {"control_guid": None, "direction": None},
        "filters": {},
        "group": {"enabled": False, "by": None, "sum_control_guid": None},
    }

    if _is_plain_object(sort):
        cg = sort.get("control_guid")
        if cg is None or isinstance(cg, str):
            out["sort"]["control_guid"] = cg
        direction = sort.get("direction")
        if direction is None or direction in ("asc", "desc"):
            out["sort"]["direction"] = direction

    if _is_plain_object(filters):
        out_filters: Dict[str, str] = {}
        for k, v in filters.items():
            if not isinstance(k, str):
                continue
            if v is None:
                continue
            if not isinstance(v, str):
                v = str(v)
            v = v.strip()
            if not v:
                continue
            out_filters[k] = v
        out["filters"] = out_filters

    if _is_plain_object(group):
        enabled = group.get("enabled")
        if isinstance(enabled, bool):
            out["group"]["enabled"] = enabled
        by = group.get("by")
        if by is None or isinstance(by, str):
            out["group"]["by"] = by
        sum_cg = group.get("sum_control_guid")
        if sum_cg is None or isinstance(sum_cg, str):
            out["group"]["sum_control_guid"] = sum_cg

    return out

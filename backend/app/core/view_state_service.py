"""View State Service

Phase 1:
- Controls-Origin aus sys_viewdaten extrahieren
- Controls-Source aus sys_systemsteuerung (GCS) laden
- Merge Origin/Source -> Effective

Wichtig:
- Niemals nach sys_viewdaten zurückschreiben.
- Router bleibt SQL-frei.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple


USER_KEYS = {
    "show",
    "display_order",
    "width",
}

SYSTEM_KEYS = {
    "gruppe",
    "feld",
    "label",
    "type",
    "default",
    "dropdown",
    "control_type",
    "expert_mode",
    "searchable",
    "sortable",
    "sortDirection",
    "sortByOriginal",
    "filterType",
    "table",
    "configs",
}


def _is_plain_object(value: Any) -> bool:
    return isinstance(value, dict)


def extract_controls_origin(view_daten: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Extrahiert Controls aus sys_viewdaten.daten.

    Erwartet Struktur: ROOT + Sektionen (z.B. PERSONDATEN) mit control_guid -> control-data.
    """
    origin: Dict[str, Dict[str, Any]] = {}

    for section_key, section_val in (view_daten or {}).items():
        if section_key == "ROOT":
            continue
        if not _is_plain_object(section_val):
            continue

        for control_guid, control_val in section_val.items():
            if not _is_plain_object(control_val):
                continue

            # System-Basisdaten (Origin) unverändert übernehmen
            origin[str(control_guid)] = dict(control_val)

    return origin


def merge_controls(
    origin: Dict[str, Dict[str, Any]],
    source: Dict[str, Dict[str, Any]],
) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, Any]]:
    """Merged origin+source zu effective.

    Regeln:
    - systemkritische Felder kommen aus origin
    - userkritische Felder (show, display_order, width) kommen aus source, wenn vorhanden
    - Controls nur in source bleiben erhalten (optional: veraltet)
    """

    effective: Dict[str, Dict[str, Any]] = {}

    # 1) Alle origin-controls
    for guid, origin_control in origin.items():
        merged = dict(origin_control)

        src = source.get(guid)
        if _is_plain_object(src):
            for k in USER_KEYS:
                if k in src:
                    merged[k] = src[k]

        # Defaults
        if "show" not in merged:
            merged["show"] = True

        # display_order default: aus origin oder 0
        try:
            merged["display_order"] = int(merged.get("display_order") or 0)
        except Exception:
            merged["display_order"] = 0

        effective[guid] = merged

    # 2) Controls nur in source (veraltet)
    for guid, src_control in source.items():
        if guid in effective:
            continue
        if not _is_plain_object(src_control):
            continue

        merged = dict(src_control)
        merged.setdefault("show", False)
        merged.setdefault("display_order", 0)
        merged["_orphan"] = True
        effective[guid] = merged

    meta: Dict[str, Any] = {
        "origin_count": len(origin),
        "source_count": len(source),
        "effective_count": len(effective),
    }

    # Sicherheitsnetz: mindestens 1 sichtbare Spalte
    visible = [c for c in effective.values() if c.get("show")]
    if not visible and effective:
        # Nimm die kleinste display_order
        sorted_controls = sorted(effective.items(), key=lambda kv: int(kv[1].get("display_order") or 0))
        first_guid, _ = sorted_controls[0]
        effective[first_guid]["show"] = True
        meta["force_one_visible"] = True

    return effective, meta


def normalize_controls_source(
    source: Dict[str, Dict[str, Any]],
    effective: Dict[str, Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    """Normalisiert source so, dass nur userrelevante Keys persistiert werden.

    Phase 1: Wir persistieren minimal (show/display_order/width) für alle controls.
    """
    normalized: Dict[str, Dict[str, Any]] = {}

    for guid, control in effective.items():
        norm: Dict[str, Any] = {}

        for k in USER_KEYS:
            if k in control:
                norm[k] = control[k]

        normalized[guid] = norm

    # Zusätzlich: falls source bereits orphan-controls hatte, behalten wir die user-keys (optional)
    for guid, src in (source or {}).items():
        if guid in normalized:
            continue
        if not _is_plain_object(src):
            continue
        norm: Dict[str, Any] = {}
        for k in USER_KEYS:
            if k in src:
                norm[k] = src[k]
        if norm:
            normalized[guid] = norm

    return normalized


def effective_controls_as_list(effective: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Für API/Frontend: controls als Liste inkl. control_guid."""
    out: List[Dict[str, Any]] = []
    for guid, ctrl in effective.items():
        item = dict(ctrl)
        item["control_guid"] = guid
        out.append(item)
    return out

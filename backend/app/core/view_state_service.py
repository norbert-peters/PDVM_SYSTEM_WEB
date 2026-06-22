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

from typing import Any, Dict, List, Tuple, Optional
import uuid

from app.core.pdvm_datenbank import PdvmDatabase
from app.core.control_runtime_service import hydrate_runtime_control_by_uid


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
    "expert_mode",
    "searchable",
    "sortable",
    "sort_direction",
    "sort_by_original",
    "filter_type",
    "table",
    "configs",
}


def _is_plain_object(value: Any) -> bool:
    return isinstance(value, dict)


def _truthy(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return bool(value)
    if isinstance(value, (int, float)):
        try:
            return float(value) != 0.0
        except Exception:
            return False
    s = str(value).strip().lower()
    return s in {"1", "true", "yes", "y", "on"}


def _pick_section_key(daten: Dict[str, Any], wanted: str) -> Optional[str]:
    if not isinstance(daten, dict):
        return None
    lw = str(wanted).lower()
    for k in daten.keys():
        if str(k).lower() == lw:
            return str(k)
    return None


def _pick_ci_value(obj: Any, *keys: str) -> Any:
    if not isinstance(obj, dict):
        return None
    for key in keys:
        if key in obj:
            return obj.get(key)
        wanted = str(key or "").strip().lower()
        if not wanted:
            continue
        for k, v in obj.items():
            if str(k or "").strip().lower() == wanted:
                return v
    return None


def derive_effective_no_data(
    view_daten: Dict[str, Any],
    *,
    root_no_data: Any = False,
) -> bool:
    """Leitet den effektiven NO_DATA-Zustand aus Root-Flag + View-Sektionen ab.

    Regel (vereinfacht):
    - True, wenn ROOT.NO_DATA explizit true ist.
    - Sonst True, wenn neben SYSTEM-Sektionen keine fachlichen Spalten angeboten werden.
    """
    if _truthy(root_no_data):
        return True

    daten = view_daten or {}
    if not isinstance(daten, dict):
        return True

    has_non_system_controls = False
    for section_key, section_val in daten.items():
        section_name = str(section_key or "").strip()
        if section_name.upper() == "ROOT":
            continue
        if not _is_plain_object(section_val):
            continue

        # "SYSTEM" und "**SYSTEM" als technische Sektionen behandeln.
        normalized_section = section_name.lstrip("*").strip().upper()
        if normalized_section == "SYSTEM":
            continue

        for control_val in section_val.values():
            if _is_plain_object(control_val):
                has_non_system_controls = True
                break

        if has_non_system_controls:
            break

    return not has_non_system_controls


def extract_controls_origin(
    view_daten: Dict[str, Any],
    *,
    root_table: Optional[str] = None,
    no_data: bool = False,
) -> Dict[str, Dict[str, Any]]:
    """Extrahiert Controls aus sys_viewdaten.daten.

    Neu (PDVM-Regel):
    - Sektion = TABLENAME (uppercase) + Default-Sektion "**System"
    - effektives NO_DATA bedeutet: table-Sektion NICHT berücksichtigen, aber weiterhin über View rendern

    Fallback: Wenn die neuen Sektionen nicht vorhanden sind, wird legacy (alle Sektionen außer ROOT) verwendet.
    """
    origin: Dict[str, Dict[str, Any]] = {}

    daten = view_daten or {}

    # Determine if new semantics apply
    table_group = str(root_table or "").strip().upper() if root_table else ""
    system_section_key = _pick_section_key(daten, "**System")
    table_section_key = _pick_section_key(daten, table_group) if table_group else None
    has_new_sections = bool(system_section_key or table_section_key)

    if has_new_sections:
        allowed_sections: List[str] = []
        if system_section_key:
            allowed_sections.append(system_section_key)

        # allow other "**" sections (future-proof), except ROOT
        for k in daten.keys():
            ks = str(k)
            if ks == "ROOT":
                continue
            if ks.startswith("**") and ks not in allowed_sections:
                allowed_sections.append(ks)

        if not bool(no_data) and table_section_key:
            allowed_sections.append(table_section_key)

        for section_key in allowed_sections:
            section_val = daten.get(section_key)
            if not _is_plain_object(section_val):
                continue
            for control_guid, control_val in section_val.items():
                if not _is_plain_object(control_val):
                    continue
                origin[str(control_guid)] = dict(control_val)

        return origin

    # Legacy behavior
    for section_key, section_val in daten.items():
        if section_key == "ROOT":
            continue
        if not _is_plain_object(section_val):
            continue
        for control_guid, control_val in section_val.items():
            if not _is_plain_object(control_val):
                continue
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
    - Controls nur in source gelten als veraltet und werden verworfen
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

    stale_source_guids: List[str] = []
    for guid, src_control in (source or {}).items():
        if guid in effective:
            continue
        if not _is_plain_object(src_control):
            continue
        stale_source_guids.append(str(guid))

    meta: Dict[str, Any] = {
        "origin_count": len(origin),
        "source_count": len(source),
        "effective_count": len(effective),
        "stale_source_count": len(stale_source_guids),
        "stale_source_guids": stale_source_guids,
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

    return normalized


def effective_controls_as_list(effective: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Für API/Frontend: controls als Liste inkl. control_guid."""
    out: List[Dict[str, Any]] = []
    for guid, ctrl in effective.items():
        item = dict(ctrl)
        item["control_guid"] = guid
        out.append(item)
    return out


async def resolve_view_control_references(
    origin: Dict[str, Dict[str, Any]],
    *,
    system_pool: Any,
    mandant_pool: Any,
) -> Dict[str, Dict[str, Any]]:
    """Löst schlanke View-Control-Referenzen (nur UID-Key) gegen sys_control_dict auf.

    Erwartetes Muster in sys_viewdaten:
    - section[<control_uid>] = {"TABLE": "..."}

    In diesem Fall fehlen gruppe/feld/type/label im View-Datensatz und werden aus
    sys_control_dict geladen. View-spezifische Overrides (z.B. TABLE) bleiben erhalten.
    """

    resolved: Dict[str, Dict[str, Any]] = {}

    for guid, cfg in (origin or {}).items():
        current = dict(cfg or {})

        # Zentrale Runtime-Hydration: Basis kommt aus sys_control_dict,
        # View-Werte ueberschreiben nur erlaubte/definierte Properties.
        merged = await hydrate_runtime_control_by_uid(
            str(guid),
            override=current,
            system_pool=system_pool,
            mandant_pool=mandant_pool,
        )

        # Legacy-Viewdaten koennen einen generischen Typ (z.B. string/base) enthalten,
        # obwohl die Control-Definition inzwischen dropdown/date/... vorgibt.
        base_type = _pick_ci_value(merged, "type")
        override_type = _pick_ci_value(current, "type", "TYPE")
        override_norm = str(override_type or "").strip().lower()
        base_norm = str(base_type or "").strip().lower()
        if override_type is not None and override_norm in {"base", "string", "text"} and base_norm not in {"", "base", "string", "text"}:
            merged["type"] = base_type

        # Fehlende Config-Teile aus der Basis ergänzen (nicht überschreiben).
        base_cfg = _pick_ci_value(merged, "configs")
        cur_cfg = _pick_ci_value(current, "configs", "CONFIGS")
        if isinstance(base_cfg, dict) and isinstance(cur_cfg, dict):
            cfg_next = dict(base_cfg)
            for k, v in cur_cfg.items():
                if k in cfg_next:
                    cfg_next[k] = v
            merged["configs"] = cfg_next

        resolved[str(guid)] = merged

    return resolved

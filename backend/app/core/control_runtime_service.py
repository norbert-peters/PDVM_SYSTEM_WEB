from __future__ import annotations

import uuid
from typing import Any, Dict, Optional

from app.core.pdvm_datenbank import PdvmDatabase


# User-spezifische View-Overrides sind weiterhin erlaubt.
# Frame-spezifische Layout-Overrides (z. B. TAB) sind ebenfalls erlaubt,
# obwohl sie nicht aus sys_control_dict stammen.
USER_OVERRIDE_KEYS = {"show", "display_order", "width", "tab", "source_path"}

# Runtime-Control-Keys, die aus sys_control_dict gelesen werden.
RUNTIME_KEY_MAP = {
    "gruppe": ("GRUPPE", "gruppe"),
    "feld": ("FELD", "feld", "FIELD", "field"),
    "type": ("TYPE", "type"),
    "label": ("LABEL", "label"),
    "table": ("TABLE", "table"),
    "default": ("DEFAULT", "default"),
    "dropdown": ("DROPDOWN", "dropdown"),
    "expert_mode": ("EXPERT_MODE", "expert_mode"),
    "searchable": ("SEARCHABLE", "searchable"),
    "sortable": ("SORTABLE", "sortable"),
    "sort_direction": ("SORT_DIRECTION", "sort_direction"),
    "sort_by_original": ("SORT_BY_ORIGINAL", "sort_by_original"),
    "filter_type": ("FILTER_TYPE", "filter_type"),
    "configs": ("CONFIGS", "configs"),
}


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


def _normalize_runtime_control_from_row(control_row: Dict[str, Any]) -> Dict[str, Any]:
    data = control_row.get("daten") if isinstance(control_row.get("daten"), dict) else {}
    control = data.get("CONTROL") if isinstance(data.get("CONTROL"), dict) else {}
    if not control:
        templates = data.get("TEMPLATES") if isinstance(data.get("TEMPLATES"), dict) else {}
        control = templates.get("CONTROL") if isinstance(templates.get("CONTROL"), dict) else {}
    if not control:
        # Legacy/Fallback: einzelne Datensaetze speichern CONTROL-Keys direkt auf Top-Level.
        flat = dict(data)
        flat.pop("ROOT", None)
        flat.pop("CONTROL", None)
        flat.pop("TEMPLATES", None)
        if isinstance(flat, dict):
            control = flat
    root = data.get("ROOT") if isinstance(data.get("ROOT"), dict) else {}

    out: Dict[str, Any] = {}
    for runtime_key, candidates in RUNTIME_KEY_MAP.items():
        val = _pick_ci_value(control, *candidates)
        if val is None and runtime_key in {"gruppe", "feld", "table"}:
            val = _pick_ci_value(root, *candidates)
        if val is not None and not (isinstance(val, str) and val.strip() == ""):
            out[runtime_key] = val

    # Legacy: dropdown/dropdown_source direkt auf CONTROL-Ebene nach configs spiegeln.
    dropdown_direct = _pick_ci_value(control, "dropdown", "DROPDOWN")
    dropdown_source_direct = _pick_ci_value(control, "dropdown_source", "DROPDOWN_SOURCE")
    if isinstance(dropdown_direct, dict) or isinstance(dropdown_source_direct, dict):
        cfg = out.get("configs") if isinstance(out.get("configs"), dict) else {}
        cfg_next = dict(cfg)
        if isinstance(dropdown_direct, dict) and not isinstance(_pick_ci_value(cfg_next, "dropdown"), dict):
            cfg_next["dropdown"] = dict(dropdown_direct)
        if isinstance(dropdown_source_direct, dict) and not isinstance(_pick_ci_value(cfg_next, "dropdown_source"), dict):
            cfg_next["dropdown_source"] = dict(dropdown_source_direct)
        if cfg_next:
            out["configs"] = cfg_next

    return out


def merge_control_runtime_with_override(base: Dict[str, Any], override: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Mergt Override nur auf erlaubte Keys.

    Regel:
    - User-/Layout-Keys (`show`, `display_order`, `width`, `tab`, `source_path`) duerfen immer gesetzt werden.
    - Sonstige Keys duerfen nur gesetzt werden, wenn sie im Basis-Control vorhanden sind.
      (Property nicht im Muttercontrol -> keine Ueberschreibung)
    """
    out = dict(base or {})
    if not isinstance(override, dict):
        return out

    for key, value in override.items():
        k = str(key or "").strip()
        if not k:
            continue
        k_norm = k.lower()

        if k_norm in USER_OVERRIDE_KEYS:
            out[k_norm] = value
            continue

        if k_norm in out:
            if k_norm == "type":
                base_norm = str(out.get("type") or "").strip().lower()
                override_norm = str(value or "").strip().lower()
                # Generische Legacy-Typen duerfen keinen spezifischen Basistyp verdrängen.
                if override_norm in {"base", "string", "text"} and base_norm not in {"", "base", "string", "text"}:
                    continue

            if k_norm == "configs" and isinstance(out.get("configs"), dict) and isinstance(value, dict):
                if not value:
                    continue
                merged_cfg = dict(out.get("configs") or {})
                for cfg_key, cfg_val in value.items():
                    if cfg_key in merged_cfg:
                        merged_cfg[cfg_key] = cfg_val
                out["configs"] = merged_cfg
                continue

            out[k_norm] = value

    return out


async def hydrate_runtime_control_by_uid(
    control_guid: str,
    *,
    override: Optional[Dict[str, Any]],
    system_pool: Any,
    mandant_pool: Any,
) -> Dict[str, Any]:
    """Lädt Control aus sys_control_dict und liefert Runtime-Control.

    Falls die UID ungueltig ist oder das Control nicht existiert, wird nur das Override zurueckgegeben.
    """
    try:
        control_uid = uuid.UUID(str(control_guid))
    except Exception:
        return dict(override or {})

    try:
        control_row = await PdvmDatabase.load_control_definition(
            control_uid,
            system_pool=system_pool,
            mandant_pool=mandant_pool,
        )
    except Exception:
        control_row = None

    if not isinstance(control_row, dict):
        return dict(override or {})

    base = _normalize_runtime_control_from_row(control_row)
    return merge_control_runtime_with_override(base, override)

"""Runtime-Config-Extraktion und generische Validierung fuer Dialoge (reine Verschiebung aus dialog_service.py).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def _get_root_table(root: Dict[str, Any]) -> str:
    table = str(root.get("TABLE") or root.get("ROOT_TABLE") or "").strip()
    return table


def _collect_edit_control_hints(daten: Dict[str, Any]) -> List[Dict[str, Any]]:
    hints: List[Dict[str, Any]] = []

    if not isinstance(daten, dict):
        return hints

    for key, value in daten.items():
        key_norm = str(key or "").strip()
        if not key_norm or key_norm.upper() == "ROOT":
            continue

        if isinstance(value, dict):
            value_type = str(value.get("type") or value.get("TYPE") or "").strip().lower()
            if value_type not in {"element_list", "group_list"}:
                hints.append(
                    {
                        "group": "__ROOT__",
                        "index": None,
                        "field": key_norm,
                        "code": "hint_missing_collection_type",
                        "message": (
                            f"Property '{key_norm}' ist ein Objekt. FÃ¼r edit_control sollte auf dieser Ebene "
                            f"TYPE=element_list oder TYPE=group_list gesetzt sein."
                        ),
                    }
                )
                continue

            for child_key, child_value in value.items():
                if str(child_key or "").strip().upper() in {"TYPE", "NAME", "LABEL", "HEAD"}:
                    continue
                if isinstance(child_value, (dict, list)):
                    hints.append(
                        {
                            "group": "__ROOT__",
                            "index": None,
                            "field": key_norm,
                            "code": "hint_nested_collection_depth",
                            "message": (
                                f"Property '{key_norm}.{child_key}' ist tiefer verschachtelt. FÃ¼r edit_control "
                                f"sollte die Sammlung eine Ebene tiefer bleiben."
                            ),
                        }
                    )

        elif isinstance(value, list):
            hints.append(
                {
                    "group": "__ROOT__",
                    "index": None,
                    "field": key_norm,
                    "code": "hint_missing_collection_type",
                    "message": (
                        f"Property '{key_norm}' ist eine Liste. FÃ¼r edit_control sollte diese Liste als "
                        f"TYPE=element_list oder TYPE=group_list modelliert sein."
                    ),
                }
            )

    return hints


def validate_dialog_daten_generic(
    daten: Dict[str, Any],
    *,
    edit_type: Optional[str] = None,
) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []

    if not isinstance(daten, dict):
        return [
            {
                "group": "ROOT",
                "index": None,
                "field": None,
                "code": "invalid_daten",
                "message": "daten muss ein JSON-Objekt sein",
            }
        ]

    root = daten.get("ROOT")
    if not isinstance(root, dict):
        issues.append(
            {
                "group": "ROOT",
                "index": None,
                "field": None,
                "code": "missing_root",
                "message": "Gruppe ROOT fehlt oder ist kein Objekt",
            }
        )
    else:
        self_name = str(root.get("SELF_NAME") or "").strip()
        if not self_name:
            issues.append(
                {
                    "group": "ROOT",
                    "index": None,
                    "field": "SELF_NAME",
                    "code": "required",
                    "message": "ROOT.SELF_NAME ist leer",
                }
            )

    for group_name, group_value in daten.items():
        g = str(group_name or "").strip()
        if not g:
            issues.append(
                {
                    "group": "ROOT",
                    "index": None,
                    "field": None,
                    "code": "invalid_group",
                    "message": "Leerer Gruppenname ist nicht erlaubt",
                }
            )
            continue
        if g.upper() == "ROOT":
            continue
        if not isinstance(group_value, dict):
            issues.append(
                {
                    "group": g,
                    "index": None,
                    "field": None,
                    "code": "invalid_group_type",
                    "message": f"Gruppe {g} muss ein Objekt sein",
                }
            )
            continue
        for field_name in group_value.keys():
            f = str(field_name or "").strip()
            if not f:
                issues.append(
                    {
                        "group": g,
                        "index": None,
                        "field": None,
                        "code": "invalid_field",
                        "message": f"Leerer Feldname in Gruppe {g}",
                    }
                )

    et = str(edit_type or "").strip().lower()
    if et == "edit_control":
        issues.extend(_collect_edit_control_hints(daten))

    return issues


def extract_dialog_runtime_config(dialog_def: Dict[str, Any]) -> Dict[str, Any]:
    """Extrahiert fÃ¼r die UI relevante Runtime-Konfiguration aus sys_dialogdaten.

    PrimÃ¤rquelle: daten.ROOT
    ZusÃ¤tzlich (neu): TAB_01/TAB_02/... BlÃ¶cke (z.B. fÃ¼r HEAD oder tab-spezifische Optionen).
    """
    daten = dialog_def.get("daten") or {}
    root = dialog_def.get("root") or {}

    def _get_ci(d: Dict[str, Any], *keys: str) -> Any:
        """Case-insensitive Zugriff auf Dict-Keys (unterstÃ¼tzt auch Varianten wie EDIT_TYPE/edit_type)."""
        if not isinstance(d, dict):
            return None
        lower_map = {str(k).lower(): k for k in d.keys()}
        for key in keys:
            if key is None:
                continue
            real = lower_map.get(str(key).lower())
            if real is not None:
                return d.get(real)
        return None

    def _find_tab_block(container: Dict[str, Any], tab_index: int) -> Optional[Dict[str, Any]]:
        """Findet TAB_01/TAB_02/... Block unabhÃ¤ngig von Schreibweise."""
        if not isinstance(container, dict):
            return None
        for k, v in container.items():
            key = str(k)
            if key and __import__("re").match(rf"^tab[_\-]?0*{tab_index}$", key, flags=__import__("re").IGNORECASE):
                return v if isinstance(v, dict) else None
        return None

    def _extract_tabs_from_elements(value: Any) -> Dict[int, Dict[str, Any]]:
        """Extrahiert TAB-BlÃ¶cke aus TAB_ELEMENTS (dict oder list)."""
        out: Dict[int, Dict[str, Any]] = {}

        if isinstance(value, dict):
            fallback_pos = 0
            for key, row in value.items():
                if not isinstance(row, dict):
                    continue

                fallback_pos += 1
                idx_raw = _get_ci(row, "INDEX", "index", "TAB", "tab")
                if idx_raw is None:
                    m = __import__("re").match(r"^tab[_\-]?0*(\d+)$", str(key), flags=__import__("re").IGNORECASE)
                    idx_raw = int(m.group(1)) if m else None
                if idx_raw is None:
                    # GUID-basierte Dict-Schluessel ohne TAB/index explizit sequentiell zuordnen.
                    idx_raw = fallback_pos

                try:
                    idx = int(idx_raw)
                except Exception:
                    continue
                if idx <= 0 or idx > 20:
                    continue
                out[idx] = row
            return out

        if isinstance(value, list):
            for pos, row in enumerate(value, start=1):
                if not isinstance(row, dict):
                    continue
                idx_raw = _get_ci(row, "INDEX", "index", "TAB", "tab") or pos
                try:
                    idx = int(idx_raw)
                except Exception:
                    continue
                if idx <= 0 or idx > 20:
                    continue
                out[idx] = row
            return out

        return out

    def _collect_tab_blocks(root_obj: Dict[str, Any], daten_obj: Dict[str, Any], tabs_count: int) -> Dict[int, Dict[str, Any]]:
        collected: Dict[int, Dict[str, Any]] = {}

        root_tab_elements = _get_ci(root_obj, "TAB_ELEMENTS", "tab_elements")
        daten_tab_elements = _get_ci(daten_obj, "TAB_ELEMENTS", "tab_elements")

        for idx, row in _extract_tabs_from_elements(root_tab_elements).items():
            collected[idx] = row
        for idx, row in _extract_tabs_from_elements(daten_tab_elements).items():
            if idx not in collected:
                collected[idx] = row

        max_tabs = min(20, max(0, int(tabs_count or 0)))
        for i in range(1, max_tabs + 1):
            if i in collected:
                continue
            legacy_block = _find_tab_block(root_obj, i) or _find_tab_block(daten_obj, i)
            if legacy_block:
                collected[i] = legacy_block

        return collected

    root_table = _get_root_table(root)
    dialog_type_raw = _get_ci(root, "DIALOG_TYPE", "dialog_type")
    dialog_type = str(dialog_type_raw or "norm").strip().lower() or "norm"
    if dialog_type not in {"norm", "work", "acti"}:
        dialog_type = "norm"
    if dialog_type == "work":
        # Work-Dialoge laufen immer ueber den Workflow-Draft-Container.
        root_table = "dev_workflow_draft"
    edit_type_raw = _get_ci(root, "EDIT_TYPE", "edit_type")
    edit_type = str(edit_type_raw or "").strip() or "show_json"

    tabs_raw = _get_ci(root, "TABS", "tabs")
    try:
        tabs = int(tabs_raw) if tabs_raw is not None else 2
    except Exception:
        tabs = 2
    if tabs < 0:
        tabs = 0
    if tabs > 20:
        tabs = 20

    tab_modules: List[Dict[str, Any]] = []
    tab_blocks = _collect_tab_blocks(root, daten, tabs)
    if tab_blocks:
        for i in sorted(tab_blocks.keys()):
            block = tab_blocks[i]
            module_raw = _get_ci(block, "MODULE", "module")
            module = str(module_raw or "").strip().lower() or None
            guid_raw = _get_ci(block, "GUID", "guid")
            guid = str(guid_raw).strip() if guid_raw else None
            head_raw = _get_ci(block, "HEAD", "head")
            head = str(head_raw).strip() if head_raw else ""
            table_raw = _get_ci(block, "TABLE", "table")
            table = str(table_raw).strip() if table_raw else ""
            edit_raw = _get_ci(block, "EDIT_TYPE", "edit_type")
            edit = str(edit_raw).strip().lower() if edit_raw else ""
            tab_modules.append(
                {
                    "index": i,
                    "head": head,
                    "module": module,
                    "guid": guid,
                    "table": table,
                    "edit_type": edit,
                }
            )

    view_guid_raw = _get_ci(root, "VIEW_GUID", "view_guid", "VIEWGUID", "viewguid")
    if not view_guid_raw:
        view_guid_raw = _get_ci(daten, "VIEW_GUID", "view_guid", "VIEWGUID", "viewguid")

    frame_guid_raw = _get_ci(root, "FRAME_GUID", "frame_guid")
    if not frame_guid_raw:
        frame_guid_raw = _get_ci(daten, "FRAME_GUID", "frame_guid")

    view_guid = str(view_guid_raw).strip() if view_guid_raw else None
    frame_guid = str(frame_guid_raw).strip() if frame_guid_raw else None

    for tm in tab_modules:
        module = str(tm.get("module") or "").strip().lower()
        guid = str(tm.get("guid") or "").strip()
        module_edit = str(tm.get("edit_type") or "").strip().lower()

        if module == "view" and guid and not view_guid:
            view_guid = guid
        if module == "edit" and guid and not frame_guid:
            frame_guid = guid
        if module in {"edit", "show"} and module_edit and (not edit_type or edit_type == "show_json"):
            edit_type = module_edit

    if not edit_type:
        edit_type = "show_json"

    selection_mode = str(_get_ci(root, "SELECTION_MODE", "selection_mode") or "").strip().lower() or "single"
    if selection_mode not in {"single", "multi"}:
        selection_mode = "single"

    open_edit_raw = _get_ci(root, "OPEN_EDIT", "open_edit")
    if not open_edit_raw:
        view_tab = next((t for t in tab_modules if str(t.get("module") or "").strip().lower() == "view"), None)
        if view_tab:
            block = tab_blocks.get(int(view_tab.get("index") or 0)) if isinstance(tab_blocks, dict) else None
            open_edit_raw = _get_ci(block or {}, "OPEN_EDIT", "open_edit")

    open_edit_mode = str(open_edit_raw or "").strip().lower() or "button"
    # Supported: button (legacy UI), double_click (double click), auto (immediate on select; reserved)
    if open_edit_mode not in {"button", "double_click", "auto"}:
        open_edit_mode = "button"

    return {
        "root_table": root_table,
        "view_guid": view_guid,
        "edit_type": edit_type,
        "frame_guid": frame_guid,
        "tabs": tabs,
        "selection_mode": selection_mode,
        "open_edit_mode": open_edit_mode,
        "dialog_type": dialog_type,
        "tab_modules": tab_modules,
    }

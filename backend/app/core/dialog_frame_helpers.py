"""Frame-/Element-Hilfen fuer den Dialog-Service (reine Verschiebung aus dialog_service.py).

Keine SQL; Datenzugriff laeuft ueber PdvmDatabase.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional
from app.core.pdvm_datenbank import PdvmDatabase
from app.core.control_runtime_service import hydrate_runtime_control_from_row, load_control_rows_bulk


def _normalize_sys_dialog_tab_elements_for_storage(*, daten: Dict[str, Any]) -> Dict[str, Any]:
    """Normalisiert sys_dialogdaten ROOT.TAB_ELEMENTS in ein kanonisches TAB_XX-Format.

    Regeln:
    - akzeptiert dict oder list als Eingabe
    - schreibt immer ROOT.TAB_ELEMENTS als dict mit TAB_01..TAB_NN
    - setzt TAB numerisch fortlaufend
    - ergÃ¤nzt fehlende Felder per Root-Defaults (TABLE/EDIT_TYPE/OPEN_EDIT/SELECTION_MODE)
    - entfernt Legacy ROOT.TAB_XX-BlÃ¶cke
    """
    if not isinstance(daten, dict):
        return daten

    out = dict(daten)
    root = _as_object(out.get("ROOT"))
    if not root:
        return out

    tab_elements_raw = root.get("TAB_ELEMENTS")

    extracted: Dict[int, Dict[str, Any]] = {}
    if isinstance(tab_elements_raw, dict):
        for key, value in tab_elements_raw.items():
            row = _as_object(value)
            if not row:
                continue
            idx_raw = row.get("TAB") if row.get("TAB") is not None else row.get("index")
            idx: Optional[int] = None
            if idx_raw is not None:
                try:
                    idx = int(idx_raw)
                except Exception:
                    idx = None
            if idx is None:
                key_norm = str(key or "").strip().upper()
                if key_norm.startswith("TAB_"):
                    try:
                        idx = int(key_norm.split("_", 1)[1])
                    except Exception:
                        idx = None
            if idx is None or idx <= 0:
                idx = len(extracted) + 1
            extracted[idx] = row
    elif isinstance(tab_elements_raw, list):
        for pos, value in enumerate(tab_elements_raw, start=1):
            row = _as_object(value)
            if not row:
                continue
            idx_raw = row.get("TAB") if row.get("TAB") is not None else row.get("index")
            try:
                idx = int(idx_raw) if idx_raw is not None else pos
            except Exception:
                idx = pos
            if idx <= 0:
                idx = pos
            extracted[idx] = row

    if not extracted and isinstance(tab_elements_raw, dict):
        root["TAB_ELEMENTS"] = {}
        out["ROOT"] = root
        return out

    root_table_default = str(root.get("TABLE") or "").strip()
    root_edit_type_default = str(root.get("EDIT_TYPE") or "").strip()
    root_open_edit_default = str(root.get("OPEN_EDIT") or "").strip()
    root_selection_mode_default = str(root.get("SELECTION_MODE") or "").strip()

    normalized: Dict[str, Dict[str, Any]] = {}
    for pos, idx in enumerate(sorted(extracted.keys()), start=1):
        row = dict(extracted[idx])

        normalized_row: Dict[str, Any] = {
            "TAB": pos,
            "GUID": str(row.get("GUID") or row.get("guid") or "").strip(),
            "HEAD": str(row.get("HEAD") or row.get("head") or "").strip(),
            "TABLE": str(row.get("TABLE") or row.get("table") or root_table_default).strip(),
            "MODULE": str(row.get("MODULE") or row.get("module") or "").strip(),
            "EDIT_TYPE": str(row.get("EDIT_TYPE") or row.get("edit_type") or root_edit_type_default).strip(),
            "OPEN_EDIT": str(row.get("OPEN_EDIT") or row.get("open_edit") or root_open_edit_default).strip(),
            "SELECTION_MODE": str(row.get("SELECTION_MODE") or row.get("selection_mode") or root_selection_mode_default).strip(),
        }

        for key, value in row.items():
            key_up = str(key or "").strip().upper()
            if key_up in normalized_row:
                continue
            normalized_row[str(key)] = value

        normalized[f"TAB_{pos:02d}"] = normalized_row

    root["TAB_ELEMENTS"] = normalized
    root["TABS"] = len(normalized)

    for i in range(1, 21):
        legacy_key = f"TAB_{i:02d}"
        if legacy_key in root and legacy_key != "TAB_ELEMENTS":
            del root[legacy_key]

    out["ROOT"] = root
    return out


def _is_guid(value: Any) -> bool:
    try:
        uuid.UUID(str(value))
        return True
    except Exception:
        return False


def _as_object(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _get_case_insensitive(obj: Dict[str, Any], key: str) -> Any:
    if not isinstance(obj, dict):
        return None
    if key in obj:
        return obj[key]
    key_norm = str(key or "").strip().lower()
    if not key_norm:
        return None
    for k, v in obj.items():
        if str(k or "").strip().lower() == key_norm:
            return v
    return None


def _extract_control_payload_for_validation(control_data: Dict[str, Any]) -> Dict[str, Any]:
    data = _as_object(control_data)

    wrapped = _as_object(data.get("CONTROL"))
    if wrapped:
        return wrapped

    templates = _as_object(data.get("TEMPLATES"))
    template_wrapped = _as_object(templates.get("CONTROL"))
    if template_wrapped:
        return template_wrapped

    flat = dict(data)
    flat.pop("ROOT", None)
    flat.pop("CONTROL", None)
    flat.pop("TEMPLATES", None)
    return _as_object(flat)


def _extract_element_definition_rows_from_frame(frame_daten: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}

    def _push(uid_raw: Any, row_raw: Any) -> None:
        uid = _as_text(uid_raw)
        if not uid:
            return
        row = _as_object(row_raw)
        if not row:
            return
        out[uid] = row

    fd = _as_object(frame_daten)
    root = _as_object(fd.get("ROOT"))

    raw = _get_case_insensitive(root, "ELEMENTS")
    if isinstance(raw, list):
        for entry in raw:
            obj = _as_object(entry)
            uid = _as_text(
                _get_case_insensitive(obj, "uid")
                or _get_case_insensitive(obj, "guid")
                or _get_case_insensitive(obj, "key")
            )
            if not uid:
                continue
            _push(uid, obj)
    elif isinstance(raw, dict):
        for uid, value in raw.items():
            _push(uid, value)

    if out:
        return out

    fields = _as_object(fd.get("FIELDS"))
    root_field = _as_text(_get_case_insensitive(root, "FIELD") or _get_case_insensitive(root, "FELD"))

    def _push_from_collection(collection_raw: Any) -> None:
        collection = _as_object(collection_raw)
        for uid, value in collection.items():
            _push(uid, value)

    if root_field:
        _push_from_collection(_get_case_insensitive(fields, root_field))

    if not out:
        for value in fields.values():
            candidate = _as_object(value)
            if not candidate:
                continue
            if all(isinstance(v, dict) and bool(v) for v in candidate.values()):
                _push_from_collection(candidate)
                if out:
                    break

    return out


async def _validate_element_list_definition_source_for_control(system_pool, *, control_data: Dict[str, Any]) -> None:
    data = _as_object(control_data)
    control = _extract_control_payload_for_validation(data)
    control_type = _as_text(_get_case_insensitive(control, "TYPE")).lower()
    if control_type not in {"element_list", "elemente_list"}:
        return

    configs = _as_object(_get_case_insensitive(control, "CONFIGS"))
    element_ref = _as_object(_get_case_insensitive(configs, "element"))
    ref_key = _as_text(_get_case_insensitive(element_ref, "key"))
    ref_table = _as_text(_get_case_insensitive(element_ref, "table") or "sys_framedaten").lower()

    if not ref_key:
        raise ValueError("Guardrail: CONTROL.TYPE=element_list erfordert CONFIGS.element.key (Frame-GUID).")
    if not _is_guid(ref_key):
        raise ValueError(f"Guardrail: CONFIGS.element.key ist keine gueltige GUID: '{ref_key}'")
    if ref_table and ref_table != "sys_framedaten":
        raise ValueError("Guardrail: CONTROL.TYPE=element_list erwartet CONFIGS.element.table='sys_framedaten'.")

    frame_db = PdvmDatabase("sys_framedaten", system_pool=system_pool, mandant_pool=None)
    frame_row = await frame_db.get_by_uid(uuid.UUID(ref_key))
    if not frame_row:
        raise ValueError(f"Guardrail: Referenziertes Element-Template-Frame nicht gefunden: {ref_key}")

    frame_daten = _as_object(frame_row.get("daten"))
    frame_root = _as_object(frame_daten.get("ROOT"))
    frame_type = _as_text(_get_case_insensitive(frame_root, "FRAME_TYPE")).lower()
    if frame_type not in {"element_list", "element"}:
        raise ValueError(
            "Guardrail: Referenziertes Element-Template-Frame muss ROOT.FRAME_TYPE='element_list' oder 'element' haben."
        )

    definition_rows = _extract_element_definition_rows_from_frame(frame_daten)
    if not definition_rows:
        raise ValueError(
            "Guardrail: FRAME_TYPE=element_list, aber im referenzierten Template-Frame wurden keine ELEMENTS-Definitionen gefunden."
        )

    child_frame_cache: Dict[str, Dict[str, Any]] = {}
    for definition_uid, definition_row in definition_rows.items():
        row = _as_object(definition_row)
        no_fields = bool(
            _get_case_insensitive(row, "no_fields")
            or _get_case_insensitive(row, "NO_FIELDS")
        )

        frame_guid = _as_text(
            _get_case_insensitive(row, "frame")
            or _get_case_insensitive(row, "frame_guid")
        )

        if no_fields:
            continue

        if not frame_guid:
            raise ValueError(
                f"Guardrail: Element-Definition '{definition_uid}' benötigt 'frame'/'frame_guid' oder no_fields=true."
            )
        if not _is_guid(frame_guid):
            raise ValueError(
                f"Guardrail: Element-Definition '{definition_uid}' hat keine gültige frame GUID: '{frame_guid}'"
            )

        child = child_frame_cache.get(frame_guid)
        if child is None:
            child_row = await frame_db.get_by_uid(uuid.UUID(frame_guid))
            if not child_row:
                raise ValueError(
                    f"Guardrail: Element-Definition '{definition_uid}' referenziert unbekanntes Frame: {frame_guid}"
                )
            child = _as_object(child_row.get("daten"))
            child_frame_cache[frame_guid] = child

        child_root = _as_object(child.get("ROOT"))
        child_frame_type = _as_text(_get_case_insensitive(child_root, "FRAME_TYPE")).lower()
        if child_frame_type != "element":
            raise ValueError(
                f"Guardrail: Element-Definition '{definition_uid}' muss auf ein Frame mit ROOT.FRAME_TYPE='element' zeigen."
            )


def _tooltip_ref_from_item(item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    tooltip_raw = item.get("tooltip")
    if isinstance(tooltip_raw, dict):
        return tooltip_raw
    tooltip_raw = item.get("TOOLTIP")
    if isinstance(tooltip_raw, dict):
        return tooltip_raw

    configs = _as_object(item.get("configs"))
    config_ref = configs.get("tooltips")
    if isinstance(config_ref, dict):
        return config_ref
    return None


async def _resolve_tooltip_text_from_ref(gcs, ref: Dict[str, Any]) -> Optional[str]:
    table = _as_text(ref.get("table") or "sys_tooltipdaten").lower()
    key = _as_text(ref.get("key"))
    feld = _as_text(ref.get("feld"))
    preferred_group = _as_text(ref.get("gruppe"))

    if not table or not key or not feld or not _is_guid(key):
        return None

    db = PdvmDatabase(table, system_pool=gcs._system_pool, mandant_pool=gcs._mandant_pool)
    row = await db.get_by_uid(uuid.UUID(key))
    if not row:
        return None

    daten = _as_object(row.get("daten"))
    root = _as_object(daten.get("ROOT"))
    default_group = _as_text(root.get("DEFAULT_LANGUAGE") or "DE-DE")

    groups_to_try: List[str] = []
    for candidate in [preferred_group, default_group, "DE-DE", "EN-EN"]:
        c = _as_text(candidate)
        if c and c not in groups_to_try:
            groups_to_try.append(c)

    for group in groups_to_try:
        group_data = _as_object(daten.get(group))
        entry = group_data.get(feld)
        if isinstance(entry, str):
            text = entry.strip()
            if text:
                return text
        if isinstance(entry, dict):
            for k in ("text", "label", "tooltip", "value"):
                text = _as_text(entry.get(k))
                if text:
                    return text

    return None


def _normalize_element_field_type(value: Any) -> str:
    t = str(value or '').strip().lower()
    if t in {'number', 'int', 'float'}:
        return 'number'
    if t in {'text', 'textarea'}:
        return 'textarea'
    if t in {'dropdown', 'multi_dropdown', 'true_false'}:
        return 'dropdown'
    return 'text'


def _build_element_config_from_frame(frame_daten: Dict[str, Any]) -> Dict[str, Any]:
    fields = _as_object(frame_daten.get('FIELDS'))
    element_fields = []
    element_template: Dict[str, Any] = {}

    for key, value in fields.items():
        item = _as_object(value)
        name = str(item.get('name') or item.get('feld') or key).strip()
        if not name:
            continue
        label = str(item.get('label') or name).strip()
        field_type = _normalize_element_field_type(item.get('type'))
        options = None
        if field_type == 'dropdown':
            options = item.get('options')
            if not options:
                options = _as_object(item.get('configs')).get('dropdown', {}).get('options')

        entry = {'name': name, 'label': label, 'type': field_type}
        if options:
            entry['options'] = options
        element_fields.append(entry)
        element_template[name] = ''

    element_fields.sort(key=lambda x: x.get('label', '').lower())
    return {
        'element_fields': element_fields,
        'element_template': element_template,
    }


async def _resolve_frame_fields(gcs, daten: Dict[str, Any], visited: Optional[set[str]] = None) -> Dict[str, Any]:
    fields = _as_object(daten.get("FIELDS"))
    if not fields:
        return daten

    if visited is None:
        visited = set()

    # Alle Controls des Frames mit einer Abfrage laden (statt je Feld eine Abfrage).
    control_rows = await load_control_rows_bulk(
        [
            dict_ref if dict_ref else key
            for key, value in fields.items()
            for dict_ref in [_as_object(value).get("dict_ref")]
            if _is_guid(dict_ref if dict_ref else key)
        ],
        system_pool=gcs._system_pool,
        mandant_pool=gcs._mandant_pool,
    )

    merged_fields: Dict[str, Any] = {}
    for key, value in fields.items():
        item = _as_object(value)
        dict_ref = item.get("dict_ref")
        base_guid = dict_ref if dict_ref else key

        if _is_guid(base_guid):
            merged = hydrate_runtime_control_from_row(
                control_rows.get(uuid.UUID(str(base_guid))),
                override=item,
            )
            if merged:
                if dict_ref:
                    merged["dict_ref"] = str(dict_ref)
                merged_fields[key] = merged
                continue

        merged_fields[key] = item

    # Tooltip-Referenzen in Laufzeit-Tooltiptext umwandeln (Storage bleibt Referenz).
    for key, value in list(merged_fields.items()):
        item = _as_object(value)
        ref = _tooltip_ref_from_item(item)
        if not ref:
            continue
        text = await _resolve_tooltip_text_from_ref(gcs, ref)
        if not text:
            continue
        next_item = dict(item)
        next_item["TOOLTIP_REF"] = ref
        next_item["tooltip"] = text
        next_item["TOOLTIP"] = text
        merged_fields[key] = next_item

    out = dict(daten)
    # Resolve element_list to a referenced frame when configured.
    for key, value in merged_fields.items():
        item = _as_object(value)
        t = str(item.get('type') or '').strip().lower()
        if t not in {'element_list', 'elemente_list'}:
            continue
        configs = _as_object(item.get('configs'))
        element_frame_guid = configs.get('element_frame_guid') or configs.get('element_frame')
        if not element_frame_guid or not _is_guid(element_frame_guid):
            continue
        if str(element_frame_guid) in visited:
            continue
        visited.add(str(element_frame_guid))

        frame_db = PdvmDatabase("sys_framedaten", system_pool=gcs._system_pool, mandant_pool=gcs._mandant_pool)
        frame_row = await frame_db.get_by_uid(uuid.UUID(str(element_frame_guid)))
        if not frame_row:
            continue
        frame_daten = frame_row.get('daten') or {}
        frame_daten = await _resolve_frame_fields(gcs, frame_daten, visited)
        element_cfg = _build_element_config_from_frame(frame_daten)
        configs = {**configs, **element_cfg, 'element_frame_guid': str(element_frame_guid)}
        merged_fields[key] = {**item, 'configs': configs}

    out["FIELDS"] = merged_fields
    return out

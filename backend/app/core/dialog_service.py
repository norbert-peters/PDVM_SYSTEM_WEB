"""Dialog Service

Architekturregel: keine SQL in Routern.
Dieses Modul kapselt Zugriff auf sys_dialogdaten / sys_framedaten und stellt
Hilfsfunktionen fÃ¼r den ersten Dialog-MVP bereit.

MVP (Phase 0):
- DialogDefinition laden (sys_dialogdaten)
- FrameDefinition laden (sys_framedaten)
- Dialog-View: Root-Tabelle nur mit Systemspalten uid + name
- Dialog-Edit: show_json -> liefert vollstÃ¤ndigen Datensatz (daten JSON)
"""

from __future__ import annotations

import copy
import uuid
import secrets
import string
import json
from typing import Any, Dict, List, Optional

from app.core.pdvm_datenbank import PdvmDatabase
from app.core.control_runtime_service import (
    hydrate_runtime_control_by_uid,
    merge_control_runtime_with_override,
)
from app.core.central_write_service import create_record_central, update_record_central
from app.core.pdvm_central_datenbank import PdvmCentralDatabase
from app.core.pdvm_central_benutzer import PdvmCentralBenutzer
from app.core.user_manager import UserManager
from app.core.database import DatabasePool


_DEFAULT_TEMPLATE_UID = uuid.UUID("66666666-6666-6666-6666-666666666666")
_MODUL_TEMPLATE_UID = uuid.UUID("55555555-5555-5555-5555-555555555555")
_DRAFT_FAKE_GUID = "66666666-6666-6666-6666-666666666662"


async def _resolve_groups_from_templates(
    gcs,
    *,
    root_table: str,
) -> Dict[str, Any]:
    """Linearer Neuanlage-Algorithmus fuer alle Tabellen ausser asy_benutzer.

    Ablauf:
    1) Basis immer aus UID 555 derselben Tabelle
    2) ROOT wird spaeter zentral ueber _apply_root_identity gesetzt
    3) Leere Gruppen der 555-Basis werden aus 666.(TEMPLATE|TEMPLATES) aufgefuellt
    4) Fehlt die gleichnamige Gruppe in 666 TEMPLATE, wird ein Fehler geworfen
    """
    if str(root_table or "").strip().lower() == "asy_benutzer":
        return {}

    _, basis_555_daten = await _load_template_row_and_daten(
        gcs,
        root_table=root_table,
        template_uuid=_MODUL_TEMPLATE_UID,
    )
    _, basis_666_daten = await _load_template_row_and_daten(
        gcs,
        root_table=root_table,
        template_uuid=_DEFAULT_TEMPLATE_UID,
    )

    if not isinstance(basis_555_daten, dict):
        raise ValueError("555-Basis 'daten' ist kein JSON-Objekt")
    if not isinstance(basis_666_daten, dict):
        raise ValueError("666-Basis 'daten' ist kein JSON-Objekt")

    out = copy.deepcopy(basis_555_daten)

    template_groups = basis_666_daten.get("TEMPLATE")
    if not isinstance(template_groups, dict):
        template_groups = basis_666_daten.get("TEMPLATES")
    if not isinstance(template_groups, dict):
        raise ValueError("666-Basis enthaelt keine Gruppe TEMPLATE/TEMPLATES")

    template_key_map = {str(k).strip().lower(): k for k in template_groups.keys() if str(k).strip()}

    for group_name, group_value in list(out.items()):
        group_norm = str(group_name or "").strip()
        if not group_norm:
            continue
        if group_norm.upper() == "ROOT":
            continue

        is_empty_group = group_value is None or (isinstance(group_value, dict) and len(group_value) == 0)
        if not is_empty_group:
            continue

        template_real_key = template_key_map.get(group_norm.lower())
        if template_real_key is None:
            raise ValueError(
                f"Leere Gruppe '{group_norm}' in 555, aber keine Vorlage in 666 TEMPLATE/TEMPLATES"
            )

        template_group_value = template_groups.get(template_real_key)
        if not isinstance(template_group_value, dict):
            raise ValueError(
                f"Vorlage fuer Gruppe '{group_norm}' in 666 TEMPLATE/TEMPLATES ist kein Objekt"
            )

        out[group_name] = copy.deepcopy(template_group_value)

    return out


async def _resolve_named_group_lists_from_elements(
    system_pool,
    *,
    daten_copy: Dict[str, Any],
) -> Dict[str, Any]:
    """FÃ¼gt benannte Gruppenlisten aus 555...daten.ELEMENTS ein.

    Ziel: Auf derselben Ebene (Top-Level) mehrere Gruppen wie
    PER_PERSONEN, FIN_BASIS etc. linear hinzufÃ¼gen.

    Datenmodell (555...daten.ELEMENTS):
    {
      "GROUP_LISTS": {
        "PER_PERSONEN": {
          "GROUP_NAME": "PER_PERSONEN",
          "GROUP_TEMPLATE": { ... },
          "AUTO_APPLY": true
        },
        "FIN_BASIS": {
          "GROUP_TEMPLATE": { ... }
        }
      }
    }

    Auswahlregel:
    - ROOT.GROUP_LISTS (Liste mit Namen) = explizite Auswahl
    - sonst: alle EintrÃ¤ge mit AUTO_APPLY=true

    Merge-Regel (linear):
    - GROUP_TEMPLATE als Default
    - vorhandene Basiswerte der Zielgruppe Ã¼berschreiben Defaults
    """
    if not isinstance(daten_copy, dict):
        return daten_copy

    db = PdvmDatabase("sys_control_dict", system_pool=system_pool, mandant_pool=None)
    modul_template_row = await db.get_by_uid(_MODUL_TEMPLATE_UID)
    if not modul_template_row:
        raise KeyError(f"Modul-Template nicht gefunden: {_MODUL_TEMPLATE_UID}")

    modul_template_daten = modul_template_row.get("daten")
    if isinstance(modul_template_daten, str):
        modul_template_daten = json.loads(modul_template_daten)
    if not isinstance(modul_template_daten, dict):
        raise ValueError("Modul-Template 'daten' ist kein JSON-Objekt")

    elements = modul_template_daten.get("ELEMENTS")
    if not isinstance(elements, dict):
        return daten_copy

    group_lists = elements.get("GROUP_LISTS")
    if not isinstance(group_lists, dict) or not group_lists:
        return daten_copy

    out = copy.deepcopy(daten_copy)

    root = out.get("ROOT") if isinstance(out.get("ROOT"), dict) else {}
    selected_raw = root.get("GROUP_LISTS")
    selected_names: List[str] = []
    if isinstance(selected_raw, list):
        selected_names = [str(v).strip() for v in selected_raw if str(v).strip()]

    selected_norm = {name.lower() for name in selected_names}

    for list_key, definition in group_lists.items():
        if not isinstance(definition, dict):
            continue

        group_name = str(definition.get("GROUP_NAME") or list_key or "").strip()
        if not group_name:
            continue
        if group_name.upper() in {"ROOT", "TEMPLATES", "ELEMENTS"}:
            continue

        auto_apply = bool(definition.get("AUTO_APPLY", False))
        if selected_norm:
            if group_name.lower() not in selected_norm and str(list_key).strip().lower() not in selected_norm:
                continue
        elif not auto_apply:
            continue

        group_template = definition.get("GROUP_TEMPLATE")
        if not isinstance(group_template, dict):
            continue

        existing_group_value = out.get(group_name)
        merged_group = copy.deepcopy(group_template)
        if isinstance(existing_group_value, dict):
            merged_group.update(existing_group_value)

        out[group_name] = merged_group

    return out


def _strip_template_meta_groups(daten_copy: Dict[str, Any]) -> Dict[str, Any]:
    """Entfernt reine Template-Metagruppen aus instanziierten DatensÃ¤tzen."""
    if not isinstance(daten_copy, dict):
        return daten_copy

    out = copy.deepcopy(daten_copy)
    out.pop("TEMPLATES", None)
    out.pop("ELEMENTS", None)
    return out


def _apply_root_identity(root: Dict[str, Any], *, self_guid: str, self_name: str, root_patch: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Appliziert ROOT-Patch ohne SELF_GUID/SELF_NAME zu Ã¼berschreiben.

    Regel fÃ¼r Neuer-Satz: nur bereits vorhandene ROOT-Felder dÃ¼rfen Ã¼berschrieben
    werden (keine neuen ROOT-Keys aus root_patch einfÃ¼hren).
    """
    out = dict(root or {})

    if root_patch and isinstance(root_patch, dict):
        for k, v in root_patch.items():
            key_upper = str(k or "").strip().upper()
            if key_upper in {"SELF_GUID", "SELF_NAME"}:
                continue
            if k in out:
                out[k] = v

    out["SELF_GUID"] = self_guid
    out["SELF_NAME"] = self_name
    return out


def _compute_overrides_from_defaults(effective: Dict[str, Any], defaults: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(effective, dict):
        return {}
    if not isinstance(defaults, dict):
        return dict(effective)

    overrides: Dict[str, Any] = {}
    for key, value in effective.items():
        if key not in defaults or defaults.get(key) != value:
            overrides[key] = value
    return overrides


async def _load_control_defaults_for_modul(system_pool, *, modul_type: str) -> Dict[str, Any]:
    modul_norm = str(modul_type or "").strip().lower()
    if not modul_norm:
        return {}

    db = PdvmDatabase("sys_control_dict", system_pool=system_pool, mandant_pool=None)
    row = await db.get_by_uid(_MODUL_TEMPLATE_UID)
    if not row:
        return {}

    data = row.get("daten") or {}
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except Exception:
            data = {}
    if not isinstance(data, dict):
        return {}

    defaults: Dict[str, Any] = {}

    templates = data.get("TEMPLATES")
    if isinstance(templates, dict):
        tpl_control = templates.get("CONTROL")
        if isinstance(tpl_control, dict):
            defaults.update(copy.deepcopy(tpl_control))

    modul_map = data.get("MODUL")
    if isinstance(modul_map, dict):
        ci_map = {str(k).strip().lower(): k for k in modul_map.keys()}
        real_key = ci_map.get(modul_norm)
        if real_key is not None:
            modul_defaults = modul_map.get(real_key)
            if isinstance(modul_defaults, dict):
                defaults.update(copy.deepcopy(modul_defaults))

    defaults["modul_type"] = modul_norm
    return defaults


async def _load_control_base_template(system_pool) -> Dict[str, Any]:
    db = PdvmDatabase("sys_control_dict", system_pool=system_pool, mandant_pool=None)
    row = await db.get_by_uid(_DEFAULT_TEMPLATE_UID)
    if not row:
        return {}

    data = row.get("daten") or {}
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except Exception:
            data = {}
    return data if isinstance(data, dict) else {}


async def _resolve_control_effective_data(system_pool, *, control_data: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(control_data, dict):
        return {}

    has_root = isinstance(control_data.get("ROOT"), dict)
    has_control = isinstance(control_data.get("CONTROL"), dict)
    templates = control_data.get("TEMPLATES") if isinstance(control_data.get("TEMPLATES"), dict) else {}
    has_template_control = isinstance(templates.get("CONTROL"), dict)
    root_in = control_data.get("ROOT") if has_root else {}
    control_in = control_data.get("CONTROL") if has_control else {}
    if not control_in and has_template_control:
        control_in = templates.get("CONTROL") or {}

    # Legacy/Fallback: flache CONTROL-Keys ohne Wrapper auf Top-Level.
    if not control_in and not has_root and not has_control and not has_template_control:
        flat = dict(control_data)
        flat.pop("ROOT", None)
        flat.pop("CONTROL", None)
        flat.pop("TEMPLATES", None)
        if flat:
            control_in = flat

    control_signature_keys = {"FIELD", "FELD", "TYPE", "LABEL", "GRUPPE", "TABLE", "CONFIGS"}
    is_control_like = isinstance(control_in, dict) and any(
        str(k or "").strip().upper() in control_signature_keys for k in control_in.keys()
    )

    if has_control or has_template_control or is_control_like:
        base = await _load_control_base_template(system_pool)
        base_root = base.get("ROOT") if isinstance(base.get("ROOT"), dict) else {}
        base_control = base.get("CONTROL") if isinstance(base.get("CONTROL"), dict) else {}

        merged_root = copy.deepcopy(base_root)
        if isinstance(root_in, dict):
            merged_root.update(root_in)

        merged_control = copy.deepcopy(base_control)
        if isinstance(control_in, dict):
            merged_control.update(control_in)
        return {
            "ROOT": merged_root,
            "CONTROL": merged_control,
        }

    modul_type = str(control_data.get("modul_type") or "").strip().lower()
    if not modul_type:
        return dict(control_data)

    defaults = await _load_control_defaults_for_modul(system_pool, modul_type=modul_type)
    if not defaults:
        return dict(control_data)

    effective = copy.deepcopy(defaults)
    effective.update(control_data)
    return effective


async def _normalize_control_data_for_storage(system_pool, *, control_data: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(control_data, dict):
        return {}

    has_root = isinstance(control_data.get("ROOT"), dict)
    has_control = isinstance(control_data.get("CONTROL"), dict)
    templates = control_data.get("TEMPLATES") if isinstance(control_data.get("TEMPLATES"), dict) else {}
    has_template_control = isinstance(templates.get("CONTROL"), dict)

    control_candidate = control_data.get("CONTROL") if has_control else {}
    if (not isinstance(control_candidate, dict) or not control_candidate) and has_template_control:
        control_candidate = templates.get("CONTROL")
    control_candidate = _as_object(control_candidate)

    control_signature_keys = {"FIELD", "FELD", "TYPE", "LABEL", "GRUPPE", "TABLE", "CONFIGS"}
    is_control_like = any(str(k or "").strip().upper() in control_signature_keys for k in control_candidate.keys())

    if has_control or has_template_control or is_control_like:
        base = await _load_control_base_template(system_pool)
        base_root = base.get("ROOT") if isinstance(base.get("ROOT"), dict) else {}
        base_control = base.get("CONTROL") if isinstance(base.get("CONTROL"), dict) else {}

        root_in = control_data.get("ROOT") if has_root else {}
        control_in = control_data.get("CONTROL") if has_control else {}
        if not isinstance(control_in, dict) or not control_in:
            control_in = templates.get("CONTROL") if has_template_control else {}

        merged_root = copy.deepcopy(base_root)
        if isinstance(root_in, dict):
            merged_root.update(root_in)

        merged_control = copy.deepcopy(base_control)
        if isinstance(control_in, dict):
            merged_control.update(control_in)

        normalized = {
            "ROOT": merged_root,
            "CONTROL": merged_control,
        }
        await _validate_element_list_definition_source_for_control(system_pool, control_data=normalized)

        return normalized

    modul_type = str(control_data.get("modul_type") or "").strip().lower()
    if not modul_type:
        return dict(control_data)

    defaults = await _load_control_defaults_for_modul(system_pool, modul_type=modul_type)
    if not defaults:
        return dict(control_data)

    overrides = _compute_overrides_from_defaults(control_data, defaults)
    overrides["modul_type"] = modul_type
    return overrides


async def _normalize_new_record_daten_unified(gcs, *, daten: Dict[str, Any]) -> Dict[str, Any]:
    """Einheitliche Normalisierung für Neuanlage-Datensätze (tabellenunabhängig)."""
    out = _as_object(daten)

    # 1) Control-Payloads kanonisieren (ROOT + CONTROL), falls control-artig.
    out = await _normalize_control_data_for_storage(
        gcs._system_pool,
        control_data=_as_object(out),
    )

    # 2) Frame-FIELDS normalisieren (nur wenn FIELDS-Struktur vorhanden).
    out = await _normalize_frame_fields_for_storage(
        gcs,
        daten=_as_object(out),
    )

    # 3) Dialog-TAB_ELEMENTS kanonisieren (nur wenn entsprechende Struktur vorhanden).
    out = _normalize_sys_dialog_tab_elements_for_storage(
        daten=_as_object(out),
    )

    # 4) Template-Metagruppen duerfen in instanziierten Datensaetzen nicht persistiert werden.
    out = _strip_template_meta_groups(_as_object(out))

    return out


async def _normalize_frame_fields_for_storage(gcs, *, daten: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(daten, dict):
        return daten

    out = dict(daten)
    fields = _as_object(out.get("FIELDS"))
    if not fields:
        return out

    normalized_fields: Dict[str, Any] = {}
    for key, value in fields.items():
        item = _as_object(value)
        dict_ref = item.get("dict_ref")
        base_guid = dict_ref if dict_ref else key

        if _is_guid(base_guid):
            base_runtime = await hydrate_runtime_control_by_uid(
                str(base_guid),
                override=None,
                system_pool=gcs._system_pool,
                mandant_pool=gcs._mandant_pool,
            )
            if base_runtime:
                merged_effective = merge_control_runtime_with_override(base_runtime, item)
                overrides = _compute_overrides_from_defaults(merged_effective, base_runtime)
                if dict_ref:
                    overrides["dict_ref"] = str(dict_ref)
                normalized_fields[key] = overrides
                continue

        normalized_fields[key] = item

    out["FIELDS"] = normalized_fields
    return out


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


class ModulSelectionRequiredException(Exception):
    """Exception wenn Modul-Auswahl erforderlich ist aber fehlt"""
    def __init__(self, modul_group_key: str, available_moduls: List[str]):
        self.modul_group_key = modul_group_key
        self.available_moduls = available_moduls
        super().__init__(
            f"Template enthÃ¤lt Gruppe 'MODUL' in '{modul_group_key}', "
            f"aber modul_type wurde nicht Ã¼bergeben. "
            f"VerfÃ¼gbare Module: {available_moduls}"
        )


async def _resolve_modul_template(
    system_pool,
    *,
    daten_copy: Dict[str, Any],
    modul_type: Optional[str] = None,
) -> Dict[str, Any]:
    """GENERISCHE MODUL-TEMPLATE-MERGE-FUNKTION
    
        PrÃ¼ft ob im Template eine Gruppe "MODUL" existiert.
        Wenn ja:
            1. Wenn modul_type gegeben â†’ Merge mit Template 555555...MODUL[type]
            2. Wenn modul_type fehlt â†’ deterministische Standardauswahl (linearer Fallback)
    
    Funktioniert fÃ¼r ALLE Tabellen (sys_control_dict, sys_framedaten, etc.)
    
    Args:
        system_pool: DB Pool
        daten_copy: Template-Daten (Deep Copy von 666666...)
        modul_type: GewÃ¤hlter Modul-Typ (z.B. "edit", "view", "tabs")
    
    Returns:
        Modified daten_copy mit MODUL-Gruppe ersetzt
    
    Raises:
        ValueError: Wenn angeforderter Modul-Typ nicht existiert
    """
    # 1. PrÃ¼fe: Gibt es eine Gruppe "MODUL" im Template?
    has_modul = False
    modul_group_key = None
    
    for key, value in daten_copy.items():
        if key.upper() == "ROOT":
            continue
        if isinstance(value, dict) and "MODUL" in value:
            has_modul = True
            modul_group_key = key
            break
    
    if not has_modul:
        # Kein MODUL â†’ Normale Template-Copy ohne Merge
        return daten_copy
    
    # 2. MODUL gefunden â†’ Lade Template 555... um verfÃ¼gbare Module zu kennen
    db = PdvmDatabase("sys_control_dict", system_pool=system_pool, mandant_pool=None)
    modul_template_row = await db.get_by_uid(_MODUL_TEMPLATE_UID)
    
    if not modul_template_row:
        raise KeyError(f"Modul-Template nicht gefunden: {_MODUL_TEMPLATE_UID}")
    
    modul_template_daten = modul_template_row.get("daten")
    if isinstance(modul_template_daten, str):
        modul_template_daten = json.loads(modul_template_daten)
    
    if not isinstance(modul_template_daten, dict):
        raise ValueError("Modul-Template 'daten' ist kein JSON-Objekt")
    
    modul_section = modul_template_daten.get("MODUL", {})
    if not isinstance(modul_section, dict):
        raise ValueError("Modul-Template 'MODUL' ist kein Dict")
    
    available_moduls = [str(k) for k in modul_section.keys()]
    available_moduls_map = {str(k).strip().lower(): k for k in modul_section.keys()}

    # 3. Linearer Fallback: fehlendes modul_type wird automatisch gesetzt
    modul_type_norm = str(modul_type or "").strip().lower()
    if not modul_type_norm:
        preferred_order = ("edit", "view", "tabs")
        selected = None
        for preferred in preferred_order:
            if preferred in available_moduls_map:
                selected = available_moduls_map[preferred]
                break
        if selected is None:
            if not available_moduls:
                raise ValueError("Modul-Template enthÃ¤lt keine MODUL-EintrÃ¤ge")
            selected = available_moduls[0]
        modul_key = selected
        modul_type_norm = str(selected).strip().lower()
    else:
        if modul_type_norm not in available_moduls_map:
            available = list(modul_section.keys())
            raise ValueError(
                f"Modul-Typ '{modul_type_norm}' nicht gefunden in Template. "
                f"VerfÃ¼gbar: {available}"
            )
        modul_key = available_moduls_map[modul_type_norm]

    if modul_key not in modul_section:
        available = list(modul_section.keys())
        raise ValueError(
            f"Modul-Typ '{modul_key}' nicht gefunden in Template. "
            f"VerfÃ¼gbar: {available}"
        )

    modul_data = modul_section[modul_key]
    if not isinstance(modul_data, dict):
        raise ValueError(f"MODUL[{modul_type_norm}] ist kein Dict")
    
    # 5. Ersetze komplette "MODUL"-Gruppe mit Template-Daten
    daten_copy[modul_group_key]["MODUL"] = copy.deepcopy(modul_data)
    
    # 6. Setze MODUL_TYPE in ROOT (fÃ¼r spÃ¤tere Referenz)
    if "ROOT" not in daten_copy:
        daten_copy["ROOT"] = {}
    daten_copy["ROOT"]["MODUL_TYPE"] = modul_type_norm
    
    return daten_copy


def _generate_temp_password(length: int = 12) -> str:
    if length < 12:
        length = 12
    lower = string.ascii_lowercase
    upper = string.ascii_uppercase
    digits = string.digits
    special = "@$!%*?&"

    chars = [
        secrets.choice(lower),
        secrets.choice(upper),
        secrets.choice(digits),
        secrets.choice(special),
    ]
    pool = lower + upper + digits + special
    while len(chars) < length:
        chars.append(secrets.choice(pool))

    secrets.SystemRandom().shuffle(chars)
    return "".join(chars)


def _get_root_table(root: Dict[str, Any]) -> str:
    table = str(root.get("TABLE") or root.get("ROOT_TABLE") or "").strip()
    return table


async def load_dialog_definition(gcs, dialog_uuid: uuid.UUID) -> Dict[str, Any]:
    db = PdvmDatabase("sys_dialogdaten", system_pool=gcs._system_pool, mandant_pool=gcs._mandant_pool)
    row = await db.get_by_uid(dialog_uuid)
    if not row:
        raise KeyError(f"Dialog nicht gefunden: {dialog_uuid}")

    daten = row.get("daten") or {}
    if isinstance(daten, str):
        try:
            daten = json.loads(daten)
        except Exception:
            daten = {}
    if not isinstance(daten, dict):
        daten = {}

    root = daten.get("ROOT") or {}
    if not isinstance(root, dict):
        root = {}

    return {
        "uid": str(row.get("uid")),
        "name": row.get("name") or "",
        "daten": daten,
        "root": root,
    }


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

    merged_fields: Dict[str, Any] = {}
    for key, value in fields.items():
        item = _as_object(value)
        dict_ref = item.get("dict_ref")
        base_guid = dict_ref if dict_ref else key

        if _is_guid(base_guid):
            merged = await hydrate_runtime_control_by_uid(
                str(base_guid),
                override=item,
                system_pool=gcs._system_pool,
                mandant_pool=gcs._mandant_pool,
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


async def load_frame_definition(gcs, frame_uuid: uuid.UUID) -> Dict[str, Any]:
    db = PdvmDatabase("sys_framedaten", system_pool=gcs._system_pool, mandant_pool=gcs._mandant_pool)
    row = await db.get_by_uid(frame_uuid)
    if not row:
        raise KeyError(f"Frame nicht gefunden: {frame_uuid}")

    daten = row.get("daten") or {}
    daten = await _resolve_frame_fields(gcs, daten)
    root = daten.get("ROOT") or {}

    return {
        "uid": str(row.get("uid")),
        "name": row.get("name") or "",
        "daten": daten,
        "root": root,
    }


async def load_dialog_rows_uid_name(
    gcs,
    *,
    root_table: str,
    limit: int = 200,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    if not root_table:
        return []

    db = PdvmDatabase(root_table, system_pool=gcs._system_pool, mandant_pool=gcs._mandant_pool)

    # MVP: keine Filter/Sort/Group Logik; nur Name/UID anzeigen.
    raw_rows = await db.get_all(order_by="name ASC", limit=limit, offset=offset)

    return [
        {
            "uid": str(r.get("uid")),
            "name": r.get("name") or "",
        }
        for r in raw_rows
    ]


async def load_dialog_record(
    gcs,
    *,
    root_table: str,
    record_uuid: uuid.UUID,
    resolve_effective: bool = True,
) -> Dict[str, Any]:
    if not root_table:
        raise KeyError("ROOT.TABLE ist leer")

    # asy_benutzer: Sonderfall mit zusÃ¤tzlichen Spalten (email/benutzer/passwort)
    if str(root_table).strip().lower() == "asy_benutzer":
        benutzer_mgr = PdvmCentralBenutzer(record_uuid)
        row = await benutzer_mgr.get_user()
        if not row:
            raise KeyError(f"Datensatz nicht gefunden: {record_uuid}")

        daten = row.get("daten") or {}
        if not isinstance(daten, dict):
            daten = {}

        # SYSTEM-Gruppe mit Spalten (benutzer als Spalte)
        system_group = daten.get("SYSTEM") if isinstance(daten.get("SYSTEM"), dict) else {}
        if not isinstance(system_group, dict):
            system_group = {}
        if row.get("benutzer") is not None:
            system_group["BENUTZER"] = row.get("benutzer")
        daten["SYSTEM"] = system_group

        return {
            "uid": str(row.get("uid")),
            "name": row.get("name") or "",
            "daten": daten,
            "historisch": int(row.get("historisch") or 0),
            "modified_at": row.get("modified_at").isoformat() if row.get("modified_at") else None,
        }

    db = PdvmDatabase(root_table, system_pool=gcs._system_pool, mandant_pool=gcs._mandant_pool)
    row = await db.get_by_uid(record_uuid)
    if not row:
        raise KeyError(f"Datensatz nicht gefunden: {record_uuid}")

    daten = row.get("daten") or {}
    table_norm = str(root_table).strip().lower()
    if resolve_effective and table_norm == "sys_control_dict":
        daten = await _resolve_control_effective_data(gcs._system_pool, control_data=_as_object(daten))
    elif resolve_effective and table_norm == "sys_framedaten":
        daten = await _resolve_frame_fields(gcs, _as_object(daten))

    # Einheitliches Payload fÃ¼r show_json
    return {
        "uid": str(row.get("uid")),
        "name": row.get("name") or "",
        "daten": daten,
        "historisch": int(row.get("historisch") or 0),
        "modified_at": row.get("modified_at").isoformat() if row.get("modified_at") else None,
    }


async def update_dialog_record_json(
    gcs,
    *,
    root_table: str,
    record_uuid: uuid.UUID,
    daten: Dict[str, Any],
    resolve_response_effective: bool = True,
) -> Dict[str, Any]:
    """Aktualisiert NUR das JSONB-Feld 'daten' eines Datensatzes.

    Gedacht fÃ¼r edit_type='edit_json' (Ã¤hnlich PostgreSQL JSON Editor).
    """
    if not root_table:
        raise KeyError("ROOT.TABLE ist leer")

    if daten is None or not isinstance(daten, dict):
        raise ValueError("daten muss ein JSON-Objekt (dict) sein")

    table_norm = str(root_table).strip().lower()
    daten_to_store = dict(daten)
    if table_norm == "sys_control_dict":
        await _validate_element_list_definition_source_for_control(
            gcs._system_pool,
            control_data=_as_object(daten_to_store),
        )

    db = PdvmDatabase(root_table, system_pool=gcs._system_pool, mandant_pool=gcs._mandant_pool)
    existing = await db.get_by_uid(record_uuid)
    if not existing:
        raise KeyError(f"Datensatz nicht gefunden: {record_uuid}")

    table_norm = str(root_table).strip().lower()
    daten_to_store = dict(daten)
    if table_norm == "sys_control_dict":
        daten_to_store = await _normalize_control_data_for_storage(
            gcs._system_pool,
            control_data=_as_object(daten_to_store),
        )
    elif table_norm == "sys_framedaten":
        daten_to_store = await _normalize_frame_fields_for_storage(
            gcs,
            daten=_as_object(daten_to_store),
        )
    elif table_norm == "sys_dialogdaten":
        daten_to_store = _normalize_sys_dialog_tab_elements_for_storage(
            daten=_as_object(daten_to_store),
        )

    # Name/historisch bleiben unverÃ¤ndert.
    await update_record_central(
        table_name=root_table,
        uid=record_uuid,
        daten=daten_to_store,
        name=existing.get("name"),
        historisch=existing.get("historisch"),
        gcs=gcs,
    )

    return await load_dialog_record(
        gcs,
        root_table=root_table,
        record_uuid=record_uuid,
        resolve_effective=resolve_response_effective,
    )


async def update_dialog_record_central(
    gcs,
    *,
    root_table: str,
    record_uuid: uuid.UUID,
    daten: Dict[str, Any],
) -> Dict[str, Any]:
    """Aktualisiert Datensatz via PdvmCentralDatabase (Pflicht fÃ¼r edit_user).

    Regeln:
    - Werte werden per set_value(gruppe, feld) gesetzt
    - SYSTEM-Gruppe ist fÃ¼r Tabellen-Spalten reserviert (SonderfÃ¤lle)
    - asy_benutzer: Spalten email/benutzer werden zusÃ¤tzlich synchronisiert
    """
    if not root_table:
        raise KeyError("ROOT.TABLE ist leer")

    if daten is None or not isinstance(daten, dict):
        raise ValueError("daten muss ein JSON-Objekt (dict) sein")

    table_norm = str(root_table).strip().lower()
    daten_to_store = dict(daten)

    if table_norm == "sys_control_dict":
        await _validate_element_list_definition_source_for_control(
            gcs._system_pool,
            control_data=_as_object(daten_to_store),
        )
        daten_to_store = await _normalize_control_data_for_storage(
            gcs._system_pool,
            control_data=_as_object(daten_to_store),
        )
    elif table_norm == "sys_framedaten":
        daten_to_store = await _normalize_frame_fields_for_storage(
            gcs,
            daten=_as_object(daten_to_store),
        )
    elif table_norm == "sys_dialogdaten":
        daten_to_store = _normalize_sys_dialog_tab_elements_for_storage(
            daten=_as_object(daten_to_store),
        )

    def _parse_pdvm_timestamp(value: Any) -> Optional[float]:
        if value is None:
            return None
        try:
            ts = float(value)
        except Exception:
            return None
        if ts < 1001.0:
            return None
        return ts

    def _extract_linear_value_and_timeline(raw_value: Any) -> tuple[Any, List[tuple[float, Any]]]:
        if not isinstance(raw_value, dict):
            return raw_value, []

        value_container = raw_value.get("VALUE")
        if isinstance(value_container, dict):
            envelope = value_container
            time_key_raw = raw_value.get("VALUE_TIME_KEY")
        else:
            # Direkte Envelope-Form: {"ORIGINAL": ..., "2026063.5": ...}
            has_original = "ORIGINAL" in raw_value
            has_ts_keys = any(_parse_pdvm_timestamp(k) is not None for k in raw_value.keys())
            if not has_original and not has_ts_keys:
                return raw_value, []
            envelope = raw_value
            time_key_raw = raw_value.get("VALUE_TIME_KEY")

        original_value = envelope.get("ORIGINAL")
        timeline: List[tuple[float, Any]] = []

        for key, value in envelope.items():
            if str(key).strip().upper() == "ORIGINAL":
                continue
            parsed_ts = _parse_pdvm_timestamp(key)
            if parsed_ts is None:
                continue
            timeline.append((parsed_ts, value))

        timeline.sort(key=lambda x: x[0])

        if original_value is None:
            active_ts = _parse_pdvm_timestamp(time_key_raw)
            if active_ts is not None and str(active_ts) in envelope:
                original_value = envelope.get(str(active_ts))
            elif timeline:
                original_value = timeline[-1][1]

        return original_value, timeline

    central = await PdvmCentralDatabase.load(
        table_name=root_table,
        guid=str(record_uuid),
        stichtag=gcs.stichtag,
        system_pool=gcs._system_pool,
        mandant_pool=gcs._mandant_pool,
    )

    system_updates: Dict[str, Any] = {}

    for gruppe, gruppe_data in daten_to_store.items():
        if not isinstance(gruppe_data, dict):
            continue

        if str(gruppe).upper() == "SYSTEM":
            for feld, wert in gruppe_data.items():
                system_updates[str(feld).upper()] = wert
            continue

        for feld, wert in gruppe_data.items():
            linear_value, value_timeline = _extract_linear_value_and_timeline(wert)
            central.set_value(str(gruppe), str(feld), linear_value)

            if central.historisch and value_timeline:
                for ts_value, timeline_value in value_timeline:
                    central.set_value(str(gruppe), str(feld), timeline_value, ab_zeit=ts_value)

    await central.save_all_values()

    # asy_benutzer: Spalten-Sync (email/benutzer)
    if table_norm == "asy_benutzer":
        benutzer_mgr = PdvmCentralBenutzer(record_uuid)
        benutzer_value = system_updates.get("BENUTZER")
        if benutzer_value is not None:
            await benutzer_mgr.update_benutzer(str(benutzer_value))

    # SYSTEM-Gruppe: falls weitere Tabellen-Spalten unterstÃ¼tzt werden, hier ergÃ¤nzen.
    # Aktuell wird SYSTEM nur fÃ¼r asy_benutzer (email/benutzer) synchronisiert.

    return await load_dialog_record(gcs, root_table=root_table, record_uuid=record_uuid)


async def _load_template_row_and_daten(
    gcs,
    *,
    root_table: str,
    template_uuid: uuid.UUID,
) -> tuple[Dict[str, Any], Dict[str, Any]]:
    db = PdvmDatabase(root_table, system_pool=gcs._system_pool, mandant_pool=gcs._mandant_pool)

    if str(root_table).strip().lower() == "asy_benutzer":
        pool = DatabasePool._pool_auth
        async with pool.acquire() as conn:
            template_row = await conn.fetchrow(
                """
                SELECT uid, benutzer, passwort, daten, name, historisch, sec_id
                FROM asy_benutzer
                WHERE uid = $1
            """,
                template_uuid,
            )
        if not template_row:
            raise KeyError(f"Template-Datensatz nicht gefunden: {template_uuid}")

        template_row = dict(template_row)
        template_daten = template_row.get("daten")
        if template_daten is None:
            template_daten = {}
        if isinstance(template_daten, str):
            try:
                template_daten = json.loads(template_daten)
            except Exception:
                template_daten = {}
        if not isinstance(template_daten, dict):
            raise ValueError("Template 'daten' ist kein JSON-Objekt")
        return template_row, template_daten

    template_row = await db.get_by_uid(template_uuid)
    if not template_row:
        raise KeyError(f"Template-Datensatz nicht gefunden: {template_uuid}")

    template_daten = template_row.get("daten")
    if template_daten is None:
        template_daten = {}
    if isinstance(template_daten, str):
        try:
            template_daten = json.loads(template_daten)
        except Exception:
            template_daten = {}
    if not isinstance(template_daten, dict):
        raise ValueError("Template 'daten' ist kein JSON-Objekt")
    return template_row, template_daten


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


async def build_dialog_draft_from_template(
    gcs,
    *,
    root_table: str,
    name: str,
    template_uuid: uuid.UUID = _DEFAULT_TEMPLATE_UID,
    root_patch: Optional[Dict[str, Any]] = None,
    modul_type: Optional[str] = None,
    resolve_templates: bool = True,
) -> Dict[str, Any]:
    if not root_table:
        raise KeyError("ROOT.TABLE ist leer")

    name_norm = str(name or "").strip()
    if not name_norm:
        raise ValueError("name ist leer")

    if str(root_table).strip().lower() == "asy_benutzer":
        template_row, template_daten = await _load_template_row_and_daten(
            gcs,
            root_table=root_table,
            template_uuid=template_uuid,
        )
        daten_copy: Dict[str, Any] = copy.deepcopy(template_daten)
    else:
        basis_row, _ = await _load_template_row_and_daten(
            gcs,
            root_table=root_table,
            template_uuid=_MODUL_TEMPLATE_UID,
        )
        template_row = basis_row
        if resolve_templates:
            daten_copy = await _resolve_groups_from_templates(
                gcs,
                root_table=root_table,
            )
        else:
            _, basis_daten = await _load_template_row_and_daten(
                gcs,
                root_table=root_table,
                template_uuid=_MODUL_TEMPLATE_UID,
            )
            daten_copy = copy.deepcopy(basis_daten)

    root = daten_copy.get("ROOT")
    if not isinstance(root, dict):
        root = {}
    daten_copy["ROOT"] = _apply_root_identity(
        root,
        self_guid=_DRAFT_FAKE_GUID,
        self_name=name_norm,
        root_patch=root_patch,
    )

    daten_copy = await _normalize_new_record_daten_unified(
        gcs,
        daten=_as_object(daten_copy),
    )

    return {
        "name": name_norm,
        "daten": daten_copy,
        "template_uid": str(template_uuid),
        "sec_id": template_row.get("sec_id"),
    }


async def create_dialog_record_from_template(
    gcs,
    *,
    root_table: str,
    name: str,
    template_uuid: uuid.UUID = _DEFAULT_TEMPLATE_UID,
    root_patch: Optional[Dict[str, Any]] = None,
    modul_type: Optional[str] = None,
    resolve_templates: bool = True,
) -> Dict[str, Any]:
    """Erstellt einen neuen Datensatz fuer den Dialog-Flow.

    Ziel: "Neuer Satz" im Dialog.
    - Tabellenweit: Basis aus 555, leere Gruppen aus 666.(TEMPLATE|TEMPLATES)
    - Ausnahme: asy_benutzer nutzt den bestehenden Sonderpfad
    - ROOT.SELF_GUID und ROOT.SELF_NAME werden auf den neuen Datensatz gesetzt
    - name-Spalte wird auf den Ã¼bergebenen Namen gesetzt

    Args:
        gcs: Global Control System
        root_table: Tabelle fÃ¼r neuen Datensatz
        name: Name des neuen Datensatzes
        template_uuid: Template-GUID fuer asy_benutzer (default: 666666...)
        root_patch: Optional ROOT-Patch
        modul_type: Optional, aktuell ohne Wirkung
    """
    if not root_table:
        raise KeyError("ROOT.TABLE ist leer")

    name_norm = str(name or "").strip()
    if not name_norm:
        raise ValueError("name ist leer")
    name_value = name_norm

    template_row, template_daten = await _load_template_row_and_daten(
        gcs,
        root_table=root_table,
        template_uuid=template_uuid,
    )

    new_uuid = uuid.uuid4()

    if str(root_table).strip().lower() == "asy_benutzer":
        daten_copy: Dict[str, Any] = copy.deepcopy(template_daten)
    else:
        basis_row, _ = await _load_template_row_and_daten(
            gcs,
            root_table=root_table,
            template_uuid=_MODUL_TEMPLATE_UID,
        )
        template_row = basis_row
        if resolve_templates:
            daten_copy = await _resolve_groups_from_templates(
                gcs,
                root_table=root_table,
            )
        else:
            _, basis_daten = await _load_template_row_and_daten(
                gcs,
                root_table=root_table,
                template_uuid=_MODUL_TEMPLATE_UID,
            )
            daten_copy = copy.deepcopy(basis_daten)

    root = daten_copy.get("ROOT")
    if not isinstance(root, dict):
        root = {}
    daten_copy["ROOT"] = _apply_root_identity(
        root,
        self_guid=str(new_uuid),
        self_name=name_value,
        root_patch=root_patch,
    )

    daten_copy = await _normalize_new_record_daten_unified(
        gcs,
        daten=_as_object(daten_copy),
    )

    if str(root_table).strip().lower() == "asy_benutzer":
        benutzer_value = name_value

        passwort_value = template_row.get("passwort")
        if not passwort_value:
            passwort_value = UserManager.hash_password(_generate_temp_password())

        pool = DatabasePool._pool_auth
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO asy_benutzer (uid, benutzer, passwort, daten, name, historisch, sec_id)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
            """,
                new_uuid,
                benutzer_value,
                passwort_value,
                json.dumps(daten_copy),
                name_value,
                0,
                template_row.get("sec_id"),
            )
            # Ensure name column and ROOT.SELF_NAME stay aligned with provided name.
            await conn.execute(
                """
                UPDATE asy_benutzer
                SET name = $1, daten = $2, modified_at = NOW()
                WHERE uid = $3
            """,
                name_value,
                json.dumps(daten_copy),
                new_uuid,
            )
    else:
        await create_record_central(
            table_name=root_table,
            uid=new_uuid,
            daten=daten_copy,
            name=name_value,
            historisch=0,
            sec_id=template_row.get("sec_id"),
            gcs=gcs,
        )

    return await load_dialog_record(gcs, root_table=root_table, record_uuid=new_uuid)


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


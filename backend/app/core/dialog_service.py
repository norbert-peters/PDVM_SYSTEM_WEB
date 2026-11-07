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
    hydrate_runtime_control_from_row,
    load_control_rows_bulk,
    merge_control_runtime_with_override,
)
from app.core.central_write_service import create_record_central, update_record_central
from app.core.pdvm_central_datenbank import PdvmCentralDatabase
from app.core.pdvm_central_benutzer import PdvmCentralBenutzer
from app.core.user_manager import UserManager
from app.core.database import DatabasePool
from app.core.dialog_frame_helpers import (
    _as_object,
    _as_text,
    _build_element_config_from_frame,
    _extract_control_payload_for_validation,
    _extract_element_definition_rows_from_frame,
    _get_case_insensitive,
    _is_guid,
    _normalize_element_field_type,
    _normalize_sys_dialog_tab_elements_for_storage,
    _resolve_frame_fields,
    _resolve_tooltip_text_from_ref,
    _tooltip_ref_from_item,
    _validate_element_list_definition_source_for_control,
)
from app.core.dialog_runtime_config import (
    _collect_edit_control_hints,
    _get_root_table,
    extract_dialog_runtime_config,
    validate_dialog_daten_generic,
)


_DEFAULT_TEMPLATE_UID = uuid.UUID("66666666-6666-6666-6666-666666666666")
_MODUL_TEMPLATE_UID = uuid.UUID("55555555-5555-5555-5555-555555555555")
_DRAFT_FAKE_GUID = "66666666-6666-6666-6666-666666666662"


def _is_new_set_legacy_user_exception(root_table: str) -> bool:
    """Ausnahme fuer den bestehenden Benutzer-Dialog-Neusatzpfad."""
    table_norm = str(root_table or "").strip().lower()
    return table_norm in {"asy_benutzer", "sys_benutzer"}


async def _resolve_groups_from_templates(
    gcs,
    *,
    root_table: str,
) -> Dict[str, Any]:
    """Linearer Neuanlage-Algorithmus fuer alle Tabellen ausser Benutzer-Ausnahme.

    Ablauf:
    1) Basis immer aus UID 555 derselben Tabelle
    2) ROOT wird spaeter zentral ueber _apply_root_identity gesetzt
    3) Leere Gruppen der 555-Basis werden aus 666.(TEMPLATE|TEMPLATES) aufgefuellt
    4) Fehlt die gleichnamige Gruppe in 666 TEMPLATE, wird ein Fehler geworfen
    """
    if _is_new_set_legacy_user_exception(root_table):
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
    # TABLE_INFO ist Tabellen-Metadatum (666.TEMPLATES.TABLE_INFO), kein Bestandteil von Fachdatensaetzen (1.12c).
    out.pop("TABLE_INFO", None)

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
        # Linearer Storage-Write: keine impliziten Basis-Merges.
        # Persistiert wird exakt die gelieferte ROOT/CONTROL-Struktur.
        root_in = control_data.get("ROOT") if has_root else {}
        control_in = control_data.get("CONTROL") if has_control else {}
        if not isinstance(control_in, dict) or not control_in:
            control_in = templates.get("CONTROL") if has_template_control else {}
        if (not isinstance(control_in, dict) or not control_in) and is_control_like:
            control_in = dict(control_candidate)

        normalized = {
            "ROOT": copy.deepcopy(root_in) if isinstance(root_in, dict) else {},
            "CONTROL": copy.deepcopy(control_in) if isinstance(control_in, dict) else {},
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


async def _normalize_new_record_daten_unified(gcs, *, root_table: str, daten: Dict[str, Any]) -> Dict[str, Any]:
    """Strikt lineare Normalisierung für Neuanlage-Datensätze.

    Regel: Für Neuer Satz werden keine tabellenspezifischen Zusatz-Normalisierungen
    ausgeführt. Persistiert wird das lineare 555/666-Ergebnis, bereinigt nur um
    Template-Metagruppen.
    """
    out = _as_object(daten)

    # Aktuell bewusst ungenutzt: root_table bleibt als API-Kontext erhalten.
    _ = root_table
    _ = gcs

    # Template-Metagruppen duerfen in instanziierten Datensaetzen nicht persistiert werden.
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


def _mirror_row_meta_into_root(*, daten: Dict[str, Any], row: Dict[str, Any]) -> Dict[str, Any]:
    """Spiegelt ROOT.SELF_* strikt aus DB-Spalten (Read-Weg gewinnt immer)."""
    payload = {
        "uid": row.get("uid"),
        "link_uid": row.get("link_uid"),
        "created_at": row.get("created_at"),
        "modified_at": row.get("modified_at"),
        "gilt_bis": row.get("gilt_bis"),
        "daten": _as_object(daten),
    }
    projected = PdvmDatabase._inject_root_meta_fields(payload)
    return _as_object(projected.get("daten"))


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


async def list_public_table_names(pool) -> List[str]:
    """Listet die Tabellen im Schema public eines Pools (fuer Tabellenauswahl bei Neuanlage)."""
    if pool is None:
        return []
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            ORDER BY table_name
            """
        )
    return [str(r.get("table_name") or "").strip() for r in rows if str(r.get("table_name") or "").strip()]


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

    # Finaler, tabellenunabhaengiger SELF_* Mirror aus DB-Metadaten.
    daten = _mirror_row_meta_into_root(daten=_as_object(daten), row=row)

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

    if _is_new_set_legacy_user_exception(root_table):
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
        root_table=root_table,
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
    - Ausnahme: Benutzer-Tabelle nutzt den bestehenden Sonderpfad
    - ROOT.SELF_GUID und ROOT.SELF_NAME werden auf den neuen Datensatz gesetzt
    - name-Spalte wird auf den Ã¼bergebenen Namen gesetzt

    Args:
        gcs: Global Control System
        root_table: Tabelle fÃ¼r neuen Datensatz
        name: Name des neuen Datensatzes
        template_uuid: Template-GUID fuer Benutzer-Sonderpfad (default: 666666...)
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

    if _is_new_set_legacy_user_exception(root_table):
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
        root_table=root_table,
        daten=_as_object(daten_copy),
    )

    if _is_new_set_legacy_user_exception(root_table):
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

"""Dropdown Service

Liest Dropdown-Definitionen aus `sys_dropdowndaten` und stellt pro Feld (z.B. "anrede")
Key->Label Mappings bereit.

Struktur in sys_dropdowndaten.daten (Beispiel):
- ROOT: { DEFAULT_LANGUAGE: "DE-DE", ... }
- "DE-DE": { <guid>: { name/list_name, edit_list:[{key,value}, ...] }, ... }

Caching:
- Pro Session (GCS) wird pro (table, dataset_uid, language) ein Cache gehalten.
- Wenn ein Feld nicht gefunden wird, wird einmal "refresh" gegen die DB gemacht.

ARCHITECTURE_RULES: kein SQL im Router; DB-Zugriff via PdvmDatabase.
"""

from __future__ import annotations

import time
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from app.core.pdvm_central_systemsteuerung import PdvmCentralSystemsteuerung
from app.core.pdvm_datenbank import PdvmDatabase


DEFAULT_LANGUAGE_FALLBACK = "DE-DE"
_DROPDOWN_CACHE_GROUP = "DROPDOWN_CACHE"


def _norm_group(value: Any) -> str:
    return str(value or "").strip().upper()


def _cache_key(*, table: str, dataset_uid: str, language: str, group: Optional[str]) -> str:
    return f"{str(table).strip().lower()}|{str(dataset_uid).strip().lower()}|{_norm_lang(language)}|{_norm_group(group)}"


def _to_iso(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    s = str(value or "").strip()
    return s


def _norm_lang(value: Any) -> str:
    s = str(value or "").strip()
    return s.upper() if s else DEFAULT_LANGUAGE_FALLBACK


def _norm_field(value: Any) -> str:
    s = str(value or "").strip()
    return s.lower() if s else ""


def _resolve_group_object(daten: Dict[str, Any], group_name: str) -> Optional[Dict[str, Any]]:
    if not isinstance(daten, dict):
        return None
    target = str(group_name or "").strip()
    if not target:
        return None

    direct = daten.get(target)
    if isinstance(direct, dict):
        return direct

    target_u = target.upper()
    for key, value in daten.items():
        if str(key or "").strip().upper() == target_u and isinstance(value, dict):
            return value
    return None


def get_user_language(gcs: PdvmCentralSystemsteuerung) -> str:
    """Best-effort: liest die Sprache aus gcs.benutzer Daten."""
    try:
        for gruppe in ("ROOT", "SYSTEM", "BENUTZER", "USER"):
            for feld in ("LANGUAGE", "language", "SPRACHE", "sprache"):
                v, _ab = gcs.benutzer.get_value(gruppe, feld, ab_zeit=float(gcs.stichtag))
                if v is not None and str(v).strip():
                    return _norm_lang(v)
    except Exception:
        pass
    return DEFAULT_LANGUAGE_FALLBACK


def _get_dropdown_cache(gcs: PdvmCentralSystemsteuerung) -> Dict[Tuple[str, str, str, str], Any]:
    cache = getattr(gcs, "_pdvm_dropdown_cache", None)
    if isinstance(cache, dict):
        return cache
    cache = {}
    setattr(gcs, "_pdvm_dropdown_cache", cache)
    return cache


async def _load_dataset_row(
    gcs: PdvmCentralSystemsteuerung,
    *,
    table: str,
    dataset_uid: str,
) -> Optional[Dict[str, Any]]:
    db = PdvmDatabase(
        table,
        system_pool=gcs._system_pool,
        mandant_pool=gcs._mandant_pool,
    )
    try:
        uid_obj = uuid.UUID(str(dataset_uid))
    except Exception:
        return None
    return await db.get_by_uid(uid_obj)


async def _load_dataset_modified_at(
    gcs: PdvmCentralSystemsteuerung,
    *,
    table: str,
    dataset_uid: str,
) -> Optional[datetime]:
    db = PdvmDatabase(
        table,
        system_pool=gcs._system_pool,
        mandant_pool=gcs._mandant_pool,
    )
    try:
        uid_obj = uuid.UUID(str(dataset_uid))
    except Exception:
        return None
    try:
        return await db.get_modified_at_by_uid(uid_obj)
    except Exception:
        return None


def _read_persistent_dropdown_cache(gcs: PdvmCentralSystemsteuerung, key: str) -> Optional[Dict[str, Any]]:
    try:
        raw, _ = gcs.anwendungsdaten.get_value(_DROPDOWN_CACHE_GROUP, key, ab_zeit=float(gcs.stichtag))
    except Exception:
        return None
    return raw if isinstance(raw, dict) else None


async def _write_persistent_dropdown_cache(gcs: PdvmCentralSystemsteuerung, key: str, payload: Dict[str, Any]) -> None:
    try:
        gcs.anwendungsdaten.set_value(_DROPDOWN_CACHE_GROUP, key, payload, float(gcs.stichtag))
        await gcs.anwendungsdaten.save_all_values()
    except Exception:
        return


def _parse_dataset(
    daten: Any,
    *,
    language: str,
    group: Optional[str] = None,
) -> Tuple[str, Dict[str, Dict[str, str]], Dict[str, List[Dict[str, str]]]]:
    """Parst sys_dropdowndaten.daten in (default_lang, maps_by_field, options_by_field)."""
    if not isinstance(daten, dict):
        return DEFAULT_LANGUAGE_FALLBACK, {}, {}

    root = daten.get("ROOT") if isinstance(daten.get("ROOT"), dict) else {}
    default_lang = _norm_lang((root or {}).get("DEFAULT_LANGUAGE") or DEFAULT_LANGUAGE_FALLBACK)

    requested_group = str(group or "").strip()
    lang_key = _norm_lang(language)

    lang_obj = _resolve_group_object(daten, requested_group) if requested_group else None
    if not isinstance(lang_obj, dict):
        lang_obj = _resolve_group_object(daten, lang_key)
    if not isinstance(lang_obj, dict):
        lang_obj = _resolve_group_object(daten, default_lang)

    if not isinstance(lang_obj, dict):
        return default_lang, {}, {}

    maps_by_field: Dict[str, Dict[str, str]] = {}
    options_by_field: Dict[str, List[Dict[str, str]]] = {}

    for item_guid, item in lang_obj.items():
        if not isinstance(item, dict):
            continue

        field_name = item.get("list_name") or item.get("name")
        field_key = _norm_field(field_name)
        if not field_key:
            continue

        edit_list = item.get("edit_list")
        if not isinstance(edit_list, list):
            continue

        mapping: Dict[str, str] = {}
        options: List[Dict[str, str]] = []
        for opt in edit_list:
            if not isinstance(opt, dict):
                continue
            k = opt.get("key")
            v = opt.get("value")
            if k is None or v is None:
                continue
            ks = str(k)
            vs = str(v)
            mapping[ks] = vs
            options.append({"key": ks, "value": vs})

        if mapping:
            aliases = {
                field_key,
                _norm_field(item.get("name")),
                _norm_field(item.get("list_name")),
                _norm_field(item_guid),
            }
            for alias in aliases:
                if not alias:
                    continue
                maps_by_field[alias] = mapping
                options_by_field[alias] = options

    return default_lang, maps_by_field, options_by_field


async def get_dropdown_mapping_for_field(
    gcs: PdvmCentralSystemsteuerung,
    *,
    table: str,
    dataset_uid: str,
    field: str,
    group: Optional[str] = None,
    language: Optional[str] = None,
) -> Dict[str, Any]:
    """Gibt Mapping+Options für ein Feld zurück.

    Returns:
        {"map": {rawKey: label, ...}, "options": [{key,value}, ...], "language": "DE-DE", "default_language": "DE-DE"}
    """
    lang = _norm_lang(language or get_user_language(gcs))
    fld = _norm_field(field)
    if not fld:
        return {"map": {}, "options": [], "language": lang, "default_language": DEFAULT_LANGUAGE_FALLBACK}

    cache = _get_dropdown_cache(gcs)
    group_norm = _norm_group(group)
    cache_key = (str(table), str(dataset_uid), str(lang), group_norm)
    persistent_key = _cache_key(table=table, dataset_uid=dataset_uid, language=lang, group=group)

    entry = cache.get(cache_key)
    if not isinstance(entry, dict):
        entry = {"ts": 0.0, "default_language": DEFAULT_LANGUAGE_FALLBACK, "maps": {}, "options": {}}
        cache[cache_key] = entry

    def _get_from_entry() -> Optional[Dict[str, Any]]:
        maps = entry.get("maps")
        opts = entry.get("options")
        if not isinstance(maps, dict) or not isinstance(opts, dict):
            return None
        m = maps.get(fld)
        o = opts.get(fld)
        if isinstance(m, dict) and isinstance(o, list):
            return {
                "map": m,
                "options": o,
                "language": lang,
                "default_language": entry.get("default_language") or DEFAULT_LANGUAGE_FALLBACK,
            }
        return None

    hit = _get_from_entry()
    if hit is not None:
        return hit

    source_modified_at = await _load_dataset_modified_at(gcs, table=str(table), dataset_uid=str(dataset_uid))
    source_modified_iso = _to_iso(source_modified_at)

    persisted = _read_persistent_dropdown_cache(gcs, persistent_key)
    if isinstance(persisted, dict):
        persisted_mod = _to_iso(persisted.get("source_modified_at"))
        maps_p = persisted.get("maps")
        opts_p = persisted.get("options")
        if source_modified_iso and persisted_mod == source_modified_iso and isinstance(maps_p, dict) and isinstance(opts_p, dict):
            entry["ts"] = float(time.time())
            entry["default_language"] = persisted.get("default_language") or DEFAULT_LANGUAGE_FALLBACK
            entry["maps"] = maps_p
            entry["options"] = opts_p
            hit_persisted = _get_from_entry()
            if hit_persisted is not None:
                return hit_persisted

    # Load/refresh dataset
    row = await _load_dataset_row(gcs, table=str(table), dataset_uid=str(dataset_uid))
    daten = (row or {}).get("daten")
    default_lang, maps_by_field, options_by_field = _parse_dataset(daten, language=lang, group=group)

    entry["ts"] = float(time.time())
    entry["default_language"] = default_lang
    entry["maps"] = maps_by_field
    entry["options"] = options_by_field

    await _write_persistent_dropdown_cache(
        gcs,
        persistent_key,
        {
            "source_modified_at": source_modified_iso,
            "default_language": default_lang,
            "maps": maps_by_field,
            "options": options_by_field,
        },
    )

    hit2 = _get_from_entry()
    if hit2 is not None:
        return hit2

    # Feld nicht vorhanden -> einmal mit default lang probieren, falls anders
    if default_lang and default_lang != lang:
        cache_key2 = (str(table), str(dataset_uid), str(default_lang), group_norm)
        entry2 = cache.get(cache_key2)
        if not isinstance(entry2, dict) or not entry2.get("maps"):
            row2 = row or await _load_dataset_row(gcs, table=str(table), dataset_uid=str(dataset_uid))
            daten2 = (row2 or {}).get("daten")
            _dl, maps2, opts2 = _parse_dataset(daten2, language=default_lang, group=group)
            cache[cache_key2] = {
                "ts": float(time.time()),
                "default_language": _dl,
                "maps": maps2,
                "options": opts2,
            }
            entry2 = cache[cache_key2]

        if isinstance(entry2, dict):
            maps = entry2.get("maps")
            opts = entry2.get("options")
            if isinstance(maps, dict) and isinstance(opts, dict) and isinstance(maps.get(fld), dict) and isinstance(opts.get(fld), list):
                return {
                    "map": maps.get(fld),
                    "options": opts.get(fld),
                    "language": default_lang,
                    "default_language": default_lang,
                }

    return {"map": {}, "options": [], "language": lang, "default_language": default_lang}

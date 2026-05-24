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

import asyncio
import copy
import logging
import re
import time
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from app.core.pdvm_central_systemsteuerung import PdvmCentralSystemsteuerung
from app.core.pdvm_datenbank import PdvmDatabase
from app.core.i18n_policy import DEFAULT_LANGUAGE_FALLBACK, normalize_language
from app.core.view_service import load_view_base_rows
from app.core.config import settings


_DROPDOWN_CACHE_GROUP = "DROPDOWN_CACHE"
_DROPDOWN_SOURCE_CACHE_GROUP = "DROPDOWN_SOURCE_CACHE"
_TABLE_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

logger = logging.getLogger(__name__)


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
    return normalize_language(value)


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


def _norm_source(value: Any) -> str:
    s = str(value or "").strip().lower()
    if not s:
        return ""
    aliases = {
        "prefix": "prefix_multi_table",
        "prefix_multi": "prefix_multi_table",
        "prefix_multitable": "prefix_multi_table",
        "table_prefix": "prefix_multi_table",
    }
    return aliases.get(s, s)


def _normalize_table_name(table_name: Any, *, allow_empty: bool = False) -> str:
    t = str(table_name or "").strip().lower()
    if not t:
        if allow_empty:
            return ""
        raise ValueError("DROPDOWN_SOURCE_INVALID: table fehlt")
    if not _TABLE_NAME_RE.match(t):
        raise ValueError(f"DROPDOWN_SOURCE_INVALID: ungueltiger table name: {t}")
    return t


def _normalize_result_limit(raw_limit: Any) -> int:
    max_limit = int(getattr(settings, "DROPDOWN_PREFIX_MAX_RESULTS", 300) or 300)
    max_limit = max(1, max_limit)
    if raw_limit is None:
        return max_limit
    try:
        requested = int(raw_limit)
    except Exception:
        requested = max_limit
    if requested <= 0:
        requested = max_limit
    return min(requested, max_limit)


def _prefix_allowlist() -> set[str]:
    raw = getattr(settings, "DROPDOWN_PREFIX_WHITELIST", "msy_,tst_")
    items = [str(i or "").strip().lower() for i in str(raw).split(",")]
    return {i for i in items if i}


def _get_source_cache(gcs: PdvmCentralSystemsteuerung) -> Dict[str, Any]:
    cache = getattr(gcs, "_pdvm_dropdown_source_cache", None)
    if isinstance(cache, dict):
        return cache
    cache = {}
    setattr(gcs, "_pdvm_dropdown_source_cache", cache)
    return cache


async def _list_tables_for_prefix(
    gcs: PdvmCentralSystemsteuerung,
    *,
    prefix: str,
    timeout_seconds: float,
) -> List[str]:
    probe_table = f"{prefix}probe"
    db = PdvmDatabase(
        probe_table,
        system_pool=gcs._system_pool,
        mandant_pool=gcs._mandant_pool,
    )

    if db.db_name == "system":
        pool = gcs._system_pool
    else:
        pool = gcs._mandant_pool

    if pool is None:
        return []

    pattern = f"{prefix}%"
    async with pool.acquire() as conn:
        rows = await asyncio.wait_for(
            conn.fetch(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name LIKE $1
                ORDER BY table_name ASC
                """,
                pattern,
            ),
            timeout=timeout_seconds,
        )

    out: List[str] = []
    for row in rows:
        t = _normalize_table_name(row.get("table_name"), allow_empty=True)
        if t and t.startswith(prefix):
            out.append(t)
    return out


async def _fetch_table_lookup_rows(
    gcs: PdvmCentralSystemsteuerung,
    *,
    table: str,
    limit: int,
    timeout_seconds: float,
) -> List[Dict[str, Any]]:
    db = PdvmDatabase(
        table,
        system_pool=gcs._system_pool,
        mandant_pool=gcs._mandant_pool,
    )
    return await asyncio.wait_for(
        db.get_all(order_by="name ASC", limit=limit, offset=0),
        timeout=timeout_seconds,
    )


async def _resolve_prefix_multi_table_dropdown(
    gcs: PdvmCentralSystemsteuerung,
    *,
    prefix: str,
    requested_limit: Any,
) -> Dict[str, Any]:
    prefix_norm = str(prefix or "").strip().lower()
    if not prefix_norm or not prefix_norm.endswith("_"):
        raise ValueError("DROPDOWN_SOURCE_INVALID: prefix muss auf '_' enden")

    allowed_prefixes = _prefix_allowlist()
    if prefix_norm not in allowed_prefixes:
        logger.warning(
            "dropdown_guardrail_denied prefix_not_allowed prefix=%s allowed=%s",
            prefix_norm,
            sorted(allowed_prefixes),
        )
        raise ValueError(f"DROPDOWN_PREFIX_NOT_ALLOWED: {prefix_norm}")

    timeout_seconds = float(getattr(settings, "DROPDOWN_PREFIX_TIMEOUT_SECONDS", 2.0) or 2.0)
    timeout_seconds = max(0.1, timeout_seconds)
    effective_limit = _normalize_result_limit(requested_limit)
    cache_ttl = float(getattr(settings, "DROPDOWN_PREFIX_CACHE_TTL_SECONDS", 60.0) or 60.0)
    cache_ttl = max(1.0, cache_ttl)
    cache_key = f"prefix|{prefix_norm}|{effective_limit}"

    cache = _get_source_cache(gcs)
    cache_entry = cache.get(cache_key)
    now_ts = time.time()
    if isinstance(cache_entry, dict):
        age = now_ts - float(cache_entry.get("ts") or 0.0)
        if age <= cache_ttl and isinstance(cache_entry.get("payload"), dict):
            logger.info("dropdown_guardrail_cache_hit prefix=%s limit=%s", prefix_norm, effective_limit)
            return copy.deepcopy(cache_entry["payload"])

    try:
        tables = await _list_tables_for_prefix(gcs, prefix=prefix_norm, timeout_seconds=timeout_seconds)
        options: List[Dict[str, str]] = []
        mapping: Dict[str, str] = {}
        seen_keys: set[str] = set()

        for table in tables:
            remaining = effective_limit - len(options)
            if remaining <= 0:
                break
            rows = await _fetch_table_lookup_rows(
                gcs,
                table=table,
                limit=remaining,
                timeout_seconds=timeout_seconds,
            )
            for row in rows:
                key = str(row.get("uid") or "").strip()
                if not key or key in seen_keys:
                    continue
                label_raw = str(row.get("name") or "").strip()
                label = label_raw or key
                options.append({"key": key, "value": label})
                mapping[key] = label
                seen_keys.add(key)
                if len(options) >= effective_limit:
                    break

        payload = {
            "map": mapping,
            "options": options,
            "language": DEFAULT_LANGUAGE_FALLBACK,
            "default_language": DEFAULT_LANGUAGE_FALLBACK,
            "source": "prefix_multi_table",
            "meta": {
                "prefix": prefix_norm,
                "tables_count": len(tables),
                "result_count": len(options),
                "max_results": effective_limit,
                "cache": "miss",
            },
        }
        cache[cache_key] = {"ts": now_ts, "payload": copy.deepcopy(payload)}
        logger.info(
            "dropdown_guardrail_cache_miss prefix=%s tables=%s result=%s max=%s",
            prefix_norm,
            len(tables),
            len(options),
            effective_limit,
        )
        return payload
    except TimeoutError:
        logger.warning(
            "dropdown_guardrail_timeout prefix=%s timeout_seconds=%s",
            prefix_norm,
            timeout_seconds,
        )
        raise ValueError(f"DROPDOWN_PREFIX_TIMEOUT: {prefix_norm}")


async def _resolve_view_dropdown(
    gcs: PdvmCentralSystemsteuerung,
    *,
    view_guid: str,
    table_override: Optional[str],
    requested_limit: Any,
) -> Dict[str, Any]:
    try:
        uuid.UUID(str(view_guid))
    except Exception:
        raise ValueError("DROPDOWN_SOURCE_INVALID: key muss eine gueltige view_guid sein")

    table_name = _normalize_table_name(table_override, allow_empty=True)
    if not table_name:
        raise ValueError("DROPDOWN_SOURCE_INVALID: table ist fuer source=view erforderlich")

    effective_limit = _normalize_result_limit(requested_limit)
    timeout_seconds = float(getattr(settings, "DROPDOWN_PREFIX_TIMEOUT_SECONDS", 2.0) or 2.0)
    timeout_seconds = max(0.1, timeout_seconds)

    rows = await asyncio.wait_for(
        load_view_base_rows(
            gcs,
            table_name=table_name,
            limit=effective_limit,
            include_historisch=False,
            control_fields=None,
        ),
        timeout=timeout_seconds,
    )

    options: List[Dict[str, str]] = []
    mapping: Dict[str, str] = {}
    for row in rows:
        key = str(row.get("uid") or "").strip()
        if not key:
            continue
        label_raw = str(row.get("name") or "").strip()
        label = label_raw or key
        options.append({"key": key, "value": label})
        mapping[key] = label
        if len(options) >= effective_limit:
            break

    return {
        "map": mapping,
        "options": options,
        "language": DEFAULT_LANGUAGE_FALLBACK,
        "default_language": DEFAULT_LANGUAGE_FALLBACK,
        "source": "view",
        "meta": {
            "view_guid": str(view_guid),
            "table": table_name,
            "result_count": len(options),
            "max_results": effective_limit,
        },
    }


async def resolve_dropdown_by_config(
    gcs: PdvmCentralSystemsteuerung,
    *,
    dropdown_config: Dict[str, Any],
    language: Optional[str] = None,
) -> Dict[str, Any]:
    """Auflösung einer Dropdown-Quelle inkl. Guardrails.

    Unterstützte Quellen:
    - static: sys_dropdowndaten per (table,key,feld,group)
    - view: Optionen aus einer View/Tabellenquelle per key=view_guid
    - prefix_multi_table: Aggregation über Prefix-Tabellen (limitiert)
    """
    if not isinstance(dropdown_config, dict):
        raise ValueError("DROPDOWN_SOURCE_INVALID: dropdown config fehlt")

    require_explicit = bool(getattr(settings, "DROPDOWN_REQUIRE_EXPLICIT_SOURCE", False))
    source = _norm_source(dropdown_config.get("source") or dropdown_config.get("source_type"))

    if not source:
        if require_explicit:
            raise ValueError("DROPDOWN_SOURCE_INVALID: source fehlt (expected: static|view|prefix_multi_table)")

        group_raw = str(dropdown_config.get("group") or "").strip().upper()
        if group_raw == "*VIEW":
            source = "view"
        elif dropdown_config.get("prefix") or dropdown_config.get("table_prefix"):
            source = "prefix_multi_table"
        else:
            source = "static"
        logger.info("dropdown_source_legacy_fallback source=%s", source)

    if source == "static":
        table_name = _normalize_table_name(dropdown_config.get("table") or "sys_dropdowndaten")
        dataset_uid = str(dropdown_config.get("key") or "").strip()
        field_name = str(dropdown_config.get("feld") or dropdown_config.get("field") or "").strip()
        if not dataset_uid:
            raise ValueError("DROPDOWN_SOURCE_INVALID: key fehlt fuer source=static")
        if not field_name:
            raise ValueError("DROPDOWN_SOURCE_INVALID: feld/field fehlt fuer source=static")

        resolved = await get_dropdown_mapping_for_field(
            gcs,
            table=table_name,
            dataset_uid=dataset_uid,
            field=field_name,
            group=str(dropdown_config.get("group") or "").strip() or None,
            language=language,
        )
        resolved["source"] = "static"
        return resolved

    if source == "view":
        try:
            resolved = await _resolve_view_dropdown(
                gcs,
                view_guid=str(dropdown_config.get("key") or "").strip(),
                table_override=str(dropdown_config.get("table") or "").strip() or None,
                requested_limit=dropdown_config.get("limit"),
            )
            return resolved
        except TimeoutError:
            raise ValueError("DROPDOWN_VIEW_TIMEOUT")

    if source == "prefix_multi_table":
        prefix = str(dropdown_config.get("prefix") or dropdown_config.get("table_prefix") or "").strip().lower()
        return await _resolve_prefix_multi_table_dropdown(
            gcs,
            prefix=prefix,
            requested_limit=dropdown_config.get("limit"),
        )

    raise ValueError(f"DROPDOWN_SOURCE_INVALID: source nicht unterstuetzt: {source}")


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

    # Neues Modell: ROOT + OPTIONS, Sprache liegt im values-Mapping pro Option.
    options_obj = daten.get("OPTIONS") if isinstance(daten.get("OPTIONS"), dict) else None
    if isinstance(options_obj, dict):
        lang_key = _norm_lang(language)
        field_key = _norm_field((root or {}).get("FIELD_KEY") or (root or {}).get("SELF_NAME") or "")

        mapping: Dict[str, str] = {}
        options: List[Dict[str, str]] = []

        for option_key, option_value in options_obj.items():
            opt = option_value if isinstance(option_value, dict) else {}
            values = opt.get("values") if isinstance(opt.get("values"), dict) else {}
            label = values.get(lang_key)
            if label is None:
                label = values.get(default_lang)
            if label is None and isinstance(values, dict) and values:
                label = next((str(v) for v in values.values() if v is not None), "")

            k = str(opt.get("key") or option_key)
            v = str(label or "")
            mapping[k] = v
            options.append({"key": k, "value": v})

        maps_by_field: Dict[str, Dict[str, str]] = {}
        options_by_field: Dict[str, List[Dict[str, str]]] = {}
        aliases = {
            field_key,
            _norm_field((root or {}).get("SELF_GUID")),
            _norm_field((root or {}).get("SELF_NAME")),
        }
        for alias in aliases:
            if not alias:
                continue
            maps_by_field[alias] = mapping
            options_by_field[alias] = options

        return default_lang, maps_by_field, options_by_field

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
    table_norm = str(table or "").strip().lower()
    if table_norm == "sys_systemdaten":
        raise ValueError(
            "LEGACY_DROPDOWN_SOURCE: table=sys_systemdaten ist für Dropdown-Auflösung nicht mehr zulässig; verwende sys_dropdowndaten"
        )

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

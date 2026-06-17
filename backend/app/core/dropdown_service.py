"""Dropdown Service

Liest Dropdown-Definitionen aus `sys_dropdowndaten` und stellt pro Feld (z.B. "anrede")
Key->Label Mappings bereit.

Struktur in sys_dropdowndaten.daten (Zielmodell):
- ROOT: { DEFAULT_LANGUAGE: "DE-DE", FIELD_KEY: "anrede", ... }
- OPTIONS: { "m": {"DE-DE": "Herr", "EN-US": "Mr"}, "w": {...}, ... }

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
from typing import Any, Dict, List, Optional, Set, Tuple

from app.core.pdvm_central_systemsteuerung import PdvmCentralSystemsteuerung
from app.core.pdvm_datenbank import PdvmDatabase
from app.core.i18n_policy import DEFAULT_LANGUAGE_FALLBACK, normalize_language
from app.core.view_service import load_view_base_rows
from app.core.config import settings


_DROPDOWN_CACHE_GROUP = "DROPDOWN_CACHE"
_DROPDOWN_SOURCE_CACHE_GROUP = "DROPDOWN_SOURCE_CACHE"
_TABLE_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_DROPDOWN_CACHE_SCHEMA_VERSION = 4

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


def _get_ci_value(obj: Dict[str, Any], *keys: str) -> Any:
    if not isinstance(obj, dict):
        return None
    for key in keys:
        if key in obj:
            return obj.get(key)
        wanted = str(key or "").strip().upper()
        for k, v in obj.items():
            if str(k or "").strip().upper() == wanted:
                return v
    return None


def _get_lang_value(values: Dict[str, Any], lang_key: str, default_lang: str) -> Optional[str]:
    if not isinstance(values, dict):
        return None

    lang_norm = _norm_lang(lang_key)
    default_norm = _norm_lang(default_lang)

    # Direkter Treffer (inkl. case-varianten)
    direct = _get_ci_value(values, lang_norm)
    if direct is None:
        direct = _get_ci_value(values, default_norm)

    # Treffer über Alias-Normalisierung der vorhandenen Keys
    if direct is None:
        for k, v in values.items():
            if _norm_lang(k) == lang_norm:
                direct = v
                break
    if direct is None:
        for k, v in values.items():
            if _norm_lang(k) == default_norm:
                direct = v
                break

    if direct is not None:
        return str(direct)

    # Fallback: erster nicht-leerer Eintrag
    for v in values.values():
        if v is not None and str(v).strip() != "":
            return str(v)
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


def _normalize_roles_raw(raw: Any) -> Set[str]:
    out: Set[str] = set()
    if raw is None:
        return out
    if isinstance(raw, list):
        for item in raw:
            role = str(item or "").strip().lower()
            if role:
                out.add(role)
        return out
    raw_s = str(raw or "").strip()
    if not raw_s:
        return out
    for token in raw_s.replace(";", ",").split(","):
        role = str(token or "").strip().lower()
        if role:
            out.add(role)
    return out


def _parse_string_list(raw: Any) -> List[str]:
    if isinstance(raw, list):
        out: List[str] = []
        for item in raw:
            value = str(item or "").strip()
            if value:
                out.append(value)
        return out
    if isinstance(raw, str):
        out: List[str] = []
        for token in str(raw).replace(";", ",").split(","):
            value = str(token or "").strip()
            if value:
                out.append(value)
        return out
    return []


def _extract_table_from_template_meta_name(name_value: Any) -> str:
    name = str(name_value or "").strip()
    if not name:
        return ""
    lower_name = name.lower()
    if not lower_name.startswith("template_meta::"):
        return ""
    tail = name.split("::", 1)[1] if "::" in name else ""
    try:
        return _normalize_table_name(tail, allow_empty=True)
    except Exception:
        return ""


async def _load_effective_user_roles(gcs: PdvmCentralSystemsteuerung) -> Set[str]:
    """Normalisierte Rollen linear aus bereits geladenen GCS-Benutzerdaten.

    Security ist aktuell nicht historisiert. Deshalb hier bewusst KEIN
    stichtagsbezogenes Neulesen via get_value(), sondern direkte Auswertung
    der Login-/Sessiondaten aus gcs.benutzer.data.
    """
    roles: Set[str] = set()

    # Direkt aus Login-/Session-Userdaten lesen.
    try:
        user_data = gcs.benutzer.data if isinstance(getattr(gcs, "benutzer", None), object) else {}
    except Exception:
        user_data = {}

    if isinstance(user_data, dict):
        permissions = _resolve_group_object(user_data, "PERMISSIONS") or {}
        security = _resolve_group_object(user_data, "SECURITY") or {}
        settings_group = _resolve_group_object(user_data, "SETTINGS") or {}

        roles.update(_normalize_roles_raw(_get_ci_value(permissions, "ROLES")))
        roles.update(_normalize_roles_raw(_get_ci_value(security, "ROLES")))

        security_role = str(_get_ci_value(security, "ROLE") or "").strip().lower()
        if security_role:
            roles.add(security_role)

        mode = str(_get_ci_value(settings_group, "MODE") or "").strip().lower()
        if mode:
            roles.add(mode)

    return roles


async def _load_table_meta_catalog(
    gcs: PdvmCentralSystemsteuerung,
    *,
    include_inactive: bool,
) -> List[Dict[str, Any]]:
    """Lädt Tabellenkatalog aus TABLE_META/TEMPLATE_META in asy_systemdaten + msy_systemdaten."""
    out_by_table: Dict[str, Dict[str, Any]] = {}

    for source_table in ("asy_systemdaten", "msy_systemdaten"):
        db = PdvmDatabase(
            source_table,
            system_pool=gcs._system_pool,
            mandant_pool=gcs._mandant_pool,
        )
        try:
            rows = await db.get_all(where="historisch = 0", order_by="name ASC", limit=5000, offset=0)
        except Exception:
            continue

        for row in rows:
            daten = row.get("daten") if isinstance(row, dict) else {}
            if not isinstance(daten, dict):
                continue
            root = daten.get("ROOT") if isinstance(daten.get("ROOT"), dict) else {}
            template_meta = daten.get("TEMPLATE_META") if isinstance(daten.get("TEMPLATE_META"), dict) else {}

            table_candidates = [
                template_meta.get("TARGET_TABLE"),
                root.get("TARGET_TABLE"),
                root.get("TABLE_NAME"),
                _extract_table_from_template_meta_name(row.get("name") if isinstance(row, dict) else ""),
                root.get("TABLE"),
            ]

            table_name = ""
            for candidate in table_candidates:
                try:
                    normalized = _normalize_table_name(candidate, allow_empty=True)
                except Exception:
                    normalized = ""
                if not normalized:
                    continue
                # In asy/msy_systemdaten ist ROOT.TABLE oft die Catalog-Tabelle selbst und
                # nicht die fachliche Zieltabelle.
                if normalized in {"asy_systemdaten", "msy_systemdaten"}:
                    continue
                table_name = normalized
                break

            if not table_name:
                continue

            is_active_raw = root.get("IS_ACTIVE")
            if is_active_raw is None:
                is_active_raw = template_meta.get("IS_ACTIVE")
            is_active = True if is_active_raw is None else bool(is_active_raw)
            if not is_active and not include_inactive:
                continue

            label = str(
                template_meta.get("DISPLAY_NAME")
                or template_meta.get("LABEL")
                or row.get("name")
                or table_name
            ).strip() or table_name

            existing = out_by_table.get(table_name)
            candidate = {
                "table": table_name,
                "label": label,
                "is_active": is_active,
                "source": source_table,
                "meta": {
                    "domain": root.get("DOMAIN") or template_meta.get("DOMAIN"),
                    "app_key": root.get("APP_KEY") or template_meta.get("APP_KEY"),
                    "template_mode": template_meta.get("TEMPLATE_MODE"),
                },
            }

            if existing is None:
                out_by_table[table_name] = candidate
                continue

            # asy-Katalog priorisieren, falls Eintrag doppelt aus asy/msy vorliegt.
            if existing.get("source") == "msy_systemdaten" and source_table == "asy_systemdaten":
                out_by_table[table_name] = candidate

    rows_out = list(out_by_table.values())
    rows_out.sort(key=lambda x: str(x.get("table") or ""))
    return rows_out


async def _load_table_acl_policies(gcs: PdvmCentralSystemsteuerung) -> Dict[str, Dict[str, Set[str]]]:
    """Lädt tabellenbezogene ACL-Policies aus msy_security (mandantenbezogen)."""
    db = PdvmDatabase(
        "msy_security",
        system_pool=gcs._system_pool,
        mandant_pool=gcs._mandant_pool,
    )
    try:
        rows = await db.get_all(where="historisch = 0", order_by="name ASC", limit=5000, offset=0)
    except Exception:
        return {}

    policies: Dict[str, Dict[str, Set[str]]] = {}

    def _bucket(table_name: str) -> Dict[str, Set[str]]:
        b = policies.get(table_name)
        if isinstance(b, dict):
            return b
        b = {"allow": set(), "read_only": set(), "deny": set()}
        policies[table_name] = b
        return b

    def _safe_norm_table(value: Any) -> str:
        try:
            return _normalize_table_name(value, allow_empty=True)
        except Exception:
            return ""

    for row in rows:
        daten = row.get("daten") if isinstance(row, dict) else {}
        if not isinstance(daten, dict):
            continue
        root = daten.get("ROOT") if isinstance(daten.get("ROOT"), dict) else {}

        role_set = _normalize_roles_raw(root.get("ROLE")) | _normalize_roles_raw(root.get("ROLES"))
        allow_roles = _normalize_roles_raw(root.get("ALLOWED_ROLES"))
        read_only_roles = _normalize_roles_raw(root.get("READ_ONLY_ROLES"))
        deny_roles = _normalize_roles_raw(root.get("DENY_ROLES"))

        if not allow_roles and role_set and root.get("READ_ONLY") in (False, 0, "0", "false", "FALSE", None):
            allow_roles = set(role_set)
        if not read_only_roles and role_set and root.get("READ_ONLY") in (True, 1, "1", "true", "TRUE"):
            read_only_roles = set(role_set)

        table_name_raw = root.get("TARGET_TABLE") or root.get("TABLE_NAME")
        table_name = _safe_norm_table(table_name_raw)
        if table_name:
            b = _bucket(table_name)
            b["allow"].update(allow_roles)
            b["read_only"].update(read_only_roles)
            b["deny"].update(deny_roles)

        allowed_tables = [_safe_norm_table(t) for t in _parse_string_list(root.get("ALLOWED_TABLES"))]
        read_only_tables = [_safe_norm_table(t) for t in _parse_string_list(root.get("READ_ONLY_TABLES"))]
        deny_tables = [_safe_norm_table(t) for t in _parse_string_list(root.get("DENY_TABLES"))]

        if role_set:
            for t in allowed_tables:
                if not t:
                    continue
                _bucket(t)["allow"].update(role_set)
            for t in read_only_tables:
                if not t:
                    continue
                _bucket(t)["read_only"].update(role_set)
            for t in deny_tables:
                if not t:
                    continue
                _bucket(t)["deny"].update(role_set)

    return policies


def _resolve_table_access(
    *,
    table_name: str,
    user_roles: Set[str],
    policies: Dict[str, Dict[str, Set[str]]],
) -> Dict[str, Any]:
    # Vorgabe: developer/develop hat immer Vollzugriff.
    if user_roles.intersection({"developer", "develop"}):
        return {"selectable": True, "read_only": False, "reason": "developer_full_access"}

    policy = policies.get(table_name)
    if not isinstance(policy, dict):
        return {"selectable": False, "read_only": True, "reason": "no_policy"}

    deny = policy.get("deny") if isinstance(policy.get("deny"), set) else set()
    allow = policy.get("allow") if isinstance(policy.get("allow"), set) else set()
    read_only = policy.get("read_only") if isinstance(policy.get("read_only"), set) else set()

    if deny and user_roles.intersection(deny):
        return {"selectable": False, "read_only": True, "reason": "denied_by_role"}
    if allow and user_roles.intersection(allow):
        return {"selectable": True, "read_only": False, "reason": "allowed_by_role"}
    if read_only and user_roles.intersection(read_only):
        return {"selectable": False, "read_only": True, "reason": "read_only_by_role"}

    return {"selectable": False, "read_only": True, "reason": "role_not_allowed"}


async def _resolve_table_catalog_dropdown(
    gcs: PdvmCentralSystemsteuerung,
    *,
    dropdown_config: Dict[str, Any],
) -> Dict[str, Any]:
    effective_limit = _normalize_result_limit(dropdown_config.get("limit"))
    include_inactive = str(dropdown_config.get("include_inactive") or "").strip().lower() in {"1", "true", "yes", "on"}
    prefix_filter = str(dropdown_config.get("prefix") or "").strip().lower()

    catalog = await _load_table_meta_catalog(gcs, include_inactive=include_inactive)
    user_roles = await _load_effective_user_roles(gcs)
    policies = await _load_table_acl_policies(gcs)
    can_see_sys_tables = bool(user_roles.intersection({"developer", "develop"}))
    current_table = _normalize_table_name(
        dropdown_config.get("table")
        or dropdown_config.get("selected_table")
        or dropdown_config.get("value"),
        allow_empty=True,
    )

    # Linearer Zusatzkatalog: sys_* direkt aus DB-Schema laden (nicht von TABLE_META abhaengig).
    # Nur fuer develop/developer sichtbar.
    if can_see_sys_tables:
        try:
            sys_tables = await _list_tables_for_prefix(
                gcs,
                prefix="sys_",
                timeout_seconds=float(getattr(settings, "DROPDOWN_PREFIX_TIMEOUT_SECONDS", 2.0) or 2.0),
            )
            existing_tables = {
                str(item.get("table") or "").strip().lower()
                for item in catalog
                if isinstance(item, dict)
            }
            for table_name in sys_tables:
                if table_name in existing_tables:
                    continue
                catalog.append(
                    {
                        "table": table_name,
                        "label": table_name,
                        "is_active": True,
                        "source": "system_schema",
                        "meta": {"domain": "system"},
                    }
                )
        except Exception:
            # Best-effort: fehlender Zusatzkatalog darf den Dialog nicht blockieren.
            pass

    options: List[Dict[str, Any]] = []
    mapping: Dict[str, str] = {}
    selectable_count = 0
    listed_tables: Set[str] = set()

    for item in catalog:
        table_name = str(item.get("table") or "").strip().lower()
        if not table_name:
            continue
        if table_name.startswith("sys_") and not can_see_sys_tables:
            continue
        if prefix_filter and not table_name.startswith(prefix_filter):
            continue

        access = _resolve_table_access(table_name=table_name, user_roles=user_roles, policies=policies)
        selectable = bool(access.get("selectable"))
        if selectable:
            selectable_count += 1

        label = str(item.get("label") or table_name)
        options.append(
            {
                "key": table_name,
                "value": label,
                "disabled": not selectable,
                "read_only": bool(access.get("read_only")),
                "reason": str(access.get("reason") or ""),
            }
        )
        mapping[table_name] = label
        listed_tables.add(table_name)

        if len(options) >= effective_limit:
            break

    # Die aktuell gesetzte Tabelle MUSS immer sichtbar sein, auch wenn sie
    # nicht im Katalog enthalten oder per Prefix/Role normal ausgefiltert wurde.
    if current_table and current_table not in listed_tables:
        fallback_item = next((item for item in catalog if str(item.get("table") or "").strip().lower() == current_table), None)
        fallback_label = str((fallback_item or {}).get("label") or current_table)
        access = _resolve_table_access(table_name=current_table, user_roles=user_roles, policies=policies)
        selectable = bool(access.get("selectable"))
        if selectable:
            selectable_count += 1

        options.append(
            {
                "key": current_table,
                "value": fallback_label,
                "disabled": not selectable,
                "read_only": bool(access.get("read_only")),
                "reason": str(access.get("reason") or "") or "forced_current_table",
            }
        )
        mapping[current_table] = fallback_label
        listed_tables.add(current_table)

    return {
        "map": mapping,
        "options": options,
        "language": DEFAULT_LANGUAGE_FALLBACK,
        "default_language": DEFAULT_LANGUAGE_FALLBACK,
        "source": "table_catalog",
        "meta": {
            "result_count": len(options),
            "selectable_count": selectable_count,
            "read_only": selectable_count == 0,
            "roles": sorted(user_roles),
            "roles_source": "asy_benutzer.PERMISSIONS.ROLES",
            "catalog_sources": ["asy_systemdaten", "msy_systemdaten"],
            "acl_source": "msy_security",
            "prefix_filter": prefix_filter or None,
            "include_inactive": include_inactive,
            "max_results": effective_limit,
        },
    }


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
    dropdown_source: Optional[Dict[str, Any]] = None,
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

    # `dropdown` bleibt die stabile Referenzstruktur.
    # Dynamische Aufloesungslogik liegt in `dropdown_source` (neu),
    # wobei legacy `dropdown.source` weiterhin als Fallback unterstuetzt wird.
    effective_config: Dict[str, Any] = dict(dropdown_config)
    embedded_dropdown_source = effective_config.get("dropdown_source") if isinstance(effective_config.get("dropdown_source"), dict) else None
    if not isinstance(dropdown_source, dict) and isinstance(embedded_dropdown_source, dict):
        dropdown_source = embedded_dropdown_source

    if isinstance(dropdown_source, dict):
        source_type = _norm_source(
            dropdown_source.get("type")
            or dropdown_source.get("source")
            or dropdown_source.get("source_type")
        )
        if source_type:
            effective_config["source"] = source_type

        # Direkte optionale Source-Parameter
        for key in ("limit", "include_inactive", "prefix", "table_prefix", "table", "key", "feld", "field", "group"):
            if key in dropdown_source and dropdown_source.get(key) is not None:
                effective_config[key] = dropdown_source.get(key)

        # Verschachtelte Source-Parameter
        params = dropdown_source.get("params") if isinstance(dropdown_source.get("params"), dict) else {}
        for key in ("limit", "include_inactive", "prefix", "table_prefix", "table", "key", "feld", "field", "group"):
            if key in params and params.get(key) is not None:
                effective_config[key] = params.get(key)

    require_explicit = bool(getattr(settings, "DROPDOWN_REQUIRE_EXPLICIT_SOURCE", False))
    source = _norm_source(_get_ci_value(effective_config, "source", "source_type"))

    if not source:
        if require_explicit:
            raise ValueError("DROPDOWN_SOURCE_INVALID: source fehlt (expected: static|view|prefix_multi_table)")

        group_raw = str(_get_ci_value(effective_config, "group") or "").strip().upper()
        if group_raw == "*VIEW":
            source = "view"
        elif _get_ci_value(effective_config, "prefix", "table_prefix"):
            source = "prefix_multi_table"
        else:
            source = "static"
        logger.info("dropdown_source_legacy_fallback source=%s", source)

    if source == "static":
        table_name = _normalize_table_name(_get_ci_value(effective_config, "table") or "sys_dropdowndaten")
        dataset_uid = str(_get_ci_value(effective_config, "key") or "").strip()
        if not dataset_uid:
            raise ValueError("DROPDOWN_SOURCE_INVALID: key fehlt fuer source=static")

        resolved = await get_dropdown_mapping_for_field(
            gcs,
            table=table_name,
            dataset_uid=dataset_uid,
            field=str(_get_ci_value(effective_config, "feld", "field") or "").strip() or None,
            group=str(_get_ci_value(effective_config, "group") or "").strip() or None,
            language=language,
        )
        resolved["source"] = "static"
        return resolved

    if source == "view":
        try:
            resolved = await _resolve_view_dropdown(
                gcs,
                view_guid=str(_get_ci_value(effective_config, "key") or "").strip(),
                table_override=str(_get_ci_value(effective_config, "table") or "").strip() or None,
                requested_limit=_get_ci_value(effective_config, "limit"),
            )
            return resolved
        except TimeoutError:
            raise ValueError("DROPDOWN_VIEW_TIMEOUT")

    if source == "prefix_multi_table":
        prefix = str(_get_ci_value(effective_config, "prefix", "table_prefix") or "").strip().lower()
        return await _resolve_prefix_multi_table_dropdown(
            gcs,
            prefix=prefix,
            requested_limit=_get_ci_value(effective_config, "limit"),
        )

    if source == "table_catalog":
        return await _resolve_table_catalog_dropdown(gcs, dropdown_config=effective_config)

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

    root = _resolve_group_object(daten, "ROOT") or {}
    default_lang = _norm_lang(_get_ci_value(root, "DEFAULT_LANGUAGE") or DEFAULT_LANGUAGE_FALLBACK)

    # Zielmodell: ROOT + OPTIONS, Sprachwerte direkt pro Option (OPTIONS.<key>.<lang>).
    options_obj = _resolve_group_object(daten, "OPTIONS")
    if isinstance(options_obj, dict):
        lang_key = _norm_lang(language)
        field_key = _norm_field(_get_ci_value(root, "FIELD_KEY") or _get_ci_value(root, "SELF_NAME") or "")

        mapping: Dict[str, str] = {}
        options: List[Dict[str, str]] = []

        for option_key, option_value in options_obj.items():
            opt = option_value if isinstance(option_value, dict) else {}

            # Strict-only: direkte Sprachfelder je Option (lineares Modell).
            values: Dict[str, Any] = {}
            meta_keys = {"KEY", "VALUE", "VALUES", "LABEL", "NAME", "ROOT", "OPTIONS", "LIST_NAME", "EDIT_LIST"}
            for vk, vv in opt.items():
                if str(vk or "").strip().upper() in meta_keys:
                    continue
                values[str(vk)] = vv

            label = _get_lang_value(values, lang_key, default_lang)
            if label is None:
                label = ""

            k = str(option_key)
            v = str(label or "")
            mapping[k] = v
            options.append({"key": k, "value": v})

        maps_by_field: Dict[str, Dict[str, str]] = {}
        options_by_field: Dict[str, List[Dict[str, str]]] = {}
        aliases = {
            field_key,
            _norm_field(_get_ci_value(root, "SELF_GUID")),
            _norm_field(_get_ci_value(root, "SELF_NAME")),
        }
        for alias in aliases:
            if not alias:
                continue
            maps_by_field[alias] = mapping
            options_by_field[alias] = options

        return default_lang, maps_by_field, options_by_field

    return default_lang, {}, {}


async def get_dropdown_mapping_for_field(
    gcs: PdvmCentralSystemsteuerung,
    *,
    table: str,
    dataset_uid: str,
    field: Optional[str],
    group: Optional[str] = None,
    language: Optional[str] = None,
) -> Dict[str, Any]:
    """Gibt Mapping+Options für ein Feld zurück.

    Returns:
        {"map": {rawKey: label, ...}, "options": [{key,value}, ...], "language": "DE-DE", "default_language": "DE-DE"}
    """
    table_norm = str(table or "").strip().lower()
    if table_norm in {"sys_systemdaten", "asy_systemdaten"}:
        raise ValueError(
            "LEGACY_DROPDOWN_SOURCE: table=asy_systemdaten (bzw. legacy sys_systemdaten) ist fuer Dropdown-Aufloesung nicht mehr zulaessig; verwende sys_dropdowndaten"
        )

    lang = _norm_lang(language or get_user_language(gcs))
    requested_fld = _norm_field(field)
    fld = requested_fld

    cache = _get_dropdown_cache(gcs)
    group_norm = _norm_group(group)
    cache_key = (str(table), str(dataset_uid), str(lang), group_norm)
    persistent_key = _cache_key(table=table, dataset_uid=dataset_uid, language=lang, group=group)

    entry = cache.get(cache_key)
    if not isinstance(entry, dict):
        entry = {
            "ts": 0.0,
            "default_language": DEFAULT_LANGUAGE_FALLBACK,
            "maps": {},
            "options": {},
            "parser_version": _DROPDOWN_CACHE_SCHEMA_VERSION,
        }
        cache[cache_key] = entry

    def _get_from_entry() -> Optional[Dict[str, Any]]:
        if int(entry.get("parser_version") or 0) != _DROPDOWN_CACHE_SCHEMA_VERSION:
            return None
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

    if fld:
        hit = _get_from_entry()
        if hit is not None:
            return hit

    source_modified_at = await _load_dataset_modified_at(gcs, table=str(table), dataset_uid=str(dataset_uid))
    source_modified_iso = _to_iso(source_modified_at)

    persisted = _read_persistent_dropdown_cache(gcs, persistent_key)
    if isinstance(persisted, dict):
        if int(persisted.get("parser_version") or 0) != _DROPDOWN_CACHE_SCHEMA_VERSION:
            persisted = None

    if isinstance(persisted, dict):
        persisted_mod = _to_iso(persisted.get("source_modified_at"))
        maps_p = persisted.get("maps")
        opts_p = persisted.get("options")
        if source_modified_iso and persisted_mod == source_modified_iso and isinstance(maps_p, dict) and isinstance(opts_p, dict):
            entry["ts"] = float(time.time())
            entry["default_language"] = persisted.get("default_language") or DEFAULT_LANGUAGE_FALLBACK
            entry["maps"] = maps_p
            entry["options"] = opts_p
            entry["parser_version"] = _DROPDOWN_CACHE_SCHEMA_VERSION
            hit_persisted = _get_from_entry()
            if hit_persisted is not None:
                return hit_persisted

    # Load/refresh dataset
    row = await _load_dataset_row(gcs, table=str(table), dataset_uid=str(dataset_uid))
    if not isinstance(row, dict):
        raise ValueError(f"DROPDOWN_DATA_INVALID: dataset nicht gefunden (table={table}, uid={dataset_uid})")

    daten = row.get("daten")
    if not isinstance(daten, dict):
        raise ValueError(f"DROPDOWN_DATA_INVALID: daten ist kein Objekt (table={table}, uid={dataset_uid})")

    root = _resolve_group_object(daten, "ROOT")
    if not isinstance(root, dict):
        raise ValueError(f"DROPDOWN_DATA_INVALID: ROOT fehlt (table={table}, uid={dataset_uid})")

    options_obj = _resolve_group_object(daten, "OPTIONS")
    if not isinstance(options_obj, dict):
        raise ValueError(f"DROPDOWN_DATA_INVALID: OPTIONS fehlt (table={table}, uid={dataset_uid})")

    field_root = _norm_field(_get_ci_value(root, "FIELD_KEY") or _get_ci_value(root, "SELF_NAME") or "")
    if not field_root:
        raise ValueError(f"DROPDOWN_DATA_INVALID: ROOT.FIELD_KEY fehlt (table={table}, uid={dataset_uid})")
    fld = field_root

    default_lang, maps_by_field, options_by_field = _parse_dataset(daten, language=lang, group=group)

    if not isinstance(maps_by_field, dict) or not maps_by_field:
        raise ValueError(f"DROPDOWN_DATA_INVALID: keine auswertbaren Optionen (table={table}, uid={dataset_uid})")

    entry["ts"] = float(time.time())
    entry["default_language"] = default_lang
    entry["maps"] = maps_by_field
    entry["options"] = options_by_field
    entry["parser_version"] = _DROPDOWN_CACHE_SCHEMA_VERSION

    await _write_persistent_dropdown_cache(
        gcs,
        persistent_key,
        {
            "parser_version": _DROPDOWN_CACHE_SCHEMA_VERSION,
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
                "parser_version": _DROPDOWN_CACHE_SCHEMA_VERSION,
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

    raise ValueError(
        f"DROPDOWN_DATA_INVALID: field nicht gefunden (field={field}, table={table}, uid={dataset_uid})"
    )

"""
PDVM Dialog/View/Frame Konsistenzanalyse V1.

Usage:
  python backend/tools/dialog_view_frame_consistency_analyzer_v1.py
  python backend/tools/dialog_view_frame_consistency_analyzer_v1.py --output backend/reports/dialog_view_frame_consistency_report_v1.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import asyncpg

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.connection_manager import ConnectionManager
from tools.phaseB_persist_template_modes import SYSTEM_MANDANT_UIDS

ALLOWED_DIALOG_TYPES = {"edit", "work", "acti", "norm"}
ALLOWED_MODULES = {"view", "show", "edit", "acti"}
POLICY_PATH = BACKEND_DIR / "config" / "dialog_view_frame_analyzer_policy_v1.json"

DEFAULT_POLICY: Dict[str, Any] = {
    "version": 1,
    "metadata": {
        "owner": "pdvm-architecture",
        "review_cycle_days": 30,
        "expires_soon_days": 14,
    },
    "tabless_dialog_exceptions": [],
    "dropdown_source_guardrails": {
        "allowed_sources": ["static", "view", "prefix_multi_table"],
        "require_explicit_source": False,
        "prefix_whitelist": ["msy_", "tst_"],
        "max_result_limit": 300,
    },
    "edit_type_contracts": {
        "view": {"status": "stable", "scope": "view modules"},
        "pdvm_edit": {"status": "stable", "scope": "default edit modules"},
        "show_json": {"status": "transitional", "scope": "developer json display"},
        "edit_json": {"status": "transitional", "scope": "developer json edit"},
        "import_data": {"status": "stable", "scope": "import flows"},
        "menu": {"status": "stable", "scope": "menu management flows"},
        "edit_user": {"status": "stable", "scope": "user management flows"},
    },
}

_TABLE_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _as_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            return {}
    return {}


def _dropdown_option_lang_values(option_item: Dict[str, Any]) -> Dict[str, Any]:
    item = _as_dict(option_item)
    out: Dict[str, Any] = {}
    for k, v in item.items():
        ku = str(k or "").strip().upper()
        if ku in {"KEY", "VALUE", "VALUES", "LABEL", "NAME"}:
            continue
        out[str(k)] = v
    return out


def _as_list(value: Any) -> List[Any]:
    if isinstance(value, list):
        return value
    return []


def _load_policy(policy_path: Path) -> Dict[str, Any]:
    policy = dict(DEFAULT_POLICY)
    if not policy_path.exists():
        return policy

    try:
        payload = json.loads(policy_path.read_text(encoding="utf-8"))
    except Exception:
        return policy

    if isinstance(payload, dict):
        policy.update(payload)
    if not isinstance(policy.get("tabless_dialog_exceptions"), list):
        policy["tabless_dialog_exceptions"] = []
    if not isinstance(policy.get("edit_type_contracts"), dict):
        policy["edit_type_contracts"] = dict(DEFAULT_POLICY["edit_type_contracts"])
    if not isinstance(policy.get("metadata"), dict):
        policy["metadata"] = dict(DEFAULT_POLICY["metadata"])
    if not isinstance(policy.get("dropdown_source_guardrails"), dict):
        policy["dropdown_source_guardrails"] = dict(DEFAULT_POLICY["dropdown_source_guardrails"])
    return policy


def _find_dropdown_nodes(obj: Any, path: str = "") -> List[Dict[str, Any]]:
    findings: List[Dict[str, Any]] = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            key_str = str(key)
            next_path = f"{path}.{key_str}" if path else key_str
            if key_str.strip().lower() == "dropdown" and isinstance(value, dict):
                findings.append({"path": next_path, "dropdown": value})
            findings.extend(_find_dropdown_nodes(value, next_path))
    elif isinstance(obj, list):
        for index, item in enumerate(obj):
            next_path = f"{path}[{index}]" if path else f"[{index}]"
            findings.extend(_find_dropdown_nodes(item, next_path))
    return findings


def _normalize_dropdown_source(cfg: Dict[str, Any]) -> str:
    raw = str(cfg.get("source") or cfg.get("source_type") or "").strip().lower()
    aliases = {
        "prefix": "prefix_multi_table",
        "prefix_multi": "prefix_multi_table",
        "prefix_multitable": "prefix_multi_table",
        "table_prefix": "prefix_multi_table",
    }
    return aliases.get(raw, raw)


def _is_valid_table_name(name: str) -> bool:
    return bool(_TABLE_NAME_RE.match(str(name or "")))


def _parse_iso_date(value: Any) -> Optional[datetime]:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(f"{text}T00:00:00+00:00")
    except Exception:
        return None


async def _table_exists(conn: asyncpg.Connection, table_name: str) -> bool:
    exists = await conn.fetchval("SELECT to_regclass($1) IS NOT NULL", f"public.{table_name}")
    return bool(exists)


async def _resolve_table(conn: asyncpg.Connection, candidates: List[str]) -> Optional[str]:
    for t in candidates:
        if await _table_exists(conn, t):
            return t
    return None


async def _load_rows(conn: asyncpg.Connection, table_name: str) -> List[Dict[str, Any]]:
    rows = await conn.fetch(
        f'''
        SELECT uid::text AS uid, name, daten
        FROM "{table_name}"
        WHERE COALESCE(historisch, 0) = 0
        ORDER BY created_at
        '''
    )
    out: List[Dict[str, Any]] = []
    for row in rows:
        uid = str(row.get("uid") or "")
        if uid in SYSTEM_MANDANT_UIDS:
            continue
        out.append({"uid": uid, "name": str(row.get("name") or ""), "daten": _as_dict(row.get("daten"))})
    return out


def _collect_tabs(root: Dict[str, Any]) -> List[Dict[str, Any]]:
    tabs = []

    # Variante A: TAB_ELEMENTS als Liste
    tab_elements_list = _as_list(root.get("TAB_ELEMENTS"))
    for i, entry in enumerate(tab_elements_list, start=1):
        e = _as_dict(entry)
        if not e:
            continue
        tabs.append(
            {
                "index": i,
                "module": str(e.get("MODULE") or e.get("module") or "").strip().lower(),
                "guid": str(e.get("GUID") or e.get("guid") or "").strip(),
                "edit_type": str(e.get("EDIT_TYPE") or e.get("edit_type") or "").strip().lower(),
                "raw": e,
            }
        )

    # Variante B: TAB_ELEMENTS als Dict mit TAB_XX Eintraegen
    tab_elements_dict = _as_dict(root.get("TAB_ELEMENTS"))
    if tab_elements_dict:
        for key, value in tab_elements_dict.items():
            key_u = str(key).upper()
            if not key_u.startswith("TAB"):
                continue
            e = _as_dict(value)
            if not e:
                continue
            suffix = key_u[3:]
            suffix = suffix.lstrip("_")
            suffix = "".join(ch for ch in suffix if ch.isdigit())
            try:
                idx = int(suffix)
            except Exception:
                idx = int(e.get("TAB") or 999)
            tabs.append(
                {
                    "index": idx,
                    "module": str(e.get("MODULE") or e.get("module") or "").strip().lower(),
                    "guid": str(e.get("GUID") or e.get("guid") or "").strip(),
                    "edit_type": str(e.get("EDIT_TYPE") or e.get("edit_type") or "").strip().lower(),
                    "raw": e,
                }
            )

    if tabs:
        return sorted(tabs, key=lambda t: int(t.get("index") or 999))

    for key, value in root.items():
        key_u = str(key).upper()
        if not key_u.startswith("TAB_"):
            continue
        e = _as_dict(value)
        if not e:
            continue
        suffix = key_u.split("TAB_", 1)[1]
        try:
            idx = int(suffix)
        except Exception:
            idx = 999
        tabs.append(
            {
                "index": idx,
                "module": str(e.get("MODULE") or e.get("module") or "").strip().lower(),
                "guid": str(e.get("GUID") or e.get("guid") or "").strip(),
                "edit_type": str(e.get("EDIT_TYPE") or e.get("edit_type") or "").strip().lower(),
                "raw": e,
            }
        )

    tabs = sorted(tabs, key=lambda t: int(t.get("index") or 999))
    return tabs


def _add_violation(report: Dict[str, Any], severity: str, code: str, details: Dict[str, Any]) -> None:
    report.setdefault("violations", []).append({"severity": severity, "code": code, "details": details})


async def build_report(policy_path: Optional[Path] = None) -> Dict[str, Any]:
    cfg = await ConnectionManager.get_system_config("pdvm_system")
    conn = await asyncpg.connect(**cfg.to_dict())
    resolved_policy_path = policy_path or POLICY_PATH
    policy = _load_policy(resolved_policy_path)
    tabless_exception_map = {
        str(_as_dict(e).get("uid") or ""): _as_dict(e)
        for e in _as_list(policy.get("tabless_dialog_exceptions"))
        if str(_as_dict(e).get("uid") or "")
    }
    known_edit_types = set(_as_dict(policy.get("edit_type_contracts")).keys())
    dropdown_guardrails = _as_dict(policy.get("dropdown_source_guardrails"))
    allowed_dropdown_sources = {
        str(x).strip().lower()
        for x in _as_list(dropdown_guardrails.get("allowed_sources"))
        if str(x).strip()
    }
    require_explicit_source = bool(dropdown_guardrails.get("require_explicit_source", False))
    prefix_whitelist = {
        str(x).strip().lower()
        for x in _as_list(dropdown_guardrails.get("prefix_whitelist"))
        if str(x).strip()
    }
    try:
        max_result_limit = int(dropdown_guardrails.get("max_result_limit", 300))
    except Exception:
        max_result_limit = 300
    if max_result_limit <= 0:
        max_result_limit = 300
    policy_metadata = _as_dict(policy.get("metadata"))
    try:
        expires_soon_days = int(policy_metadata.get("expires_soon_days", 14))
    except Exception:
        expires_soon_days = 14
    if expires_soon_days < 0:
        expires_soon_days = 14

    report: Dict[str, Any] = {
        "phase": "dialog_view_frame_consistency_analyzer_v1",
        "generated_at_utc": _utc_now(),
        "database": cfg.database,
        "policy": {
            "path": str(resolved_policy_path),
            "version": policy.get("version"),
            "tabless_dialog_exceptions": len(tabless_exception_map),
            "known_edit_types": sorted(known_edit_types),
            "dropdown_source_guardrails": {
                "allowed_sources": sorted(allowed_dropdown_sources),
                "require_explicit_source": require_explicit_source,
                "prefix_whitelist": sorted(prefix_whitelist),
                "max_result_limit": max_result_limit,
            },
            "metadata": policy_metadata,
        },
        "resolved_tables": {},
        "inventory": {
            "dialog_count": 0,
            "view_count": 0,
            "frame_count": 0,
            "dialog_types": {},
            "modules": {},
            "edit_types": {},
            "unknown_edit_types": [],
            "dropdown_config_count": 0,
            "dropdown_sources": {},
            "single_tab_dialogs": 0,
            "work_dialogs": 0,
        },
        "checks": [],
        "violations": [],
        "recommendations": [],
        "summary": {
            "checks_total": 0,
            "checks_passed": 0,
            "checks_failed": 0,
            "violations_error": 0,
            "violations_warning": 0,
            "overall_status": "passed",
        },
    }

    try:
        dialog_table = await _resolve_table(conn, ["sys_dialogdaten", "asy_dialogdaten", "msy_dialogdaten"])
        view_table = await _resolve_table(conn, ["sys_viewdaten", "asy_viewdaten", "msy_viewdaten"])
        frame_table = await _resolve_table(conn, ["sys_framedaten", "asy_framedaten", "msy_framedaten"])
        dropdown_table = await _resolve_table(conn, ["sys_dropdowndaten", "asy_dropdowndaten", "msy_dropdowndaten"])

        report["resolved_tables"] = {
            "dialog": dialog_table,
            "view": view_table,
            "frame": frame_table,
            "dropdown": dropdown_table,
        }

        if not dialog_table:
            _add_violation(report, "error", "dialog_table_missing", {"candidates": ["sys_dialogdaten", "asy_dialogdaten", "msy_dialogdaten"]})
        if not view_table:
            _add_violation(report, "error", "view_table_missing", {"candidates": ["sys_viewdaten", "asy_viewdaten", "msy_viewdaten"]})
        if not frame_table:
            _add_violation(report, "error", "frame_table_missing", {"candidates": ["sys_framedaten", "asy_framedaten", "msy_framedaten"]})

        dialog_rows = await _load_rows(conn, dialog_table) if dialog_table else []
        view_rows = await _load_rows(conn, view_table) if view_table else []
        frame_rows = await _load_rows(conn, frame_table) if frame_table else []
        dropdown_rows = await _load_rows(conn, dropdown_table) if dropdown_table else []

        def _scan_dropdowns_in_row(row: Dict[str, Any], *, object_type: str) -> None:
            data = _as_dict(row.get("daten"))
            for node in _find_dropdown_nodes(data):
                cfg = _as_dict(node.get("dropdown"))
                path = str(node.get("path") or "")
                report["inventory"]["dropdown_config_count"] = int(report["inventory"].get("dropdown_config_count", 0)) + 1

                source = _normalize_dropdown_source(cfg)
                source_key = source or "<implicit>"
                report["inventory"]["dropdown_sources"][source_key] = report["inventory"]["dropdown_sources"].get(source_key, 0) + 1

                if not source:
                    if require_explicit_source:
                        _add_violation(
                            report,
                            "error",
                            "dropdown_guardrail_source_missing",
                            {
                                "object_type": object_type,
                                "object_uid": row.get("uid"),
                                "object_name": row.get("name"),
                                "path": path,
                            },
                        )
                    continue

                if source not in allowed_dropdown_sources:
                    _add_violation(
                        report,
                        "error",
                        "dropdown_guardrail_source_not_allowed",
                        {
                            "object_type": object_type,
                            "object_uid": row.get("uid"),
                            "object_name": row.get("name"),
                            "path": path,
                            "source": source,
                            "allowed_sources": sorted(allowed_dropdown_sources),
                        },
                    )
                    continue

                table_name = str(cfg.get("table") or "").strip().lower()
                if table_name and not _is_valid_table_name(table_name):
                    _add_violation(
                        report,
                        "error",
                        "dropdown_guardrail_table_name_invalid",
                        {
                            "object_type": object_type,
                            "object_uid": row.get("uid"),
                            "object_name": row.get("name"),
                            "path": path,
                            "table": table_name,
                        },
                    )

                if table_name == "sys_systemdaten":
                    _add_violation(
                        report,
                        "error",
                        "dropdown_guardrail_legacy_table_forbidden",
                        {
                            "object_type": object_type,
                            "object_uid": row.get("uid"),
                            "object_name": row.get("name"),
                            "path": path,
                            "table": table_name,
                        },
                    )

                if source == "static":
                    key = str(cfg.get("key") or "").strip()
                    field_name = str(cfg.get("feld") or cfg.get("field") or "").strip()
                    if not key:
                        _add_violation(
                            report,
                            "error",
                            "dropdown_guardrail_static_key_missing",
                            {
                                "object_type": object_type,
                                "object_uid": row.get("uid"),
                                "object_name": row.get("name"),
                                "path": path,
                            },
                        )
                    if not field_name:
                        _add_violation(
                            report,
                            "error",
                            "dropdown_guardrail_static_field_missing",
                            {
                                "object_type": object_type,
                                "object_uid": row.get("uid"),
                                "object_name": row.get("name"),
                                "path": path,
                            },
                        )

                if source == "view":
                    key = str(cfg.get("key") or "").strip()
                    if not key:
                        _add_violation(
                            report,
                            "error",
                            "dropdown_guardrail_view_key_missing",
                            {
                                "object_type": object_type,
                                "object_uid": row.get("uid"),
                                "object_name": row.get("name"),
                                "path": path,
                            },
                        )
                    if not table_name:
                        _add_violation(
                            report,
                            "error",
                            "dropdown_guardrail_view_table_missing",
                            {
                                "object_type": object_type,
                                "object_uid": row.get("uid"),
                                "object_name": row.get("name"),
                                "path": path,
                            },
                        )

                if source == "prefix_multi_table":
                    prefix = str(cfg.get("prefix") or cfg.get("table_prefix") or "").strip().lower()
                    if not prefix:
                        _add_violation(
                            report,
                            "error",
                            "dropdown_guardrail_prefix_missing",
                            {
                                "object_type": object_type,
                                "object_uid": row.get("uid"),
                                "object_name": row.get("name"),
                                "path": path,
                            },
                        )
                    elif not prefix.endswith("_"):
                        _add_violation(
                            report,
                            "error",
                            "dropdown_guardrail_prefix_format_invalid",
                            {
                                "object_type": object_type,
                                "object_uid": row.get("uid"),
                                "object_name": row.get("name"),
                                "path": path,
                                "prefix": prefix,
                            },
                        )
                    elif prefix not in prefix_whitelist:
                        _add_violation(
                            report,
                            "error",
                            "dropdown_guardrail_prefix_not_whitelisted",
                            {
                                "object_type": object_type,
                                "object_uid": row.get("uid"),
                                "object_name": row.get("name"),
                                "path": path,
                                "prefix": prefix,
                                "prefix_whitelist": sorted(prefix_whitelist),
                            },
                        )

                    raw_limit = cfg.get("limit")
                    if raw_limit is not None:
                        try:
                            limit_value = int(raw_limit)
                        except Exception:
                            _add_violation(
                                report,
                                "error",
                                "dropdown_guardrail_limit_invalid",
                                {
                                    "object_type": object_type,
                                    "object_uid": row.get("uid"),
                                    "object_name": row.get("name"),
                                    "path": path,
                                    "limit": raw_limit,
                                },
                            )
                        else:
                            if limit_value <= 0 or limit_value > max_result_limit:
                                _add_violation(
                                    report,
                                    "error",
                                    "dropdown_guardrail_limit_exceeds_max",
                                    {
                                        "object_type": object_type,
                                        "object_uid": row.get("uid"),
                                        "object_name": row.get("name"),
                                        "path": path,
                                        "limit": limit_value,
                                        "max_result_limit": max_result_limit,
                                    },
                                )

        for row in dialog_rows:
            _scan_dropdowns_in_row(row, object_type="dialog")
        for row in view_rows:
            _scan_dropdowns_in_row(row, object_type="view")
        for row in frame_rows:
            _scan_dropdowns_in_row(row, object_type="frame")

        view_guids = {r["uid"] for r in view_rows}
        frame_guids = {r["uid"] for r in frame_rows}

        report["inventory"]["dialog_count"] = len(dialog_rows)
        report["inventory"]["view_count"] = len(view_rows)
        report["inventory"]["frame_count"] = len(frame_rows)

        for d in dialog_rows:
            data = _as_dict(d.get("daten"))
            root = _as_dict(data.get("ROOT"))
            dtype = str(root.get("DIALOG_TYPE") or "").strip().lower()
            tabs = _collect_tabs(root)

            report["inventory"]["dialog_types"][dtype or "<missing>"] = report["inventory"]["dialog_types"].get(dtype or "<missing>", 0) + 1
            if dtype == "work":
                report["inventory"]["work_dialogs"] += 1
            if len(tabs) == 1:
                report["inventory"]["single_tab_dialogs"] += 1

            if not dtype or dtype not in ALLOWED_DIALOG_TYPES:
                _add_violation(report, "error", "dialog_type_invalid", {"dialog_uid": d["uid"], "dialog_name": d["name"], "dialog_type": dtype})

            if not tabs:
                if d["uid"] in tabless_exception_map:
                    ex = tabless_exception_map[d["uid"]]
                    owner = str(ex.get("owner") or "").strip()
                    expires_at = str(ex.get("expires_at") or "").strip()
                    expires_dt = _parse_iso_date(expires_at)

                    if not owner or not expires_at or expires_dt is None:
                        _add_violation(
                            report,
                            "warning",
                            "dialog_tabs_exception_metadata_missing",
                            {
                                "dialog_uid": d["uid"],
                                "dialog_name": d["name"],
                                "owner": owner,
                                "expires_at": expires_at,
                            },
                        )
                    else:
                        today = datetime.now(timezone.utc).date()
                        if expires_dt.date() < today:
                            _add_violation(
                                report,
                                "warning",
                                "dialog_tabs_exception_expired",
                                {
                                    "dialog_uid": d["uid"],
                                    "dialog_name": d["name"],
                                    "owner": owner,
                                    "expires_at": expires_at,
                                },
                            )
                        else:
                            days_left = (expires_dt.date() - today).days
                            if days_left <= expires_soon_days:
                                _add_violation(
                                    report,
                                    "warning",
                                    "dialog_tabs_exception_expiring_soon",
                                    {
                                        "dialog_uid": d["uid"],
                                        "dialog_name": d["name"],
                                        "owner": owner,
                                        "expires_at": expires_at,
                                        "days_left": days_left,
                                        "threshold_days": expires_soon_days,
                                    },
                                )

                    _add_violation(
                        report,
                        "warning",
                        "dialog_tabs_missing_allowed_exception",
                        {
                            "dialog_uid": d["uid"],
                            "dialog_name": d["name"],
                            "reason": str(ex.get("reason") or "policy exception"),
                            "owner": owner,
                            "expires_at": expires_at,
                        },
                    )
                else:
                    _add_violation(report, "error", "dialog_tabs_missing", {"dialog_uid": d["uid"], "dialog_name": d["name"]})
                continue

            last_tab_module = str(tabs[-1].get("module") or "")
            if dtype == "work" and last_tab_module != "acti":
                _add_violation(
                    report,
                    "error",
                    "work_last_tab_not_acti",
                    {"dialog_uid": d["uid"], "dialog_name": d["name"], "last_tab_module": last_tab_module},
                )

            for tab in tabs:
                module = str(tab.get("module") or "")
                guid = str(tab.get("guid") or "")
                edit_type = str(tab.get("edit_type") or "")

                report["inventory"]["modules"][module or "<missing>"] = report["inventory"]["modules"].get(module or "<missing>", 0) + 1
                if edit_type:
                    report["inventory"]["edit_types"][edit_type] = report["inventory"]["edit_types"].get(edit_type, 0) + 1

                if module not in ALLOWED_MODULES:
                    _add_violation(report, "error", "tab_module_invalid", {"dialog_uid": d["uid"], "module": module, "tab_index": tab.get("index")})
                    continue

                if module == "view":
                    if not guid or guid not in view_guids:
                        _add_violation(report, "error", "view_guid_missing_or_not_found", {"dialog_uid": d["uid"], "guid": guid, "tab_index": tab.get("index")})

                if module in {"edit", "acti"}:
                    if not guid or guid not in frame_guids:
                        _add_violation(report, "error", "frame_guid_missing_or_not_found", {"dialog_uid": d["uid"], "guid": guid, "tab_index": tab.get("index")})

                if edit_type and edit_type not in known_edit_types:
                    _add_violation(report, "warning", "unknown_edit_type", {"dialog_uid": d["uid"], "edit_type": edit_type, "tab_index": tab.get("index")})

            unknown_edit_types = [k for k in report["inventory"]["edit_types"].keys() if k not in known_edit_types]
        report["inventory"]["unknown_edit_types"] = sorted(unknown_edit_types)

        # Dropdown language convention check
        dropdown_langs = set()
        for row in dropdown_rows:
            data = _as_dict(row.get("daten"))
            options = _as_dict(data.get("OPTIONS"))
            for _, opt in options.items():
                values = _dropdown_option_lang_values(_as_dict(opt))
                for lang in values.keys():
                    key = str(lang or "").strip().upper()
                    if key:
                        dropdown_langs.add(key)

        has_de = "DE-DE" in dropdown_langs
        has_en = "EN-US" in dropdown_langs
        if not has_de or not has_en:
            _add_violation(
                report,
                "warning",
                "dropdown_two_language_convention_not_met",
                {
                    "observed_languages": sorted(dropdown_langs),
                    "required_hint": ["DE-DE", "EN-US"],
                },
            )

        report.setdefault("checks", []).extend(
            [
                {
                    "name": "dialog_table_present",
                    "ok": dialog_table is not None,
                    "details": {"resolved": dialog_table},
                },
                {
                    "name": "view_table_present",
                    "ok": view_table is not None,
                    "details": {"resolved": view_table},
                },
                {
                    "name": "frame_table_present",
                    "ok": frame_table is not None,
                    "details": {"resolved": frame_table},
                },
                {
                    "name": "work_last_tab_acti_rule",
                    "ok": not any(v for v in report["violations"] if v["code"] == "work_last_tab_not_acti"),
                    "details": {"work_dialogs": report["inventory"].get("work_dialogs", 0)},
                },
                {
                    "name": "guid_references_valid",
                    "ok": not any(v for v in report["violations"] if v["code"] in {"view_guid_missing_or_not_found", "frame_guid_missing_or_not_found"}),
                    "details": {
                        "dialogs": report["inventory"].get("dialog_count", 0),
                        "views": report["inventory"].get("view_count", 0),
                        "frames": report["inventory"].get("frame_count", 0),
                    },
                },
                {
                    "name": "dropdown_two_language_hint",
                    "ok": has_de and has_en,
                    "details": {"observed_languages": sorted(dropdown_langs)},
                },
                {
                    "name": "dropdown_source_guardrails_valid",
                    "ok": not any(v for v in report["violations"] if str(v.get("code") or "").startswith("dropdown_guardrail_")),
                    "details": {
                        "dropdown_config_count": report["inventory"].get("dropdown_config_count", 0),
                        "dropdown_sources": report["inventory"].get("dropdown_sources", {}),
                        "allowed_sources": sorted(allowed_dropdown_sources),
                        "require_explicit_source": require_explicit_source,
                        "prefix_whitelist": sorted(prefix_whitelist),
                        "max_result_limit": max_result_limit,
                    },
                },
            ]
        )

        # Recommendations
        if any(v for v in report["violations"] if v["code"] == "work_last_tab_not_acti"):
            report["recommendations"].append("Work-Dialoge auf Endtab MODULE=acti normalisieren.")
        if any(v for v in report["violations"] if v["code"] in {"view_guid_missing_or_not_found", "frame_guid_missing_or_not_found"}):
            report["recommendations"].append("Dialog-Tab-GUID-Referenzen auf existierende View/Frame Datensaetze korrigieren.")
        if any(v for v in report["violations"] if v["code"] == "unknown_edit_type"):
            report["recommendations"].append("Unbekannte Edit-Typen dokumentieren oder auf bekannte Contracts migrieren.")
        if any(v for v in report["violations"] if v["code"] == "dialog_tabs_missing_allowed_exception"):
            report["recommendations"].append("Zugelassene tab-lose Spezialdialoge regelmaessig pruefen und mittelfristig auf explizites Tab-Layout migrieren.")
        if any(v for v in report["violations"] if v["code"] == "dialog_tabs_exception_metadata_missing"):
            report["recommendations"].append("Tab-lose Ausnahmen mit owner und expires_at vollstaendig pflegen.")
        if any(v for v in report["violations"] if v["code"] == "dialog_tabs_exception_expired"):
            report["recommendations"].append("Abgelaufene Tab-Ausnahmen verlaengern oder den Dialog auf Tab-Layout migrieren.")
        if any(v for v in report["violations"] if v["code"] == "dialog_tabs_exception_expiring_soon"):
            report["recommendations"].append("Tab-Ausnahmen mit kurzem Restlauf (T-Threshold) aktiv reviewen und fruehzeitig entscheiden.")
        if any(v for v in report["violations"] if v["code"] == "dropdown_two_language_convention_not_met"):
            report["recommendations"].append("Statische Dropdowns auf zweisprachige Pflege (DE-DE + EN-US) haerten.")
        if any(v for v in report["violations"] if str(v.get("code") or "").startswith("dropdown_guardrail_")):
            report["recommendations"].append("Dropdown-Quellen auf B.4 Guardrails (source/prefix/limit/legacy-table) standardisieren.")

    finally:
        await conn.close()

    checks = report.get("checks", [])
    checks_total = len(checks)
    checks_passed = sum(1 for c in checks if bool(c.get("ok")))
    checks_failed = checks_total - checks_passed

    violations = report.get("violations", [])
    v_err = sum(1 for v in violations if str(v.get("severity") or "") == "error")
    v_warn = sum(1 for v in violations if str(v.get("severity") or "") == "warning")

    report["summary"] = {
        "checks_total": checks_total,
        "checks_passed": checks_passed,
        "checks_failed": checks_failed,
        "violations_error": v_err,
        "violations_warning": v_warn,
        "overall_status": "passed" if v_err == 0 else "failed",
    }

    return report


def _default_output_path() -> Path:
    return BACKEND_DIR / "reports" / "dialog_view_frame_consistency_report_v1.json"


async def _run(output_path: Path, policy_path: Optional[Path]) -> int:
    report = await build_report(policy_path=policy_path)
    s = _as_dict(report.get("summary"))
    print("\n=== Dialog/View/Frame Consistency Analyzer V1 ===")
    print(f"Overall status: {s.get('overall_status')}")
    print(f"Checks passed/total: {s.get('checks_passed')} / {s.get('checks_total')}")
    print(f"Violations (error/warning): {s.get('violations_error')} / {s.get('violations_warning')}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nReport geschrieben: {output_path}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Dialog/View/Frame consistency analyzer v1")
    parser.add_argument("--output", default=str(_default_output_path()), help="Pfad fuer JSON-Report")
    parser.add_argument("--policy", default=None, help="Optionaler Pfad auf eine Analyzer-Policy JSON")
    args = parser.parse_args()
    policy_path = Path(args.policy) if args.policy else None
    return asyncio.run(_run(Path(args.output), policy_path))


if __name__ == "__main__":
    raise SystemExit(main())

"""
Phase C Punkt 7: Pflicht-Uebersetzungsumfang je Inhaltstyp validieren.

Usage:
  python backend/tools/phaseC_define_required_translation_scope.py
  python backend/tools/phaseC_define_required_translation_scope.py --output backend/reports/phaseC_define_required_translation_scope_v1.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

import asyncpg

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.connection_manager import ConnectionManager
from app.core.i18n_policy import normalize_language
from tools.phaseB_persist_template_modes import SYSTEM_MANDANT_UIDS


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


def _load_scope_config(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _normalize_content_type(raw: str, aliases: Dict[str, str]) -> str:
    key = str(raw or "").strip().lower()
    if not key:
        return "text"
    return aliases.get(key, key)


def _required_set(rule: Dict[str, Any]) -> Set[str]:
    values = rule.get("required_languages") or []
    return {normalize_language(v) for v in values if str(v or "").strip()}


async def _collect_dropdown_coverage(
    conn: asyncpg.Connection,
    required_by_type: Dict[str, Set[str]],
) -> Dict[str, Any]:
    rule_required = required_by_type.get("dropdown", set())
    rows = await conn.fetch(
        '''
        SELECT uid::text AS uid, daten
        FROM "sys_dropdowndaten"
        WHERE COALESCE(historisch, 0) = 0
        ORDER BY created_at
        '''
    )

    items_total = 0
    items_with_missing_required = 0
    required_lang_hits: Dict[str, int] = {k: 0 for k in sorted(rule_required)}
    missing_by_language: Dict[str, int] = {k: 0 for k in sorted(rule_required)}
    sample_missing: List[Dict[str, Any]] = []

    for row in rows:
        uid = str(row.get("uid") or "")
        if uid in SYSTEM_MANDANT_UIDS:
            continue
        daten = _as_dict(row.get("daten"))
        options = _as_dict(daten.get("OPTIONS"))

        for option_key, option_item in options.items():
            item = _as_dict(option_item)
            values = _as_dict(item.get("values"))
            norm_langs = {normalize_language(k) for k in values.keys() if str(k or "").strip()}
            items_total += 1

            missing = sorted(rule_required - norm_langs)
            if missing:
                items_with_missing_required += 1
            for lang in rule_required:
                if lang in norm_langs:
                    required_lang_hits[lang] += 1
                else:
                    missing_by_language[lang] += 1

            if missing and len(sample_missing) < 20:
                sample_missing.append(
                    {
                        "uid": uid,
                        "option_key": str(option_key),
                        "missing_required_languages": missing,
                    }
                )

    return {
        "content_type": "dropdown",
        "items_total": items_total,
        "required_languages": sorted(rule_required),
        "required_lang_hits": required_lang_hits,
        "missing_by_language": missing_by_language,
        "items_with_missing_required": items_with_missing_required,
        "sample_missing": sample_missing,
    }


async def _collect_text_coverage(
    conn: asyncpg.Connection,
    required_by_type: Dict[str, Set[str]],
    type_aliases: Dict[str, str],
) -> Dict[str, Any]:
    rows = await conn.fetch(
        '''
        SELECT uid::text AS uid, daten
        FROM "sys_beschreibungen"
        WHERE COALESCE(historisch, 0) = 0
        ORDER BY created_at
        '''
    )

    coverage: Dict[str, Dict[str, Any]] = {}

    for content_type in ("label", "hilfe", "text"):
        req = required_by_type.get(content_type, set())
        coverage[content_type] = {
            "content_type": content_type,
            "items_total": 0,
            "required_languages": sorted(req),
            "required_lang_hits": {k: 0 for k in sorted(req)},
            "missing_by_language": {k: 0 for k in sorted(req)},
            "items_with_missing_required": 0,
            "sample_missing": [],
        }

    for row in rows:
        uid = str(row.get("uid") or "")
        if uid in SYSTEM_MANDANT_UIDS:
            continue
        daten = _as_dict(row.get("daten"))
        texts = _as_dict(daten.get("TEXTS"))

        for text_key, text_item in texts.items():
            item = _as_dict(text_item)
            raw_type = item.get("text_type") or item.get("type") or "text"
            content_type = _normalize_content_type(str(raw_type), type_aliases)
            if content_type not in coverage:
                content_type = "text"

            c = coverage[content_type]
            req = set(c["required_languages"])
            values = _as_dict(item.get("values"))
            norm_langs = {normalize_language(k) for k in values.keys() if str(k or "").strip()}

            c["items_total"] += 1
            missing = sorted(req - norm_langs)
            if missing:
                c["items_with_missing_required"] += 1

            for lang in req:
                if lang in norm_langs:
                    c["required_lang_hits"][lang] += 1
                else:
                    c["missing_by_language"][lang] += 1

            if missing and len(c["sample_missing"]) < 20:
                c["sample_missing"].append(
                    {
                        "uid": uid,
                        "text_key": str(text_key),
                        "content_type": content_type,
                        "missing_required_languages": missing,
                    }
                )

    return coverage


async def build_report(config_path: Path) -> Dict[str, Any]:
    config = _load_scope_config(config_path)
    rules = _as_dict(config.get("content_type_rules"))
    type_aliases = {str(k).lower(): str(v).lower() for k, v in _as_dict(config.get("type_aliases")).items()}

    required_by_type = {
        content_type: _required_set(_as_dict(rule))
        for content_type, rule in rules.items()
    }

    cfg = await ConnectionManager.get_system_config("pdvm_system")
    conn = await asyncpg.connect(**cfg.to_dict())
    try:
        dropdown_cov = await _collect_dropdown_coverage(conn, required_by_type)
        text_cov = await _collect_text_coverage(conn, required_by_type, type_aliases)
    finally:
        await conn.close()

    all_sections = [dropdown_cov] + [text_cov[k] for k in ("label", "hilfe", "text")]
    items_total = sum(int(x.get("items_total") or 0) for x in all_sections)
    items_with_missing = sum(int(x.get("items_with_missing_required") or 0) for x in all_sections)

    return {
        "phase": "phaseC_define_required_translation_scope",
        "generated_at_utc": _utc_now(),
        "database": cfg.database,
        "scope_config_path": str(config_path),
        "scope_config": config,
        "coverage": {
            "dropdown": dropdown_cov,
            "texts": text_cov,
        },
        "summary": {
            "content_types": ["dropdown", "label", "hilfe", "text"],
            "items_total": items_total,
            "items_with_missing_required": items_with_missing,
            "required_scope_fully_covered": items_with_missing == 0,
        },
    }


def _default_output_path() -> Path:
    return BACKEND_DIR / "reports" / "phaseC_define_required_translation_scope_v1.json"


def _default_config_path() -> Path:
    return BACKEND_DIR / "config" / "i18n_required_translation_scope_v1.json"


def _print_summary(report: Dict[str, Any]) -> None:
    s = report.get("summary", {})
    print("\n=== Phase C Punkt 7: Required Translation Scope ===")
    print(f"Items total: {s.get('items_total')}")
    print(f"Items with missing required: {s.get('items_with_missing_required')}")
    print(f"Required scope fully covered: {s.get('required_scope_fully_covered')}")


async def _run(config_path: Path, output_path: Path) -> int:
    report = await build_report(config_path)
    _print_summary(report)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nReport geschrieben: {output_path}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase C Punkt 7: required translation scope")
    parser.add_argument("--config", default=str(_default_config_path()), help="Pfad zur Scope-Config")
    parser.add_argument("--output", default=str(_default_output_path()), help="Pfad fuer JSON-Report")
    args = parser.parse_args()
    return asyncio.run(_run(Path(args.config), Path(args.output)))


if __name__ == "__main__":
    raise SystemExit(main())

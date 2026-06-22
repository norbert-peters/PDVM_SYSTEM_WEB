"""
Phase C Punkt 6: Finalisiert SUPPORTED_LANGUAGES und DEFAULT_LANGUAGE.

Ziel:
1. Verbindliche Sprach-Policy aus zentraler Config bereitstellen.
2. Beobachtete Sprachcodes in infos-Tabellen erfassen.
3. Nachweisreport fuer Entscheidungsdokumentation erzeugen.

Usage:
  python backend/tools/phaseC_finalize_supported_languages.py
  python backend/tools/phaseC_finalize_supported_languages.py --output backend/reports/phaseC_finalize_supported_languages_v1.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Set

import asyncpg

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.connection_manager import ConnectionManager
from app.core.i18n_policy import (
    DEFAULT_LANGUAGE_FALLBACK,
    SUPPORTED_LANGUAGES,
    get_i18n_policy_summary,
    normalize_language,
)
from tools.phaseB_persist_template_modes import SYSTEM_MANDANT_UIDS


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


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _collect_dropdowndaten(conn: asyncpg.Connection) -> Dict[str, Any]:
    rows = await conn.fetch(
        '''
        SELECT uid::text AS uid, daten
        FROM "sys_dropdowndaten"
        WHERE COALESCE(historisch, 0) = 0
        ORDER BY created_at
        '''
    )

    root_defaults_raw: Set[str] = set()
    root_defaults_norm: Set[str] = set()
    options_values_raw: Set[str] = set()
    options_values_norm: Set[str] = set()

    for row in rows:
        uid = str(row.get("uid") or "")
        if uid in SYSTEM_MANDANT_UIDS:
            continue
        daten = _as_dict(row.get("daten"))
        root = _as_dict(daten.get("ROOT"))
        dlang = str(root.get("DEFAULT_LANGUAGE") or "").strip()
        if dlang:
            root_defaults_raw.add(dlang)
            root_defaults_norm.add(normalize_language(dlang))

        options = _as_dict(daten.get("OPTIONS"))
        for opt in options.values():
            values = _dropdown_option_lang_values(_as_dict(opt))
            for k in values.keys():
                raw = str(k or "").strip()
                if not raw:
                    continue
                options_values_raw.add(raw)
                options_values_norm.add(normalize_language(raw))

    return {
        "root_defaults_raw": sorted(root_defaults_raw),
        "root_defaults_normalized": sorted(root_defaults_norm),
        "options_values_raw": sorted(options_values_raw),
        "options_values_normalized": sorted(options_values_norm),
    }


async def _collect_beschreibungen(conn: asyncpg.Connection) -> Dict[str, Any]:
    rows = await conn.fetch(
        '''
        SELECT uid::text AS uid, daten
        FROM "sys_beschreibungen"
        WHERE COALESCE(historisch, 0) = 0
        ORDER BY created_at
        '''
    )

    langs_raw: Set[str] = set()
    langs_norm: Set[str] = set()

    for row in rows:
        uid = str(row.get("uid") or "")
        if uid in SYSTEM_MANDANT_UIDS:
            continue
        daten = _as_dict(row.get("daten"))
        texts = _as_dict(daten.get("TEXTS"))
        for text_item in texts.values():
            item = _as_dict(text_item)
            values = _as_dict(item.get("values"))
            for k in values.keys():
                raw = str(k or "").strip()
                if not raw:
                    continue
                langs_raw.add(raw)
                langs_norm.add(normalize_language(raw))

    return {
        "texts_values_raw": sorted(langs_raw),
        "texts_values_normalized": sorted(langs_norm),
    }


async def build_report() -> Dict[str, Any]:
    cfg = await ConnectionManager.get_system_config("pdvm_system")
    conn = await asyncpg.connect(**cfg.to_dict())
    try:
        dd = await _collect_dropdowndaten(conn)
        bb = await _collect_beschreibungen(conn)
    finally:
        await conn.close()

    observed_norm = sorted(
        set(dd.get("root_defaults_normalized", []))
        | set(dd.get("options_values_normalized", []))
        | set(bb.get("texts_values_normalized", []))
    )
    supported = [str(x).upper() for x in SUPPORTED_LANGUAGES]
    unsupported_observed = [x for x in observed_norm if x not in supported]

    return {
        "phase": "phaseC_finalize_supported_languages",
        "generated_at_utc": _utc_now(),
        "database": cfg.database,
        "policy": get_i18n_policy_summary(),
        "observed": {
            "sys_dropdowndaten": dd,
            "sys_beschreibungen": bb,
            "normalized_union": observed_norm,
            "unsupported_observed": unsupported_observed,
        },
        "summary": {
            "default_language": DEFAULT_LANGUAGE_FALLBACK,
            "supported_languages": supported,
            "observed_language_count": len(observed_norm),
            "unsupported_observed_count": len(unsupported_observed),
        },
    }


def _default_output_path() -> Path:
    return BACKEND_DIR / "reports" / "phaseC_finalize_supported_languages_v1.json"


def _print_summary(report: Dict[str, Any]) -> None:
    s = report.get("summary", {})
    print("\n=== Phase C Punkt 6: Supported Languages Finalization ===")
    print(f"Default language: {s.get('default_language')}")
    print(f"Supported languages: {s.get('supported_languages')}")
    print(f"Observed language count: {s.get('observed_language_count')}")
    print(f"Unsupported observed count: {s.get('unsupported_observed_count')}")


async def _run(output_path: Path) -> int:
    report = await build_report()
    _print_summary(report)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nReport geschrieben: {output_path}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase C Punkt 6: finalize supported languages")
    parser.add_argument("--output", default=str(_default_output_path()), help="Pfad fuer JSON-Report")
    args = parser.parse_args()
    return asyncio.run(_run(Path(args.output)))


if __name__ == "__main__":
    raise SystemExit(main())

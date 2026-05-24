"""
Phase C Punkt 9: Freigabemodell je Sprache definieren und nachweisen.

Usage:
  python backend/tools/phaseC_define_language_release_model.py
  python backend/tools/phaseC_define_language_release_model.py --output backend/reports/phaseC_define_language_release_model_v1.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
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

EXPECTED_STATUSES = {"new", "machine", "review", "approved"}


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


def _as_list(value: Any) -> List[Any]:
    if isinstance(value, list):
        return value
    return []


def _load_config(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _has_release_fields(item: Dict[str, Any]) -> bool:
    return all(k in item for k in ("version", "status", "approved_by", "approved_at"))


def _is_non_empty(value: Any) -> bool:
    return bool(str(value or "").strip())


def _validate_iso8601(value: str) -> bool:
    raw = str(value or "").strip()
    if not raw:
        return False
    try:
        datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return True
    except Exception:
        return False


def _validate_item_release_state(item: Dict[str, Any], version_pattern: re.Pattern[str]) -> Tuple[bool, List[str]]:
    errors: List[str] = []

    version = str(item.get("version") or "").strip()
    status = str(item.get("status") or "").strip().lower()
    approved_by = item.get("approved_by")
    approved_at = item.get("approved_at")

    if not version_pattern.match(version):
        errors.append("invalid_version")
    if status not in EXPECTED_STATUSES:
        errors.append("invalid_status")

    if status == "approved":
        if not _is_non_empty(approved_by):
            errors.append("approved_by_missing")
        if not _validate_iso8601(str(approved_at or "")):
            errors.append("approved_at_invalid")

    return (len(errors) == 0, errors)


async def _scan_dropdowndaten(conn: asyncpg.Connection, version_pattern: re.Pattern[str]) -> Dict[str, Any]:
    rows = await conn.fetch(
        '''
        SELECT uid::text AS uid, daten
        FROM "sys_dropdowndaten"
        WHERE COALESCE(historisch, 0) = 0
        ORDER BY created_at
        '''
    )

    items_total = 0
    with_release_fields = 0
    valid_release_state = 0
    invalid_release_state = 0
    invalid_samples: List[Dict[str, Any]] = []

    for row in rows:
        uid = str(row.get("uid") or "")
        if uid in SYSTEM_MANDANT_UIDS:
            continue

        daten = _as_dict(row.get("daten"))
        options = _as_dict(daten.get("OPTIONS"))
        for option_key, option_item in options.items():
            item = _as_dict(option_item)
            items_total += 1

            if not _has_release_fields(item):
                continue
            with_release_fields += 1

            ok, errors = _validate_item_release_state(item, version_pattern)
            if ok:
                valid_release_state += 1
            else:
                invalid_release_state += 1
                if len(invalid_samples) < 20:
                    invalid_samples.append(
                        {
                            "uid": uid,
                            "option_key": str(option_key),
                            "errors": errors,
                        }
                    )

    return {
        "content_type": "dropdown",
        "items_total": items_total,
        "items_with_release_fields": with_release_fields,
        "items_without_release_fields": items_total - with_release_fields,
        "valid_release_state": valid_release_state,
        "invalid_release_state": invalid_release_state,
        "invalid_samples": invalid_samples,
    }


async def _scan_beschreibungen(conn: asyncpg.Connection, version_pattern: re.Pattern[str]) -> Dict[str, Any]:
    rows = await conn.fetch(
        '''
        SELECT uid::text AS uid, daten
        FROM "sys_beschreibungen"
        WHERE COALESCE(historisch, 0) = 0
        ORDER BY created_at
        '''
    )

    items_total = 0
    with_release_fields = 0
    valid_release_state = 0
    invalid_release_state = 0
    invalid_samples: List[Dict[str, Any]] = []

    for row in rows:
        uid = str(row.get("uid") or "")
        if uid in SYSTEM_MANDANT_UIDS:
            continue

        daten = _as_dict(row.get("daten"))
        texts = _as_dict(daten.get("TEXTS"))
        for text_key, text_item in texts.items():
            item = _as_dict(text_item)
            items_total += 1

            if not _has_release_fields(item):
                continue
            with_release_fields += 1

            ok, errors = _validate_item_release_state(item, version_pattern)
            if ok:
                valid_release_state += 1
            else:
                invalid_release_state += 1
                if len(invalid_samples) < 20:
                    invalid_samples.append(
                        {
                            "uid": uid,
                            "text_key": str(text_key),
                            "errors": errors,
                        }
                    )

    return {
        "content_type": "text",
        "items_total": items_total,
        "items_with_release_fields": with_release_fields,
        "items_without_release_fields": items_total - with_release_fields,
        "valid_release_state": valid_release_state,
        "invalid_release_state": invalid_release_state,
        "invalid_samples": invalid_samples,
    }


def _validate_config_model(config: Dict[str, Any]) -> Dict[str, Any]:
    required_fields = {str(x) for x in _as_list(config.get("required_release_fields"))}
    status_model = _as_dict(config.get("status_model"))
    status_keys = {str(k).lower() for k in status_model.keys()}

    missing_required_fields = sorted({"version", "status", "approved_by", "approved_at"} - required_fields)
    missing_status_keys = sorted(EXPECTED_STATUSES - status_keys)

    version_rules = _as_dict(config.get("version_field_rules"))
    pattern_str = str(version_rules.get("pattern") or "")
    pattern_valid = True
    try:
        re.compile(pattern_str)
    except Exception:
        pattern_valid = False

    return {
        "required_fields_present": len(missing_required_fields) == 0,
        "missing_required_fields": missing_required_fields,
        "status_keys_complete": len(missing_status_keys) == 0,
        "missing_status_keys": missing_status_keys,
        "version_pattern_valid": pattern_valid,
        "model_definition_complete": (
            len(missing_required_fields) == 0
            and len(missing_status_keys) == 0
            and pattern_valid
        ),
    }


async def build_report(config_path: Path) -> Dict[str, Any]:
    config = _load_config(config_path)
    model_validation = _validate_config_model(config)

    pattern = str(_as_dict(config.get("version_field_rules")).get("pattern") or "")
    version_pattern = re.compile(pattern)

    cfg = await ConnectionManager.get_system_config("pdvm_system")
    conn = await asyncpg.connect(**cfg.to_dict())
    try:
        dropdown = await _scan_dropdowndaten(conn, version_pattern)
        texts = await _scan_beschreibungen(conn, version_pattern)
    finally:
        await conn.close()

    items_total = int(dropdown.get("items_total") or 0) + int(texts.get("items_total") or 0)
    with_fields = int(dropdown.get("items_with_release_fields") or 0) + int(texts.get("items_with_release_fields") or 0)
    valid_state = int(dropdown.get("valid_release_state") or 0) + int(texts.get("valid_release_state") or 0)

    return {
        "phase": "phaseC_define_language_release_model",
        "generated_at_utc": _utc_now(),
        "database": cfg.database,
        "config_path": str(config_path),
        "config": config,
        "model_validation": model_validation,
        "coverage": {
            "sys_dropdowndaten": dropdown,
            "sys_beschreibungen": texts,
        },
        "summary": {
            "items_total": items_total,
            "items_with_release_fields": with_fields,
            "items_without_release_fields": items_total - with_fields,
            "valid_release_state_count": valid_state,
            "model_definition_complete": bool(model_validation.get("model_definition_complete")),
            "runtime_release_metadata_coverage": (with_fields == items_total if items_total > 0 else True),
        },
    }


def _default_config_path() -> Path:
    return BACKEND_DIR / "config" / "i18n_language_release_model_v1.json"


def _default_output_path() -> Path:
    return BACKEND_DIR / "reports" / "phaseC_define_language_release_model_v1.json"


def _print_summary(report: Dict[str, Any]) -> None:
    s = _as_dict(report.get("summary"))
    print("\n=== Phase C Punkt 9: Language Release Model ===")
    print(f"Items total: {s.get('items_total')}")
    print(f"Items with release fields: {s.get('items_with_release_fields')}")
    print(f"Items without release fields: {s.get('items_without_release_fields')}")
    print(f"Valid release state count: {s.get('valid_release_state_count')}")
    print(f"Model definition complete: {s.get('model_definition_complete')}")
    print(f"Runtime release metadata coverage: {s.get('runtime_release_metadata_coverage')}")


async def _run(config_path: Path, output_path: Path) -> int:
    report = await build_report(config_path)
    _print_summary(report)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nReport geschrieben: {output_path}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase C Punkt 9: define language release model")
    parser.add_argument("--config", default=str(_default_config_path()), help="Pfad zur Release-Model-Config")
    parser.add_argument("--output", default=str(_default_output_path()), help="Pfad fuer JSON-Report")
    args = parser.parse_args()
    return asyncio.run(_run(Path(args.config), Path(args.output)))


if __name__ == "__main__":
    raise SystemExit(main())

"""
Konsolidiert Plan/Apply/Validate/Pilot-Reports in einen Abschlussreport.

Usage:
  python backend/tools/mandant_update_report_v1.py
  python backend/tools/mandant_update_report_v1.py --output backend/reports/mandant_update_report_v1.json
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

BACKEND_DIR = Path(__file__).resolve().parents[1]
DEFAULT_REPORTS = {
    "plan_before": BACKEND_DIR / "reports" / "mandant_update_pilot_standard_plan_before_v1.json",
    "apply": BACKEND_DIR / "reports" / "mandant_update_pilot_standard_apply_v1.json",
    "validate": BACKEND_DIR / "reports" / "mandant_update_pilot_standard_validate_v1.json",
    "plan_after": BACKEND_DIR / "reports" / "mandant_update_pilot_standard_plan_after_v1.json",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _as_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _load_json(path: Path) -> Tuple[Dict[str, Any], str]:
    if not path.exists():
        return {}, "file_missing"
    try:
        return _as_dict(json.loads(path.read_text(encoding="utf-8"))), "ok"
    except Exception as exc:
        return {}, f"json_read_error: {exc}"


def _check_plan(data: Dict[str, Any], stage: str) -> Dict[str, Any]:
    summary = _as_dict(data.get("summary"))
    status = str(summary.get("plan_status") or "")
    delta = int(summary.get("delta_count") or 0)

    if stage == "before":
        ok = status in {"ready", "no_change"}
        expected = "ready_or_no_change"
    else:
        ok = status == "no_change" and delta == 0
        expected = "no_change_and_zero_delta"

    return {
        "ok": bool(ok),
        "expected": expected,
        "actual": {"plan_status": status, "delta_count": delta},
    }


def _check_apply(data: Dict[str, Any]) -> Dict[str, Any]:
    summary = _as_dict(data.get("summary"))
    status = str(summary.get("apply_status") or "")
    errors = int(summary.get("errors") or 0)
    ok = status in {"applied", "no_change"} and errors == 0
    return {
        "ok": bool(ok),
        "expected": "apply_status_in_applied_or_no_change_and_errors_0",
        "actual": {
            "apply_status": status,
            "delta_count": int(summary.get("delta_count") or 0),
            "applied_writes": int(summary.get("applied_writes") or 0),
            "errors": errors,
        },
    }


def _check_validate(data: Dict[str, Any]) -> Dict[str, Any]:
    summary = _as_dict(data.get("summary"))
    status = str(summary.get("validation_status") or "")
    failed = int(summary.get("checks_failed") or 0)
    errors = int(summary.get("errors") or 0)
    ok = status == "passed" and failed == 0 and errors == 0
    return {
        "ok": bool(ok),
        "expected": "validation_status_passed_and_no_failed_checks",
        "actual": {
            "validation_status": status,
            "checks_total": int(summary.get("checks_total") or 0),
            "checks_passed": int(summary.get("checks_passed") or 0),
            "checks_failed": failed,
            "errors": errors,
        },
    }


def build_report(paths: Dict[str, Path]) -> Dict[str, Any]:
    loaded: Dict[str, Dict[str, Any]] = {}
    file_status: Dict[str, str] = {}

    for key, path in paths.items():
        data, status = _load_json(path)
        loaded[key] = data
        file_status[key] = status

    main_mandant = _as_dict(loaded.get("plan_before", {}).get("main_mandant"))
    if not main_mandant:
        main_mandant = _as_dict(loaded.get("apply", {}).get("main_mandant"))

    checks: List[Dict[str, Any]] = []

    for key, status in file_status.items():
        checks.append(
            {
                "name": f"file_available::{key}",
                "ok": status == "ok",
                "details": {"status": status, "path": str(paths[key])},
            }
        )

    if file_status.get("plan_before") == "ok":
        checks.append({"name": "plan_before", **_check_plan(loaded["plan_before"], "before")})
    if file_status.get("apply") == "ok":
        checks.append({"name": "apply", **_check_apply(loaded["apply"])})
    if file_status.get("validate") == "ok":
        checks.append({"name": "validate", **_check_validate(loaded["validate"])})
    if file_status.get("plan_after") == "ok":
        checks.append({"name": "plan_after", **_check_plan(loaded["plan_after"], "after")})

    checks_total = len(checks)
    checks_passed = sum(1 for c in checks if bool(c.get("ok")))
    checks_failed = checks_total - checks_passed

    return {
        "phase": "mandant_update_report_v1",
        "generated_at_utc": _utc_now(),
        "target_mandant": {
            "uid": str(main_mandant.get("uid") or ""),
            "name": str(main_mandant.get("name") or ""),
        },
        "inputs": {k: str(v) for k, v in paths.items()},
        "checks": checks,
        "summary": {
            "checks_total": checks_total,
            "checks_passed": checks_passed,
            "checks_failed": checks_failed,
            "overall_status": "passed" if checks_failed == 0 else "failed",
            "idempotence_confirmed": bool(
                file_status.get("plan_after") == "ok"
                and _check_plan(loaded.get("plan_after", {}), "after").get("ok")
            ),
        },
    }


def _default_output_path() -> Path:
    return BACKEND_DIR / "reports" / "mandant_update_report_v1.json"


def main() -> int:
    parser = argparse.ArgumentParser(description="Build consolidated mandant update report")
    parser.add_argument("--plan-before", default=str(DEFAULT_REPORTS["plan_before"]), help="Report path plan before")
    parser.add_argument("--apply", default=str(DEFAULT_REPORTS["apply"]), help="Report path apply")
    parser.add_argument("--validate", default=str(DEFAULT_REPORTS["validate"]), help="Report path validate")
    parser.add_argument("--plan-after", default=str(DEFAULT_REPORTS["plan_after"]), help="Report path plan after")
    parser.add_argument("--output", default=str(_default_output_path()), help="Output path")
    args = parser.parse_args()

    paths = {
        "plan_before": Path(args.plan_before),
        "apply": Path(args.apply),
        "validate": Path(args.validate),
        "plan_after": Path(args.plan_after),
    }
    report = build_report(paths)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    s = _as_dict(report.get("summary"))
    print("\n=== Mandant Update Report V1 ===")
    print(f"Overall status: {s.get('overall_status')}")
    print(f"Checks passed/total: {s.get('checks_passed')} / {s.get('checks_total')}")
    print(f"Idempotence confirmed: {s.get('idempotence_confirmed')}")
    print(f"Report geschrieben: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""
Validates dialog edit_type usage against policy contracts.

Usage:
  python backend/tools/validate_edit_type_contracts_v1.py
  python backend/tools/validate_edit_type_contracts_v1.py --output backend/reports/edit_type_contract_validation_report_v1.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
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

POLICY_PATH = BACKEND_DIR / "config" / "dialog_view_frame_analyzer_policy_v1.json"


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


def _load_contracts() -> Dict[str, Dict[str, Any]]:
    try:
        payload = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    except Exception:
        payload = {}
    contracts = _as_dict(_as_dict(payload).get("edit_type_contracts"))
    out: Dict[str, Dict[str, Any]] = {}
    for k, v in contracts.items():
        key = str(k or "").strip().lower()
        if not key:
            continue
        c = _as_dict(v)
        if not isinstance(c.get("allowed_operations"), list):
            c["allowed_operations"] = ["read", "write"]
        out[key] = c
    return out


async def _table_exists(conn: asyncpg.Connection, table_name: str) -> bool:
    return bool(await conn.fetchval("SELECT to_regclass($1) IS NOT NULL", f"public.{table_name}"))


async def _resolve_table(conn: asyncpg.Connection, candidates: List[str]) -> Optional[str]:
    for t in candidates:
        if await _table_exists(conn, t):
            return t
    return None


def _collect_tabs(root: Dict[str, Any]) -> List[Dict[str, Any]]:
    tabs: List[Dict[str, Any]] = []
    tab_elements = _as_dict(root.get("TAB_ELEMENTS"))
    for key, val in tab_elements.items():
        if not str(key).upper().startswith("TAB"):
            continue
        row = _as_dict(val)
        if not row:
            continue
        tabs.append(
            {
                "key": str(key),
                "module": str(row.get("MODULE") or "").strip().lower(),
                "edit_type": str(row.get("EDIT_TYPE") or "").strip().lower(),
            }
        )
    return tabs


def _add_violation(report: Dict[str, Any], severity: str, code: str, details: Dict[str, Any]) -> None:
    report.setdefault("violations", []).append({"severity": severity, "code": code, "details": details})


async def build_report() -> Dict[str, Any]:
    contracts = _load_contracts()
    cfg = await ConnectionManager.get_system_config("pdvm_system")
    conn = await asyncpg.connect(**cfg.to_dict())

    report: Dict[str, Any] = {
        "phase": "validate_edit_type_contracts_v1",
        "generated_at_utc": _utc_now(),
        "database": cfg.database,
        "policy_path": str(POLICY_PATH),
        "inventory": {
            "dialogs_scanned": 0,
            "edit_types_observed": {},
            "contracts_known": sorted(contracts.keys()),
        },
        "violations": [],
        "summary": {},
    }

    try:
        dialog_table = await _resolve_table(conn, ["sys_dialogdaten", "asy_dialogdaten", "msy_dialogdaten"])
        report["dialog_table"] = dialog_table
        if not dialog_table:
            _add_violation(report, "error", "dialog_table_missing", {})
            return report

        rows = await conn.fetch(
            f'''
            SELECT uid::text AS uid, name, daten
            FROM "{dialog_table}"
            WHERE COALESCE(historisch,0)=0
            ORDER BY created_at
            '''
        )

        for r in rows:
            uid = str(r["uid"] or "")
            if uid in SYSTEM_MANDANT_UIDS:
                continue
            report["inventory"]["dialogs_scanned"] += 1
            name = str(r["name"] or "")
            data = _as_dict(r.get("daten"))
            root = _as_dict(data.get("ROOT"))

            root_edit_type = str(root.get("EDIT_TYPE") or "").strip().lower()
            if root_edit_type:
                report["inventory"]["edit_types_observed"][root_edit_type] = report["inventory"]["edit_types_observed"].get(root_edit_type, 0) + 1
                contract = _as_dict(contracts.get(root_edit_type))
                if not contract:
                    _add_violation(report, "error", "root_edit_type_without_contract", {"dialog_uid": uid, "dialog_name": name, "edit_type": root_edit_type})

            for tab in _collect_tabs(root):
                et = str(tab.get("edit_type") or "").strip().lower()
                module = str(tab.get("module") or "").strip().lower()
                if not et:
                    continue

                report["inventory"]["edit_types_observed"][et] = report["inventory"]["edit_types_observed"].get(et, 0) + 1
                contract = _as_dict(contracts.get(et))
                if not contract:
                    _add_violation(
                        report,
                        "error",
                        "tab_edit_type_without_contract",
                        {"dialog_uid": uid, "dialog_name": name, "tab_key": tab.get("key"), "module": module, "edit_type": et},
                    )
                    continue

                allowed_ops = [str(x).strip().lower() for x in _as_list(contract.get("allowed_operations"))]
                preferred_modules = [str(x).strip().lower() for x in _as_list(contract.get("preferred_modules")) if str(x).strip()]

                if preferred_modules and module and module not in preferred_modules:
                    _add_violation(
                        report,
                        "error",
                        "tab_module_not_in_contract_preferred_modules",
                        {
                            "dialog_uid": uid,
                            "dialog_name": name,
                            "tab_key": tab.get("key"),
                            "module": module,
                            "edit_type": et,
                            "preferred_modules": preferred_modules,
                        },
                    )

                if module in {"edit", "acti"} and "write" not in allowed_ops:
                    _add_violation(
                        report,
                        "error",
                        "tab_write_module_with_readonly_contract",
                        {
                            "dialog_uid": uid,
                            "dialog_name": name,
                            "tab_key": tab.get("key"),
                            "module": module,
                            "edit_type": et,
                            "allowed_operations": allowed_ops,
                        },
                    )

                if module in {"view", "show"} and "read" not in allowed_ops:
                    _add_violation(
                        report,
                        "warning",
                        "read_module_without_read_contract",
                        {
                            "dialog_uid": uid,
                            "dialog_name": name,
                            "tab_key": tab.get("key"),
                            "module": module,
                            "edit_type": et,
                            "allowed_operations": allowed_ops,
                        },
                    )

                if module == "show" and "write" in allowed_ops:
                    _add_violation(
                        report,
                        "warning",
                        "show_module_with_write_contract",
                        {
                            "dialog_uid": uid,
                            "dialog_name": name,
                            "tab_key": tab.get("key"),
                            "edit_type": et,
                            "allowed_operations": allowed_ops,
                        },
                    )

    finally:
        await conn.close()

    violations = report.get("violations", [])
    v_err = sum(1 for v in violations if v.get("severity") == "error")
    v_warn = sum(1 for v in violations if v.get("severity") == "warning")
    report["summary"] = {
        "violations_error": v_err,
        "violations_warning": v_warn,
        "overall_status": "passed" if v_err == 0 else "failed",
    }

    return report


def _default_output_path() -> Path:
    return BACKEND_DIR / "reports" / "edit_type_contract_validation_report_v1.json"


async def _run(output: Path) -> int:
    report = await build_report()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    s = _as_dict(report.get("summary"))
    print("\n=== validate_edit_type_contracts_v1 ===")
    print(f"Overall status: {s.get('overall_status')}")
    print(f"Violations (error/warning): {s.get('violations_error')} / {s.get('violations_warning')}")
    print(f"Report: {output}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate edit type contracts against dialog configuration")
    parser.add_argument("--output", default=str(_default_output_path()), help="Output report path")
    args = parser.parse_args()
    return asyncio.run(_run(Path(args.output)))


if __name__ == "__main__":
    raise SystemExit(main())

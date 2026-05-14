"""Health-Check fuer Release-Workflow-Templates (Phase A).

Prueft:
- Existenz der benoetigten Template-Saetze
- Mindeststruktur je Kategorie (dialog/view/frame/control)

Usage:
  python backend/tools/release_workflow_template_health_check.py
  python backend/tools/release_workflow_template_health_check.py --json
  python backend/tools/release_workflow_template_health_check.py --db-url postgresql://...
"""
from __future__ import annotations

import argparse
import asyncio
import json
import uuid
from pathlib import Path
from typing import Any, Dict, List

import sys

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import asyncpg

from app.core.connection_manager import ConnectionManager
from tools.release_workflow_template_registry import (
    TemplateSpec,
    get_release_workflow_template_specs,
)


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _validate_spec_data(spec: TemplateSpec, data: Dict[str, Any]) -> List[str]:
    issues: List[str] = []
    root = _as_dict(data.get("ROOT"))
    if not root:
        issues.append("ROOT fehlt")
        return issues

    if not str(root.get("SELF_GUID") or "").strip():
        issues.append("ROOT.SELF_GUID fehlt")
    if not str(root.get("SELF_NAME") or "").strip():
        issues.append("ROOT.SELF_NAME fehlt")

    if spec.category == "dialog":
        if str(root.get("DIALOG_TYPE") or "").strip().lower() != "work":
            issues.append("ROOT.DIALOG_TYPE ist nicht work")
        tab_elements = _as_dict(root.get("TAB_ELEMENTS"))
        if not tab_elements:
            issues.append("ROOT.TAB_ELEMENTS fehlt/leer")
        else:
            has_view_module = False
            has_acti_module = False
            for tab_key, tab_value in tab_elements.items():
                tab_obj = _as_dict(tab_value)
                module = str(tab_obj.get("MODULE") or "").strip().lower()
                guid_value = str(tab_obj.get("GUID") or "").strip()

                if module not in {"view", "edit", "acti"}:
                    issues.append(f"{tab_key}.MODULE ungueltig: {module}")

                if not guid_value:
                    issues.append(f"{tab_key}.GUID fehlt")
                else:
                    try:
                        uuid.UUID(guid_value)
                    except Exception:
                        issues.append(f"{tab_key}.GUID ist keine gueltige UUID")

                if module == "view":
                    has_view_module = True
                if module == "acti":
                    has_acti_module = True

            if not has_view_module:
                issues.append("TAB_ELEMENTS enthaelt kein MODULE=view")
            if not has_acti_module:
                issues.append("TAB_ELEMENTS enthaelt kein MODULE=acti")

    if spec.category == "view":
        if not str(root.get("TABLE") or "").strip():
            issues.append("ROOT.TABLE fehlt")

    if spec.category == "frame":
        tab_elements = _as_dict(root.get("TAB_ELEMENTS"))
        if not tab_elements:
            issues.append("ROOT.TAB_ELEMENTS fehlt/leer")
        fields = _as_dict(data.get("FIELDS"))
        if data.get("FIELDS") is None:
            issues.append("FIELDS fehlt")
        elif not isinstance(fields, dict):
            issues.append("FIELDS ist kein Objekt")
        elif spec.name.startswith("WORKFLOW_") and len(fields) == 0:
            issues.append("FIELDS ist leer")

        if isinstance(fields, dict):
            feld_values = {
                str(_as_dict(item).get("feld") or "").strip().upper()
                for item in fields.values()
                if isinstance(item, dict)
            }
            if spec.name.startswith("WORKFLOW_"):
                wrong_groups = [
                    str(_as_dict(item).get("gruppe") or "").strip().upper()
                    for item in fields.values()
                    if isinstance(item, dict)
                    and str(_as_dict(item).get("gruppe") or "").strip().upper() not in {"FIELDS"}
                ]
                if wrong_groups:
                    issues.append("FIELDS.*.gruppe muss FIELDS sein")
            if spec.name == "WORKFLOW_SETUP_FRAME_TEMPLATE" and "RELEASE_TYPE" not in feld_values:
                issues.append("FIELDS enthaelt kein RELEASE_TYPE")
            if spec.name == "WORKFLOW_PROPERTY_MAPPING_FRAME_TEMPLATE":
                if "DICTIONARY_SEARCH" not in feld_values:
                    issues.append("FIELDS enthaelt kein DICTIONARY_SEARCH")
                if "CREATE_PROPERTY_ACTION" not in feld_values:
                    issues.append("FIELDS enthaelt kein CREATE_PROPERTY_ACTION")
            if spec.name == "WORKFLOW_APPLY_FRAME_TEMPLATE":
                if "DRY_RUN_ACTION" not in feld_values:
                    issues.append("FIELDS enthaelt kein DRY_RUN_ACTION")
                if "APPLY_ACTION" not in feld_values:
                    issues.append("FIELDS enthaelt kein APPLY_ACTION")

    if spec.category == "control":
        control = _as_dict(data.get("CONTROL"))
        if not control:
            issues.append("CONTROL fehlt")
        else:
            field = str(control.get("FIELD") or "").strip()
            feld = str(control.get("FELD") or "").strip()
            if not field:
                issues.append("CONTROL.FIELD fehlt")
            if not feld:
                issues.append("CONTROL.FELD fehlt")
            if field and field != field.upper():
                issues.append("CONTROL.FIELD nicht GROSS")
            if feld and feld != feld.upper():
                issues.append("CONTROL.FELD nicht GROSS")

    return issues


async def _get_db_url(cli_db_url: str | None) -> str:
    if cli_db_url:
        return cli_db_url
    cfg = await ConnectionManager.get_system_config("pdvm_system")
    return cfg.to_url()


async def main_async(args: argparse.Namespace) -> int:
    db_url = await _get_db_url(args.db_url)
    specs = get_release_workflow_template_specs()

    conn = await asyncpg.connect(db_url)
    try:
        report: Dict[str, Any] = {
            "total_required": len(specs),
            "found": 0,
            "missing": [],
            "invalid": [],
        }

        for spec in specs:
            row = await conn.fetchrow(
                f"SELECT uid, name, daten FROM {spec.table_name} WHERE uid = $1",
                spec.uid,
            )
            if not row:
                report["missing"].append(
                    {
                        "category": spec.category,
                        "table": spec.table_name,
                        "name": spec.name,
                        "uid": str(spec.uid),
                    }
                )
                continue

            report["found"] += 1
            data = row.get("daten")
            if isinstance(data, str):
                try:
                    data = json.loads(data)
                except Exception:
                    data = None
            data = data if isinstance(data, dict) else {}

            issues = _validate_spec_data(spec, data)
            if issues:
                report["invalid"].append(
                    {
                        "category": spec.category,
                        "table": spec.table_name,
                        "name": spec.name,
                        "uid": str(spec.uid),
                        "issues": issues,
                    }
                )

        report["ok"] = not report["missing"] and not report["invalid"]

        if args.json:
            print(json.dumps(report, indent=2, ensure_ascii=False))
        else:
            print("=== Release Workflow Template Health Check ===")
            print(f"Required: {report['total_required']}")
            print(f"Found:    {report['found']}")
            print(f"Missing:  {len(report['missing'])}")
            print(f"Invalid:  {len(report['invalid'])}")
            if report["missing"]:
                print("\nMissing templates:")
                for item in report["missing"]:
                    print(f"- {item['table']} :: {item['name']} ({item['uid']})")
            if report["invalid"]:
                print("\nInvalid templates:")
                for item in report["invalid"]:
                    print(f"- {item['table']} :: {item['name']} ({item['uid']})")
                    for issue in item["issues"]:
                        print(f"  - {issue}")

        return 0 if report["ok"] else 2
    finally:
        await conn.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Health check for release workflow templates")
    parser.add_argument("--db-url", default=None, help="Optional PostgreSQL URL")
    parser.add_argument("--json", action="store_true", help="Print JSON output")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main_async(parse_args())))

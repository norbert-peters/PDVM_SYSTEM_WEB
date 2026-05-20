"""
Erzeugt einen maschinenlesbaren Ausnahmekatalog fuer die 555/666 Strukturmigration.

Quelle:
- Laufzeitklassifizierung aus phaseB_persist_template_modes (dry-run, kein Write).

Ergebnis:
- JSON-Report mit allen Tabellen inkl. Zielmodus, Reason-Code, Review-Flag.

Usage:
  python backend/tools/phaseB_generate_exception_catalog.py
  python backend/tools/phaseB_generate_exception_catalog.py --output backend/reports/phaseB_exception_catalog_v1.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from tools.phaseB_persist_template_modes import build_report


def _default_output_path() -> Path:
    return BACKEND_DIR / "reports" / "phaseB_exception_catalog_v1.json"


def _reason_code(table_name: str, mode: str, table_type: str) -> str:
    t = str(table_name or "").lower()
    if mode == "ausgenommen":
        if t in {"dev_workflow_draft", "dev_workflow_draft_item"}:
            return "explicit_excluded_dev_workflow"
        if "historie" in t or "history" in t or "audit" in t or t.startswith("log_"):
            return "audit_or_history_table"
        return "explicit_excluded_or_non_template_pattern"

    if mode == "teiltemplatefaehig":
        if t in {"asy_benutzer", "sys_benutzer"}:
            return "user_auth_special_handling"
        return "partial_template_special_columns"

    if mode == "nicht_im_scope":
        return "missing_required_columns_uid_daten"

    if table_type in {"audit_history", "process"}:
        return "review_recommended_for_table_type"

    return "standard_template_mode"


def _review_required(mode: str, table_type: str) -> bool:
    if mode in {"ausgenommen", "teiltemplatefaehig", "nicht_im_scope"}:
        return True
    if table_type in {"audit_history", "process"}:
        return True
    return False


def _build_catalog(source_report: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "phase": "phaseB_exception_catalog",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_phase": source_report.get("phase"),
        "source_apply": source_report.get("apply"),
        "databases": [],
        "summary": {
            "db_count": 0,
            "table_count": 0,
            "mode_counts": {
                "voll_templatefaehig": 0,
                "teiltemplatefaehig": 0,
                "ausgenommen": 0,
                "nicht_im_scope": 0,
            },
            "review_required_count": 0,
            "open_decisions_count": 0,
        },
    }

    for db in source_report.get("databases", []):
        db_label = str(db.get("db_label") or "")
        database = str(db.get("database") or "")
        db_entry = {
            "db_label": db_label,
            "database": database,
            "tables": [],
            "summary": {
                "table_count": 0,
                "review_required_count": 0,
                "open_decisions_count": 0,
            },
        }

        for t in db.get("tables", []):
            mode = str(t.get("mode") or "")
            table_name = str(t.get("table") or "")
            table_type = str(t.get("table_type") or "")

            entry = {
                "table": table_name,
                "target_mode": mode,
                "table_type": table_type,
                "table_type_source": t.get("table_type_source"),
                "reason_code": _reason_code(table_name, mode, table_type),
                "review_required": _review_required(mode, table_type),
                "decision_locked": mode == "voll_templatefaehig",
                "source_record_uid": t.get("record_uid"),
                "source_record_name": t.get("record_name"),
            }

            db_entry["tables"].append(entry)
            db_entry["summary"]["table_count"] += 1
            out["summary"]["table_count"] += 1

            if mode in out["summary"]["mode_counts"]:
                out["summary"]["mode_counts"][mode] += 1

            if entry["review_required"]:
                db_entry["summary"]["review_required_count"] += 1
                out["summary"]["review_required_count"] += 1

            if mode in {"ausgenommen", "teiltemplatefaehig", "nicht_im_scope"}:
                db_entry["summary"]["open_decisions_count"] += 1
                out["summary"]["open_decisions_count"] += 1

        out["databases"].append(db_entry)

    out["summary"]["db_count"] = len(out["databases"])
    return out


async def _run(output_path: Path) -> int:
    source_report = await build_report(apply=False)
    catalog = _build_catalog(source_report)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(catalog, indent=2, ensure_ascii=False), encoding="utf-8")

    summary = catalog.get("summary", {})
    print("\n=== Phase B Exception Catalog ===")
    print(f"DB count: {summary.get('db_count', 0)}")
    print(f"Table count: {summary.get('table_count', 0)}")
    print(f"Open decisions: {summary.get('open_decisions_count', 0)}")
    print(f"Review required: {summary.get('review_required_count', 0)}")
    print(f"\nReport geschrieben: {output_path}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate machine-readable exception catalog")
    parser.add_argument("--output", default=str(_default_output_path()), help="Pfad für JSON-Report")
    args = parser.parse_args()
    return asyncio.run(_run(Path(args.output)))


if __name__ == "__main__":
    raise SystemExit(main())

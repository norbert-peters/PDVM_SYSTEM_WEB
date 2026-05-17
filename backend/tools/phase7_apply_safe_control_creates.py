"""
Phase 7: sichere Erstellung fehlender Basis-Controls

Liest create_actions aus
backend/reports/phase7_control_dict_migration_suggestions.json
und erstellt NUR eine konservative Whitelist von Basis-Controls.

Default: dry-run
Mit --apply werden Datensaetze in sys_control_dict angelegt.

Usage:
  python backend/tools/phase7_apply_safe_control_creates.py
  python backend/tools/phase7_apply_safe_control_creates.py --apply
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import uuid
from pathlib import Path
from typing import Any, Dict, List, Set

import asyncpg

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.connection_manager import ConnectionManager

SAFE_BASE_CONTROLS: Set[str] = {
    "NAME",
    "LABEL",
    "TABLE",
    "GRUPPE",
    "FELD",
    "TYPE",
    "UID",
    "SELF_GUID",
    "SELF_NAME",
    "EDIT_TYPE",
    "DIALOG_TYPE",
    "TABS",
    "TAB_ELEMENTS",
    "WORKFLOW_NAME",
}

IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")
BLOCKED_CANONICAL = {
    "ROOT",
    "CONTROL",
    "FIELDS",
    "CONFIGS",
    "TEMPLATES",
}


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _normalize_control_name(raw_name: str) -> str:
    name = _norm(raw_name)
    if not name:
        return ""

    # Aus Legacy-Ausreissern wie "{'FELD': 'SELF_NAME', ...}" den Feldnamen extrahieren.
    if name.startswith("{") and "FELD" in name:
        m = re.search(r"['\"]FELD['\"]\s*:\s*['\"]([^'\"]+)['\"]", name)
        if m:
            name = str(m.group(1) or "").strip()

    # Template-Pfade auf den letzten logischen Feldteil reduzieren.
    if "." in name:
        name = name.split(".")[-1]

    name = name.replace(" ", "_").replace("-", "_")

    low = name.lower()
    if low == "field":
        return "FELD"
    if low == "group":
        return "GRUPPE"

    return name.upper()


def _load_json(path: Path) -> Dict[str, Any]:
    raw = path.read_text(encoding="utf-8")
    data = json.loads(raw)
    return data if isinstance(data, dict) else {}


async def _load_existing_names(conn: asyncpg.Connection) -> Set[str]:
    rows = await conn.fetch(
        """
        SELECT name, daten
        FROM sys_control_dict
        WHERE historisch = 0
        """
    )
    names: Set[str] = set()
    for row in rows:
        name = _norm(row.get("name"))
        if name:
            names.add(name.upper())
        daten = row.get("daten")
        if isinstance(daten, str):
            try:
                daten = json.loads(daten)
            except Exception:
                daten = {}
        if isinstance(daten, dict):
            root = daten.get("ROOT") if isinstance(daten.get("ROOT"), dict) else {}
            self_name = _norm(root.get("SELF_NAME"))
            if self_name:
                names.add(self_name.upper())
    return names


def _build_control_payload(control_name: str) -> Dict[str, Any]:
    return {
        "ROOT": {
            "SELF_NAME": control_name,
            "NAME": control_name,
        },
        "CONTROL": {
            "FIELD": control_name,
            "FELD": control_name,
            "LABEL": control_name,
            "TYPE": "text",
            "TABLE": "",
            "GRUPPE": "",
        },
    }


def _is_identifier_safe(canonical: str) -> bool:
    if not canonical:
        return False
    if canonical in BLOCKED_CANONICAL:
        return False
    return bool(IDENT_RE.match(canonical))


async def _run(
    apply_changes: bool,
    allow_identifiers: bool,
    min_references: int,
    suggestions_path: Path,
    output_path: Path,
) -> Dict[str, Any]:
    suggestions = _load_json(suggestions_path)
    create_actions = (((suggestions.get("missing_name_resolution") or {}).get("create_actions")) or [])

    cfg = await ConnectionManager.get_system_config()
    conn = await asyncpg.connect(**cfg.to_dict())
    try:
        existing_names = await _load_existing_names(conn)

        selected: List[Dict[str, Any]] = []
        skipped: List[Dict[str, Any]] = []
        created: List[Dict[str, Any]] = []
        planned_names: Set[str] = set(existing_names)

        for action in create_actions:
            raw_name = _norm(action.get("control_name"))
            if not raw_name:
                continue

            canonical = _normalize_control_name(raw_name)
            if not canonical:
                skipped.append({"control_name": raw_name, "reason": "empty_after_normalization"})
                continue

            if canonical not in SAFE_BASE_CONTROLS:
                if not (allow_identifiers and _is_identifier_safe(canonical)):
                    skipped.append({"control_name": raw_name, "canonical": canonical, "reason": "not_in_safe_whitelist"})
                    continue

            refs = int(action.get("references") or 0)
            if refs < int(min_references):
                skipped.append(
                    {
                        "control_name": raw_name,
                        "canonical": canonical,
                        "reason": "below_min_references",
                        "references": refs,
                    }
                )
                continue

            if canonical in planned_names:
                skipped.append({"control_name": raw_name, "canonical": canonical, "reason": "already_exists"})
                continue

            selected.append(
                {
                    "control_name": raw_name,
                    "canonical": canonical,
                    "references": refs,
                }
            )
            planned_names.add(canonical)

        if apply_changes:
            for item in selected:
                control_name = item["canonical"]
                uid = uuid.uuid4()
                payload = _build_control_payload(control_name)
                await conn.execute(
                    """
                    INSERT INTO sys_control_dict (uid, daten, name, historisch)
                    VALUES ($1, $2, $3, 0)
                    """,
                    uid,
                    json.dumps(payload),
                    control_name,
                )
                existing_names.add(control_name)
                created.append(
                    {
                        "uid": str(uid),
                        "name": control_name,
                    }
                )

        result = {
            "phase": "phase7",
            "title": "Apply Safe Control Creates",
            "database": cfg.database,
            "mode": "apply" if apply_changes else "dry-run",
            "allow_identifiers": bool(allow_identifiers),
            "min_references": int(min_references),
            "summary": {
                "create_candidates_input": len(create_actions),
                "safe_selected": len(selected),
                "created": len(created),
                "skipped": len(skipped),
            },
            "selected": selected,
            "created": created,
            "skipped": skipped,
        }

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        return result
    finally:
        await conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 7 sichere Erstellung fehlender Basis-Controls")
    parser.add_argument(
        "--suggestions",
        default=str(BACKEND_DIR / "reports" / "phase7_control_dict_migration_suggestions.json"),
        help="Pfad zu Vorschlaegen JSON",
    )
    parser.add_argument(
        "--output",
        default=str(BACKEND_DIR / "reports" / "phase7_control_dict_safe_create_result.json"),
        help="Ausgabe JSON",
    )
    parser.add_argument(
        "--allow-identifiers",
        action="store_true",
        help="Erlaubt zusaetzlich saubere Identifier-Namen (A-Z, 0-9, _) ausserhalb der Basis-Whitelist",
    )
    parser.add_argument(
        "--min-references",
        type=int,
        default=1,
        help="Nur Kandidaten mit mindestens N Referenzen beruecksichtigen",
    )
    parser.add_argument("--apply", action="store_true", help="Schreibt Controls wirklich in DB")
    args = parser.parse_args()

    suggestions_path = Path(args.suggestions)
    if not suggestions_path.exists():
        print(f"ERROR: suggestions not found: {suggestions_path}")
        return 2

    result = asyncio.run(
        _run(
            apply_changes=args.apply,
            allow_identifiers=args.allow_identifiers,
            min_references=max(1, int(args.min_references or 1)),
            suggestions_path=suggestions_path,
            output_path=Path(args.output),
        )
    )
    summary = result.get("summary", {})

    print("PHASE7_SAFE_CREATE")
    print(f"mode={result.get('mode')}")
    print(f"allow_identifiers={result.get('allow_identifiers')}")
    print(f"min_references={result.get('min_references')}")
    print(f"output={args.output}")
    for key in ["create_candidates_input", "safe_selected", "created", "skipped"]:
        print(f"{key}={summary.get(key)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

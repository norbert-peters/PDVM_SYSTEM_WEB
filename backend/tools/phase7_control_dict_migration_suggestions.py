"""
Phase 7: Vorschlags-Generator fuer Control-Dict-Migration

Liest den Konsistenzreport und erzeugt priorisierte Vorschlaege:
- Duplicate-Aufloesung (keep_uid + retire_uids)
- Mapping fehlender Referenzen auf bestehende Controls (heuristisch)
- Kandidaten fuer neu anzulegende Basis-Controls

Usage:
  python backend/tools/phase7_control_dict_migration_suggestions.py
  python backend/tools/phase7_control_dict_migration_suggestions.py \
      --report backend/reports/phase7_control_dict_consistency_report.json \
      --output backend/reports/phase7_control_dict_migration_suggestions.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

import asyncpg

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.connection_manager import ConnectionManager

TEMPLATE_UIDS = {
    "55555555-5555-5555-5555-555555555555",
    "66666666-6666-6666-6666-666666666666",
}

IGNORE_NAMES_EXACT = {
    "",
    "none",
    "null",
    "true",
    "false",
}

IGNORE_NAME_PATTERNS = [
    re.compile(r"^[0-9]+$"),
    re.compile(r"^[a-f0-9\-]{36}$", re.IGNORECASE),
]


def _norm(value: Any) -> str:
    return str(value or "").strip().lower()


def _is_ignorable_name(name: str) -> bool:
    n = _norm(name)
    if n in IGNORE_NAMES_EXACT:
        return True
    return any(p.match(n) for p in IGNORE_NAME_PATTERNS)


def _candidate_variants(name: str) -> List[str]:
    raw = str(name or "").strip()
    if not raw:
        return []

    candidates = {
        raw,
        raw.lower(),
        raw.upper(),
        raw.replace(".", "_"),
        raw.replace(".", "_").lower(),
        raw.replace(".", "_").upper(),
    }

    lower = raw.lower()
    prefixes = [
        "templates.control.",
        "templates.configs_elements.",
        "templates.",
        "control.",
    ]
    for prefix in prefixes:
        if lower.startswith(prefix):
            tail = raw[len(prefix):]
            if tail:
                candidates.add(tail)
                candidates.add(tail.lower())
                candidates.add(tail.upper())
                candidates.add(tail.replace(".", "_"))
                candidates.add(tail.replace(".", "_").lower())
                candidates.add(tail.replace(".", "_").upper())

    if "." in raw:
        last = raw.split(".")[-1]
        candidates.add(last)
        candidates.add(last.lower())
        candidates.add(last.upper())

    if "_" in raw:
        last_u = raw.split("_")[-1]
        candidates.add(last_u)
        candidates.add(last_u.lower())
        candidates.add(last_u.upper())

    return [c for c in candidates if str(c).strip()]


async def _load_controls() -> Tuple[Dict[str, Dict[str, Any]], Dict[str, List[str]]]:
    cfg = await ConnectionManager.get_system_config()
    conn = await asyncpg.connect(**cfg.to_dict())
    try:
        rows = await conn.fetch(
            '''
            SELECT uid::text AS uid, name, daten, modified_at
            FROM sys_control_dict
            WHERE historisch = 0
            '''
        )

        by_uid: Dict[str, Dict[str, Any]] = {}
        by_name: Dict[str, List[str]] = defaultdict(list)

        for row in rows:
            uid = str(row.get("uid") or "").strip().lower()
            name = str(row.get("name") or "").strip()
            daten = row.get("daten")
            if isinstance(daten, str):
                try:
                    daten = json.loads(daten)
                except Exception:
                    daten = {}
            if not isinstance(daten, dict):
                daten = {}

            root = daten.get("ROOT") if isinstance(daten.get("ROOT"), dict) else {}
            control = daten.get("CONTROL") if isinstance(daten.get("CONTROL"), dict) else {}
            ref_name = (
                str(root.get("SELF_NAME") or "").strip()
                or str(control.get("FIELD") or control.get("FELD") or "").strip()
                or name
            )

            entry = {
                "uid": uid,
                "name": name,
                "ref_name": ref_name,
                "modified_at": str(row.get("modified_at") or ""),
            }
            by_uid[uid] = entry
            for n in {name, ref_name}:
                nn = _norm(n)
                if nn:
                    by_name[nn].append(uid)

        return by_uid, by_name
    finally:
        await conn.close()


def _choose_keep_uid(uids: List[str], controls_by_uid: Dict[str, Dict[str, Any]]) -> str:
    clean = [u for u in uids if u not in TEMPLATE_UIDS]
    if not clean:
        clean = list(uids)

    def rank(uid: str) -> Tuple[int, str, str]:
        c = controls_by_uid.get(uid, {})
        mod = str(c.get("modified_at") or "")
        name = str(c.get("name") or "")
        return (0 if uid not in TEMPLATE_UIDS else 1, mod, name)

    return sorted(clean, key=rank, reverse=True)[0]


def _build_duplicate_suggestions(
    duplicates: List[Dict[str, Any]],
    controls_by_uid: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for d in duplicates:
        uids = [str(u).strip().lower() for u in d.get("uids", []) if str(u).strip()]
        if len(uids) <= 1:
            continue
        keep_uid = _choose_keep_uid(uids, controls_by_uid)
        retire_uids = [u for u in uids if u != keep_uid]
        out.append(
            {
                "ref_name": d.get("ref_name"),
                "count": len(uids),
                "keep_uid": keep_uid,
                "retire_uids": retire_uids,
                "priority": "high" if len(uids) >= 3 else "medium",
            }
        )
    out.sort(key=lambda x: (-int(x.get("count", 0)), str(x.get("ref_name") or "")))
    return out


def _build_missing_name_suggestions(
    missing_refs: List[Dict[str, Any]],
    controls_by_name: Dict[str, List[str]],
) -> Dict[str, Any]:
    map_actions: List[Dict[str, Any]] = []
    create_counter: Counter[str] = Counter()
    ignored: List[Dict[str, Any]] = []

    for ref in missing_refs:
        raw_name = str(ref.get("control_name") or "").strip()
        if _is_ignorable_name(raw_name):
            ignored.append(ref)
            continue

        variants = _candidate_variants(raw_name)
        matches: Set[str] = set()
        matched_variant = None
        for variant in variants:
            key = _norm(variant)
            if key in controls_by_name:
                matches.update(controls_by_name[key])
                matched_variant = variant
                if len(matches) == 1:
                    break

        if len(matches) == 1:
            map_actions.append(
                {
                    "source_table": ref.get("source_table"),
                    "row_uid": ref.get("row_uid"),
                    "row_name": ref.get("row_name"),
                    "path": ref.get("path"),
                    "from_name": raw_name,
                    "to_uid": next(iter(matches)),
                    "matched_variant": matched_variant,
                    "confidence": "high",
                }
            )
        elif len(matches) > 1:
            map_actions.append(
                {
                    "source_table": ref.get("source_table"),
                    "row_uid": ref.get("row_uid"),
                    "row_name": ref.get("row_name"),
                    "path": ref.get("path"),
                    "from_name": raw_name,
                    "candidate_uids": sorted(matches),
                    "matched_variant": matched_variant,
                    "confidence": "medium",
                    "needs_review": True,
                }
            )
        else:
            create_counter[raw_name] += 1

    create_actions = [
        {
            "control_name": name,
            "references": cnt,
            "priority": "high" if cnt >= 3 else "medium",
        }
        for name, cnt in create_counter.items()
    ]
    create_actions.sort(key=lambda x: (-int(x.get("references", 0)), str(x.get("control_name") or "")))

    return {
        "map_actions": map_actions,
        "create_actions": create_actions,
        "ignored_references": ignored,
    }


def build_suggestions(
    report: Dict[str, Any],
    controls_by_uid: Dict[str, Dict[str, Any]],
    controls_by_name: Dict[str, List[str]],
) -> Dict[str, Any]:
    duplicates = report.get("duplicates_by_ref_name") if isinstance(report.get("duplicates_by_ref_name"), list) else []
    missing_name_refs = report.get("missing_name_references") if isinstance(report.get("missing_name_references"), list) else []

    dup_suggestions = _build_duplicate_suggestions(duplicates, controls_by_uid)
    missing_suggestions = _build_missing_name_suggestions(missing_name_refs, controls_by_name)

    out = {
        "phase": "phase7",
        "title": "Control Dict Migrationsvorschlaege",
        "input_report_title": report.get("title"),
        "summary": {
            "duplicate_ref_groups": len(duplicates),
            "duplicate_actions": len(dup_suggestions),
            "missing_name_references": len(missing_name_refs),
            "map_actions": len(missing_suggestions.get("map_actions", [])),
            "create_actions": len(missing_suggestions.get("create_actions", [])),
            "ignored_references": len(missing_suggestions.get("ignored_references", [])),
        },
        "duplicate_resolution": dup_suggestions,
        "missing_name_resolution": missing_suggestions,
    }
    return out


def _load_json(path: Path) -> Dict[str, Any]:
    raw = path.read_text(encoding="utf-8")
    obj = json.loads(raw)
    return obj if isinstance(obj, dict) else {}


def _save_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


async def _run(report_path: Path, output_path: Path) -> Dict[str, Any]:
    report = _load_json(report_path)
    controls_by_uid, controls_by_name = await _load_controls()
    suggestions = build_suggestions(report, controls_by_uid, controls_by_name)
    _save_json(output_path, suggestions)
    return suggestions


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 7 Migrationsvorschlaege fuer control_dict")
    parser.add_argument(
        "--report",
        default=str(BACKEND_DIR / "reports" / "phase7_control_dict_consistency_report.json"),
        help="Pfad zum Konsistenzreport",
    )
    parser.add_argument(
        "--output",
        default=str(BACKEND_DIR / "reports" / "phase7_control_dict_migration_suggestions.json"),
        help="Pfad fuer Ausgabe der Vorschlaege",
    )
    args = parser.parse_args()

    report_path = Path(args.report)
    output_path = Path(args.output)

    if not report_path.exists():
        print(f"ERROR: report not found: {report_path}")
        return 2

    suggestions = asyncio.run(_run(report_path, output_path))
    summary = suggestions.get("summary", {})

    print("PHASE7_CONTROL_DICT_SUGGESTIONS")
    print(f"output={output_path}")
    for key in [
        "duplicate_ref_groups",
        "duplicate_actions",
        "missing_name_references",
        "map_actions",
        "create_actions",
        "ignored_references",
    ]:
        print(f"{key}={summary.get(key)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""
Phase 7: Name-Mapping aus migration_suggestions anwenden

Verarbeitet missing_name_resolution.map_actions aus
backend/reports/phase7_control_dict_migration_suggestions.json.

Default: dry-run
Mit --apply werden Referenzen in sys_framedaten/sys_viewdaten/sys_dialogdaten angepasst.

Standardmodus (--mode name):
- ersetzt den gefundenen Namen am Pfad durch den kanonischen Ziel-Referenznamen.

Optional (--mode uid):
- schreibt stattdessen die Ziel-UID in das Feld am Pfad.

Usage:
  python backend/tools/phase7_apply_name_map_actions.py
  python backend/tools/phase7_apply_name_map_actions.py --apply
  python backend/tools/phase7_apply_name_map_actions.py --apply --mode uid
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import asyncpg

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.connection_manager import ConnectionManager


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


def _load_json(path: Path) -> Dict[str, Any]:
    raw = path.read_text(encoding="utf-8")
    data = json.loads(raw)
    return data if isinstance(data, dict) else {}


def _tokenize_path(path: str) -> List[Any]:
    """Tokenisiert Pfade wie daten.FIELDS.xxx.feld oder daten.items[0].field."""
    s = str(path or "").strip()
    if not s:
        return []

    if s.startswith("daten."):
        s = s[len("daten."):]
    elif s == "daten":
        return []

    tokens: List[Any] = []
    for part in s.split("."):
        m = re.match(r"^([^\[]+)", part)
        if m:
            key = m.group(1)
            if key:
                tokens.append(key)
        for idx_m in re.finditer(r"\[(\d+)\]", part):
            tokens.append(int(idx_m.group(1)))
    return tokens


def _get_by_tokens(root: Any, tokens: List[Any]) -> Tuple[bool, Any]:
    cur = root
    for tok in tokens:
        if isinstance(tok, int):
            if not isinstance(cur, list) or tok < 0 or tok >= len(cur):
                return False, None
            cur = cur[tok]
        else:
            if not isinstance(cur, dict) or tok not in cur:
                return False, None
            cur = cur[tok]
    return True, cur


def _set_by_tokens(root: Any, tokens: List[Any], value: Any) -> bool:
    if not tokens:
        return False

    cur = root
    for tok in tokens[:-1]:
        if isinstance(tok, int):
            if not isinstance(cur, list) or tok < 0 or tok >= len(cur):
                return False
            cur = cur[tok]
        else:
            if not isinstance(cur, dict) or tok not in cur:
                return False
            cur = cur[tok]

    last = tokens[-1]
    if isinstance(last, int):
        if not isinstance(cur, list) or last < 0 or last >= len(cur):
            return False
        cur[last] = value
        return True
    if not isinstance(cur, dict) or last not in cur:
        return False
    cur[last] = value
    return True


async def _load_controls(conn: asyncpg.Connection) -> Dict[str, Dict[str, str]]:
    rows = await conn.fetch(
        """
        SELECT uid::text AS uid, name, daten, modified_at
        FROM sys_control_dict
        WHERE historisch = 0
        """
    )

    out: Dict[str, Dict[str, str]] = {}
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
        ref_name = str(root.get("SELF_NAME") or "").strip() or name
        out[uid] = {
            "uid": uid,
            "name": name,
            "ref_name": ref_name,
            "modified_at": str(row.get("modified_at") or ""),
        }
    return out


def _norm(value: Any) -> str:
    return str(value or "").strip().lower()


def _pick_medium_safe_uid(action: Dict[str, Any], controls: Dict[str, Dict[str, str]]) -> Optional[str]:
    candidate_uids = [str(u).strip().lower() for u in (action.get("candidate_uids") or []) if str(u).strip()]
    if not candidate_uids:
        return None

    existing = [u for u in candidate_uids if u in controls]
    if not existing:
        return None

    # Medium-safe nur wenn alle Kandidaten semantisch derselben Referenz entsprechen.
    sem_refs = {_norm((controls[u].get("ref_name") or controls[u].get("name") or "")) for u in existing}
    sem_refs.discard("")
    if len(sem_refs) != 1:
        return None

    # Deterministische Auswahl: neuester modified_at, dann UID.
    existing_sorted = sorted(
        existing,
        key=lambda uid: (str(controls[uid].get("modified_at") or ""), uid),
        reverse=True,
    )
    return existing_sorted[0] if existing_sorted else None


async def _load_row(conn: asyncpg.Connection, table: str, row_uid: str) -> Optional[Dict[str, Any]]:
    row = await conn.fetchrow(
        f'''
        SELECT uid::text AS uid, name, daten
        FROM "{table}"
        WHERE uid = $1::uuid
          AND historisch = 0
        ''',
        row_uid,
    )
    if not row:
        return None
    return {
        "uid": str(row.get("uid") or ""),
        "name": str(row.get("name") or ""),
        "daten": _as_dict(row.get("daten")),
    }


async def _save_row(conn: asyncpg.Connection, table: str, row_uid: str, daten: Dict[str, Any]) -> None:
    await conn.execute(
        f'''
        UPDATE "{table}"
        SET daten = $1,
            modified_at = NOW()
        WHERE uid = $2::uuid
          AND historisch = 0
        ''',
        json.dumps(daten),
        row_uid,
    )


async def _run(
    apply_changes: bool,
    mode: str,
    allow_medium: bool,
    suggestions_path: Path,
    output_path: Path,
) -> Dict[str, Any]:
    suggestions = _load_json(suggestions_path)
    map_actions = (((suggestions.get("missing_name_resolution") or {}).get("map_actions")) or [])

    cfg = await ConnectionManager.get_system_config()
    conn = await asyncpg.connect(**cfg.to_dict())
    try:
        controls = await _load_controls(conn)

        safe_actions: List[Dict[str, Any]] = []
        medium_promoted = 0
        for raw_action in map_actions:
            if not isinstance(raw_action, dict):
                continue

            action = dict(raw_action)
            high_safe = (
                action.get("to_uid")
                and not bool(action.get("needs_review"))
                and str(action.get("confidence") or "").lower() == "high"
            )
            if high_safe:
                safe_actions.append(action)
                continue

            if allow_medium and str(action.get("confidence") or "").lower() == "medium":
                picked = _pick_medium_safe_uid(action, controls)
                if picked:
                    action["to_uid"] = picked
                    action["promoted_from_medium"] = True
                    safe_actions.append(action)
                    medium_promoted += 1

        by_row: Dict[Tuple[str, str], List[Dict[str, Any]]] = defaultdict(list)
        for action in safe_actions:
            key = (str(action.get("source_table") or ""), str(action.get("row_uid") or ""))
            if key[0] and key[1]:
                by_row[key].append(action)

        touched_rows = 0
        changed_refs = 0
        skipped: List[Dict[str, Any]] = []
        changed: List[Dict[str, Any]] = []

        for (table, row_uid), actions in by_row.items():
            row = await _load_row(conn, table, row_uid)
            if not row:
                for action in actions:
                    skipped.append({"action": action, "reason": "row_not_found"})
                continue

            daten = row["daten"]
            row_changed = False

            for action in actions:
                path = str(action.get("path") or "")
                tokens = _tokenize_path(path)
                ok_get, current_value = _get_by_tokens(daten, tokens)
                if not ok_get:
                    skipped.append({"action": action, "reason": "path_not_found"})
                    continue

                from_name = str(action.get("from_name") or "").strip()
                if str(current_value) != from_name:
                    skipped.append(
                        {
                            "action": action,
                            "reason": "value_mismatch",
                            "current_value": current_value,
                        }
                    )
                    continue

                target_uid = str(action.get("to_uid") or "").strip().lower()
                target = controls.get(target_uid)
                if not target:
                    skipped.append({"action": action, "reason": "target_control_missing"})
                    continue

                new_value = target_uid if mode == "uid" else str(target.get("ref_name") or target.get("name") or "")
                if not new_value:
                    skipped.append({"action": action, "reason": "target_value_empty"})
                    continue

                ok_set = _set_by_tokens(daten, tokens, new_value)
                if not ok_set:
                    skipped.append({"action": action, "reason": "path_not_settable"})
                    continue

                row_changed = True
                changed_refs += 1
                changed.append(
                    {
                        "source_table": table,
                        "row_uid": row_uid,
                        "path": path,
                        "from": from_name,
                        "to": new_value,
                        "to_uid": target_uid,
                    }
                )

            if row_changed:
                touched_rows += 1
                if apply_changes:
                    await _save_row(conn, table, row_uid, daten)

        result = {
            "phase": "phase7",
            "title": "Apply Name Map Actions",
            "database": cfg.database,
            "mode": "apply" if apply_changes else "dry-run",
            "value_mode": mode,
            "allow_medium": allow_medium,
            "summary": {
                "map_actions_input": len(map_actions),
                "safe_actions": len(safe_actions),
                "medium_promoted": medium_promoted,
                "touched_rows": touched_rows,
                "changed_references": changed_refs,
                "skipped": len(skipped),
            },
            "changed": changed,
            "skipped": skipped,
        }

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        return result
    finally:
        await conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 7 Name-Mapping anwenden")
    parser.add_argument(
        "--suggestions",
        default=str(BACKEND_DIR / "reports" / "phase7_control_dict_migration_suggestions.json"),
        help="Pfad zu migration suggestions",
    )
    parser.add_argument(
        "--output",
        default=str(BACKEND_DIR / "reports" / "phase7_control_dict_map_apply_result.json"),
        help="Pfad fuer Ergebnisreport",
    )
    parser.add_argument(
        "--mode",
        choices=["name", "uid"],
        default="name",
        help="Schreibmodus fuer gemappte Werte",
    )
    parser.add_argument(
        "--allow-medium",
        action="store_true",
        help="Erlaubt medium-Aktionen nur bei eindeutiger semantischer Kandidatenmenge",
    )
    parser.add_argument("--apply", action="store_true", help="Aenderungen in DB schreiben")
    args = parser.parse_args()

    suggestions_path = Path(args.suggestions)
    if not suggestions_path.exists():
        print(f"ERROR: suggestions file not found: {suggestions_path}")
        return 2

    result = asyncio.run(
        _run(
            apply_changes=args.apply,
            mode=args.mode,
            allow_medium=args.allow_medium,
            suggestions_path=suggestions_path,
            output_path=Path(args.output),
        )
    )

    summary = result.get("summary", {})
    print("PHASE7_MAP_APPLY")
    print(f"mode={result.get('mode')}")
    print(f"value_mode={result.get('value_mode')}")
    print(f"allow_medium={result.get('allow_medium')}")
    print(f"output={args.output}")
    for key in ["map_actions_input", "safe_actions", "medium_promoted", "touched_rows", "changed_references", "skipped"]:
        print(f"{key}={summary.get(key)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

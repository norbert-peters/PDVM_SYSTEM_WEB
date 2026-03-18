"""Egalisierung: sys_control_dict auf lineare Soll-Struktur ROOT+CONTROL.

ZIEL (ohne Fallbacks):
- Jeder Satz hat exakt die Gruppen ROOT und CONTROL.
- CONTROL.FIELD ist immer GROSSBUCHSTABEN.
- Name folgt immer: <TABELLENPREFIX>_<FIELD> in GROSSBUCHSTABEN.
  Beispiel: table=sys_control_dict + field=label -> SYS_LABEL
- Spalte name wird identisch zum berechneten Namen gesetzt.

Usage:
  python backend/tools/normalize_sys_control_dict_linear.py --dry-run
  python backend/tools/normalize_sys_control_dict_linear.py --apply
  python backend/tools/normalize_sys_control_dict_linear.py --uid <control_guid> --dry-run
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any, Dict, Tuple

import asyncpg

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.connection_manager import ConnectionManager


def _as_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _pick_ci(d: Dict[str, Any], *keys: str) -> Any:
    if not isinstance(d, dict):
        return None
    for key in keys:
        if key in d:
            return d[key]
        up = key.upper()
        if up in d:
            return d[up]
        low = key.lower()
        if low in d:
            return d[low]
    return None


def _table_prefix(table_name: str) -> str:
    table = str(table_name or "").strip()
    if not table:
        return "SYS"
    if "_" in table:
        return table.split("_", 1)[0].upper()
    return table[:3].upper() or "CTL"


def _to_upper_text(value: Any) -> str:
    return str(value or "").strip().upper()


def _canonical_control_name(table_name: str, field_name: str) -> str:
    prefix = _table_prefix(table_name)
    field = _to_upper_text(field_name)
    if not field:
        return prefix
    return f"{prefix}_{field}"


def _upper_top_keys(control_data: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for key, value in control_data.items():
        out[str(key).upper()] = value
    return out


def normalize_row(uid: str, row_name: str, daten: Dict[str, Any]) -> Tuple[Dict[str, Any], str, bool]:
    if not isinstance(daten, dict):
        return daten, row_name, False

    original = json.dumps(daten, ensure_ascii=False, sort_keys=True)

    root_in = _as_dict(daten.get("ROOT"))
    control_in = _as_dict(daten.get("CONTROL"))

    if not control_in:
        control_in = {k: v for k, v in daten.items() if str(k).upper() not in {"ROOT", "CONTROL"}}

    control = _upper_top_keys(control_in)

    table_name = str(
        _pick_ci(control, "TABLE")
        or _pick_ci(root_in, "TABLE")
        or ""
    ).strip()
    if not table_name:
        table_name = "sys_control_dict"

    field_name = str(
        _pick_ci(control, "FIELD", "FELD")
        or _pick_ci(root_in, "FIELD", "FELD")
        or _pick_ci(control, "NAME")
        or row_name
        or ""
    ).strip()

    field_upper = _to_upper_text(field_name)
    canonical_name = _canonical_control_name(table_name, field_upper)

    control["FIELD"] = field_upper
    control["FELD"] = field_upper
    control["NAME"] = canonical_name

    gruppe_val = _pick_ci(control, "GRUPPE")
    if gruppe_val is not None:
        control["GRUPPE"] = _to_upper_text(gruppe_val)

    if table_name:
        control["TABLE"] = str(table_name).strip().lower()

    root: Dict[str, Any] = {}
    root["SELF_GUID"] = str(uid)
    root["SELF_NAME"] = canonical_name
    root["NAME"] = canonical_name
    if table_name:
        root["TABLE"] = str(table_name).strip().lower()
    if field_upper:
        root["FIELD"] = field_upper

    new_daten = {
        "ROOT": root,
        "CONTROL": control,
    }

    changed = json.dumps(new_daten, ensure_ascii=False, sort_keys=True) != original or str(row_name or "") != canonical_name
    return new_daten, canonical_name, changed


async def main() -> int:
    parser = argparse.ArgumentParser(description="Normalize sys_control_dict to linear ROOT+CONTROL format")
    parser.add_argument("--dry-run", action="store_true", help="Only analyze, no DB update")
    parser.add_argument("--apply", action="store_true", help="Persist updates")
    parser.add_argument("--uid", default=None, help="Optional: only one control UID")
    parser.add_argument("--db-url", default=None, help="Optional Postgres URL")
    args = parser.parse_args()

    if args.apply and args.dry_run:
        print("❌ --apply und --dry-run gleichzeitig nicht erlaubt")
        return 2

    apply_mode = bool(args.apply) and not bool(args.dry_run)

    if args.db_url:
        db_url = args.db_url
    else:
        cfg = await ConnectionManager.get_system_config("pdvm_system")
        db_url = cfg.to_url()

    conn = await asyncpg.connect(db_url)

    total = 0
    changed_count = 0
    changed_uids = []

    try:
        if args.uid:
            rows = await conn.fetch(
                "SELECT uid, name, daten FROM public.sys_control_dict WHERE historisch = 0 AND uid = $1::uuid",
                args.uid,
            )
        else:
            rows = await conn.fetch("SELECT uid, name, daten FROM public.sys_control_dict WHERE historisch = 0")

        total = len(rows)

        for row in rows:
            uid = str(row["uid"])
            row_name = str(row.get("name") or "")
            daten = row.get("daten") or {}
            if isinstance(daten, str):
                try:
                    daten = json.loads(daten)
                except Exception:
                    continue
            if not isinstance(daten, dict):
                continue

            normalized_daten, normalized_name, changed = normalize_row(uid, row_name, daten)
            if not changed:
                continue

            changed_count += 1
            changed_uids.append(uid)

            if apply_mode:
                await conn.execute(
                    """
                    UPDATE public.sys_control_dict
                    SET name = $1,
                        daten = $2::jsonb,
                        modified_at = NOW()
                    WHERE uid = $3::uuid
                    """,
                    normalized_name,
                    json.dumps(normalized_daten, ensure_ascii=False),
                    uid,
                )

        mode = "APPLY" if apply_mode else "DRY-RUN"
        print(f"✅ sys_control_dict Egalisierung {mode} abgeschlossen")
        print(f"   Datensaetze gesamt: {total}")
        print(f"   Datensaetze angepasst: {changed_count}")
        if changed_uids:
            preview = changed_uids[:10]
            print(f"   Beispiel-UIDs: {preview}")

    finally:
        await conn.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

"""Canonicalize sys_framedaten FIELDS[*].FIELD references to sys_control_dict UUIDs.

Usage:
  python backend/tools/canonicalize_sys_framedaten_fields_uid.py --dry-run
  python backend/tools/canonicalize_sys_framedaten_fields_uid.py --apply
"""

from __future__ import annotations

import argparse
import asyncio
import json
from typing import Any, Dict

import asyncpg

DEFAULT_DB_URL = "postgresql://postgres:Polari$55@localhost:5432/pdvm_system"


def as_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def norm_token(value: Any) -> str:
    return str(value or "").strip().upper()


def is_uuid(value: Any) -> bool:
    s = str(value or "").strip()
    if not s:
        return False
    import re

    return bool(re.match(r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$", s, re.I))


def read_ci(source: Dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in source:
            return source[key]
        up = key.upper()
        if up in source:
            return source[up]
        low = key.lower()
        if low in source:
            return source[low]
    return None


async def main() -> None:
    parser = argparse.ArgumentParser(description="Canonicalize sys_framedaten FIELD refs to UUID")
    parser.add_argument("--db-url", default=DEFAULT_DB_URL, help="PostgreSQL connection URL")
    parser.add_argument("--dry-run", action="store_true", help="Preview only")
    parser.add_argument("--apply", action="store_true", help="Persist updates")
    args = parser.parse_args()

    apply_mode = args.apply and not args.dry_run
    conn = await asyncpg.connect(args.db_url)
    try:
        control_rows = await conn.fetch("SELECT uid, name, daten FROM public.sys_control_dict WHERE historisch = 0")
        uid_by_token: Dict[str, str] = {}

        def add_token(token: Any, uid: str) -> None:
            key = norm_token(token)
            if key and key not in uid_by_token:
                uid_by_token[key] = uid

        for row in control_rows:
            uid = str(row["uid"])
            data = as_dict(row["daten"])
            control = as_dict(data.get("CONTROL"))
            root = as_dict(data.get("ROOT"))

            add_token(uid, uid)
            add_token(row.get("name"), uid)
            add_token(control.get("FIELD"), uid)
            add_token(control.get("FELD"), uid)
            add_token(control.get("NAME"), uid)
            add_token(control.get("LABEL"), uid)
            add_token(root.get("SELF_NAME"), uid)
            add_token(root.get("NAME"), uid)

        frame_rows = await conn.fetch("SELECT uid, name, daten FROM public.sys_framedaten WHERE historisch = 0")

        changed_rows = 0
        changed_entries = 0

        for row in frame_rows:
            data = as_dict(row["daten"])
            fields = as_dict(data.get("FIELDS"))
            if not fields:
                continue

            frame_changed = False

            for entry_uid, entry_value in fields.items():
                entry = as_dict(entry_value)
                if not entry:
                    continue

                raw_field = str(read_ci(entry, "FIELD", "FELD") or "").strip()
                if not raw_field or is_uuid(raw_field):
                    continue

                resolved_uid = uid_by_token.get(norm_token(raw_field), "")
                if not is_uuid(resolved_uid):
                    continue

                entry["FIELD"] = resolved_uid
                fields[entry_uid] = entry
                frame_changed = True
                changed_entries += 1

            if not frame_changed:
                continue

            changed_rows += 1
            data["FIELDS"] = fields

            if apply_mode:
                await conn.execute(
                    """
                    UPDATE public.sys_framedaten
                       SET daten = $1::jsonb,
                           modified_at = NOW()
                     WHERE uid = $2::uuid
                    """,
                    json.dumps(data, ensure_ascii=False),
                    str(row["uid"]),
                )

        print("=" * 80)
        print("sys_framedaten FIELD canonicalization")
        print("=" * 80)
        print(f"mode: {'APPLY' if apply_mode else 'DRY-RUN'}")
        print(f"frames changed: {changed_rows}")
        print(f"entries changed: {changed_entries}")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())

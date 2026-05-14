"""Normalisiert einen Datensatz in sys_dialogdaten/sys_viewdaten/sys_framedaten gegen die 666-ROOT-Basis.

Usage:
  python tools/normalize_table_record.py --table sys_viewdaten --uid <uid>
"""
from __future__ import annotations

import argparse
import asyncio
import copy
import json
from pathlib import Path
import sys
import uuid
from typing import Any, Dict

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import asyncpg

from app.core.connection_manager import ConnectionManager

UID_666 = "66666666-6666-6666-6666-666666666666"
ALLOWED_TABLES = {"sys_dialogdaten", "sys_viewdaten", "sys_framedaten"}


def _as_obj(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def _is_meaningful(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str) and not value.strip():
        return False
    return True


async def main_async(table: str, target_uid: str) -> int:
    if table not in ALLOWED_TABLES:
        raise RuntimeError(f"ungueltige Tabelle: {table}")

    cfg = await ConnectionManager.get_system_config("pdvm_system")
    conn = await asyncpg.connect(cfg.to_url())
    try:
        tpl_row = await conn.fetchrow(
            f"SELECT daten FROM {table} WHERE uid = $1::uuid AND COALESCE(historisch,0)=0",
            UID_666,
        )
        if not tpl_row:
            raise RuntimeError(f"Template 666 fehlt in {table}")

        row = await conn.fetchrow(
            f"SELECT uid, name, daten FROM {table} WHERE uid = $1::uuid AND COALESCE(historisch,0)=0",
            target_uid,
        )
        if not row:
            raise RuntimeError(f"Datensatz nicht gefunden: {target_uid}")

        template = _as_obj(tpl_row["daten"])
        current = _as_obj(row["daten"])
        template_root = _as_obj(template.get("ROOT"))
        current_root = _as_obj(current.get("ROOT"))

        merged = copy.deepcopy(current)
        next_root = dict(template_root)
        for key, value in current_root.items():
            if _is_meaningful(value):
                next_root[key] = value

        next_root["SELF_GUID"] = str(row["uid"])
        if not str(next_root.get("SELF_NAME") or "").strip():
            next_root["SELF_NAME"] = str(row["name"] or "")

        merged["ROOT"] = next_root

        await conn.execute(
            f"""
            UPDATE {table}
            SET daten = $2::jsonb,
                modified_at = NOW()
            WHERE uid = $1::uuid
            """,
            uuid.UUID(str(row["uid"])),
            json.dumps(merged, ensure_ascii=False),
        )

        print(f"Normalisiert: {table} | {row['name']} [{row['uid']}]")
        return 0
    finally:
        await conn.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Normalize one record in target table against 666 ROOT")
    parser.add_argument("--table", required=True)
    parser.add_argument("--uid", required=True)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    raise SystemExit(asyncio.run(main_async(args.table, args.uid)))

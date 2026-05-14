"""Normalisiert einen sys_dialogdaten-Datensatz gegen die 666-ROOT-Basis.

- Fehlende ROOT-Keys aus 666 werden ergänzt.
- Bestehende Werte bleiben erhalten.
- SELF_GUID/SELF_NAME werden konsistent gesetzt.

Usage:
  python tools/normalize_sys_dialog_record.py --uid <dialog_uid>
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


async def main_async(target_uid: str) -> int:
    cfg = await ConnectionManager.get_system_config("pdvm_system")
    conn = await asyncpg.connect(cfg.to_url())
    try:
        tpl_row = await conn.fetchrow(
            "SELECT daten FROM sys_dialogdaten WHERE uid = $1::uuid AND COALESCE(historisch,0)=0",
            UID_666,
        )
        if not tpl_row:
            raise RuntimeError("Template 666 in sys_dialogdaten fehlt")

        row = await conn.fetchrow(
            "SELECT uid, name, daten FROM sys_dialogdaten WHERE uid = $1::uuid AND COALESCE(historisch,0)=0",
            target_uid,
        )
        if not row:
            raise RuntimeError(f"Datensatz nicht gefunden: {target_uid}")

        template = _as_obj(tpl_row["daten"])
        current = _as_obj(row["daten"])

        template_root = template.get("ROOT") if isinstance(template.get("ROOT"), dict) else {}
        current_root = current.get("ROOT") if isinstance(current.get("ROOT"), dict) else {}

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
            """
            UPDATE sys_dialogdaten
            SET daten = $2::jsonb,
                modified_at = NOW()
            WHERE uid = $1::uuid
            """,
            uuid.UUID(str(row["uid"])),
            json.dumps(merged, ensure_ascii=False),
        )

        print(f"Normalisiert: {row['name']} [{row['uid']}]")
        return 0
    finally:
        await conn.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Normalize one sys_dialogdaten record against template 666")
    parser.add_argument("--uid", required=True, help="UID des zu normalisierenden Datensatzes")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    raise SystemExit(asyncio.run(main_async(args.uid)))

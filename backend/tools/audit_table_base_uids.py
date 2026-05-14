"""Prueft tabellenweit die reservierten Basissaetze 000/555/666.

Checks:
- Existenz von 000..., 555..., 666... in jeder Tabelle mit UID-Spalte.
- 555-Datenstruktur: ROOT + TEMPLATES vorhanden.
- 666-Datenstruktur: ROOT vorhanden.

Usage:
  python tools/audit_table_base_uids.py
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
import sys
from typing import Any, Dict, List

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import asyncpg

from app.core.connection_manager import ConnectionManager


UID_META = "00000000-0000-0000-0000-000000000000"
UID_555 = "55555555-5555-5555-5555-555555555555"
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


async def _get_db_url() -> str:
    cfg = await ConnectionManager.get_system_config("pdvm_system")
    return cfg.to_url()


async def main_async() -> int:
    db_url = await _get_db_url()
    conn = await asyncpg.connect(db_url)
    try:
        rows = await conn.fetch(
            """
            SELECT table_name
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND column_name = 'uid'
            ORDER BY table_name
            """
        )
        tables = [str(r["table_name"]).strip() for r in rows if str(r["table_name"]).strip()]

        findings: List[str] = []
        checked = 0
        for table in tables:
            checked += 1
            recs = await conn.fetch(
                f"SELECT uid, daten FROM {table} WHERE uid IN ($1::uuid, $2::uuid, $3::uuid)",
                UID_META,
                UID_555,
                UID_666,
            )
            by_uid = {str(r["uid"]): r for r in recs}

            for required_uid in (UID_META, UID_555, UID_666):
                if required_uid not in by_uid:
                    findings.append(f"{table}: fehlende UID {required_uid}")

            row_555 = by_uid.get(UID_555)
            if row_555:
                data_555 = _as_obj(row_555["daten"])
                if "ROOT" not in data_555 or not isinstance(data_555.get("ROOT"), dict):
                    findings.append(f"{table}: UID 555 ohne ROOT-Objekt")
                if "TEMPLATES" not in data_555 or not isinstance(data_555.get("TEMPLATES"), dict):
                    findings.append(f"{table}: UID 555 ohne TEMPLATES-Objekt")

            row_666 = by_uid.get(UID_666)
            if row_666:
                data_666 = _as_obj(row_666["daten"])
                if "ROOT" not in data_666 or not isinstance(data_666.get("ROOT"), dict):
                    findings.append(f"{table}: UID 666 ohne ROOT-Objekt")

        print("=== Audit 000/555/666 (tabellenweit) ===")
        print(f"Gepruefte Tabellen: {checked}")
        print(f"Findings: {len(findings)}")
        for item in findings:
            print(f"- {item}")

        return 0 if not findings else 2
    finally:
        await conn.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main_async()))

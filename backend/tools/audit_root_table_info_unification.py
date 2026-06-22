from __future__ import annotations

import argparse
import asyncio
import json
from collections import Counter
from pathlib import Path
import sys
from typing import Any, Dict, List, Tuple

import asyncpg

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.connection_manager import ConnectionManager


UID_000 = "00000000-0000-0000-0000-000000000000"
UID_555 = "55555555-5555-5555-5555-555555555555"
UID_666 = "66666666-6666-6666-6666-666666666666"
RESERVED = {UID_000, UID_555, UID_666}


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


async def _tables_with_uid_and_daten(conn: asyncpg.Connection) -> List[str]:
    rows = await conn.fetch(
        """
        SELECT c.table_name
        FROM information_schema.columns c
        WHERE c.table_schema = 'public'
          AND c.column_name IN ('uid', 'daten')
        GROUP BY c.table_name
        HAVING COUNT(DISTINCT c.column_name) = 2
        ORDER BY c.table_name
        """
    )
    return [str(r["table_name"]).strip() for r in rows]


def _sorted_keys(value: Any) -> List[str]:
    if isinstance(value, dict):
        return sorted([str(k) for k in value.keys()])
    return []


def _extract_table_info_from_666(d666: Dict[str, Any]) -> Tuple[bool, str, Dict[str, Any], bool]:
    """Akzeptiert TABLE_INFO nur unter 666.TEMPLATES.TABLE_INFO.

    Rueckgabe:
    - exists
    - path
    - table_info_obj
    - has_invalid_direct_table_info
    """
    data = _as_obj(d666)

    has_invalid_direct_table_info = isinstance(data.get("TABLE_INFO"), dict)

    templates = _as_obj(data.get("TEMPLATES"))
    nested = _as_obj(templates.get("TABLE_INFO"))
    if nested:
        return True, "666.TEMPLATES.TABLE_INFO", nested, has_invalid_direct_table_info

    return False, "", {}, has_invalid_direct_table_info


async def _analyze_table(conn: asyncpg.Connection, table: str) -> Dict[str, Any]:
    rows = await conn.fetch(
        f"SELECT uid, name, daten FROM {table} WHERE COALESCE(historisch, 0) = 0"
    )
    by_uid: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        uid = str(row["uid"])
        by_uid[uid] = {
            "uid": uid,
            "name": str(row.get("name") or ""),
            "daten": _as_obj(row.get("daten")),
        }

    has_000 = UID_000 in by_uid
    has_555 = UID_555 in by_uid
    has_666 = UID_666 in by_uid

    d555 = by_uid.get(UID_555, {}).get("daten") if has_555 else {}
    d666 = by_uid.get(UID_666, {}).get("daten") if has_666 else {}

    root_555 = _as_obj(_as_obj(d555).get("ROOT"))
    root_666 = _as_obj(_as_obj(d666).get("ROOT"))
    templates_555 = _as_obj(_as_obj(d555).get("TEMPLATES"))

    groups_666 = [
        str(k)
        for k in _as_obj(d666).keys()
        if str(k).upper() != "ROOT"
    ]

    table_info_exists, table_info_path, table_info_666, table_info_invalid_direct = _extract_table_info_from_666(_as_obj(d666))

    invalid_666_groups = sorted(
        [
            str(k)
            for k in _as_obj(d666).keys()
            if str(k).upper() not in {"ROOT", "TEMPLATES"}
        ]
    )

    non_reserved = [r for uid, r in by_uid.items() if uid not in RESERVED]

    root_missing_vs_666_count = 0
    root_missing_vs_666_examples: List[Dict[str, Any]] = []
    required_666_keys = set(root_666.keys())
    for row in non_reserved:
        root = _as_obj(_as_obj(row.get("daten")).get("ROOT"))
        missing = sorted([k for k in required_666_keys if k not in root])
        if missing:
            root_missing_vs_666_count += 1
            if len(root_missing_vs_666_examples) < 5:
                root_missing_vs_666_examples.append(
                    {
                        "uid": row.get("uid"),
                        "name": row.get("name"),
                        "missing": missing,
                    }
                )

    return {
        "table": table,
        "active_rows": len(rows),
        "non_reserved_rows": len(non_reserved),
        "reserved_presence": {
            "000": has_000,
            "555": has_555,
            "666": has_666,
        },
        "root_keys_555": _sorted_keys(root_555),
        "root_keys_666": _sorted_keys(root_666),
        "templates_keys_555": _sorted_keys(templates_555),
        "groups_666": sorted(groups_666),
        "groups_666_invalid_extra": invalid_666_groups,
        "table_info": {
            "exists_in_666": table_info_exists,
            "path_in_666": table_info_path,
            "keys_666": _sorted_keys(table_info_666),
            "invalid_direct_path_666_table_info": table_info_invalid_direct,
        },
        "conformance": {
            "non_reserved_rows_with_missing_root_keys_vs_666": root_missing_vs_666_count,
            "examples": root_missing_vs_666_examples,
        },
    }


async def main_async(dialog_uid: str, output_path: str) -> int:
    db_url = await _get_db_url()
    conn = await asyncpg.connect(db_url)
    try:
        tables = await _tables_with_uid_and_daten(conn)
        analyses: List[Dict[str, Any]] = []

        root_key_freq = Counter()
        table_info_key_freq = Counter()
        tables_with_table_info = 0
        tables_with_invalid_666_group_structure = 0
        tables_with_invalid_666_direct_table_info = 0

        for table in tables:
            item = await _analyze_table(conn, table)
            analyses.append(item)

            for key in item.get("root_keys_666", []):
                root_key_freq[str(key)] += 1

            ti = item.get("table_info", {}) if isinstance(item.get("table_info"), dict) else {}
            if bool(ti.get("exists_in_666")):
                tables_with_table_info += 1
            if bool(ti.get("invalid_direct_path_666_table_info")):
                tables_with_invalid_666_direct_table_info += 1
            if isinstance(item.get("groups_666_invalid_extra"), list) and len(item.get("groups_666_invalid_extra")) > 0:
                tables_with_invalid_666_group_structure += 1
            for key in ti.get("keys_666", []) if isinstance(ti.get("keys_666"), list) else []:
                table_info_key_freq[str(key)] += 1

        total_tables = len(analyses)
        all_root_common = sorted([k for k, c in root_key_freq.items() if c == total_tables]) if total_tables else []
        root_majority = sorted([k for k, c in root_key_freq.items() if c >= max(1, int(total_tables * 0.7))])
        table_info_majority = sorted([k for k, c in table_info_key_freq.items() if c >= max(1, int(total_tables * 0.7))])

        dialog_row = await conn.fetchrow(
            "SELECT uid, name, daten FROM sys_dialogdaten WHERE uid = $1::uuid AND COALESCE(historisch,0)=0",
            dialog_uid,
        )
        dialog_audit: Dict[str, Any] = {"found": False}
        if dialog_row:
            dialog_daten = _as_obj(dialog_row.get("daten"))
            dialog_root = _as_obj(dialog_daten.get("ROOT"))

            row_555 = await conn.fetchrow(
                "SELECT daten FROM sys_dialogdaten WHERE uid = $1::uuid AND COALESCE(historisch,0)=0",
                UID_555,
            )
            row_666 = await conn.fetchrow(
                "SELECT daten FROM sys_dialogdaten WHERE uid = $1::uuid AND COALESCE(historisch,0)=0",
                UID_666,
            )

            root_555 = _as_obj(_as_obj(row_555.get("daten") if row_555 else {}).get("ROOT"))
            root_666 = _as_obj(_as_obj(row_666.get("daten") if row_666 else {}).get("ROOT"))

            keys_dialog = set(dialog_root.keys())
            keys_555 = set(root_555.keys())
            keys_666 = set(root_666.keys())

            dialog_audit = {
                "found": True,
                "uid": str(dialog_row["uid"]),
                "name": str(dialog_row.get("name") or ""),
                "root_keys_dialog": sorted(keys_dialog),
                "root_keys_555": sorted(keys_555),
                "root_keys_666": sorted(keys_666),
                "missing_vs_555": sorted([k for k in keys_555 if k not in keys_dialog]),
                "missing_vs_666": sorted([k for k in keys_666 if k not in keys_dialog]),
                "extra_vs_666": sorted([k for k in keys_dialog if k not in keys_666]),
            }

        report = {
            "title": "ROOT und TABLE_INFO Vereinheitlichungs-Audit",
            "database": "pdvm_system",
            "dialog_uid_focus": dialog_uid,
            "summary": {
                "tables_analyzed": total_tables,
                "tables_with_table_info_in_666": tables_with_table_info,
                "tables_without_table_info_in_666": total_tables - tables_with_table_info,
                "tables_with_invalid_666_group_structure": tables_with_invalid_666_group_structure,
                "tables_with_invalid_666_direct_table_info": tables_with_invalid_666_direct_table_info,
            },
            "common_candidates": {
                "root_keys_common_all_tables": all_root_common,
                "root_keys_majority_70pct": root_majority,
                "table_info_keys_majority_70pct": table_info_majority,
            },
            "dialog_focus": dialog_audit,
            "tables": analyses,
            "questions_guidance": {
                "table_info_as_second_group": "Ja: TABLE_INFO als feste zweite Gruppe in 666 definieren. In Fachdaten optional, in 666 verpflichtend.",
                "root_to_table_info_split": "ROOT fuer Datensatzidentitaet/Laufzeitsteuerung; TABLE_INFO fuer Tabellenmetadaten und statische Konfiguration.",
            },
        }

        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

        print("Audit geschrieben:", str(out))
        print("Tabellen:", total_tables)
        print("TABLE_INFO in 666 vorhanden:", tables_with_table_info)
        if dialog_audit.get("found"):
            print("Dialog missing_vs_666:", len(dialog_audit.get("missing_vs_666", [])))
            print("Dialog extra_vs_666:", len(dialog_audit.get("extra_vs_666", [])))
        else:
            print("Dialog nicht gefunden")

        return 0
    finally:
        await conn.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit ROOT/TABLE_INFO Vereinheitlichung")
    parser.add_argument("--dialog-uid", required=True)
    parser.add_argument(
        "--output",
        default=str(BACKEND_DIR / "reports" / "root_table_info_unification_audit_2026_05_27.json"),
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    raise SystemExit(asyncio.run(main_async(args.dialog_uid, args.output)))

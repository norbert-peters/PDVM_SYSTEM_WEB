"""Audit und optionale Bereinigung der sys_dialogdaten Grundstruktur.

Regeln:
- Reservierte UIDs: 000..., 555..., 666... muessen vorhanden sein.
- Nicht-reservierte Datensaetze muessen mindestens eine ROOT-Struktur besitzen,
  SELF_GUID passend zur Zeilen-UID haben und die Pflichtfelder aus 666-ROOT tragen.

Usage:
  python tools/audit_sys_dialogdaten_structure.py
  python tools/audit_sys_dialogdaten_structure.py --normalize-builder
  python tools/audit_sys_dialogdaten_structure.py --delete-invalid
"""
from __future__ import annotations

import argparse
import asyncio
import copy
import json
from pathlib import Path
import sys
from typing import Any, Dict, List, Tuple
import uuid

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import asyncpg

from app.core.connection_manager import ConnectionManager


UID_META = "00000000-0000-0000-0000-000000000000"
UID_555 = "55555555-5555-5555-5555-555555555555"
UID_666 = "66666666-6666-6666-6666-666666666666"
RESERVED = {UID_META, UID_555, UID_666}
BUILDER_NAME = "WORKFLOW_DRAFT_BUILDER_DIALOG_TEMPLATE"


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


def _validate_record(*, uid: str, daten: Dict[str, Any], required_root_keys: List[str]) -> List[str]:
    issues: List[str] = []
    if not daten:
        return ["daten leer/ungueltig"]

    root = daten.get("ROOT")
    if not isinstance(root, dict):
        return ["ROOT fehlt oder ist kein Objekt"]

    self_guid = str(root.get("SELF_GUID") or "").strip()
    if self_guid.lower() != uid.lower():
        issues.append("ROOT.SELF_GUID passt nicht zur Zeilen-UID")

    self_name = str(root.get("SELF_NAME") or "").strip()
    if not self_name:
        issues.append("ROOT.SELF_NAME fehlt")

    for key in required_root_keys:
        if key in {"SELF_GUID", "SELF_NAME"}:
            continue
        if key not in root:
            issues.append(f"ROOT.{key} fehlt (laut 666-Basis)")

    if "TAB_ELEMENTS" in required_root_keys and not isinstance(root.get("TAB_ELEMENTS"), dict):
        issues.append("ROOT.TAB_ELEMENTS ist nicht vom Typ Objekt")

    return issues


async def main_async(args: argparse.Namespace) -> int:
    db_url = await _get_db_url()
    conn = await asyncpg.connect(db_url)
    try:
        rows = await conn.fetch("SELECT uid, name, daten FROM sys_dialogdaten ORDER BY name")
        by_uid: Dict[str, asyncpg.Record] = {str(r["uid"]): r for r in rows}

        missing_reserved = [u for u in [UID_META, UID_555, UID_666] if u not in by_uid]
        if missing_reserved:
            print("❌ Fehlende reservierte UID(s):")
            for uid in missing_reserved:
                print(f"  - {uid}")
            return 2

        template_666 = _as_obj(by_uid[UID_666]["daten"])
        root_666 = template_666.get("ROOT") if isinstance(template_666.get("ROOT"), dict) else {}
        required_root_keys = sorted(list(root_666.keys()))

        if args.normalize_builder:
            builder_row = None
            for row in rows:
                if str(row["name"] or "").strip().upper() == BUILDER_NAME:
                    builder_row = row
                    break

            if builder_row:
                builder_uid = str(builder_row["uid"])
                builder_name = str(builder_row["name"] or "").strip() or BUILDER_NAME
                builder_daten = _as_obj(builder_row["daten"])
                builder_root = builder_daten.get("ROOT") if isinstance(builder_daten.get("ROOT"), dict) else {}

                normalized = copy.deepcopy(template_666)
                norm_root = normalized.get("ROOT") if isinstance(normalized.get("ROOT"), dict) else {}
                norm_root = dict(norm_root)
                # 666-Struktur als Basis, fachliche Builder-Werte bleiben erhalten.
                for key in ["TABLE", "DIALOG_TYPE", "OPEN_EDIT", "SELECTION_MODE", "TAB_ELEMENTS", "CREATE_FRAME_GUID", "CREATE_REQUIRED", "CREATE_DEFAULTS"]:
                    if key in builder_root:
                        norm_root[key] = builder_root[key]
                norm_root["SELF_GUID"] = builder_uid
                norm_root["SELF_NAME"] = builder_name
                normalized["ROOT"] = norm_root

                payload = json.dumps(normalized, ensure_ascii=False)
                await conn.execute(
                    """
                    UPDATE sys_dialogdaten
                    SET daten = $2::jsonb,
                        modified_at = NOW()
                    WHERE uid = $1::uuid
                    """,
                    uuid.UUID(builder_uid),
                    payload,
                )
                print(f"Builder-Template normalisiert: {builder_name} ({builder_uid})")
            else:
                print("Builder-Template nicht gefunden (Name WORKFLOW_DRAFT_BUILDER_DIALOG_TEMPLATE).")

        invalid: List[Tuple[str, str, List[str]]] = []
        for row in rows:
            uid = str(row["uid"])
            if uid in RESERVED:
                continue
            name = str(row["name"] or "")
            daten = _as_obj(row["daten"])
            issues = _validate_record(uid=uid, daten=daten, required_root_keys=required_root_keys)
            if issues:
                invalid.append((uid, name, issues))

        print("\n=== Audit sys_dialogdaten ===")
        print(f"Gesamt: {len(rows)}")
        print("Reserviert vorhanden: 000/555/666 OK")
        print(f"Löschkandidaten (nicht-reserviert, strukturell fehlerhaft): {len(invalid)}")

        for uid, name, issues in invalid:
            print(f"- {name} [{uid}]")
            for issue in issues:
                print(f"    * {issue}")

        if args.delete_invalid and invalid:
            for uid, _name, _issues in invalid:
                await conn.execute("DELETE FROM sys_dialogdaten WHERE uid = $1::uuid", uuid.UUID(uid))
            print(f"\nGeloescht: {len(invalid)} Datensatz/Datensaetze")
        elif args.delete_invalid:
            print("\nKeine Loeschkandidaten vorhanden.")
        else:
            print("\nKein Loeschen durchgefuehrt (nur Angebot). Mit --delete-invalid aktivieren.")

        return 0
    finally:
        await conn.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit sys_dialogdaten structure and offer cleanup")
    parser.add_argument("--normalize-builder", action="store_true", help="Builder-Template auf 666-Basisstruktur normalisieren")
    parser.add_argument("--delete-invalid", action="store_true", help="Gefundene Löschkandidaten wirklich löschen")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main_async(parse_args())))

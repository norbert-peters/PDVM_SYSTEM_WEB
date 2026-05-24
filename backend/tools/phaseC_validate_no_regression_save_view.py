"""
Phase C Punkt 3: Formale Regression-Validierung fuer Save/Reload/View.

Ziel:
1. Save-Pfad pruefen (UPDATE daten) je Stichprobentabelle.
2. Reload-Pfad pruefen (geaenderte Daten im selben TX sichtbar).
3. View-Lesepfad pruefen (daten als Dict mit ROOT auslesbar/serialisierbar).

Sicherheitsprinzip:
1. Save-Probe laeuft in Transaktion mit explizitem ROLLBACK.
2. Produktivdaten bleiben unveraendert.

Usage:
  python backend/tools/phaseC_validate_no_regression_save_view.py
  python backend/tools/phaseC_validate_no_regression_save_view.py --output backend/reports/phaseC_validate_no_regression_save_view_v1.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import asyncpg

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.connection_manager import ConnectionConfig, ConnectionManager
from tools.phaseB_persist_template_modes import SYSTEM_MANDANT_UIDS, _resolve_main_mandant_config


@dataclass
class ProbeTarget:
    db_label: str
    table_name: str
    expectation: str


TARGETS: List[ProbeTarget] = [
    ProbeTarget("system", "sys_framedaten", "view_config"),
    ProbeTarget("system", "sys_viewdaten", "view_config"),
    ProbeTarget("system", "sys_dropdowndaten", "infos_dropdown"),
    ProbeTarget("auth", "asy_mandanten", "auth_master"),
    ProbeTarget("mandant_main", "msy_systemdaten", "mandant_config"),
    ProbeTarget("mandant_main", "msy_systemsteuerung", "mandant_config"),
]


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


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _table_exists(conn: asyncpg.Connection, table_name: str) -> bool:
    exists = await conn.fetchval("SELECT to_regclass($1) IS NOT NULL", f"public.{table_name}")
    return bool(exists)


async def _load_probe_rows(conn: asyncpg.Connection, table_name: str) -> List[Dict[str, Any]]:
    if not await _table_exists(conn, table_name):
        return []

    rows = await conn.fetch(
        f'''
        SELECT uid::text AS uid, name, daten
        FROM "{table_name}"
        WHERE COALESCE(historisch, 0) = 0
        ORDER BY created_at
        LIMIT 50
        '''
    )
    out: List[Dict[str, Any]] = []
    for row in rows:
        uid = str(row.get("uid") or "")
        if uid in SYSTEM_MANDANT_UIDS:
            continue
        out.append(
            {
            "uid": uid,
            "name": str(row.get("name") or ""),
            "daten": _as_dict(row.get("daten")),
            }
        )
    return out


def _check_view_readability(data: Dict[str, Any], expectation: str) -> Tuple[bool, str]:
    if not isinstance(data, dict):
        return False, "daten_not_dict"

    try:
        json.dumps(data, ensure_ascii=False)
    except Exception as exc:
        return False, f"json_serialize_failed: {exc}"

    root = _as_dict(data.get("ROOT"))
    if not root:
        return False, "root_missing"

    if expectation == "infos_dropdown":
        if "OPTIONS" not in data:
            return False, "options_missing"

    if expectation == "view_config":
        if not ("FIELDS" in data or "ROOT" in data):
            return False, "view_keys_missing"

    return True, "ok"


async def _run_save_reload_probe(conn: asyncpg.Connection, table_name: str, row: Dict[str, Any]) -> Tuple[bool, str]:
    uid = str(row.get("uid") or "")
    data = _as_dict(row.get("daten"))
    if not data:
        return False, "daten_empty"

    probe_ts = _utc_now()
    root = _as_dict(data.get("ROOT"))
    root["__REGRESSION_PROBE__"] = probe_ts
    candidate = dict(data)
    candidate["ROOT"] = root

    tx = conn.transaction()
    await tx.start()
    try:
        await conn.execute(
            f'''
            UPDATE "{table_name}"
            SET daten = $1::jsonb,
                modified_at = NOW()
            WHERE uid::text = $2
            ''',
            json.dumps(candidate, ensure_ascii=False),
            uid,
        )

        reloaded = await conn.fetchrow(
            f'''SELECT daten FROM "{table_name}" WHERE uid::text = $1''',
            uid,
        )
        r_data = _as_dict(reloaded.get("daten") if reloaded else None)
        r_root = _as_dict(r_data.get("ROOT"))
        probe_seen = str(r_root.get("__REGRESSION_PROBE__") or "")
        if probe_seen != probe_ts:
            await tx.rollback()
            return False, "reload_probe_not_visible"

        await tx.rollback()
        return True, "ok"
    except Exception as exc:
        try:
            await tx.rollback()
        except Exception:
            pass
        return False, f"save_reload_failed: {exc}"


async def _probe_target(conn: asyncpg.Connection, target: ProbeTarget) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "db_label": target.db_label,
        "table": target.table_name,
        "expectation": target.expectation,
        "row_uid": None,
        "row_name": None,
        "candidates_checked": 0,
        "candidates_skipped_nonconformant": 0,
        "view_check": {"ok": False, "message": "not_run"},
        "save_reload_check": {"ok": False, "message": "not_run"},
        "status": "failed",
    }

    rows = await _load_probe_rows(conn, target.table_name)
    if not rows:
        out["status"] = "skipped"
        out["view_check"] = {"ok": False, "message": "no_probe_row"}
        out["save_reload_check"] = {"ok": False, "message": "no_probe_row"}
        return out

    picked: Optional[Dict[str, Any]] = None
    picked_msg = "no_conformant_probe_row"
    for row in rows:
        out["candidates_checked"] += 1
        ok_view, msg_view = _check_view_readability(row["daten"], target.expectation)
        if ok_view:
            picked = row
            picked_msg = msg_view
            break
        out["candidates_skipped_nonconformant"] += 1
        picked_msg = msg_view

    if not picked:
        out["view_check"] = {"ok": False, "message": picked_msg}
        out["save_reload_check"] = {"ok": False, "message": "not_run"}
        out["status"] = "failed"
        return out

    out["row_uid"] = picked["uid"]
    out["row_name"] = picked["name"]

    ok_view, msg_view = _check_view_readability(picked["daten"], target.expectation)
    out["view_check"] = {"ok": ok_view, "message": msg_view}

    ok_save, msg_save = await _run_save_reload_probe(conn, target.table_name, picked)
    out["save_reload_check"] = {"ok": ok_save, "message": msg_save}

    if ok_view and ok_save:
        out["status"] = "passed"
    return out


async def build_report() -> Dict[str, Any]:
    system_cfg = await ConnectionManager.get_system_config("pdvm_system")
    auth_cfg = await ConnectionManager.get_auth_config()
    mandant_cfg, mandant_info = await _resolve_main_mandant_config()

    cfg_map: Dict[str, ConnectionConfig] = {
        "system": system_cfg,
        "auth": auth_cfg,
    }
    if mandant_cfg:
        cfg_map["mandant_main"] = mandant_cfg

    report: Dict[str, Any] = {
        "phase": "phaseC_validate_no_regression_save_view",
        "generated_at_utc": _utc_now(),
        "main_mandant": mandant_info,
        "probes": [],
        "summary": {
            "targets_total": 0,
            "targets_passed": 0,
            "targets_failed": 0,
            "targets_skipped": 0,
        },
    }

    connections: Dict[str, asyncpg.Connection] = {}
    try:
        for db_label, cfg in cfg_map.items():
            connections[db_label] = await asyncpg.connect(**cfg.to_dict())

        for target in TARGETS:
            conn = connections.get(target.db_label)
            if not conn:
                report["probes"].append(
                    {
                        "db_label": target.db_label,
                        "table": target.table_name,
                        "expectation": target.expectation,
                        "row_uid": None,
                        "row_name": None,
                        "view_check": {"ok": False, "message": "db_not_available"},
                        "save_reload_check": {"ok": False, "message": "db_not_available"},
                        "status": "skipped",
                    }
                )
                continue

            probe = await _probe_target(conn, target)
            report["probes"].append(probe)
    finally:
        for conn in connections.values():
            await conn.close()

    report["summary"]["targets_total"] = len(report["probes"])
    for p in report["probes"]:
        status = str(p.get("status") or "")
        if status == "passed":
            report["summary"]["targets_passed"] += 1
        elif status == "skipped":
            report["summary"]["targets_skipped"] += 1
        else:
            report["summary"]["targets_failed"] += 1

    return report


def _default_output_path() -> Path:
    return BACKEND_DIR / "reports" / "phaseC_validate_no_regression_save_view_v1.json"


def _print_summary(report: Dict[str, Any]) -> None:
    s = report.get("summary", {})
    print("\n=== Phase C Punkt 3: Save/Reload/View Regression Check ===")
    print(f"Targets total: {s.get('targets_total', 0)}")
    print(f"Targets passed: {s.get('targets_passed', 0)}")
    print(f"Targets failed: {s.get('targets_failed', 0)}")
    print(f"Targets skipped: {s.get('targets_skipped', 0)}")


async def _run(output_path: Path) -> int:
    report = await build_report()
    _print_summary(report)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nReport geschrieben: {output_path}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase C Punkt 3 validation for no Save/View regression")
    parser.add_argument("--output", default=str(_default_output_path()), help="Pfad fuer JSON-Report")
    args = parser.parse_args()
    return asyncio.run(_run(Path(args.output)))


if __name__ == "__main__":
    raise SystemExit(main())

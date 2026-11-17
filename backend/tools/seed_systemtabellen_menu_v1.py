"""
Teilt den Admin-Menuezweig "Systemtabellen bearbeiten" in JSON-Pflege und Masken-Pflege (Frames).

- Bisheriger Zweig wird zu "Systemtabellen (JSON) pflegen" und behaelt alle Eintraege mit JSON-Dialog
  (effektiver Edit-Typ edit_json/show_json).
- Neuer Zweig "Systemtabellen pflegen" (feste UID) nimmt alle Eintraege auf, deren Dialog kein JSON-Editor ist
  (z. B. pdvm_edit: Mandanten, Textvorlagen). Neue Frame-Dialoge werden danach ebenfalls hier eingehaengt.
- Idempotent; verschiebt nur `parent_guid`/`sort_order` und benennt den bisherigen Zweig um.
- Reihenfolge bei frischer Datenbank: erst seed_text_template_dialogs_v1.py, dann dieses Tool.

Aufruf aus backend/ (Standard ist Dry-Run):
  ..\\.venv\\Scripts\\python.exe tools\\seed_systemtabellen_menu_v1.py
  ..\\.venv\\Scripts\\python.exe tools\\seed_systemtabellen_menu_v1.py --apply --confirm-backup --snapshot <Pfad.json>
"""
from __future__ import annotations

import argparse
import asyncio
import copy
import json
import sys
import uuid
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.core.dialog_runtime_config import extract_dialog_runtime_config  # noqa: E402
from app.core.pdvm_datetime import now_pdvm_str  # noqa: E402
from audit_system_data import as_dict, load_env_url  # noqa: E402
from seed_base_records import connect  # noqa: E402

NS = uuid.UUID("6f1a5b0e-2a0c-4d6b-9b3e-5d1f0c7a9e11")
MENU_UID = "4cfbf1ac-c7db-4a3a-ab37-c5b457b89440"  # Admin-Administration
JSON_BRANCH_UID = "58ebd97e-d2cd-4e36-b933-6ec0a2f9dfc2"  # bisher "Systemtabellen bearbeiten"
FORM_BRANCH_UID = str(uuid.uuid5(NS, "menu:systemtabellen_pflegen"))
JSON_LABEL = "Systemtabellen (JSON) pflegen"
FORM_LABEL = "Systemtabellen pflegen"
JSON_EDIT_TYPES = {"edit_json", "show_json"}
FORM_SORT_ORDER = 45


async def run(args) -> int:
    stamp = now_pdvm_str()
    system = await connect(load_env_url(), "pdvm_system", read_only=not args.apply)
    try:
        menu = as_dict(await system.fetchval("select daten from sys_menudaten where uid = $1::uuid", MENU_UID))
        before = copy.deepcopy(menu)
        grund = menu.setdefault("GRUND", {})
        json_branch = grund.get(JSON_BRANCH_UID)
        if not json_branch:
            raise SystemExit(f"Zweig {JSON_BRANCH_UID} nicht gefunden")
        log: list[str] = []

        if json_branch.get("label") != JSON_LABEL:
            log.append(f"Zweig umbenannt: {json_branch.get('label')} -> {JSON_LABEL}")
            json_branch["label"] = JSON_LABEL
        if FORM_BRANCH_UID not in grund:
            grund[FORM_BRANCH_UID] = {
                "icon": "Database", "type": "SUBMENU", "label": FORM_LABEL, "enabled": True, "visible": True,
                "sort_order": FORM_SORT_ORDER, "parent_guid": json_branch.get("parent_guid"),
                "tooltip": "Pflege über Masken (Frames) mit Eingabeprüfung, Schreibschutz und Rollenrechten.",
            }
            log.append(f"Zweig angelegt: {FORM_LABEL}")

        children = sorted(
            ((uid, it) for uid, it in grund.items() if it.get("parent_guid") == JSON_BRANCH_UID),
            key=lambda x: (x[1].get("sort_order") or 0, str(x[1].get("label") or "")),
        )
        moved = 0
        for uid, item in children:
            params = ((item.get("command") or {}).get("params")) or {}
            dialog_guid = params.get("dialog_guid")
            if not dialog_guid:
                continue
            dialog = as_dict(await system.fetchval("select daten from sys_dialogdaten where uid = $1::uuid", dialog_guid))
            edit_type = extract_dialog_runtime_config({"root": dialog.get("ROOT") or {}, "daten": dialog}).get("edit_type")
            if str(edit_type or "").lower() in JSON_EDIT_TYPES:
                continue
            moved += 1
            item["parent_guid"] = FORM_BRANCH_UID
            item["sort_order"] = moved * 10
            log.append(f"verschoben: {item.get('label')} ({edit_type})")

        print(f"{'APPLY' if args.apply else 'Dry-Run'}: {len(log)} Aenderung(en)")
        for line in log:
            print(f"  {line}")
        if menu == before or not args.apply:
            return 0
        menu["ROOT"]["SELF_MODIFIED_AT"] = stamp
        Path(args.snapshot).write_text(json.dumps({"menu": before}, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        await system.execute(
            "update sys_menudaten set daten=$1::jsonb, modified_at=now() where uid=$2::uuid",
            json.dumps(menu, ensure_ascii=False), MENU_UID,
        )
        print(f"Snapshot: {args.snapshot}")
        return 0
    finally:
        await system.close()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--confirm-backup", action="store_true")
    ap.add_argument("--snapshot", help="Pfad fuer den Snapshot des Menues vor der Aenderung (ausserhalb des Repositorys)")
    args = ap.parse_args()
    if args.apply and not (args.confirm_backup and args.snapshot):
        raise SystemExit("--apply verlangt --confirm-backup und --snapshot")
    sys.exit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()

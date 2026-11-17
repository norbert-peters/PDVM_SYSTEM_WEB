"""
Legt den Menuepunkt "Neuer Mandant" an (Handler `go_mandant_create`, Route /mandant/new, nur Rolle `superadmin`).

- Der Eintrag erscheint im selben Zweig direkt hinter "Mandanten bearbeiten" (Dialog MANDANT_DIALOG_GUID).
- `roles: ["superadmin"]` blendet ihn fuer alle anderen Benutzer serverseitig aus (menu.py, filter_menu_group_by_roles).
- Idempotent (feste UID); aendert sonst nichts am Menue. Spezifikation: docs/specs/PDVM_MANDANT_ANLEGEN_FLOW_SPEC_V1.md.

Aufruf aus backend/ (Standard ist Dry-Run):
  ..\\.venv\\Scripts\\python.exe tools\\seed_mandant_menu_v1.py
  ..\\.venv\\Scripts\\python.exe tools\\seed_mandant_menu_v1.py --apply --confirm-backup --snapshot <Pfad.json>
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

from app.core.mandant_record_rules import MANDANT_DIALOG_GUID  # noqa: E402
from app.core.pdvm_datetime import now_pdvm_str  # noqa: E402
from audit_system_data import as_dict, load_env_url  # noqa: E402
from seed_base_records import connect  # noqa: E402

NS = uuid.UUID("6f1a5b0e-2a0c-4d6b-9b3e-5d1f0c7a9e11")
MENU_UID = "4cfbf1ac-c7db-4a3a-ab37-c5b457b89440"  # Admin-Administration
ITEM_UID = str(uuid.uuid5(NS, "menu:mandant_neu"))
ITEM_LABEL = "Neuer Mandant"
ITEM_TOOLTIP = "Legt einen neuen Mandanten mit Datenbank an (nur Superadmin)."


async def run(args) -> int:
    stamp = now_pdvm_str()
    system = await connect(load_env_url(), "pdvm_system", read_only=not args.apply)
    try:
        menu = as_dict(await system.fetchval("select daten from sys_menudaten where uid = $1::uuid", MENU_UID))
        before = copy.deepcopy(menu)
        grund = menu.setdefault("GRUND", {})

        anchor_uid, anchor = next(
            (
                (uid, item) for uid, item in grund.items()
                if isinstance(item, dict) and (((item.get("command") or {}).get("params")) or {}).get("dialog_guid") == MANDANT_DIALOG_GUID
            ),
            (None, None),
        )
        if not anchor:
            raise SystemExit(f"Eintrag 'Mandanten bearbeiten' (Dialog {MANDANT_DIALOG_GUID}) nicht im Menue {MENU_UID} gefunden")

        wanted = {
            **{k: v for k, v in anchor.items() if k in {"icon", "enabled", "visible", "parent_guid"}},
            "type": "BUTTON",
            "label": ITEM_LABEL,
            "tooltip": ITEM_TOOLTIP,
            "sort_order": int(anchor.get("sort_order") or 0) + 1,
            "command": {"handler": "go_mandant_create", "params": {}},
            "roles": ["superadmin"],
        }
        wanted.setdefault("enabled", True)
        wanted.setdefault("visible", True)

        log: list[str] = []
        current = grund.get(ITEM_UID)
        if current != wanted:
            log.append(f"Menuepunkt {'aktualisiert' if current else 'angelegt'}: {ITEM_LABEL} (hinter {anchor.get('label')})")
            grund[ITEM_UID] = wanted

        print(f"{'APPLY' if args.apply else 'Dry-Run'}: {len(log)} Aenderung(en)")
        for line in log:
            print(f"  {line}")
        if menu == before or not args.apply:
            return 0
        menu.setdefault("ROOT", {})["SELF_MODIFIED_AT"] = stamp
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

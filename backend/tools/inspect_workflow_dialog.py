from __future__ import annotations

import argparse
import asyncio
import json
from typing import Any, Dict, List

import asyncpg

from app.core.connection_manager import ConnectionManager
from app.core.dialog_service import extract_dialog_runtime_config


def as_obj(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def tab_idx(entry: Dict[str, Any]) -> int:
    import re

    key = str(entry.get("key") or "")
    m = re.search(r"(\d+)", key)
    return int(m.group(1)) if m else 999


async def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect workflow dialog config")
    parser.add_argument("--dialog-uid", required=True, help="Dialog UID")
    args = parser.parse_args()

    cfg = await ConnectionManager.get_system_config("pdvm_system")
    conn = await asyncpg.connect(cfg.to_url())
    try:
        row = await conn.fetchrow(
            "SELECT uid, name, daten FROM public.sys_dialogdaten WHERE uid = $1::uuid AND COALESCE(historisch,0)=0",
            args.dialog_uid,
        )
        if not row:
            print("NO_DIALOG")
            return 1

        data = as_obj(row["daten"])
        root = as_obj(data.get("ROOT"))

        print("UID", str(row["uid"]))
        print("NAME", row["name"])
        print("DIALOG_TYPE", root.get("DIALOG_TYPE") or root.get("dialog_type"))
        print("DRAFT_TABLE", root.get("DRAFT_TABLE") or root.get("draft_table"))
        print("DRAFT_ITEM_TABLE", root.get("DRAFT_ITEM_TABLE") or root.get("draft_item_table"))
        print("ROOT_TABS", root.get("TABS") or root.get("tabs"))

        tab_entries: List[Dict[str, Any]] = []
        for k, v in root.items():
            key = str(k)
            if not key.upper().startswith("TAB"):
                continue
            payload = as_obj(v)
            if not payload:
                continue
            tab_entries.append(
                {
                    "key": key,
                    "HEAD": payload.get("HEAD") or payload.get("head"),
                    "MODULE": payload.get("MODULE") or payload.get("module"),
                    "GUID": payload.get("GUID") or payload.get("guid"),
                    "TABLE": payload.get("TABLE") or payload.get("table"),
                    "EDIT_TYPE": payload.get("EDIT_TYPE") or payload.get("edit_type"),
                }
            )

        tab_entries.sort(key=tab_idx)
        print("ROOT_TAB_ENTRIES", tab_entries)

        runtime = extract_dialog_runtime_config({
            "uid": str(row["uid"]),
            "name": row["name"],
            "daten": data,
            "root": root,
        })
        runtime_tabs = runtime.get("tab_modules") if isinstance(runtime, dict) else []
        print("RUNTIME_TAB_MODULES", runtime_tabs)
        if isinstance(runtime_tabs, list) and runtime_tabs:
            sorted_runtime_tabs = sorted(runtime_tabs, key=lambda x: int((x or {}).get("index") or 0))
            last_runtime_module = str((sorted_runtime_tabs[-1] or {}).get("module") or "").strip().lower()
            print("RUNTIME_LAST_MODULE", last_runtime_module)
            print("RUNTIME_LAST_IS_ACTI", str(last_runtime_module == "acti").lower())

        tab_modules = data.get("TAB_MODULES") if isinstance(data, dict) else None
        if isinstance(tab_modules, list):
            print("DATA_TAB_MODULES", tab_modules)
            sorted_mods = sorted(tab_modules, key=lambda x: int((x or {}).get("index") or 0))
            last_module = str((sorted_mods[-1] or {}).get("module") or "").strip().lower() if sorted_mods else ""
            print("LAST_MODULE", last_module)
            print("LAST_IS_ACTI", str(last_module == "acti").lower())
        else:
            print("DATA_TAB_MODULES", None)

        return 0
    finally:
        await conn.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

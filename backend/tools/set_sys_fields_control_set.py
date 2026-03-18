"""Persist a canonical control set for SYS_FIELDS element list.

This script updates the sys_control_dict control row
83206c27-0eb9-4690-b4c1-7ce45761f05e (SYS_FIELDS_ELEMENTS) so
the web editor can use control-driven element metadata without
hardcoded UI fallbacks.

Usage:
  python backend/tools/set_sys_fields_control_set.py --dry-run
  python backend/tools/set_sys_fields_control_set.py --apply
"""

from __future__ import annotations

import argparse
import asyncio
import json
from typing import Any, Dict

import asyncpg

DEFAULT_DB_URL = "postgresql://postgres:Polari$55@localhost:5432/pdvm_system"
TARGET_UID = "83206c27-0eb9-4690-b4c1-7ce45761f05e"


def _as_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return {}
        try:
            parsed = json.loads(text)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def _build_control_set() -> Dict[str, Any]:
    element_template = {
        "FIELD": "",
        "TAB": 1,
        "DISPLAY_ORDER": 10,
        "TABLE": "sys_control_dict",
        "GRUPPE": "FIELDS",
    }

    element_fields = [
        {
            "name": "FIELD",
            "label": "Feld (sys_control_dict)",
            "type": "go_select_view",
            "lookupTable": "sys_control_dict",
            "SAVE_PATH": "FIELD",
            "required": True,
            "display_order": 10,
            "configs": {
                "go_select_view": {
                    "table": "sys_control_dict",
                }
            },
        },
        {
            "name": "TAB",
            "label": "Tab",
            "type": "number",
            "SAVE_PATH": "TAB",
            "required": True,
            "display_order": 20,
        },
        {
            "name": "DISPLAY_ORDER",
            "label": "Display Order",
            "type": "number",
            "SAVE_PATH": "DISPLAY_ORDER",
            "required": True,
            "display_order": 30,
        },
    ]

    return {
        "element_template": element_template,
        "element_fields": element_fields,
        # Uppercase aliases for legacy readers.
        "ELEMENT_TEMPLATE": element_template,
        "ELEMENT_FIELDS": element_fields,
    }


async def main() -> None:
    parser = argparse.ArgumentParser(description="Set SYS_FIELDS control set for element_list editor")
    parser.add_argument("--db-url", default=DEFAULT_DB_URL, help="PostgreSQL connection URL")
    parser.add_argument("--dry-run", action="store_true", help="Show planned changes only")
    parser.add_argument("--apply", action="store_true", help="Persist changes")
    args = parser.parse_args()

    apply_mode = args.apply and not args.dry_run
    conn = await asyncpg.connect(args.db_url)
    try:
        row = await conn.fetchrow(
            "SELECT uid, name, daten FROM public.sys_control_dict WHERE uid = $1::uuid AND historisch = 0",
            TARGET_UID,
        )
        if not row:
            raise RuntimeError(f"SYS_FIELDS control not found: {TARGET_UID}")

        daten = _as_dict(row["daten"])
        control = _as_dict(daten.get("CONTROL"))
        root = _as_dict(daten.get("ROOT"))

        configs_elements = _build_control_set()
        control["CONFIGS_ELEMENTS"] = configs_elements
        control["FIELDS_ELEMENTS"] = {"BY_FRAME_GUID": False}

        # Keep root/control metadata explicit and stable.
        control.setdefault("TYPE", "element_list")
        control.setdefault("FIELD", "FIELDS")
        control.setdefault("FELD", "FIELDS")
        control.setdefault("TABLE", "sys_control_dict")
        control.setdefault("LABEL", "Felder")

        root.setdefault("SELF_GUID", TARGET_UID)
        root.setdefault("SELF_NAME", "SYS_FIELDS")
        root.setdefault("TABLE", "sys_control_dict")
        root.setdefault("FIELD", "FIELDS")

        daten["ROOT"] = root
        daten["CONTROL"] = control

        print("=" * 80)
        print("SYS_FIELDS control set update")
        print("=" * 80)
        print(f"uid:  {row['uid']}")
        print(f"name: {row['name']}")
        print(f"mode: {'APPLY' if apply_mode else 'DRY-RUN'}")
        print("\nCONFIGS_ELEMENTS preview:")
        print(json.dumps(configs_elements, indent=2, ensure_ascii=False))

        if apply_mode:
            await conn.execute(
                """
                UPDATE public.sys_control_dict
                   SET daten = $1::jsonb,
                       modified_at = NOW()
                 WHERE uid = $2::uuid
                """,
                json.dumps(daten, ensure_ascii=False),
                TARGET_UID,
            )
            print("\n✅ SYS_FIELDS control set persisted")
        else:
            print("\nℹ️ Dry-run only. Use --apply to persist.")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())

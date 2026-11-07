"""\
Patch V2 theme records in pdvm_system.sys_layout to include the new header sub-blocks.

Adds (if missing) in every theme group (e.g. Orange_Light / Orange_Dark):
- block_header_mandant_std: { text_color, subtext_color }
- block_header_user_std:    { text_color, subtext_color }

Colors are derived from the group's V2 legacy color block when present:
- text_color    <- color["text-primary"]  (fallback: block_header_std.text_color)
- subtext_color <- color["text-secondary"] (fallback: text_color)

Safe-by-default:
- Only adds missing blocks (does not overwrite existing values).
- Supports --dry-run.

Run:
  python backend/patch_theme_header_blocks.py --dry-run
  python backend/patch_theme_header_blocks.py
"""

from __future__ import annotations

import argparse
import asyncio
import json
from typing import Any, Dict

import asyncpg

from app.core.pdvm_database import PdvmDatabaseService


def _is_theme_group(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    if "block_header_std" in value:
        return True
    # Fallback: V2 groups usually contain these blocks
    return any(k in value for k in ("color", "font", "block_input_std", "block_sidebar_std"))


def _derive_text_colors(group: Dict[str, Any]) -> tuple[str | None, str | None]:
    color_block = group.get("color") if isinstance(group.get("color"), dict) else {}
    primary = None
    secondary = None

    if isinstance(color_block, dict):
        primary = color_block.get("text-primary")
        secondary = color_block.get("text-secondary")

    if not primary:
        header_std = group.get("block_header_std") if isinstance(group.get("block_header_std"), dict) else {}
        primary = header_std.get("text_color")

    if not secondary:
        secondary = primary

    return primary, secondary


def _patch_group_in_place(group: Dict[str, Any]) -> bool:
    changed = False

    primary, secondary = _derive_text_colors(group)

    if "block_header_mandant_std" not in group:
        group["block_header_mandant_std"] = {
            "text_color": primary,
            "subtext_color": secondary,
        }
        changed = True

    if "block_header_user_std" not in group:
        group["block_header_user_std"] = {
            "text_color": primary,
            "subtext_color": secondary,
        }
        changed = True

    return changed


async def main() -> int:
    parser = argparse.ArgumentParser(description="Patch sys_layout themes with header sub-blocks")
    parser.add_argument("--dry-run", action="store_true", help="Do not write, only report changes")
    args = parser.parse_args()

    # sys_layout can be located in different schemas depending on migration history.
    # Try common candidates in a safe order.
    candidates = [
        "pdvm_system.sys_layout",
        "public.sys_layout",
        "sys_layout",
    ]

    db: PdvmDatabaseService | None = None
    records = None
    last_err: Exception | None = None
    for table in candidates:
        try:
            probe = PdvmDatabaseService(database="pdvm_system", table=table)
            records = await probe.list_all(historisch=0)
            db = probe
            print(f"✅ Using table: {table}")
            break
        except asyncpg.exceptions.UndefinedTableError as e:
            last_err = e
            continue

    if db is None or records is None:
        raise RuntimeError(
            "Could not find sys_layout table in pdvm_system database. "
            "Tried: " + ", ".join(candidates)
        ) from last_err

    total = 0
    changed_records = 0
    changed_groups = 0

    for record in records:
        total += 1
        uid = record.get("uid")
        daten = record.get("daten")

        if not isinstance(daten, dict):
            continue

        record_changed = False

        for key, value in list(daten.items()):
            if key == "info":
                continue
            if not _is_theme_group(value):
                continue
            if _patch_group_in_place(value):
                record_changed = True
                changed_groups += 1

        if record_changed:
            changed_records += 1
            if args.dry_run:
                print(f"🧪 DRY-RUN: would update sys_layout {uid}")
            else:
                await db.update(uid=uid, daten=daten, backup_old=True)
                print(f"✅ updated sys_layout {uid}")

    print("\n=== Patch Summary ===")
    print(f"Total active sys_layout records scanned: {total}")
    print(f"Records updated: {changed_records}")
    print(f"Theme groups patched: {changed_groups}")

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

"""Menu Editor Service

ARCHITECTURE_RULES: kein SQL im Router; DB-Zugriff via PdvmDatabase.

Aufgabe:
- sys_menudaten Datensatz laden/speichern
- Validierung: Ein Submenü (ein Item mit Kindern) darf kein command haben.

Wir interpretieren "Submenü" pragmatisch: jedes Item, das mindestens ein Kind hat
(innerhalb derselben Gruppe), darf kein command besitzen.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict

from app.core.pdvm_datenbank import PdvmDatabase


def _has_children(group_items: Dict[str, Any], uid: str) -> bool:
    for _k, item in (group_items or {}).items():
        if not isinstance(item, dict):
            continue
        if str(item.get("parent_guid") or "").strip() == str(uid):
            return True
    return False


def _strip_commands_from_parents(daten: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(daten, dict):
        raise ValueError("daten muss ein Objekt sein")

    out = {**daten}
    for group_name in ("GRUND", "VERTIKAL"):
        group = out.get(group_name)
        if not isinstance(group, dict):
            continue

        # First pass: detect parents
        parent_uids = set()
        for uid_key, _item in group.items():
            uid_str = str(uid_key)
            if _has_children(group, uid_str):
                parent_uids.add(uid_str)

        # Second pass: strip commands from parents
        if not parent_uids:
            continue

        new_group: Dict[str, Any] = {}
        for uid_key, item in group.items():
            if not isinstance(item, dict):
                new_group[uid_key] = item
                continue
            if str(uid_key) in parent_uids:
                if item.get("command") is not None:
                    item = {**item}
                    item["command"] = None
            new_group[uid_key] = item
        out[group_name] = new_group

    return out


def _normalize_types_in_group(group_items: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(group_items, dict):
        return group_items

    parent_uids = set()
    for uid_key, _item in group_items.items():
        uid_str = str(uid_key)
        if _has_children(group_items, uid_str):
            parent_uids.add(uid_str)

    if not parent_uids:
        return group_items

    out: Dict[str, Any] = {}
    for uid_key, item in group_items.items():
        if not isinstance(item, dict):
            out[uid_key] = item
            continue

        uid_str = str(uid_key)
        t = str(item.get("type") or "").strip().upper()

        # Do not force-change structural types.
        if t in {"SEPARATOR", "SPACER"}:
            out[uid_key] = item
            continue

        if uid_str in parent_uids:
            # Parent => must be SUBMENU and must not have a command.
            next_item = {**item}
            next_item["type"] = "SUBMENU"
            if next_item.get("command") is not None:
                next_item["command"] = None
            out[uid_key] = next_item
            continue

        # Childless item: if it was SUBMENU, convert back to BUTTON.
        if t == "SUBMENU":
            next_item = {**item}
            next_item["type"] = "BUTTON"
            out[uid_key] = next_item
            continue

        # Default: keep as-is
        out[uid_key] = item

    return out


def _normalize_menu_types(daten: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(daten, dict):
        raise ValueError("daten muss ein Objekt sein")

    out = {**daten}
    for group_name in ("GRUND", "VERTIKAL"):
        group = out.get(group_name)
        if not isinstance(group, dict):
            continue

        # First: ensure parents are SUBMENU and commands are stripped.
        # Second: if a SUBMENU loses its last child, convert to BUTTON.
        # We need the full group to determine parenthood.
        parent_uids = set()
        for uid_key, _item in group.items():
            uid_str = str(uid_key)
            if _has_children(group, uid_str):
                parent_uids.add(uid_str)

        new_group: Dict[str, Any] = {}
        for uid_key, item in group.items():
            if not isinstance(item, dict):
                new_group[uid_key] = item
                continue

            uid_str = str(uid_key)
            t = str(item.get("type") or "").strip().upper()

            if t in {"SEPARATOR", "SPACER"}:
                new_group[uid_key] = item
                continue

            next_item = {**item}
            if uid_str in parent_uids:
                next_item["type"] = "SUBMENU"
                if next_item.get("command") is not None:
                    next_item["command"] = None
            else:
                if t == "SUBMENU":
                    next_item["type"] = "BUTTON"
                elif not t:
                    next_item["type"] = "BUTTON"

            new_group[uid_key] = next_item

        out[group_name] = new_group

    return out


async def load_menu_record(gcs, *, menu_uuid: uuid.UUID) -> Dict[str, Any]:
    db = PdvmDatabase("sys_menudaten", system_pool=gcs._system_pool, mandant_pool=gcs._mandant_pool)
    row = await db.get_by_uid(menu_uuid)
    if not row:
        raise KeyError(f"Menü nicht gefunden: {menu_uuid}")

    return {
        "uid": str(row.get("uid")),
        "name": row.get("name") or "",
        "daten": row.get("daten") or {},
    }


async def update_menu_record(gcs, *, menu_uuid: uuid.UUID, daten: Dict[str, Any]) -> Dict[str, Any]:
    if daten is None or not isinstance(daten, dict):
        raise ValueError("daten muss ein JSON Objekt sein")

    db = PdvmDatabase("sys_menudaten", system_pool=gcs._system_pool, mandant_pool=gcs._mandant_pool)
    existing = await db.get_by_uid(menu_uuid)
    if not existing:
        raise KeyError(f"Menü nicht gefunden: {menu_uuid}")

    cleaned = _strip_commands_from_parents(daten)
    cleaned = _normalize_menu_types(cleaned)

    await db.update(
        menu_uuid,
        daten=cleaned,
        name=existing.get("name"),
        historisch=existing.get("historisch"),
    )

    return await load_menu_record(gcs, menu_uuid=menu_uuid)

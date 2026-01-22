"""Dialog Service

Architekturregel: keine SQL in Routern.
Dieses Modul kapselt Zugriff auf sys_dialogdaten / sys_framedaten und stellt
Hilfsfunktionen für den ersten Dialog-MVP bereit.

MVP (Phase 0):
- DialogDefinition laden (sys_dialogdaten)
- FrameDefinition laden (sys_framedaten)
- Dialog-View: Root-Tabelle nur mit Systemspalten uid + name
- Dialog-Edit: show_json -> liefert vollständigen Datensatz (daten JSON)
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from app.core.pdvm_datenbank import PdvmDatabase


def _get_root_table(root: Dict[str, Any]) -> str:
    table = str(root.get("TABLE") or root.get("ROOT_TABLE") or "").strip()
    return table


async def load_dialog_definition(gcs, dialog_uuid: uuid.UUID) -> Dict[str, Any]:
    db = PdvmDatabase("sys_dialogdaten", system_pool=gcs._system_pool, mandant_pool=gcs._mandant_pool)
    row = await db.get_by_uid(dialog_uuid)
    if not row:
        raise KeyError(f"Dialog nicht gefunden: {dialog_uuid}")

    daten = row.get("daten") or {}
    root = daten.get("ROOT") or {}

    return {
        "uid": str(row.get("uid")),
        "name": row.get("name") or "",
        "daten": daten,
        "root": root,
    }


async def load_frame_definition(gcs, frame_uuid: uuid.UUID) -> Dict[str, Any]:
    db = PdvmDatabase("sys_framedaten", system_pool=gcs._system_pool, mandant_pool=gcs._mandant_pool)
    row = await db.get_by_uid(frame_uuid)
    if not row:
        raise KeyError(f"Frame nicht gefunden: {frame_uuid}")

    daten = row.get("daten") or {}
    root = daten.get("ROOT") or {}

    return {
        "uid": str(row.get("uid")),
        "name": row.get("name") or "",
        "daten": daten,
        "root": root,
    }


async def load_dialog_rows_uid_name(
    gcs,
    *,
    root_table: str,
    limit: int = 200,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    if not root_table:
        return []

    db = PdvmDatabase(root_table, system_pool=gcs._system_pool, mandant_pool=gcs._mandant_pool)

    # MVP: keine Filter/Sort/Group Logik; nur Name/UID anzeigen.
    raw_rows = await db.get_all(order_by="name ASC", limit=limit, offset=offset)

    return [
        {
            "uid": str(r.get("uid")),
            "name": r.get("name") or "",
        }
        for r in raw_rows
    ]


async def load_dialog_record(gcs, *, root_table: str, record_uuid: uuid.UUID) -> Dict[str, Any]:
    if not root_table:
        raise KeyError("ROOT.TABLE ist leer")

    db = PdvmDatabase(root_table, system_pool=gcs._system_pool, mandant_pool=gcs._mandant_pool)
    row = await db.get_by_uid(record_uuid)
    if not row:
        raise KeyError(f"Datensatz nicht gefunden: {record_uuid}")

    # Einheitliches Payload für show_json
    return {
        "uid": str(row.get("uid")),
        "name": row.get("name") or "",
        "daten": row.get("daten") or {},
        "historisch": int(row.get("historisch") or 0),
        "modified_at": row.get("modified_at").isoformat() if row.get("modified_at") else None,
    }


async def update_dialog_record_json(
    gcs,
    *,
    root_table: str,
    record_uuid: uuid.UUID,
    daten: Dict[str, Any],
) -> Dict[str, Any]:
    """Aktualisiert NUR das JSONB-Feld 'daten' eines Datensatzes.

    Gedacht für edit_type='edit_json' (ähnlich PostgreSQL JSON Editor).
    """
    if not root_table:
        raise KeyError("ROOT.TABLE ist leer")

    if daten is None or not isinstance(daten, dict):
        raise ValueError("daten muss ein JSON-Objekt (dict) sein")

    db = PdvmDatabase(root_table, system_pool=gcs._system_pool, mandant_pool=gcs._mandant_pool)
    existing = await db.get_by_uid(record_uuid)
    if not existing:
        raise KeyError(f"Datensatz nicht gefunden: {record_uuid}")

    # Name/historisch bleiben unverändert.
    await db.update(
        record_uuid,
        daten=daten,
        name=existing.get("name"),
        historisch=existing.get("historisch"),
    )

    return await load_dialog_record(gcs, root_table=root_table, record_uuid=record_uuid)


def extract_dialog_runtime_config(dialog_def: Dict[str, Any]) -> Dict[str, Any]:
    """Extrahiert für die UI relevante Runtime-Konfiguration aus sys_dialogdaten.

    Primärquelle: daten.ROOT
    Zusätzlich (neu): TAB_01/TAB_02/... Blöcke (z.B. für HEAD oder tab-spezifische Optionen).
    """
    daten = dialog_def.get("daten") or {}
    root = dialog_def.get("root") or {}

    def _get_ci(d: Dict[str, Any], *keys: str) -> Any:
        """Case-insensitive Zugriff auf Dict-Keys (unterstützt auch Varianten wie EDIT_TYPE/edit_type)."""
        if not isinstance(d, dict):
            return None
        lower_map = {str(k).lower(): k for k in d.keys()}
        for key in keys:
            if key is None:
                continue
            real = lower_map.get(str(key).lower())
            if real is not None:
                return d.get(real)
        return None

    def _find_tab_block(container: Dict[str, Any], tab_index: int) -> Optional[Dict[str, Any]]:
        """Findet TAB_01/TAB_02/... Block unabhängig von Schreibweise."""
        if not isinstance(container, dict):
            return None
        for k, v in container.items():
            key = str(k)
            # Matches: TAB_02, Tab_02, tab02, TAB-02, tab2, ...
            if key and __import__("re").match(rf"^tab[_\-]?0*{tab_index}$", key, flags=__import__("re").IGNORECASE):
                return v if isinstance(v, dict) else None
        return None

    root_table = _get_root_table(root)
    view_guid_raw = _get_ci(root, "VIEW_GUID", "view_guid")
    view_guid = str(view_guid_raw).strip() if view_guid_raw else None

    edit_type_raw = _get_ci(root, "EDIT_TYPE", "edit_type")
    # Fallback: wenn EDIT_TYPE nicht in ROOT steht, unterstützen wir TAB_02.EDIT_TYPE.
    if not edit_type_raw:
        tab2 = _find_tab_block(daten, 2) or _find_tab_block(root, 2)
        edit_type_raw = _get_ci(tab2 or {}, "EDIT_TYPE", "edit_type")
    edit_type = str(edit_type_raw or "").strip() or "show_json"

    frame_guid_raw = _get_ci(root, "FRAME_GUID", "frame_guid")
    frame_guid = str(frame_guid_raw).strip() if frame_guid_raw else None

    tabs_raw = _get_ci(root, "TABS", "tabs")
    try:
        tabs = int(tabs_raw) if tabs_raw is not None else 2
    except Exception:
        tabs = 2
    if tabs < 2:
        tabs = 2

    selection_mode = str(_get_ci(root, "SELECTION_MODE", "selection_mode") or "").strip().lower() or "single"
    if selection_mode not in {"single", "multi"}:
        selection_mode = "single"

    open_edit_raw = _get_ci(root, "OPEN_EDIT", "open_edit")
    # Optional fallback: allow OPEN_EDIT in TAB_01 (view tab block)
    if not open_edit_raw:
        tab1 = _find_tab_block(daten, 1) or _find_tab_block(root, 1)
        open_edit_raw = _get_ci(tab1 or {}, "OPEN_EDIT", "open_edit")

    open_edit_mode = str(open_edit_raw or "").strip().lower() or "button"
    # Supported: button (legacy UI), double_click (double click), auto (immediate on select; reserved)
    if open_edit_mode not in {"button", "double_click", "auto"}:
        open_edit_mode = "button"

    return {
        "root_table": root_table,
        "view_guid": view_guid,
        "edit_type": edit_type,
        "frame_guid": frame_guid,
        "tabs": tabs,
        "selection_mode": selection_mode,
        "open_edit_mode": open_edit_mode,
    }

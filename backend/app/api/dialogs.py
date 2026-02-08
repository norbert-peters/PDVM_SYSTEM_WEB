"""Dialogs API

Erster MVP-Dialog:
- Dialogdefinition aus sys_dialogdaten
- 2 Tabs: View (uid+name) + Edit (show_json)

Wichtig: Keine SQL im Router. Zugriff über app.core.dialog_service.
"""

from __future__ import annotations

import uuid
import re
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.security import get_current_user
from app.core.pdvm_central_systemsteuerung import get_gcs_session
from app.core.dialog_service import (
    create_dialog_record_from_template,
    extract_dialog_runtime_config,
    load_dialog_definition,
    load_dialog_record,
    load_dialog_rows_uid_name,
    load_frame_definition,
    update_dialog_record_json,
    update_dialog_record_central,
)
from app.core.pdvm_datenbank import PdvmDatabase

router = APIRouter()

_SYS_FIELD_LAST_CALL = "LAST_CALL"
_SYS_FIELD_UI_STATE = "UI_STATE"


_TABLE_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _normalize_dialog_table(dialog_table: Optional[str]) -> Optional[str]:
    if dialog_table is None:
        return None
    t = str(dialog_table).strip()
    if not t:
        return None
    # Security: PdvmDatabase uses the table name inside f-strings.
    if not _TABLE_NAME_RE.match(t):
        raise HTTPException(status_code=400, detail="Ungültige dialog_table (nur [A-Za-z0-9_] erlaubt)")
    return t


def _ensure_allowed_edit_type(edit_type: str):
    et = str(edit_type or "").strip().lower()
    if et not in {"show_json", "edit_json", "menu", "edit_user", "import_data"}:
        raise HTTPException(
            status_code=400,
            detail="Nur EDIT_TYPE show_json, edit_json, menu, edit_user und import_data sind erlaubt",
        )


def _normalize_table_name(value: Optional[str]) -> str:
    return str(value or "").strip().lower()


def _table_key_upper(root_table: str) -> str:
    return str(root_table or "").strip().upper()


def _normalize_last_call_payload(raw: Any) -> Dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if raw is None:
        return {}
    try:
        import json

        parsed = json.loads(str(raw))
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


async def _clear_last_call_for_table(gcs, *, key: str, root_table: str) -> None:
    table_key = _table_key_upper(root_table)
    if not table_key:
        return

    gcs.systemsteuerung.set_value(key, table_key, {_SYS_FIELD_LAST_CALL: None}, gcs.stichtag)
    await gcs.systemsteuerung.save_all_values()


async def _clear_legacy_last_call_map(gcs, *, key: str) -> None:
    """Removes legacy LAST_CALL map under field LAST_CALL (old structure)."""
    try:
        raw, _ = gcs.systemsteuerung.get_value(key, _SYS_FIELD_LAST_CALL, ab_zeit=gcs.stichtag)
    except Exception:
        raw = None

    legacy = _normalize_last_call_payload(raw)
    if not legacy:
        return

    try:
        gcs.systemsteuerung.delete_field(key, _SYS_FIELD_LAST_CALL)
        await gcs.systemsteuerung.save_all_values()
    except Exception:
        pass


async def _read_last_call_scoped_by_table(
    gcs,
    *,
    key: str,
    root_table: str,
) -> Optional[str]:
    """Liest last_call aus sys_systemsteuerung.

    Datenmodell (vereinfacht):
    - Gruppe: view_guid
    - Feld: TABLE (Großbuchstaben)
    - Wert: {"LAST_CALL": <guid|null>}
    """

    table_norm = _normalize_table_name(root_table)
    if not table_norm:
        return None

    table_key = _table_key_upper(root_table)
    if not table_key:
        return None

    try:
        raw, _ = gcs.systemsteuerung.get_value(key, table_key, ab_zeit=gcs.stichtag)
    except Exception:
        return None

    if raw is None:
        return None

    payload = _normalize_last_call_payload(raw)
    if _SYS_FIELD_LAST_CALL in payload:
        value = payload.get(_SYS_FIELD_LAST_CALL)
    else:
        value = raw

    s = str(value).strip() if value is not None else ""
    if not s:
        return None

    try:
        return str(uuid.UUID(s))
    except Exception:
        return None


def _compute_last_call_key(runtime: Dict[str, Any]) -> Optional[str]:
    """Berechnet den Persistenz-Key für last_call.

    PDVM-Dialog-Regel (vereinfacht): last_call ist ausschließlich
    an view_guid + table gekoppelt. Keine frame/dialog Fallbacks.

    Returns:
        view_guid als String oder None wenn nicht vorhanden/ungültig.
    """

    view_guid = runtime.get("view_guid")
    if not view_guid:
        return None

    try:
        return str(uuid.UUID(str(view_guid)))
    except Exception:
        return None


def _compute_dialog_ui_state_group(*, dialog_guid: str, root_table: str, edit_type: str) -> str:
    """UI-State Persistenz-Key (pro User) für Dialog-spezifische UI-Zustände.

    Vorgabe: Composite-Key ("Kombi-Schlüssel") analog zum View-State, aber mit dialog_guid.
    Format: "{dialog_guid}::{table}::{edit_type}" (lower-case).
    """

    dg = str(dialog_guid or "").strip().lower()
    t = _normalize_table_name(root_table)
    et = str(edit_type or "").strip().lower()
    return f"{dg}::{t}::{et}".strip().lower()


async def _read_ui_state(gcs, *, group: str) -> Dict[str, Any]:
    try:
        raw, _ = gcs.systemsteuerung.get_value(group, _SYS_FIELD_UI_STATE, ab_zeit=gcs.stichtag)
    except Exception:
        return {}

    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw

    try:
        import json

        parsed = json.loads(str(raw))
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


class DialogUiStateResponse(BaseModel):
    group: str
    ui_state: Dict[str, Any] = Field(default_factory=dict)


class DialogUiStateUpdateRequest(BaseModel):
    ui_state: Dict[str, Any] = Field(default_factory=dict)


async def get_gcs_instance(current_user: dict = Depends(get_current_user)):
    token = current_user.get("token")
    if not token:
        raise HTTPException(status_code=401, detail="Kein Session-Token gefunden")

    gcs = get_gcs_session(token)
    if not gcs:
        raise HTTPException(status_code=404, detail="Keine GCS-Session gefunden. Bitte Mandant auswählen.")

    return gcs


class FrameDefinitionResponse(BaseModel):
    uid: str
    name: str
    daten: Dict[str, Any]
    root: Dict[str, Any]


class DialogDefinitionResponse(BaseModel):
    uid: str
    name: str
    daten: Dict[str, Any]
    root: Dict[str, Any]
    root_table: str
    view_guid: Optional[str] = None
    edit_type: str
    selection_mode: str = "single"
    open_edit_mode: str = "button"
    frame_guid: Optional[str] = None
    frame: Optional[FrameDefinitionResponse] = None
    meta: Dict[str, Any] = Field(default_factory=dict)


class DialogRowsRequest(BaseModel):
    limit: int = Field(default=200, ge=1, le=2000)
    offset: int = Field(default=0, ge=0)


class DialogRow(BaseModel):
    uid: str
    name: str


class DialogRowsResponse(BaseModel):
    dialog_guid: str
    table: str
    rows: List[DialogRow]
    meta: Dict[str, Any] = Field(default_factory=dict)


class DialogRecordResponse(BaseModel):
    uid: str
    name: str
    daten: Dict[str, Any]
    historisch: int = 0
    modified_at: Optional[str] = None


class DialogRecordUpdateRequest(BaseModel):
    daten: Dict[str, Any]


class DialogRecordCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    template_uid: Optional[str] = None
    is_template: Optional[bool] = None


class DialogLastCallResponse(BaseModel):
    key: str
    last_call: Optional[str] = None


class DialogLastCallUpdateRequest(BaseModel):
    record_uid: Optional[str] = None


@router.get("/{dialog_guid}", response_model=DialogDefinitionResponse)
async def get_dialog_definition(dialog_guid: str, dialog_table: Optional[str] = None, gcs=Depends(get_gcs_instance)):
    try:
        dialog_uuid = uuid.UUID(dialog_guid)
    except Exception:
        raise HTTPException(status_code=400, detail="Ungültige dialog_guid")

    try:
        dialog_def = await load_dialog_definition(gcs, dialog_uuid)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Dialog nicht gefunden: {dialog_guid}")

    runtime = extract_dialog_runtime_config(dialog_def)

    dialog_table_norm = _normalize_dialog_table(dialog_table)
    if dialog_table_norm:
        # Override mode: menu can point to any table.
        # Only JSON editor modes are permitted.
        _ensure_allowed_edit_type(runtime.get("edit_type") or "show_json")
        runtime["root_table"] = dialog_table_norm

    frame_payload = None
    frame_guid = runtime.get("frame_guid")
    if frame_guid:
        try:
            frame_uuid = uuid.UUID(frame_guid)
            frame_payload = await load_frame_definition(gcs, frame_uuid)
        except Exception:
            # Frame ist optional; Dialog soll trotzdem rendern.
            frame_payload = None

    # last_call aus sys_systemsteuerung (pro User): group = view_guid
    # table-scoped: TABLE + LAST_CALL (Objekt: {"LAST_CALL": <uid|null>})
    last_call_key = _compute_last_call_key(runtime)
    root_table = runtime.get("root_table") or ""
    last_call_str = None
    if last_call_key:
        table_key = _table_key_upper(root_table)
        if table_key:
            try:
                existing_raw, _ = gcs.systemsteuerung.get_value(last_call_key, table_key, ab_zeit=gcs.stichtag)
            except Exception:
                existing_raw = None

            # Wenn Feld fehlt → initialisieren mit LAST_CALL = None
            if existing_raw is None:
                gcs.systemsteuerung.set_value(last_call_key, table_key, {_SYS_FIELD_LAST_CALL: None}, gcs.stichtag)
                await gcs.systemsteuerung.save_all_values()
                last_call_str = None
            else:
                payload = _normalize_last_call_payload(existing_raw)
                value = payload.get(_SYS_FIELD_LAST_CALL) if _SYS_FIELD_LAST_CALL in payload else None
                last_call_str = str(value).strip() if value is not None else None

    return {
        **dialog_def,
        "root_table": runtime.get("root_table") or "",
        "view_guid": runtime.get("view_guid"),
        "edit_type": runtime.get("edit_type") or "show_json",
        "selection_mode": runtime.get("selection_mode") or "single",
        "open_edit_mode": runtime.get("open_edit_mode") or "button",
        "frame_guid": frame_guid,
        "frame": frame_payload,
        "meta": {
            "tabs": runtime.get("tabs", 2),
            "dialog_table": dialog_table_norm,
            "last_call": last_call_str,
            "last_call_key": f"{last_call_key}::{_table_key_upper(root_table)}" if last_call_key and root_table else last_call_key,
        },
    }


@router.get("/{dialog_guid}/last-call", response_model=DialogLastCallResponse)
async def get_dialog_last_call(dialog_guid: str, dialog_table: Optional[str] = None, gcs=Depends(get_gcs_instance)):
    try:
        dialog_uuid = uuid.UUID(dialog_guid)
    except Exception:
        raise HTTPException(status_code=400, detail="Ungültige dialog_guid")

    try:
        dialog_def = await load_dialog_definition(gcs, dialog_uuid)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Dialog nicht gefunden: {dialog_guid}")

    runtime = extract_dialog_runtime_config(dialog_def)

    dialog_table_norm = _normalize_dialog_table(dialog_table)
    if dialog_table_norm:
        _ensure_allowed_edit_type(runtime.get("edit_type") or "show_json")
        runtime["root_table"] = dialog_table_norm

    key = _compute_last_call_key(runtime)
    root_table = runtime.get("root_table") or ""
    if not key:
        return {"key": "", "last_call": None}

    last_call = await _read_last_call_scoped_by_table(gcs, key=key, root_table=root_table)

    return {"key": key, "last_call": last_call}


@router.put("/{dialog_guid}/last-call", response_model=DialogLastCallResponse)
async def put_dialog_last_call(
    dialog_guid: str,
    payload: DialogLastCallUpdateRequest,
    dialog_table: Optional[str] = None,
    gcs=Depends(get_gcs_instance),
):
    try:
        dialog_uuid = uuid.UUID(dialog_guid)
    except Exception:
        raise HTTPException(status_code=400, detail="Ungültige dialog_guid")

    try:
        dialog_def = await load_dialog_definition(gcs, dialog_uuid)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Dialog nicht gefunden: {dialog_guid}")

    runtime = extract_dialog_runtime_config(dialog_def)

    dialog_table_norm = _normalize_dialog_table(dialog_table)
    if dialog_table_norm:
        _ensure_allowed_edit_type(runtime.get("edit_type") or "show_json")
        runtime["root_table"] = dialog_table_norm

    key = _compute_last_call_key(runtime)
    if not key:
        raise HTTPException(status_code=400, detail="VIEW_GUID fehlt - last_call kann nicht gesetzt werden")

    record_uid = payload.record_uid
    if record_uid is not None:
        s = str(record_uid).strip()
        if s == "":
            record_uid = None
        else:
            try:
                uuid.UUID(s)
            except Exception:
                raise HTTPException(status_code=400, detail="Ungültige record_uid")
            record_uid = s

    root_table = runtime.get("root_table") or ""
    table_key = _table_key_upper(root_table)
    if not table_key:
        raise HTTPException(status_code=400, detail="ROOT.TABLE ist leer")

    # Persist per view_guid + table (payload contains LAST_CALL only).
    payload = {_SYS_FIELD_LAST_CALL: record_uid if record_uid is not None else None}
    gcs.systemsteuerung.set_value(key, table_key, payload, gcs.stichtag)
    await gcs.systemsteuerung.save_all_values()

    return {"key": key, "last_call": record_uid}


@router.post("/{dialog_guid}/rows", response_model=DialogRowsResponse)
async def post_dialog_rows(dialog_guid: str, payload: DialogRowsRequest, dialog_table: Optional[str] = None, gcs=Depends(get_gcs_instance)):
    try:
        dialog_uuid = uuid.UUID(dialog_guid)
    except Exception:
        raise HTTPException(status_code=400, detail="Ungültige dialog_guid")

    try:
        dialog_def = await load_dialog_definition(gcs, dialog_uuid)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Dialog nicht gefunden: {dialog_guid}")

    runtime = extract_dialog_runtime_config(dialog_def)
    dialog_table_norm = _normalize_dialog_table(dialog_table)
    if dialog_table_norm:
        _ensure_allowed_edit_type(runtime.get("edit_type") or "show_json")
        runtime["root_table"] = dialog_table_norm

    table = runtime.get("root_table") or ""
    if not table:
        raise HTTPException(status_code=400, detail="Dialog ROOT.TABLE ist leer")

    rows = await load_dialog_rows_uid_name(gcs, root_table=table, limit=payload.limit, offset=payload.offset)
    return {
        "dialog_guid": dialog_guid,
        "table": table,
        "rows": rows,
        "meta": {"limit": payload.limit, "offset": payload.offset},
    }


@router.get("/{dialog_guid}/record/{record_uid}", response_model=DialogRecordResponse)
async def get_dialog_record(dialog_guid: str, record_uid: str, dialog_table: Optional[str] = None, gcs=Depends(get_gcs_instance)):
    try:
        dialog_uuid = uuid.UUID(dialog_guid)
    except Exception:
        raise HTTPException(status_code=400, detail="Ungültige dialog_guid")

    try:
        record_uuid = uuid.UUID(record_uid)
    except Exception:
        raise HTTPException(status_code=400, detail="Ungültige record uid")

    try:
        dialog_def = await load_dialog_definition(gcs, dialog_uuid)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Dialog nicht gefunden: {dialog_guid}")

    runtime = extract_dialog_runtime_config(dialog_def)
    dialog_table_norm = _normalize_dialog_table(dialog_table)
    if dialog_table_norm:
        _ensure_allowed_edit_type(runtime.get("edit_type") or "show_json")
        runtime["root_table"] = dialog_table_norm

    table = runtime.get("root_table") or ""
    if not table:
        raise HTTPException(status_code=400, detail="Dialog ROOT.TABLE ist leer")

    try:
        return await load_dialog_record(gcs, root_table=table, record_uuid=record_uuid)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Datensatz nicht gefunden: {record_uid}")


@router.put("/{dialog_guid}/record/{record_uid}", response_model=DialogRecordResponse)
async def put_dialog_record(
    dialog_guid: str,
    record_uid: str,
    payload: DialogRecordUpdateRequest,
    dialog_table: Optional[str] = None,
    gcs=Depends(get_gcs_instance),
):
    """Aktualisiert einen Datensatz.

    Unterstützt:
    - EDIT_TYPE=edit_json (JSON Editor)
    - EDIT_TYPE=edit_user (PIC über PdvmCentralDatabase)
    """
    try:
        dialog_uuid = uuid.UUID(dialog_guid)
    except Exception:
        raise HTTPException(status_code=400, detail="Ungültige dialog_guid")

    try:
        record_uuid = uuid.UUID(record_uid)
    except Exception:
        raise HTTPException(status_code=400, detail="Ungültige record uid")

    try:
        dialog_def = await load_dialog_definition(gcs, dialog_uuid)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Dialog nicht gefunden: {dialog_guid}")

    runtime = extract_dialog_runtime_config(dialog_def)
    dialog_table_norm = _normalize_dialog_table(dialog_table)
    if dialog_table_norm:
        _ensure_allowed_edit_type(runtime.get("edit_type") or "show_json")
        runtime["root_table"] = dialog_table_norm
        runtime["view_guid"] = None

    table = runtime.get("root_table") or ""
    if not table:
        raise HTTPException(status_code=400, detail="Dialog ROOT.TABLE ist leer")

    edit_type = str(runtime.get("edit_type") or "show_json").strip().lower()
    if edit_type not in {"edit_json", "edit_user", "import_data"}:
        raise HTTPException(status_code=400, detail="Dialog ist nicht für edit_json, edit_user oder import_data konfiguriert")

    try:
        if edit_type == "edit_user":
            return await update_dialog_record_central(gcs, root_table=table, record_uuid=record_uuid, daten=payload.daten)
        return await update_dialog_record_json(gcs, root_table=table, record_uuid=record_uuid, daten=payload.daten)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Datensatz nicht gefunden: {record_uid}")


@router.post("/{dialog_guid}/record", response_model=DialogRecordResponse)
async def post_dialog_record_create(
    dialog_guid: str,
    payload: DialogRecordCreateRequest,
    dialog_table: Optional[str] = None,
    gcs=Depends(get_gcs_instance),
):
    """Erstellt einen neuen Datensatz anhand eines Template-Records (Default: 6666...)."""
    try:
        dialog_uuid = uuid.UUID(dialog_guid)
    except Exception:
        raise HTTPException(status_code=400, detail="Ungültige dialog_guid")

    try:
        dialog_def = await load_dialog_definition(gcs, dialog_uuid)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Dialog nicht gefunden: {dialog_guid}")

    runtime = extract_dialog_runtime_config(dialog_def)
    dialog_table_norm = _normalize_dialog_table(dialog_table)
    if dialog_table_norm:
        _ensure_allowed_edit_type(runtime.get("edit_type") or "show_json")
        runtime["root_table"] = dialog_table_norm
        runtime["view_guid"] = None

    table = runtime.get("root_table") or ""
    if not table:
        raise HTTPException(status_code=400, detail="Dialog ROOT.TABLE ist leer")

    name = str(payload.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name ist leer")

    template_uuid = None
    if payload.template_uid is not None:
        s = str(payload.template_uid).strip()
        if s:
            try:
                template_uuid = uuid.UUID(s)
            except Exception:
                raise HTTPException(status_code=400, detail="Ungültige template_uid")

    try:
        root_patch = None
        if str(table).strip().lower() == "sys_menudaten" and payload.is_template is not None:
            root_patch = {"is_template": bool(payload.is_template)}

        if template_uuid is None:
            return await create_dialog_record_from_template(gcs, root_table=table, name=name, root_patch=root_patch)
        return await create_dialog_record_from_template(
            gcs, root_table=table, name=name, template_uuid=template_uuid, root_patch=root_patch
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{dialog_guid}/ui-state", response_model=DialogUiStateResponse)
async def get_dialog_ui_state(dialog_guid: str, dialog_table: Optional[str] = None, gcs=Depends(get_gcs_instance)):
    try:
        dialog_uuid = uuid.UUID(dialog_guid)
    except Exception:
        raise HTTPException(status_code=400, detail="Ungültige dialog_guid")

    try:
        dialog_def = await load_dialog_definition(gcs, dialog_uuid)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Dialog nicht gefunden: {dialog_guid}")

    runtime = extract_dialog_runtime_config(dialog_def)
    dialog_table_norm = _normalize_dialog_table(dialog_table)
    if dialog_table_norm:
        _ensure_allowed_edit_type(runtime.get("edit_type") or "show_json")
        runtime["root_table"] = dialog_table_norm

    table = runtime.get("root_table") or ""
    if not table:
        raise HTTPException(status_code=400, detail="Dialog ROOT.TABLE ist leer")

    edit_type = str(runtime.get("edit_type") or "show_json").strip().lower()
    group = _compute_dialog_ui_state_group(dialog_guid=dialog_guid, root_table=table, edit_type=edit_type)
    ui_state = await _read_ui_state(gcs, group=group)
    return {"group": group, "ui_state": ui_state}


@router.put("/{dialog_guid}/ui-state", response_model=DialogUiStateResponse)
async def put_dialog_ui_state(
    dialog_guid: str,
    payload: DialogUiStateUpdateRequest,
    dialog_table: Optional[str] = None,
    gcs=Depends(get_gcs_instance),
):
    try:
        dialog_uuid = uuid.UUID(dialog_guid)
    except Exception:
        raise HTTPException(status_code=400, detail="Ungültige dialog_guid")

    try:
        dialog_def = await load_dialog_definition(gcs, dialog_uuid)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Dialog nicht gefunden: {dialog_guid}")

    runtime = extract_dialog_runtime_config(dialog_def)
    dialog_table_norm = _normalize_dialog_table(dialog_table)
    if dialog_table_norm:
        _ensure_allowed_edit_type(runtime.get("edit_type") or "show_json")
        runtime["root_table"] = dialog_table_norm

    table = runtime.get("root_table") or ""
    if not table:
        raise HTTPException(status_code=400, detail="Dialog ROOT.TABLE ist leer")

    edit_type = str(runtime.get("edit_type") or "show_json").strip().lower()
    group = _compute_dialog_ui_state_group(dialog_guid=dialog_guid, root_table=table, edit_type=edit_type)

    existing = await _read_ui_state(gcs, group=group)
    next_state = dict(existing)
    incoming = payload.ui_state if isinstance(payload.ui_state, dict) else {}
    next_state.update(incoming)

    gcs.systemsteuerung.set_value(group, _SYS_FIELD_UI_STATE, next_state, gcs.stichtag)
    await gcs.systemsteuerung.save_all_values()
    return {"group": group, "ui_state": next_state}

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
    extract_dialog_runtime_config,
    load_dialog_definition,
    load_dialog_record,
    load_dialog_rows_uid_name,
    load_frame_definition,
    update_dialog_record_json,
)

router = APIRouter()

_SYS_FIELD_LAST_CALL = "LAST_CALL"


_TABLE_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _normalize_dialog_table(dialog_table: Optional[str]) -> Optional[str]:
    if dialog_table is None:
        return None
    t = str(dialog_table).strip()
    if not t:
        return None
    # Security: PdvmDatabase uses the table name inside f-strings.
    # We must strictly validate to prevent SQL injection.
    if not _TABLE_NAME_RE.match(t):
        raise HTTPException(status_code=400, detail="Ungültige dialog_table (nur [A-Za-z0-9_] erlaubt)")
    return t


def _ensure_allowed_edit_type(edit_type: str):
    et = str(edit_type or "").strip().lower()
    if et not in {"show_json", "edit_json"}:
        raise HTTPException(status_code=400, detail="Nur EDIT_TYPE show_json und edit_json sind erlaubt")


def _normalize_table_name(value: Optional[str]) -> str:
    return str(value or "").strip().lower()


def _table_key_upper(root_table: str) -> str:
    return str(root_table or "").strip().upper()


async def _read_last_call_scoped_by_table(
    gcs,
    *,
    key: str,
    root_table: str,
) -> Optional[str]:
    """Liest last_call aus sys_systemsteuerung.

    Datenmodell (gewünscht):
    - Gruppe: frame_guid (oder fallback view_guid/dialog_guid)
    - Feld: LAST_CALL (Großbuchstaben)
    - Wert: Dict/JSON-Objekt, Key = TABLE (Großbuchstaben), Value = GUID

    Beispiel:
    LAST_CALL = {"SYS_VIEWDATEN": "...", "SYS_FRAMDATEN": "..."}
    """

    table_norm = _normalize_table_name(root_table)
    if not table_norm:
        return None

    table_key = _table_key_upper(root_table)
    if not table_key:
        return None

    try:
        raw, _ = gcs.systemsteuerung.get_value(key, _SYS_FIELD_LAST_CALL, ab_zeit=gcs.stichtag)
    except Exception:
        return None

    if raw is None:
        return None

    mapping: Dict[str, Any]
    if isinstance(raw, dict):
        mapping = raw
    else:
        # In early testing it might be persisted as a JSON-string; be tolerant.
        try:
            import json

            parsed = json.loads(str(raw))
            mapping = parsed if isinstance(parsed, dict) else {}
        except Exception:
            mapping = {}

    value = mapping.get(table_key)
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None

    try:
        return str(uuid.UUID(s))
    except Exception:
        return None


def _compute_last_call_key(runtime: Dict[str, Any], dialog_guid: str) -> str:
    """Berechnet den Persistenz-Key für last_call.

    Vorgabe (PDVM Dialog Spec): Die letzte selektierte GUID wird pro User in der
    Systemsteuerung unter der *frame_guid* abgelegt.

    Priorität:
    1) frame_guid
    2) view_guid (legacy / Fallback, wenn kein Frame vorhanden)
    3) dialog_guid (letzter Fallback)
    """

    frame_guid = runtime.get("frame_guid")
    if frame_guid:
        try:
            return str(uuid.UUID(str(frame_guid)))
        except Exception:
            pass

    view_guid = runtime.get("view_guid")
    if view_guid:
        try:
            return str(uuid.UUID(str(view_guid)))
        except Exception:
            pass

    return str(dialog_guid)


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

    # last_call aus sys_systemsteuerung (pro User): group = frame_guid (wenn vorhanden), sonst view_guid, sonst dialog_guid
    # zusätzlich table-scoped: TABELLE + LAST_CALL
    last_call_key = _compute_last_call_key(runtime, dialog_guid)
    last_call_str = await _read_last_call_scoped_by_table(gcs, key=last_call_key, root_table=runtime.get("root_table") or "")

    return {
        **dialog_def,
        "root_table": runtime.get("root_table") or "",
        "view_guid": runtime.get("view_guid"),
        "edit_type": runtime.get("edit_type") or "show_json",
        "selection_mode": runtime.get("selection_mode") or "single",
        "open_edit_mode": runtime.get("open_edit_mode") or "button",
        "frame_guid": frame_guid,
        "frame": frame_payload,
        "meta": {"tabs": runtime.get("tabs", 2), "dialog_table": dialog_table_norm, "last_call": last_call_str, "last_call_key": last_call_key},
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

    key = _compute_last_call_key(runtime, dialog_guid)

    last_call = await _read_last_call_scoped_by_table(gcs, key=key, root_table=runtime.get("root_table") or "")

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

    key = _compute_last_call_key(runtime, dialog_guid)

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

    # Read-modify-write the LAST_CALL map.
    try:
        existing_raw, _ = gcs.systemsteuerung.get_value(key, _SYS_FIELD_LAST_CALL, ab_zeit=gcs.stichtag)
    except Exception:
        existing_raw = None

    existing_map: Dict[str, Any] = existing_raw if isinstance(existing_raw, dict) else {}
    next_map = dict(existing_map)

    if record_uid is None:
        next_map.pop(table_key, None)
    else:
        next_map[table_key] = record_uid

    gcs.systemsteuerung.set_value(key, _SYS_FIELD_LAST_CALL, next_map, gcs.stichtag)
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
    """Aktualisiert das JSONB-Feld 'daten' eines Datensatzes.

    Aktiv, wenn der Dialog mit EDIT_TYPE='edit_json' konfiguriert ist.
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
    if edit_type != "edit_json":
        raise HTTPException(status_code=400, detail="Dialog ist nicht für edit_json konfiguriert")

    try:
        return await update_dialog_record_json(gcs, root_table=table, record_uuid=record_uuid, daten=payload.daten)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Datensatz nicht gefunden: {record_uid}")

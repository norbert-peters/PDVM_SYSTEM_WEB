"""Views API

Phase 0:
- GET ViewDefinition aus sys_viewdaten
- GET Base-Rohdaten aus ROOT.TABLE

Wichtig: Keine SQL im Router. Zugriff über app.core.view_service.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.core.security import get_current_user
from app.core.pdvm_central_systemsteuerung import get_gcs_session
from app.core.view_service import load_view_definition, load_view_base_rows
from app.core.view_state_service import (
    extract_controls_origin,
    merge_controls,
    normalize_controls_source,
    effective_controls_as_list,
)
from app.core.view_table_state_service import merge_table_state, normalize_table_state_source
from app.core.view_matrix_service import build_view_matrix

router = APIRouter()


async def get_gcs_instance(current_user: dict = Depends(get_current_user)):
    token = current_user.get("token")
    if not token:
        raise HTTPException(status_code=401, detail="Kein Session-Token gefunden")

    gcs = get_gcs_session(token)
    if not gcs:
        raise HTTPException(status_code=404, detail="Keine GCS-Session gefunden. Bitte Mandant auswählen.")

    return gcs


class ViewDefinitionResponse(BaseModel):
    uid: str
    name: str
    daten: Dict[str, Any]
    root: Dict[str, Any]


class ViewBaseRow(BaseModel):
    uid: str
    name: str
    daten: Dict[str, Any]
    historisch: int = 0
    modified_at: Optional[str] = None


class ViewBaseResponse(BaseModel):
    view_guid: str
    table: str
    rows: List[ViewBaseRow]


class ViewStateResponse(BaseModel):
    view_guid: str
    controls_source: Dict[str, Any]
    controls_effective: List[Dict[str, Any]]
    table_state_source: Dict[str, Any]
    table_state_effective: Dict[str, Any]
    meta: Dict[str, Any]


class ViewStateUpdateRequest(BaseModel):
    # controls_source: Mapping control_guid -> {show, display_order, width, ...}
    controls_source: Optional[Dict[str, Any]] = None
    table_state_source: Optional[Dict[str, Any]] = None


class ViewMatrixRequest(BaseModel):
    controls_source: Optional[Dict[str, Any]] = None
    table_state_source: Optional[Dict[str, Any]] = None
    include_historisch: bool = True
    limit: int = 200
    offset: int = 0


class ViewMatrixResponse(BaseModel):
    view_guid: str
    table: str
    stichtag: float
    controls_source: Dict[str, Any]
    controls_effective: List[Dict[str, Any]]
    table_state_source: Dict[str, Any]
    table_state_effective: Dict[str, Any]
    rows: List[Dict[str, Any]]
    totals: Optional[Dict[str, Any]] = None
    dropdowns: Optional[Dict[str, Any]] = None
    meta: Dict[str, Any]


@router.get("/{view_guid}", response_model=ViewDefinitionResponse)
async def get_view_definition(view_guid: str, gcs=Depends(get_gcs_instance)):
    try:
        view_uuid = uuid.UUID(view_guid)
    except Exception:
        raise HTTPException(status_code=400, detail="Ungültige view_guid")

    try:
        result = await load_view_definition(gcs, view_uuid)
        return result
    except KeyError:
        raise HTTPException(status_code=404, detail=f"View nicht gefunden: {view_guid}")


@router.get("/{view_guid}/base", response_model=ViewBaseResponse)
async def get_view_base(
    view_guid: str,
    limit: int = Query(default=200, ge=1, le=2000),
    include_historisch: bool = Query(default=True),
    gcs=Depends(get_gcs_instance),
):
    try:
        view_uuid = uuid.UUID(view_guid)
    except Exception:
        raise HTTPException(status_code=400, detail="Ungültige view_guid")

    try:
        definition = await load_view_definition(gcs, view_uuid)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"View nicht gefunden: {view_guid}")

    table = str((definition.get("root") or {}).get("TABLE") or "").strip()
    if not table:
        raise HTTPException(status_code=400, detail="View ROOT.TABLE ist leer")

    # Stichtag-Projektion nur für Felder, die die View wirklich nutzt (Controls aus sys_viewdaten)
    origin = extract_controls_origin(definition.get("daten") or {})
    control_fields = []
    try:
        for c in origin.values():
            gruppe = str((c or {}).get("gruppe") or "").strip()
            feld = str((c or {}).get("feld") or "").strip()
            if gruppe and feld:
                control_fields.append((gruppe, feld))
    except Exception:
        control_fields = []

    rows = await load_view_base_rows(
        gcs,
        table_name=table,
        limit=limit,
        include_historisch=include_historisch,
        control_fields=control_fields,
    )

    return {
        "view_guid": view_guid,
        "table": table,
        "rows": rows,
    }


@router.get("/{view_guid}/state", response_model=ViewStateResponse)
async def get_view_state(view_guid: str, gcs=Depends(get_gcs_instance)):
    try:
        view_uuid = uuid.UUID(view_guid)
    except Exception:
        raise HTTPException(status_code=400, detail="Ungültige view_guid")

    try:
        definition = await load_view_definition(gcs, view_uuid)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"View nicht gefunden: {view_guid}")

    origin = extract_controls_origin(definition.get("daten") or {})
    source = gcs.get_view_controls(view_guid) or {}
    if not isinstance(source, dict):
        source = {}

    table_state_src = gcs.get_view_table_state(view_guid) or {}
    if not isinstance(table_state_src, dict):
        table_state_src = {}

    effective, meta = merge_controls(origin=origin, source=source) 
    normalized_source = normalize_controls_source(source=source, effective=effective)

    table_state_effective, table_state_meta = merge_table_state(table_state_src)
    table_state_normalized = normalize_table_state_source(table_state_effective)
    meta["table_state"] = table_state_meta

    return {
        "view_guid": view_guid,
        "controls_source": normalized_source,
        "controls_effective": effective_controls_as_list(effective),
        "table_state_source": table_state_normalized,
        "table_state_effective": table_state_effective,
        "meta": meta,
    }


@router.put("/{view_guid}/state", response_model=ViewStateResponse)
async def put_view_state(view_guid: str, request: ViewStateUpdateRequest, gcs=Depends(get_gcs_instance)):
    try:
        view_uuid = uuid.UUID(view_guid)
    except Exception:
        raise HTTPException(status_code=400, detail="Ungültige view_guid")

    try:
        definition = await load_view_definition(gcs, view_uuid)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"View nicht gefunden: {view_guid}")

    origin = extract_controls_origin(definition.get("daten") or {})

    # Backward compatible: wenn controls_source nicht gesendet wird, behalten wir den bestehenden Wert.
    source = request.controls_source
    if source is None:
        source = gcs.get_view_controls(view_guid) or {}
    if not isinstance(source, dict):
        raise HTTPException(status_code=400, detail="controls_source muss ein Dict sein")

    table_state_src = request.table_state_source
    if table_state_src is None:
        table_state_src = gcs.get_view_table_state(view_guid) or {}
    if not isinstance(table_state_src, dict):
        raise HTTPException(status_code=400, detail="table_state_source muss ein Dict sein")

    effective, meta = merge_controls(origin=origin, source=source)
    normalized_source = normalize_controls_source(source=source, effective=effective)

    table_state_effective, table_state_meta = merge_table_state(table_state_src)
    table_state_normalized = normalize_table_state_source(table_state_effective)
    meta["table_state"] = table_state_meta

    # Persistenz ausschließlich in sys_systemsteuerung
    gcs.set_view_controls(view_guid, normalized_source)
    gcs.set_view_table_state(view_guid, table_state_normalized)
    await gcs.save_all_values()

    return {
        "view_guid": view_guid,
        "controls_source": normalized_source,
        "controls_effective": effective_controls_as_list(effective),
        "table_state_source": table_state_normalized,
        "table_state_effective": table_state_effective,
        "meta": meta,
    }


@router.post("/{view_guid}/matrix", response_model=ViewMatrixResponse)
async def post_view_matrix(view_guid: str, request: ViewMatrixRequest, gcs=Depends(get_gcs_instance)):
    try:
        result = await build_view_matrix(
            gcs,
            view_guid,
            controls_source=request.controls_source,
            table_state_source=request.table_state_source,
            include_historisch=bool(request.include_historisch),
            limit=int(request.limit),
            offset=int(request.offset),
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except KeyError:
        raise HTTPException(status_code=404, detail=f"View nicht gefunden: {view_guid}")

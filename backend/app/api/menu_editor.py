"""Menu Editor API

Ermöglicht Laden/Speichern eines sys_menudaten Datensatzes für den Web-Menüeditor.
ARCHITECTURE_RULES: kein SQL im Router.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.security import get_current_user
from app.core.pdvm_central_systemsteuerung import get_gcs_session
from app.core.menu_editor_service import load_menu_record, update_menu_record

router = APIRouter()


async def get_gcs_instance(current_user: dict = Depends(get_current_user)):
    token = current_user.get("token")
    if not token:
        raise HTTPException(status_code=401, detail="Kein Session-Token gefunden")

    gcs = get_gcs_session(token)
    if not gcs:
        raise HTTPException(status_code=404, detail="Keine GCS-Session gefunden. Bitte Mandant auswählen.")

    return gcs


class MenuRecordResponse(BaseModel):
    uid: str
    name: str
    daten: Dict[str, Any]


class MenuRecordUpdateRequest(BaseModel):
    daten: Dict[str, Any]


@router.get("/{menu_guid}", response_model=MenuRecordResponse)
async def get_menu(menu_guid: str, gcs=Depends(get_gcs_instance)):
    try:
        menu_uuid = uuid.UUID(menu_guid)
    except Exception:
        raise HTTPException(status_code=400, detail="Ungültige menu_guid")

    try:
        return await load_menu_record(gcs, menu_uuid=menu_uuid)
    except KeyError:
        raise HTTPException(status_code=404, detail="Menü nicht gefunden")


@router.put("/{menu_guid}", response_model=MenuRecordResponse)
async def put_menu(menu_guid: str, payload: MenuRecordUpdateRequest, gcs=Depends(get_gcs_instance)):
    try:
        menu_uuid = uuid.UUID(menu_guid)
    except Exception:
        raise HTTPException(status_code=400, detail="Ungültige menu_guid")

    try:
        return await update_menu_record(gcs, menu_uuid=menu_uuid, daten=payload.daten)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except KeyError:
        raise HTTPException(status_code=404, detail="Menü nicht gefunden")

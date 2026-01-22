"""Systemdaten API

Stellt systemweite Kataloge bereit, z.B. für den Menüeditor.
ARCHITECTURE_RULES: kein SQL im Router.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException

from app.core.security import get_current_user
from app.core.pdvm_central_systemsteuerung import get_gcs_session
from app.core.systemdaten_service import load_menu_command_catalog

router = APIRouter()


async def get_gcs_instance(current_user: dict = Depends(get_current_user)):
    token = current_user.get("token")
    if not token:
        raise HTTPException(status_code=401, detail="Kein Session-Token gefunden")

    gcs = get_gcs_session(token)
    if not gcs:
        raise HTTPException(status_code=404, detail="Keine GCS-Session gefunden. Bitte Mandant auswählen.")

    return gcs


@router.get("/menu-commands")
async def get_menu_commands(
    language: Optional[str] = None,
    dataset_uid: Optional[str] = None,
    gcs=Depends(get_gcs_instance),
) -> Dict[str, Any]:
    return await load_menu_command_catalog(gcs, language=language, dataset_uid=dataset_uid)

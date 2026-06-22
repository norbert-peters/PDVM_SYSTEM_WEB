"""Systemdaten API

Stellt systemweite Kataloge bereit, z.B. für den Menüeditor.
ARCHITECTURE_RULES: kein SQL im Router.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Depends, HTTPException

from app.core.security import get_current_user
from app.core.pdvm_central_systemsteuerung import get_gcs_session
from app.core.systemdaten_service import load_menu_command_catalog, load_systemdaten_text, load_menu_param_configs
from app.core.dropdown_service import get_dropdown_mapping_for_field, resolve_dropdown_by_config

router = APIRouter()


async def get_gcs_instance(current_user: dict = Depends(get_current_user)):
    token = current_user.get("token")
    if not token:
        raise HTTPException(status_code=401, detail="Kein Session-Token gefunden")

    gcs = get_gcs_session(token)
    if not gcs:
        raise HTTPException(status_code=404, detail="Keine GCS-Session gefunden. Bitte Mandant auswählen.")

    if hasattr(gcs, "set_request_context"):
        gcs.set_request_context(actor_ip=current_user.get("client_ip"))

    return gcs


@router.get("/menu-commands")
async def get_menu_commands(
    language: Optional[str] = None,
    dataset_uid: Optional[str] = None,
    gcs=Depends(get_gcs_instance),
) -> Dict[str, Any]:
    try:
        target_uid = dataset_uid or "00000000-0000-0000-0000-000000000000"
        return await load_menu_command_catalog(gcs, language=language, dataset_uid=target_uid)
    except Exception:
        # Wenn asy_systemdaten fehlt oder nicht verfuegbar ist, liefere leeren Katalog.
        return {"commands": [], "language": language or "", "default_language": ""}


@router.get("/text")
async def get_systemdaten_text(
    dataset_uid: str,
    entry_key: str,
    group: Optional[str] = None,
    language: Optional[str] = None,
    gcs=Depends(get_gcs_instance),
) -> Dict[str, Any]:
    try:
        return await load_systemdaten_text(
            gcs,
            dataset_uid=dataset_uid,
            entry_key=entry_key,
            group=group,
            language=language,
        )
    except Exception:
        return {"text": None, "label": None, "name": None}


@router.get("/dropdown")
async def get_systemdaten_dropdown(
    table: str,
    dataset_uid: str,
    field: str,
    group: Optional[str] = None,
    language: Optional[str] = None,
    gcs=Depends(get_gcs_instance),
) -> Dict[str, Any]:
    try:
        return await get_dropdown_mapping_for_field(
            gcs,
            table=table,
            dataset_uid=dataset_uid,
            field=field,
            group=group,
            language=language,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DROPDOWN_RUNTIME_ERROR: {e}")


@router.post("/dropdown-source")
async def post_systemdaten_dropdown_source(
    payload: Dict[str, Any] = Body(default_factory=dict),
    language: Optional[str] = None,
    gcs=Depends(get_gcs_instance),
) -> Dict[str, Any]:
    dropdown_config = payload.get("dropdown_config") if isinstance(payload.get("dropdown_config"), dict) else payload
    dropdown_source = payload.get("dropdown_source") if isinstance(payload.get("dropdown_source"), dict) else None
    if not isinstance(dropdown_config, dict):
        return {"map": {}, "options": [], "language": language or "", "default_language": "", "meta": {"read_only": True}}

    try:
        return await resolve_dropdown_by_config(
            gcs,
            dropdown_config=dropdown_config,
            dropdown_source=dropdown_source,
            language=language,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DROPDOWN_RUNTIME_ERROR: {e}")


@router.get("/menu-configs")
async def get_menu_configs(
    dataset_uid: Optional[str] = None,
    gcs=Depends(get_gcs_instance),
) -> Dict[str, Any]:
    try:
        target_uid = dataset_uid or "00000000-0000-0000-0000-000000000000"
        return await load_menu_param_configs(gcs, dataset_uid=target_uid)
    except Exception:
        return {"configs": {}}

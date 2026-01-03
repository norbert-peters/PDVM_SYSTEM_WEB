"""
GCS (Global Configuration System) API
Neu entwickelt mit PdvmCentralSystemsteuerung

Verwendet neue PDVM-Architektur für einheitlichen Datenzugriff
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional, Any
from pydantic import BaseModel
from app.core.security import get_current_user
from app.core.pdvm_central_systemsteuerung import PdvmCentralSystemsteuerung
import uuid

router = APIRouter()


class GCSValueRequest(BaseModel):
    """Request model für GCS-Werte"""
    gruppe: str
    feld: str
    value: Any


class GCSValueResponse(BaseModel):
    """Response model für GCS-Werte"""
    gruppe: str
    feld: str
    value: Any


async def get_gcs_instance(current_user: dict = Depends(get_current_user)) -> PdvmCentralSystemsteuerung:
    """
    Erstellt GCS-Instanz für aktuellen User
    
    TODO: mandant_guid aus Session/Token holen
    Aktuell: Hardcoded Test-Mandant
    """
    user_guid = uuid.UUID(current_user.get("sub"))
    
    # TODO: Aus Session holen
    mandant_guid = uuid.UUID("f05b62ef-0f41-4fd7-ba98-408ce6adba6c")  # Test-Mandant
    
    # Stichtag aus GCS selbst holen (oder default)
    gcs = PdvmCentralSystemsteuerung(user_guid, mandant_guid)
    stichtag = await gcs.get_stichtag()
    gcs.stichtag = stichtag
    
    return gcs


@router.get("/value", response_model=GCSValueResponse)
async def get_gcs_value(
    gruppe: str = Query(..., description="Gruppe (z.B. menu_guid, user_guid)"),
    feld: str = Query(..., description="Feld (z.B. toggle_menu, stichtag)"),
    gcs: PdvmCentralSystemsteuerung = Depends(get_gcs_instance)
):
    """
    Liest einen GCS-Wert aus sys_systemsteuerung
    
    Verwendet PdvmCentralSystemsteuerung für einheitlichen Zugriff
    """
    value = await gcs.get_static_value(gruppe, feld)
    
    if value is None:
        raise HTTPException(
            status_code=404,
            detail=f"GCS-Wert nicht gefunden: {gruppe}.{feld}"
        )
    
    return GCSValueResponse(gruppe=gruppe, feld=feld, value=value)


@router.post("/value")
async def set_gcs_value(
    request: GCSValueRequest,
    gcs: PdvmCentralSystemsteuerung = Depends(get_gcs_instance)
):
    """
    Setzt einen GCS-Wert in sys_systemsteuerung
    
    Verwendet PdvmCentralSystemsteuerung für einheitlichen Zugriff
    """
    await gcs.set_static_value(request.gruppe, request.feld, request.value)
    
    return {
        "success": True,
        "message": f"GCS-Wert {request.gruppe}.{request.feld} gesetzt",
        "gruppe": request.gruppe,
        "feld": request.feld,
        "value": request.value
    }


@router.delete("/value")
async def delete_gcs_value(
    gruppe: str = Query(..., description="Gruppe"),
    feld: str = Query(..., description="Feld"),
    gcs: PdvmCentralSystemsteuerung = Depends(get_gcs_instance)
):
    """
    Löscht einen GCS-Wert
    
    Verwendet PdvmCentralSystemsteuerung für einheitlichen Zugriff
    """
    await gcs.delete_value(gruppe, feld)
    
    return {
        "success": True,
        "message": f"GCS-Wert {gruppe}.{feld} gelöscht"
    }


# === Spezielle Endpunkte für häufige Zugriffe ===

@router.get("/menu/toggle/{menu_guid}")
async def get_menu_toggle(
    menu_guid: str,
    gcs: PdvmCentralSystemsteuerung = Depends(get_gcs_instance)
):
    """Liest toggle_menu für spezifisches Menü"""
    toggle = await gcs.get_menu_toggle(menu_guid)
    return {"menu_guid": menu_guid, "toggle": toggle}


@router.post("/menu/toggle/{menu_guid}")
async def set_menu_toggle(
    menu_guid: str,
    toggle: int,
    gcs: PdvmCentralSystemsteuerung = Depends(get_gcs_instance)
):
    """Setzt toggle_menu für spezifisches Menü"""
    await gcs.set_menu_toggle(menu_guid, toggle)
    return {"success": True, "menu_guid": menu_guid, "toggle": toggle}


@router.get("/stichtag")
async def get_stichtag(gcs: PdvmCentralSystemsteuerung = Depends(get_gcs_instance)):
    """Liest aktuellen Stichtag des Users"""
    stichtag = await gcs.get_stichtag()
    return {"stichtag": stichtag}


@router.post("/stichtag")
async def set_stichtag(
    stichtag: float,
    gcs: PdvmCentralSystemsteuerung = Depends(get_gcs_instance)
):
    """Setzt Stichtag des Users"""
    await gcs.set_stichtag(stichtag)
    return {"success": True, "stichtag": stichtag}


@router.post("/save")
async def save_all_gcs_values(gcs: PdvmCentralSystemsteuerung = Depends(get_gcs_instance)):
    """
    Speichert alle GCS-Werte in die Datenbank
    
    In der Web-Version werden Werte bereits direkt gespeichert,
    dieser Endpoint existiert für Kompatibilität mit Desktop-Logik.
    """
    # In der Web-Version ist kein explizites save_all nötig,
    # da Werte bereits bei set_gcs_value geschrieben werden
    return {
        "success": True,
        "message": "GCS-Werte gespeichert (Web-Version: bereits persistent)"
    }

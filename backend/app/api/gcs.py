"""
GCS (Global Configuration System) API
Verwendet PdvmCentralSystemsteuerung aus Session
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Body
from typing import Optional, Any
from pydantic import BaseModel
from app.core.security import get_current_user
from app.core.pdvm_central_systemsteuerung import get_gcs_session
import uuid

from datetime import datetime

from app.core.pdvm_datetime import pdvm_to_datetime, datetime_to_pdvm, pdvm_format_display

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


async def get_gcs_instance(current_user: dict = Depends(get_current_user)):
    """
    Holt PdvmCentralSystemsteuerung aus der Session
    
    Nach Mandanten-Auswahl ist GCS mit Pools in _gcs_sessions gespeichert.
    Diese Funktion holt die Session-Instanz für den aktuellen JWT-Token.
    """
    # JWT-Token aus current_user holen
    token = current_user.get("token")
    
    if not token:
        raise HTTPException(
            status_code=401,
            detail="Kein Session-Token gefunden"
        )
    
    # GCS aus Session holen
    gcs = get_gcs_session(token)
    
    if not gcs:
        raise HTTPException(
            status_code=404,
            detail="Keine GCS-Session gefunden. Bitte Mandant auswählen."
        )
    
    return gcs


@router.get("/value", response_model=GCSValueResponse)
async def get_gcs_value(
    gruppe: str = Query(..., description="Gruppe (z.B. menu_guid, user_guid)"),
    feld: str = Query(..., description="Feld (z.B. toggle_menu, stichtag)"),
    gcs = Depends(get_gcs_instance)
):
    """
    Liest einen GCS-Wert aus sys_systemsteuerung
    
    Verwendet PdvmCentralSystemsteuerung für einheitlichen Zugriff
    """
    # get_value liefert (wert, ab_zeit) Tuple
    value, _ = gcs.get_value(gruppe, feld, ab_zeit=gcs.stichtag)
    
    if value is None:
        raise HTTPException(
            status_code=404,
            detail=f"GCS-Wert nicht gefunden: {gruppe}.{feld}"
        )
    
    return GCSValueResponse(gruppe=gruppe, feld=feld, value=value)


@router.post("/value")
async def set_gcs_value(
    request: GCSValueRequest,
    gcs = Depends(get_gcs_instance)
):
    """
    Setzt einen GCS-Wert in sys_systemsteuerung
    
    Verwendet PdvmCentralSystemsteuerung für einheitlichen Zugriff
    """
    # set_value schreibt direkt in Gruppe/Feld-Struktur
    gcs.set_value(request.gruppe, request.feld, request.value, ab_zeit=gcs.stichtag)
    
    # Persistent speichern
    await gcs.save_all_values()
    
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
    gcs = Depends(get_gcs_instance)
):
    """
    Löscht einen GCS-Wert
    
    Verwendet PdvmCentralSystemsteuerung für einheitlichen Zugriff
    """
    # delete_value entfernt Feld aus Gruppe
    await gcs.delete_value(gruppe, feld)
    
    return {
        "success": True,
        "message": f"GCS-Wert {gruppe}.{feld} gelöscht"
    }


# === Spezielle Endpunkte für häufige Zugriffe ===

@router.get("/menu/toggle/{menu_guid}")
async def get_menu_toggle(
    menu_guid: str,
    gcs = Depends(get_gcs_instance)
):
    """Liest toggle_menu für spezifisches Menü"""
    toggle = gcs.get_menu_toggle(menu_guid)
    return {"menu_guid": menu_guid, "toggle": toggle}


@router.post("/menu/toggle/{menu_guid}")
async def set_menu_toggle(
    menu_guid: str,
    toggle: int,
    gcs = Depends(get_gcs_instance)
):
    """Setzt toggle_menu für spezifisches Menü"""
    gcs.set_menu_toggle(menu_guid, toggle)
    await gcs.save_all_values()
    return {"success": True, "menu_guid": menu_guid, "toggle": toggle}


@router.get("/stichtag")
async def get_stichtag(gcs = Depends(get_gcs_instance)):
    """Liest aktuellen Stichtag des Users"""

    st = float(gcs.get_stichtag())
    dt = pdvm_to_datetime(st)
    iso = dt.isoformat() if dt else None
    display = pdvm_format_display(st) if dt else ""

    return {
        "stichtag": st,
        "iso": iso,
        "display": display,
    }


class SetStichtagRequest(BaseModel):
    stichtag: Optional[float] = None
    iso: Optional[str] = None


@router.post("/stichtag")
async def set_stichtag(
    request: Optional[SetStichtagRequest] = Body(default=None),
    stichtag: Optional[float] = Query(default=None, description="PDVM float (legacy/query)"),
    gcs = Depends(get_gcs_instance)
):
    """Setzt Stichtag des Users"""

    new_stichtag: Optional[float] = None

    # 1) Legacy query param
    if stichtag is not None:
        new_stichtag = float(stichtag)

    # 2) JSON body
    if request is not None:
        if request.stichtag is not None:
            new_stichtag = float(request.stichtag)
        elif request.iso:
            try:
                # Python akzeptiert kein 'Z' direkt in fromisoformat
                iso_normalized = request.iso.replace("Z", "+00:00")
                dt = datetime.fromisoformat(iso_normalized)
                # Konvertierung in PDVM float (naive/local wie im System) – tzinfo wird ignoriert
                if getattr(dt, "tzinfo", None) is not None:
                    dt = dt.replace(tzinfo=None)
                new_stichtag = float(datetime_to_pdvm(dt))
            except Exception:
                raise HTTPException(status_code=400, detail="Ungültiges ISO-Datum für Stichtag")

    if new_stichtag is None:
        raise HTTPException(status_code=400, detail="stichtag (float) oder iso (string) muss gesetzt sein")

    gcs.set_stichtag(new_stichtag)
    await gcs.save_all_values()

    dt = pdvm_to_datetime(new_stichtag)
    return {
        "success": True,
        "stichtag": float(new_stichtag),
        "iso": dt.isoformat() if dt else None,
        "display": pdvm_format_display(float(new_stichtag)) if dt else "",
    }


@router.post("/save")
async def save_all_gcs_values(gcs = Depends(get_gcs_instance)):
    """
    Speichert alle GCS-Werte in die Datenbank
    
    Verwendet PdvmCentralSystemsteuerung.save_all_values()
    """
    guid = await gcs.save_all_values()
    return {
        "success": True,
        "guid": str(guid),
        "message": "GCS-Werte gespeichert"
    }


@router.get("/theme")
async def get_theme_colors(gcs = Depends(get_gcs_instance)):
    """
    Liefert Theme-Farben aus sys_layout
    
    Liest THEME_GUID aus Mandant-CONFIG und holt Farbschema aus sys_layout.
    Liefert alle COLOR-Gruppen (PRIMARY, BACKGROUND, TEXT, etc.)
    
    Returns:
        Dict mit allen Farbwerten des aktuellen Themes
    """
    if not gcs.theme:
        raise HTTPException(
            status_code=404,
            detail="Kein Theme konfiguriert für diesen Mandanten"
        )
    
    # Alle Farb-Gruppen aus Theme-Instanz holen
    # Typische Gruppen: PRIMARY, SECONDARY, BACKGROUND, TEXT, BORDER, etc.
    theme_data = gcs.theme.data
    
    return {
        "theme_guid": str(gcs.theme.guid),
        "colors": theme_data
    }

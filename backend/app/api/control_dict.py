"""
REST API Endpoints für Control Dictionary (edit_dict)

Endpoints:
- POST /api/control/create - Neues Control anlegen
- PUT /api/control/{uid}/switch-modul - MODUL_TYPE wechseln
- GET /api/control/template/{modul_type} - Template laden
- GET /api/control/{uid} - Control laden
- PUT /api/control/{uid} - Control aktualisieren
- DELETE /api/control/{uid} - Control löschen
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional
from uuid import UUID
from app.api.gcs import get_gcs_instance
from app.core.control_dict_service import ControlDictService

router = APIRouter(tags=["control_dict"])


def _extract_list_item_values(effective: Dict[str, Any], source_data: Dict[str, Any]) -> Dict[str, Any]:
    effective_control = effective.get('CONTROL') if isinstance(effective.get('CONTROL'), dict) else {}
    source_control = source_data.get('CONTROL') if isinstance(source_data.get('CONTROL'), dict) else {}

    return {
        "modul_type": (
            effective.get('modul_type') or effective.get('MODUL_TYPE')
            or effective_control.get('MODUL_TYPE')
            or source_data.get('modul_type') or source_data.get('MODUL_TYPE')
            or source_control.get('MODUL_TYPE')
        ),
        "label": (
            effective.get('label') or effective.get('LABEL')
            or effective_control.get('LABEL')
            or source_data.get('label') or source_data.get('LABEL')
            or source_control.get('LABEL')
        ),
        "type": (
            effective.get('type') or effective.get('TYPE')
            or effective_control.get('TYPE')
            or source_data.get('type') or source_data.get('TYPE')
            or source_control.get('TYPE')
        ),
        "table": (
            effective.get('table') or effective.get('TABLE')
            or effective_control.get('TABLE')
            or source_data.get('table') or source_data.get('TABLE')
            or source_control.get('TABLE')
        ),
        "gruppe": (
            effective.get('gruppe') or effective.get('GRUPPE')
            or effective_control.get('GRUPPE')
            or source_data.get('gruppe') or source_data.get('GRUPPE')
            or source_control.get('GRUPPE')
        ),
        "field": (
            effective.get('field') or effective.get('FIELD') or effective.get('feld') or effective.get('FELD')
            or effective_control.get('FIELD') or effective_control.get('FELD')
            or source_data.get('field') or source_data.get('FIELD') or source_data.get('feld') or source_data.get('FELD')
            or source_control.get('FIELD') or source_control.get('FELD')
        ),
    }


# Request/Response Models
class CreateControlRequest(BaseModel):
    """Request für neues Control"""
    modul_type: str = Field(..., pattern="^(edit|view|tabs)$")
    table_name: str
    field_data: Dict[str, Any]

class CreateControlResponse(BaseModel):
    """Response mit neuer Control-UUID"""
    uid: UUID
    name: str
    modul_type: str

class SwitchModulRequest(BaseModel):
    """Request für MODUL_TYPE Switch"""
    new_modul_type: str = Field(..., pattern="^(edit|view|tabs)$")

class UpdateControlRequest(BaseModel):
    """Request für Control-Update"""
    field_data: Dict[str, Any]

class ControlResponse(BaseModel):
    """Complete Control Data"""
    uid: UUID
    name: str
    daten: Dict[str, Any]
    historisch: int


# Endpoints

@router.post("/create", response_model=CreateControlResponse)
async def create_new_control(
    request: CreateControlRequest,
    gcs=Depends(get_gcs_instance)
):
    """
    Erstellt neues Control basierend auf MODUL_TYPE Template
    
    Prozess:
    1. Template 666666... + 555555...[modul_type] laden
    2. Merge mit User-Daten
    3. SELF_NAME generieren (Tabellenpräfix + name)
    4. In DB einfügen
    """
    try:
        service = ControlDictService(gcs)
        created = await service.create_control(
            modul_type=request.modul_type,
            table_name=request.table_name,
            field_data=request.field_data,
        )
        effective = created.get("daten") if isinstance(created.get("daten"), dict) else {}
        
        return CreateControlResponse(
            uid=created.get("uid"),
            name=str(created.get("name") or ""),
            modul_type=effective.get('modul_type')
        )
    
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/{uid}/switch-modul", response_model=ControlResponse)
async def switch_modul_type(
    uid: UUID,
    request: SwitchModulRequest,
    gcs=Depends(get_gcs_instance)
):
    """
    Wechselt MODUL_TYPE eines bestehenden Controls
    
    Prozess:
    1. Aktuelles Control laden
    2. Felder mappen (alte → neue)
    3. Template-Defaults für neuen Typ anwenden
    4. In DB aktualisieren
    """
    try:
        service = ControlDictService(gcs)
        updated = await service.switch_modul(uid=uid, new_modul_type=request.new_modul_type)
        
        return ControlResponse(
            uid=updated.get("uid"),
            name=str(updated.get("name") or ""),
            daten=updated.get("daten") if isinstance(updated.get("daten"), dict) else {},
            historisch=int(updated.get("historisch") or 0),
        )
    
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/template/{modul_type}")
async def get_modul_template(
    modul_type: str,
    gcs=Depends(get_gcs_instance)
):
    """
    Lädt Modul-Template aus 555555...
    
    Verwendet von Frontend beim Initialisieren neuer Controls
    """
    if modul_type not in ['edit', 'view', 'tabs']:
        raise HTTPException(status_code=400, detail=f"Ungültiger modul_type: {modul_type}")
    
    try:
        service = ControlDictService(gcs)
        template = await service.get_modul_template(modul_type)
        return {"modul_type": modul_type, "template": template}
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/list-controls")
async def list_controls_v2(
    modul_type: Optional[str] = None,
    table: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
    gcs=Depends(get_gcs_instance)
):
    """Listet Controls mit optionalen Filtern (nicht kollidierende Route)."""
    service = ControlDictService(gcs)
    return await service.list_controls(modul_type=modul_type, table=table, skip=skip, limit=limit)


@router.get("/{uid}", response_model=ControlResponse)
async def get_control(
    uid: UUID,
    gcs=Depends(get_gcs_instance)
):
    """Lädt Control by UUID"""
    service = ControlDictService(gcs)
    result = await service.get_control(uid)

    if not result:
        raise HTTPException(status_code=404, detail="Control nicht gefunden")
    
    return ControlResponse(
        uid=result.get("uid"),
        name=str(result.get("name") or ""),
        daten=result.get("daten") if isinstance(result.get("daten"), dict) else {},
        historisch=int(result.get("historisch") or 0),
    )


@router.put("/{uid}", response_model=ControlResponse)
async def update_control(
    uid: UUID,
    request: UpdateControlRequest,
    gcs=Depends(get_gcs_instance)
):
    """
    Aktualisiert Control-Daten
    
    Merged request.field_data mit bestehenden Daten
    SELF_NAME wird automatisch aktualisiert wenn name ändert
    """
    service = ControlDictService(gcs)
    result = await service.update_control(uid=uid, field_data=request.field_data)

    if not result:
        raise HTTPException(status_code=404, detail="Control nicht gefunden")
    
    return ControlResponse(
        uid=result.get("uid"),
        name=str(result.get("name") or ""),
        daten=result.get("daten") if isinstance(result.get("daten"), dict) else {},
        historisch=int(result.get("historisch") or 0),
    )


@router.delete("/{uid}")
async def delete_control(
    uid: UUID,
    gcs=Depends(get_gcs_instance)
):
    """
    Löscht Control (setzt historisch=1)
    
    NICHT physisch löschen für Audit-Trail
    """
    service = ControlDictService(gcs)
    ok = await service.delete_control(uid)

    if not ok:
        raise HTTPException(status_code=404, detail="Control nicht gefunden oder bereits gelöscht")
    
    return {"status": "deleted", "uid": str(uid)}


@router.get("/list")
async def list_controls(
    modul_type: Optional[str] = None,
    table: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
    gcs=Depends(get_gcs_instance)
):
    """
    Listet Controls mit optionalen Filtern
    
    Query Parameters:
    - modul_type: Filtere nach edit/view/tabs
    - table: Filtere nach Zieltabelle
    - skip: Pagination offset
    - limit: Max. Anzahl Ergebnisse
    """
    service = ControlDictService(gcs)
    return await service.list_controls(modul_type=modul_type, table=table, skip=skip, limit=limit)

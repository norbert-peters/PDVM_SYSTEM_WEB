"""
Table CRUD API Routes
Generic endpoints for all PDVM tables
"""
from fastapi import APIRouter, Depends, HTTPException, status, Path
from typing import List
from app.models.schemas import RecordCreate, RecordUpdate, RecordResponse, RecordListItem
from app.core.database import PdvmDatabase
from app.core.central_write_service import create_record_central, delete_record_central, update_record_central
from app.core.pdvm_central_systemsteuerung import get_gcs_session
from app.core.security import get_current_user

router = APIRouter()

@router.get("/{table_name}", response_model=List[RecordListItem])
async def read_all_records(
    table_name: str = Path(..., description="Table name"),
    current_user: dict = Depends(get_current_user)
):
    """
    Get all records from a table
    Returns list of records with uid, name, modified_at
    """
    db = PdvmDatabase(table_name)
    records = await db.read_all()
    return records

@router.get("/{table_name}/{uid}", response_model=RecordResponse)
async def read_record(
    table_name: str = Path(..., description="Table name"),
    uid: str = Path(..., description="Record UID"),
    current_user: dict = Depends(get_current_user)
):
    """
    Get single record by UID
    Returns full record with all fields
    """
    db = PdvmDatabase(table_name)
    record = await db.read(uid)
    
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Record {uid} not found in {table_name}"
        )
    
    return record

@router.post("/{table_name}", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_record(
    table_name: str,
    record: RecordCreate,
    current_user: dict = Depends(get_current_user)
):
    """
    Create new record
    Returns created record UID
    """
    token = current_user.get("token")
    gcs = get_gcs_session(token) if token else None

    try:
        created = await create_record_central(
            table_name=table_name,
            daten=record.daten,
            name=record.name,
            gcs=gcs,
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
    
    return {"uid": str(created.get("uid")), "message": "Record created"}

@router.put("/{table_name}/{uid}")
async def update_record(
    table_name: str,
    uid: str,
    record: RecordUpdate,
    current_user: dict = Depends(get_current_user)
):
    """
    Update existing record
    """
    token = current_user.get("token")
    gcs = get_gcs_session(token) if token else None

    try:
        updated = await update_record_central(
            table_name=table_name,
            uid=uid,
            daten=record.daten,
            name=record.name,
            gcs=gcs,
            actor_user_uid=current_user.get("sub"),
            actor_ip=current_user.get("client_ip"),
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
    
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Record {uid} not found"
        )
    
    return {"message": "Record updated"}

@router.delete("/{table_name}/{uid}")
async def delete_record(
    table_name: str,
    uid: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Delete record
    """
    token = current_user.get("token")
    gcs = get_gcs_session(token) if token else None

    try:
        success = await delete_record_central(
            table_name=table_name,
            uid=uid,
            gcs=gcs,
            soft_delete=True,
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Record {uid} not found"
        )
    
    return {"message": "Record deleted"}

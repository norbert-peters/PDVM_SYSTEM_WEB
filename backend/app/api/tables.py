"""
Table CRUD API Routes
Generic endpoints for all PDVM tables
"""
import uuid
from fastapi import APIRouter, Depends, HTTPException, status, Path, Query
from typing import List, Optional, Any, Dict
from app.models.schemas import RecordCreate, RecordUpdate, RecordResponse, RecordListItem
from app.core.database import PdvmDatabase
from app.core.central_write_service import create_record_central, delete_record_central, update_record_central
from app.core.pdvm_central_systemsteuerung import get_gcs_session
from app.core.security import get_current_user
from app.core.workflow_draft_access import WorkflowDraftAccess
from app.core.workflow_draft_service import WorkflowDraftService, DRAFT_TABLE

router = APIRouter()


def _normalize_storage_scope(storage_scope: Optional[str]) -> str:
    scope = str(storage_scope or "live").strip().lower() or "live"
    if scope not in {"live", "draft"}:
        raise HTTPException(status_code=400, detail="storage_scope muss 'live' oder 'draft' sein")
    return scope


def _require_draft_guid_for_scope(scope: str, draft_guid: Optional[str]) -> str:
    if scope != "draft":
        return ""
    raw = str(draft_guid or "").strip()
    if not raw:
        raise HTTPException(status_code=400, detail="Bei storage_scope='draft' ist draft_guid verpflichtend")
    try:
        return str(uuid.UUID(raw))
    except Exception:
        raise HTTPException(status_code=400, detail="draft_guid ist ungueltig")


def _extract_record_name(record_payload: Dict[str, Any], fallback: str) -> str:
    if not isinstance(record_payload, dict):
        return fallback
    root = record_payload.get("ROOT") if isinstance(record_payload.get("ROOT"), dict) else {}
    return str(root.get("SELF_NAME") or root.get("NAME") or fallback)


def _extract_work_payload_from_loaded_draft(draft_data: Dict[str, Any]) -> Dict[str, Any]:
    items = draft_data.get("items") if isinstance(draft_data.get("items"), list) else []
    for item in items:
        item_type = str(item.get("item_type") or "").strip().lower()
        item_key = str(item.get("item_key") or "").strip().lower()
        if item_type == "work" and item_key == "container":
            payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
            normalized: Dict[str, Any] = {}
            for key, value in payload.items():
                key_norm = str(key or "").strip()
                if not key_norm:
                    continue
                if key_norm.upper() == "WORKFLOW":
                    normalized["WORKFLOW"] = dict(value) if isinstance(value, dict) else {}
                elif isinstance(value, dict):
                    normalized[key_norm.upper()] = dict(value)
            if "WORKFLOW" not in normalized:
                normalized["WORKFLOW"] = {}
            return normalized
    return {"WORKFLOW": {}}


def _require_system_pool(gcs: Any):
    system_pool = getattr(gcs, "_system_pool", None)
    if system_pool is None:
        raise HTTPException(status_code=503, detail="System-Pool nicht verfuegbar")
    return system_pool


def _resolve_actor_user_guid(current_user: Dict[str, Any], gcs: Any) -> str:
    sub = str(current_user.get("sub") or "").strip()
    if sub:
        try:
            return str(uuid.UUID(sub))
        except Exception:
            pass
    gcs_user = getattr(gcs, "user_guid", None)
    if gcs_user is None:
        raise HTTPException(status_code=401, detail="Benutzerkontext fehlt")
    return str(gcs_user)

@router.get("/{table_name}", response_model=List[RecordListItem])
async def read_all_records(
    table_name: str = Path(..., description="Table name"),
    storage_scope: Optional[str] = Query(default="live"),
    draft_guid: Optional[str] = Query(default=None),
    current_user: dict = Depends(get_current_user)
):
    """
    Get all records from a table
    Returns list of records with uid, name, modified_at
    """
    scope = _normalize_storage_scope(storage_scope)
    token = current_user.get("token")
    gcs = get_gcs_session(token) if token else None

    if scope == "draft":
        if not gcs:
            raise HTTPException(status_code=401, detail="GCS-Session nicht gefunden")
        resolved_draft_guid = _require_draft_guid_for_scope(scope, draft_guid)
        system_pool = _require_system_pool(gcs)
        rows = await WorkflowDraftAccess.list_table_records(
            system_pool,
            draft_guid=resolved_draft_guid,
            table_name=table_name,
            draft_table=DRAFT_TABLE,
        )
        result: List[Dict[str, Any]] = []
        for uid_value, record_payload in rows.items():
            uid_txt = str(uid_value)
            result.append(
                {
                    "uid": uid_txt,
                    "name": _extract_record_name(record_payload, uid_txt),
                    "modified_at": None,
                }
            )
        return result

    db = PdvmDatabase(table_name)
    records = await db.read_all()
    return records

@router.get("/{table_name}/{uid}", response_model=RecordResponse)
async def read_record(
    table_name: str = Path(..., description="Table name"),
    uid: str = Path(..., description="Record UID"),
    storage_scope: Optional[str] = Query(default="live"),
    draft_guid: Optional[str] = Query(default=None),
    current_user: dict = Depends(get_current_user)
):
    """
    Get single record by UID
    Returns full record with all fields
    """
    scope = _normalize_storage_scope(storage_scope)

    if scope == "draft":
        token = current_user.get("token")
        gcs = get_gcs_session(token) if token else None
        if not gcs:
            raise HTTPException(status_code=401, detail="GCS-Session nicht gefunden")
        resolved_draft_guid = _require_draft_guid_for_scope(scope, draft_guid)
        system_pool = _require_system_pool(gcs)
        rows = await WorkflowDraftAccess.list_table_records(
            system_pool,
            draft_guid=resolved_draft_guid,
            table_name=table_name,
            draft_table=DRAFT_TABLE,
        )
        uid_norm = str(uid).strip()
        record_payload = rows.get(uid_norm) if isinstance(rows.get(uid_norm), dict) else None
        if not record_payload:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Record {uid} not found in {table_name} (draft)",
            )
        return {
            "uid": uid_norm,
            "daten": record_payload,
            "name": _extract_record_name(record_payload, uid_norm),
            "historisch": 0,
            "sec_id": None,
            "gilt_bis": "9999365.00000",
            "created_at": None,
            "modified_at": None,
        }

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
    storage_scope: Optional[str] = Query(default="live"),
    draft_guid: Optional[str] = Query(default=None),
    current_user: dict = Depends(get_current_user)
):
    """
    Create new record
    Returns created record UID
    """
    token = current_user.get("token")
    gcs = get_gcs_session(token) if token else None
    scope = _normalize_storage_scope(storage_scope)

    if scope == "draft":
        if not gcs:
            raise HTTPException(status_code=401, detail="GCS-Session nicht gefunden")
        resolved_draft_guid = _require_draft_guid_for_scope(scope, draft_guid)
        system_pool = _require_system_pool(gcs)
        actor_user_guid = _resolve_actor_user_guid(current_user, gcs)
        saved = await WorkflowDraftAccess.save_table_record(
            system_pool,
            draft_guid=resolved_draft_guid,
            table_name=table_name,
            record_uid=None,
            payload=record.daten,
            updated_by_user_guid=actor_user_guid,
            draft_table=DRAFT_TABLE,
            single_record=False,
        )
        return {"uid": str(saved.get("record_uid")), "message": "Draft record created", "storage_scope": "draft", "draft_guid": resolved_draft_guid}

    try:
        created = await create_record_central(
            table_name=table_name,
            daten=record.daten,
            name=record.name,
            gcs=gcs,
            storage_scope=scope,
            draft_guid=draft_guid,
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
    storage_scope: Optional[str] = Query(default="live"),
    draft_guid: Optional[str] = Query(default=None),
    current_user: dict = Depends(get_current_user)
):
    """
    Update existing record
    """
    token = current_user.get("token")
    gcs = get_gcs_session(token) if token else None
    scope = _normalize_storage_scope(storage_scope)

    if scope == "draft":
        if not gcs:
            raise HTTPException(status_code=401, detail="GCS-Session nicht gefunden")
        resolved_draft_guid = _require_draft_guid_for_scope(scope, draft_guid)
        system_pool = _require_system_pool(gcs)
        actor_user_guid = _resolve_actor_user_guid(current_user, gcs)
        saved = await WorkflowDraftAccess.save_table_record(
            system_pool,
            draft_guid=resolved_draft_guid,
            table_name=table_name,
            record_uid=uid,
            payload=record.daten,
            updated_by_user_guid=actor_user_guid,
            draft_table=DRAFT_TABLE,
            single_record=False,
        )
        return {"message": "Draft record updated", "uid": str(saved.get("record_uid")), "storage_scope": "draft", "draft_guid": resolved_draft_guid}

    try:
        updated = await update_record_central(
            table_name=table_name,
            uid=uid,
            daten=record.daten,
            name=record.name,
            gcs=gcs,
            actor_user_uid=current_user.get("sub"),
            actor_ip=current_user.get("client_ip"),
            storage_scope=scope,
            draft_guid=draft_guid,
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
    storage_scope: Optional[str] = Query(default="live"),
    draft_guid: Optional[str] = Query(default=None),
    current_user: dict = Depends(get_current_user)
):
    """
    Delete record
    """
    token = current_user.get("token")
    gcs = get_gcs_session(token) if token else None
    scope = _normalize_storage_scope(storage_scope)

    if scope == "draft":
        if not gcs:
            raise HTTPException(status_code=401, detail="GCS-Session nicht gefunden")
        resolved_draft_guid = _require_draft_guid_for_scope(scope, draft_guid)
        system_pool = _require_system_pool(gcs)
        actor_user_guid = _resolve_actor_user_guid(current_user, gcs)

        draft = await WorkflowDraftService.load_draft(
            system_pool,
            draft_guid=resolved_draft_guid,
            draft_table=DRAFT_TABLE,
        )
        work_payload = _extract_work_payload_from_loaded_draft(draft)
        bucket_key = str(table_name or "").strip().upper()
        bucket = work_payload.get(bucket_key) if isinstance(work_payload.get(bucket_key), dict) else {}

        uid_norm = str(uid).strip()
        if uid_norm not in bucket:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Record {uid} not found in {table_name} (draft)",
            )

        bucket = dict(bucket)
        bucket.pop(uid_norm, None)
        work_payload[bucket_key] = bucket

        sanitized_payload = await WorkflowDraftAccess.sanitize_work_container_payload(system_pool, work_payload)
        await WorkflowDraftService.save_draft_item(
            system_pool,
            draft_guid=resolved_draft_guid,
            item_type="work",
            item_key="container",
            payload=sanitized_payload,
            updated_by_user_guid=actor_user_guid,
            draft_table=DRAFT_TABLE,
        )
        return {"message": "Draft record deleted", "storage_scope": "draft", "draft_guid": resolved_draft_guid}

    try:
        success = await delete_record_central(
            table_name=table_name,
            uid=uid,
            gcs=gcs,
            soft_delete=True,
            storage_scope=scope,
            draft_guid=draft_guid,
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

"""Workflow Draft API (Single table model).

Endpoints fuer den Testdialog-Lebenszyklus:
- create draft
- save setup/item
- load draft
- list open drafts
- validate draft
"""
from __future__ import annotations

from typing import Any, Dict, Optional
import re
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.security import get_current_user, require_admin_or_develop_user
from app.core.pdvm_central_systemsteuerung import get_gcs_session
from app.core.workflow_draft_access import WorkflowDraftAccess
from app.core.workflow_draft_service import WorkflowDraftService


router = APIRouter()
_TABLE_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class CreateDraftRequest(BaseModel):
    workflow_type: str = Field(default="work", description="Workflow-Typ")
    title: str = Field(..., min_length=1, description="Anzeigename des Drafts")
    initial_setup: Optional[Dict[str, Any]] = Field(default=None, description="Optionaler Setup-Block")
    draft_table: Optional[str] = Field(default=None)


class SaveDraftItemRequest(BaseModel):
    item_type: str = Field(..., min_length=1)
    item_key: str = Field(..., min_length=1)
    payload: Dict[str, Any] = Field(default_factory=dict)


class EnsureDraftStepRequest(BaseModel):
    step: int = Field(..., ge=1, le=20, description="Aktiver/naechster Workflow-Tab")
    table: Optional[str] = Field(default=None, description="Zieltabelle des naechsten Tabs")
    module: Optional[str] = Field(default=None, description="Tab-Modul (view/edit/acti)")
    head: Optional[str] = Field(default=None, description="Tab-Ueberschrift")
    draft_table: Optional[str] = Field(default=None)


class UpsertDraftTableRecordRequest(BaseModel):
    record_uid: Optional[str] = Field(default=None)
    payload: Dict[str, Any] = Field(default_factory=dict)
    draft_table: Optional[str] = Field(default=None)
    single_record: Optional[bool] = Field(default=False)


async def get_gcs_instance(current_user: dict = Depends(get_current_user)):
    token = current_user.get("token")
    if not token:
        raise HTTPException(status_code=401, detail="Kein Session-Token gefunden")

    gcs = get_gcs_session(token)
    if not gcs:
        raise HTTPException(
            status_code=404,
            detail="Keine GCS-Session gefunden. Bitte Mandant auswaehlen.",
        )

    if hasattr(gcs, "set_request_context"):
        gcs.set_request_context(actor_ip=current_user.get("client_ip"))

    return gcs


def _extract_user_guid(current_user: dict, gcs) -> str:
    user_guid = str(getattr(gcs, "user_guid", "") or current_user.get("sub") or "").strip()
    if not user_guid:
        raise HTTPException(status_code=400, detail="user_guid konnte nicht ermittelt werden")

    try:
        return str(uuid.UUID(user_guid))
    except Exception:
        raise HTTPException(status_code=400, detail="user_guid ist ungueltig")


def _extract_mandant_guid(gcs) -> str:
    mandant_guid = str(getattr(gcs, "mandant_guid", "") or "").strip()
    if not mandant_guid:
        raise HTTPException(status_code=400, detail="mandant_guid konnte nicht ermittelt werden")

    try:
        return str(uuid.UUID(mandant_guid))
    except Exception:
        raise HTTPException(status_code=400, detail="mandant_guid ist ungueltig")


def _normalize_table_name(value: Optional[str], *, label: str, default: str) -> str:
    table = str(value or "").strip().lower() or str(default).strip().lower()
    if not _TABLE_NAME_RE.match(table):
        raise HTTPException(status_code=400, detail=f"{label} enthaelt ungueltige Zeichen")
    return table


def _resolve_draft_table(*, draft_table: Optional[str]) -> str:
    return _normalize_table_name(
        draft_table,
        label="draft_table",
        default="dev_workflow_draft",
    )


def _require_system_pool(gcs):
    # Keep compatibility with both attribute variants.
    system_pool = getattr(gcs, "_pool_system", None) or getattr(gcs, "_system_pool", None)
    if not system_pool:
        raise HTTPException(status_code=500, detail="Systemdatenbank-Pool nicht verfuegbar")
    return system_pool


def _normalize_workflow_name(*, payload_workflow: Dict[str, Any], draft_root: Dict[str, Any]) -> str:
    from_work = str(payload_workflow.get("WORKFLOW_NAME") or "").strip()
    from_title = str(draft_root.get("TITLE") or "").strip()
    return from_title or from_work or "WORKFLOW_DRAFT"


def _normalize_bucket_name(table_name: str) -> str:
    table = str(table_name or "").strip().upper()
    return table


@router.post("/bootstrap")
async def bootstrap_workflow_draft_tables(
    draft_table: Optional[str] = None,
    gcs=Depends(get_gcs_instance),
    _operator: dict = Depends(require_admin_or_develop_user),
):
    system_pool = _require_system_pool(gcs)

    draft_table_norm = _resolve_draft_table(draft_table=draft_table)
    result = await WorkflowDraftService.ensure_draft_tables(
        system_pool,
        draft_table=draft_table_norm,
    )
    return {
        "success": True,
        "message": "Workflow-Draft-Tabelle geprueft/angelegt",
        **result,
    }


@router.post("/create")
async def create_draft(
    payload: CreateDraftRequest,
    gcs=Depends(get_gcs_instance),
    operator_user: dict = Depends(require_admin_or_develop_user),
):
    system_pool = _require_system_pool(gcs)

    try:
        user_guid = _extract_user_guid(operator_user, gcs)
        mandant_guid = _extract_mandant_guid(gcs)
        draft_table_norm = _resolve_draft_table(draft_table=payload.draft_table)

        created = await WorkflowDraftService.create_draft(
            system_pool,
            workflow_type=payload.workflow_type,
            title=payload.title,
            owner_user_guid=user_guid,
            mandant_guid=mandant_guid,
            initial_setup=payload.initial_setup,
            draft_table=draft_table_norm,
        )

        if isinstance(payload.initial_setup, dict) and payload.initial_setup:
            await WorkflowDraftService.save_draft_item(
                system_pool,
                draft_guid=created["draft_guid"],
                item_type="setup",
                item_key="setup",
                payload=payload.initial_setup,
                updated_by_user_guid=user_guid,
                draft_table=draft_table_norm,
            )

        if str(payload.workflow_type or "").strip().lower() != "dictionary_builder":
            await WorkflowDraftService.save_draft_item(
                system_pool,
                draft_guid=created["draft_guid"],
                item_type="work",
                item_key="container",
                payload={
                    "WORKFLOW": {
                        "DIALOG_TYPE": "work",
                        "WORKFLOW_TYPE": str(payload.workflow_type or "").strip().lower() or "work",
                        "WORKFLOW_NAME": str(payload.title or "").strip(),
                        "TARGET_TABLE": str((payload.initial_setup or {}).get("TARGET_TABLE") or "sys_dialogdaten"),
                        "DESCRIPTION": str((payload.initial_setup or {}).get("DESCRIPTION") or ""),
                    },
                    "SYS_DIALOGDATEN": {},
                    "SYS_VIEWDATEN": {},
                    "SYS_FRAMEDATEN": {},
                },
                updated_by_user_guid=user_guid,
                draft_table=draft_table_norm,
            )

        return {
            "success": True,
            "message": "Draft erstellt",
            **created,
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Draft-Erstellung fehlgeschlagen: {exc}")


@router.post("/{draft_guid}/items")
async def save_draft_item(
    draft_guid: str,
    payload: SaveDraftItemRequest,
    draft_table: Optional[str] = None,
    gcs=Depends(get_gcs_instance),
    operator_user: dict = Depends(require_admin_or_develop_user),
):
    system_pool = _require_system_pool(gcs)

    try:
        user_guid = _extract_user_guid(operator_user, gcs)
        draft_table_norm = _resolve_draft_table(draft_table=draft_table)
        payload_data = payload.payload
        if str(payload.item_type or "").strip().lower() == "work" and str(payload.item_key or "").strip().lower() == "container":
            payload_data = await WorkflowDraftAccess.sanitize_work_container_payload(
                system_pool,
                payload.payload,
            )

        result = await WorkflowDraftService.save_draft_item(
            system_pool,
            draft_guid=draft_guid,
            item_type=payload.item_type,
            item_key=payload.item_key,
            payload=payload_data,
            updated_by_user_guid=user_guid,
            draft_table=draft_table_norm,
        )
        return {
            "success": True,
            "message": "Draft-Item gespeichert",
            **result,
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Draft-Item konnte nicht gespeichert werden: {exc}")


@router.get("/{draft_guid}")
async def load_draft(
    draft_guid: str,
    draft_table: Optional[str] = None,
    gcs=Depends(get_gcs_instance),
    _operator: dict = Depends(require_admin_or_develop_user),
):
    system_pool = _require_system_pool(gcs)

    try:
        draft_table_norm = _resolve_draft_table(draft_table=draft_table)
        data = await WorkflowDraftService.load_draft(
            system_pool,
            draft_guid=draft_guid,
            draft_table=draft_table_norm,
        )
        return {
            "success": True,
            "message": "Draft geladen",
            **data,
        }
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Draft konnte nicht geladen werden: {exc}")


@router.get("/list/open")
async def list_open_drafts(
    draft_table: Optional[str] = None,
    gcs=Depends(get_gcs_instance),
    operator_user: dict = Depends(require_admin_or_develop_user),
):
    system_pool = _require_system_pool(gcs)

    try:
        user_guid = _extract_user_guid(operator_user, gcs)
        mandant_guid = _extract_mandant_guid(gcs)
        draft_table_norm = _resolve_draft_table(draft_table=draft_table)
        result = await WorkflowDraftService.list_open_drafts(
            system_pool,
            owner_user_guid=user_guid,
            mandant_guid=mandant_guid,
            draft_table=draft_table_norm,
        )
        return {
            "success": True,
            "message": "Offene Drafts geladen",
            **result,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Draft-Liste konnte nicht geladen werden: {exc}")


@router.post("/{draft_guid}/validate")
async def validate_draft(
    draft_guid: str,
    draft_table: Optional[str] = None,
    gcs=Depends(get_gcs_instance),
    _operator: dict = Depends(require_admin_or_develop_user),
):
    system_pool = _require_system_pool(gcs)

    try:
        draft_table_norm = _resolve_draft_table(draft_table=draft_table)
        result = await WorkflowDraftService.validate_draft(
            system_pool,
            draft_guid=draft_guid,
            draft_table=draft_table_norm,
        )
        return {
            "success": True,
            "message": "Draft validiert",
            **result,
        }
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Draft-Validierung fehlgeschlagen: {exc}")


@router.post("/{draft_guid}/ensure-step")
async def ensure_draft_step(
    draft_guid: str,
    payload: EnsureDraftStepRequest,
    gcs=Depends(get_gcs_instance),
    operator_user: dict = Depends(require_admin_or_develop_user),
):
    system_pool = _require_system_pool(gcs)

    try:
        user_guid = _extract_user_guid(operator_user, gcs)
        draft_table_norm = _resolve_draft_table(draft_table=payload.draft_table)
        data = await WorkflowDraftService.load_draft(
            system_pool,
            draft_guid=draft_guid,
            draft_table=draft_table_norm,
        )
        root = data.get("root") if isinstance(data.get("root"), dict) else {}
        items = data.get("items") if isinstance(data.get("items"), list) else []

        work_item = None
        for item in items:
            item_type = str(item.get("item_type") or "").strip().lower()
            item_key = str(item.get("item_key") or "").strip().lower()
            if item_type == "work" and item_key == "container":
                work_item = item
                break

        work_payload = work_item.get("payload") if work_item and isinstance(work_item.get("payload"), dict) else {}
        work_payload = dict(work_payload)
        workflow_meta = work_payload.get("WORKFLOW") if isinstance(work_payload.get("WORKFLOW"), dict) else {}
        workflow_meta = dict(workflow_meta)

        workflow_name = _normalize_workflow_name(payload_workflow=workflow_meta, draft_root=root)
        workflow_type = str(workflow_meta.get("WORKFLOW_TYPE") or root.get("WORKFLOW_TYPE") or "work").strip().lower() or "work"
        target_table = str(workflow_meta.get("TARGET_TABLE") or "sys_dialogdaten").strip() or "sys_dialogdaten"
        module_norm = str(payload.module or "").strip().lower()
        tab_table = str(payload.table or "").strip().lower()

        workflow_meta["WORKFLOW_NAME"] = workflow_name
        workflow_meta["WORKFLOW_TYPE"] = workflow_type
        workflow_meta["DIALOG_TYPE"] = "work"
        workflow_meta["TARGET_TABLE"] = target_table
        workflow_meta["DRAFT_GUID"] = str(data.get("draft_guid") or draft_guid)
        work_payload["WORKFLOW"] = workflow_meta

        created: Dict[str, str] = {}
        if module_norm == "edit" and tab_table:
            work_payload, uid_value = await WorkflowDraftAccess.ensure_table_record_in_payload(
                system_pool,
                payload=work_payload,
                table_name=tab_table,
                workflow_name=workflow_name,
                workflow_type=workflow_type,
                target_table=target_table,
                single_record=True,
            )
            bucket_name = _normalize_bucket_name(tab_table)
            created[bucket_name] = uid_value
        elif not tab_table:
            if int(payload.step) >= 3:
                work_payload, dialog_uid = await WorkflowDraftAccess.ensure_table_record_in_payload(
                    system_pool,
                    payload=work_payload,
                    table_name="sys_dialogdaten",
                    workflow_name=workflow_name,
                    workflow_type=workflow_type,
                    target_table=target_table,
                    single_record=True,
                )
                created["SYS_DIALOGDATEN"] = dialog_uid

            if int(payload.step) >= 4:
                work_payload, view_uid = await WorkflowDraftAccess.ensure_table_record_in_payload(
                    system_pool,
                    payload=work_payload,
                    table_name="sys_viewdaten",
                    workflow_name=workflow_name,
                    workflow_type=workflow_type,
                    target_table=target_table,
                    single_record=True,
                )
                created["SYS_VIEWDATEN"] = view_uid

            if int(payload.step) >= 5:
                work_payload, frame_uid = await WorkflowDraftAccess.ensure_table_record_in_payload(
                    system_pool,
                    payload=work_payload,
                    table_name="sys_framedaten",
                    workflow_name=workflow_name,
                    workflow_type=workflow_type,
                    target_table=target_table,
                    single_record=True,
                )
                created["SYS_FRAMEDATEN"] = frame_uid

        work_payload = await WorkflowDraftAccess.sanitize_work_container_payload(
            system_pool,
            work_payload,
        )

        saved = await WorkflowDraftService.save_draft_item(
            system_pool,
            draft_guid=draft_guid,
            item_type="work",
            item_key="container",
            payload=work_payload,
            updated_by_user_guid=user_guid,
            draft_table=draft_table_norm,
        )

        return {
            "success": True,
            "message": "Workflow-Step geprueft/angelegt",
            "draft_guid": str(data.get("draft_guid") or draft_guid),
            "step": int(payload.step),
            "workflow_name": workflow_name,
            "created_or_present": created,
            "work_item_uid": str(saved.get("item_uid") or ""),
        }
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Workflow-Step konnte nicht vorbereitet werden: {exc}")


@router.get("/{draft_guid}/records/{table_name}")
async def list_draft_table_records(
    draft_guid: str,
    table_name: str,
    draft_table: Optional[str] = None,
    gcs=Depends(get_gcs_instance),
    _operator: dict = Depends(require_admin_or_develop_user),
):
    system_pool = _require_system_pool(gcs)

    try:
        draft_table_norm = _resolve_draft_table(draft_table=draft_table)
        rows = await WorkflowDraftAccess.list_table_records(
            system_pool,
            draft_guid=draft_guid,
            table_name=table_name,
            draft_table=draft_table_norm,
        )
        return {
            "success": True,
            "table": str(table_name or "").strip().lower(),
            "count": len(rows),
            "records": rows,
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Draft-Records konnten nicht geladen werden: {exc}")


@router.post("/{draft_guid}/records/{table_name}")
async def upsert_draft_table_record(
    draft_guid: str,
    table_name: str,
    payload: UpsertDraftTableRecordRequest,
    gcs=Depends(get_gcs_instance),
    operator_user: dict = Depends(require_admin_or_develop_user),
):
    system_pool = _require_system_pool(gcs)

    try:
        user_guid = _extract_user_guid(operator_user, gcs)
        draft_table_norm = _resolve_draft_table(draft_table=payload.draft_table)
        saved = await WorkflowDraftAccess.save_table_record(
            system_pool,
            draft_guid=draft_guid,
            table_name=table_name,
            record_uid=payload.record_uid,
            payload=payload.payload,
            updated_by_user_guid=user_guid,
            draft_table=draft_table_norm,
            single_record=bool(payload.single_record),
        )
        return {
            "success": True,
            "message": "Draft-Record gespeichert",
            **saved,
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Draft-Record konnte nicht gespeichert werden: {exc}")

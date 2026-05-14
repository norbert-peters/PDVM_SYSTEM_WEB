"""Workflow Draft API (Minimal Vertical Slice).

Endpoints fuer den Testdialog-Lebenszyklus:
- create draft
- save setup/item
- load draft
- list open drafts
- validate draft
"""
from __future__ import annotations

from typing import Any, Dict, Optional
import copy
import json
import re
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.security import get_current_user, require_admin_or_develop_user
from app.core.pdvm_central_systemsteuerung import get_gcs_session
from app.core.workflow_draft_service import WorkflowDraftService


router = APIRouter()
_TABLE_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class CreateDraftRequest(BaseModel):
    workflow_type: str = Field(default="work", description="Workflow-Typ")
    title: str = Field(..., min_length=1, description="Anzeigename des Drafts")
    initial_setup: Optional[Dict[str, Any]] = Field(default=None, description="Optionaler Setup-Block")
    draft_table: Optional[str] = Field(default=None)
    draft_item_table: Optional[str] = Field(default=None)


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
    draft_item_table: Optional[str] = Field(default=None)


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


def _resolve_draft_tables(
    *,
    draft_table: Optional[str],
    draft_item_table: Optional[str],
) -> tuple[str, str]:
    draft_table_norm = _normalize_table_name(
        draft_table,
        label="draft_table",
        default="dev_workflow_draft",
    )
    draft_item_table_norm = _normalize_table_name(
        draft_item_table,
        label="draft_item_table",
        default="dev_workflow_draft_item",
    )
    return draft_table_norm, draft_item_table_norm


async def _load_table_666(system_pool, table_name: str) -> Dict[str, Any]:
    async with system_pool.acquire() as conn:
        row = await conn.fetchrow(
            f"SELECT daten FROM {table_name} WHERE uid = $1::uuid AND COALESCE(historisch, 0) = 0",
            uuid.UUID("66666666-6666-6666-6666-666666666666"),
        )
    if not row:
        raise HTTPException(status_code=500, detail=f"Template 666 fehlt in {table_name}")

    data = row.get("daten")
    if isinstance(data, dict):
        return data
    if isinstance(data, str):
        try:
            parsed = json.loads(data)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def _normalize_workflow_name(*, payload_workflow: Dict[str, Any], draft_root: Dict[str, Any]) -> str:
    from_work = str(payload_workflow.get("WORKFLOW_NAME") or "").strip()
    from_title = str(draft_root.get("TITLE") or "").strip()
    return from_title or from_work or "WORKFLOW_DRAFT"


def _normalize_bucket_name(table_name: str) -> str:
    table = str(table_name or "").strip().lower()
    return table


def _ensure_bucket_record(
    *,
    payload: Dict[str, Any],
    bucket_name: str,
    template_666: Dict[str, Any],
    workflow_name: str,
    workflow_type: str,
    target_table: str,
    table_for_root: str,
    edit_type_for_root: str,
) -> str:
    bucket_raw = payload.get(bucket_name)
    bucket = bucket_raw if isinstance(bucket_raw, dict) else {}
    if bucket:
        payload[bucket_name] = bucket
        existing_uid = next(iter(bucket.keys()))
        return str(existing_uid)

    record_uid = str(uuid.uuid4())
    record_data = copy.deepcopy(template_666)
    root = record_data.get("ROOT") if isinstance(record_data.get("ROOT"), dict) else {}
    root = dict(root)
    root["SELF_GUID"] = record_uid
    root["SELF_NAME"] = workflow_name
    root["TABLE"] = table_for_root
    if edit_type_for_root:
        root["EDIT_TYPE"] = edit_type_for_root
    root["WORKFLOW_TYPE"] = workflow_type
    root["TARGET_TABLE"] = target_table
    record_data["ROOT"] = root

    bucket[record_uid] = record_data
    payload[bucket_name] = bucket
    return record_uid


@router.post("/bootstrap")
async def bootstrap_workflow_draft_tables(
    draft_table: Optional[str] = None,
    draft_item_table: Optional[str] = None,
    gcs=Depends(get_gcs_instance),
    _operator: dict = Depends(require_admin_or_develop_user),
):
    if not getattr(gcs, "_pool_system", None):
        raise HTTPException(status_code=500, detail="Systemdatenbank-Pool nicht verfuegbar")

    draft_table_norm, draft_item_table_norm = _resolve_draft_tables(
        draft_table=draft_table,
        draft_item_table=draft_item_table,
    )
    result = await WorkflowDraftService.ensure_draft_tables(
        gcs._pool_system,
        draft_table=draft_table_norm,
        draft_item_table=draft_item_table_norm,
    )
    return {
        "success": True,
        "message": "Workflow-Draft-Tabellen geprueft/angelegt",
        **result,
    }


@router.post("/create")
async def create_draft(
    payload: CreateDraftRequest,
    gcs=Depends(get_gcs_instance),
    operator_user: dict = Depends(require_admin_or_develop_user),
):
    if not getattr(gcs, "_pool_system", None):
        raise HTTPException(status_code=500, detail="Systemdatenbank-Pool nicht verfuegbar")

    try:
        user_guid = _extract_user_guid(operator_user, gcs)
        mandant_guid = _extract_mandant_guid(gcs)
        draft_table_norm, draft_item_table_norm = _resolve_draft_tables(
            draft_table=payload.draft_table,
            draft_item_table=payload.draft_item_table,
        )

        created = await WorkflowDraftService.create_draft(
            gcs._pool_system,
            workflow_type=payload.workflow_type,
            title=payload.title,
            owner_user_guid=user_guid,
            mandant_guid=mandant_guid,
            initial_setup=payload.initial_setup,
            draft_table=draft_table_norm,
            draft_item_table=draft_item_table_norm,
        )

        # Komfort: initial_setup als setup-item persistieren, wenn vorhanden.
        if isinstance(payload.initial_setup, dict) and payload.initial_setup:
            await WorkflowDraftService.save_draft_item(
                gcs._pool_system,
                draft_guid=created["draft_guid"],
                item_type="setup",
                item_key="setup",
                payload=payload.initial_setup,
                updated_by_user_guid=user_guid,
                draft_table=draft_table_norm,
                draft_item_table=draft_item_table_norm,
            )

        if str(payload.workflow_type or "").strip().lower() != "dictionary_builder":
            await WorkflowDraftService.save_draft_item(
                gcs._pool_system,
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
                    "sys_dialogdaten": {},
                    "sys_viewdaten": {},
                    "sys_framedaten": {},
                },
                updated_by_user_guid=user_guid,
                draft_table=draft_table_norm,
                draft_item_table=draft_item_table_norm,
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
    draft_item_table: Optional[str] = None,
    gcs=Depends(get_gcs_instance),
    operator_user: dict = Depends(require_admin_or_develop_user),
):
    if not getattr(gcs, "_pool_system", None):
        raise HTTPException(status_code=500, detail="Systemdatenbank-Pool nicht verfuegbar")

    try:
        user_guid = _extract_user_guid(operator_user, gcs)
        draft_table_norm, draft_item_table_norm = _resolve_draft_tables(
            draft_table=draft_table,
            draft_item_table=draft_item_table,
        )
        result = await WorkflowDraftService.save_draft_item(
            gcs._pool_system,
            draft_guid=draft_guid,
            item_type=payload.item_type,
            item_key=payload.item_key,
            payload=payload.payload,
            updated_by_user_guid=user_guid,
            draft_table=draft_table_norm,
            draft_item_table=draft_item_table_norm,
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
    draft_item_table: Optional[str] = None,
    gcs=Depends(get_gcs_instance),
    _operator: dict = Depends(require_admin_or_develop_user),
):
    if not getattr(gcs, "_pool_system", None):
        raise HTTPException(status_code=500, detail="Systemdatenbank-Pool nicht verfuegbar")

    try:
        draft_table_norm, draft_item_table_norm = _resolve_draft_tables(
            draft_table=draft_table,
            draft_item_table=draft_item_table,
        )
        data = await WorkflowDraftService.load_draft(
            gcs._pool_system,
            draft_guid=draft_guid,
            draft_table=draft_table_norm,
            draft_item_table=draft_item_table_norm,
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
    draft_item_table: Optional[str] = None,
    gcs=Depends(get_gcs_instance),
    operator_user: dict = Depends(require_admin_or_develop_user),
):
    if not getattr(gcs, "_pool_system", None):
        raise HTTPException(status_code=500, detail="Systemdatenbank-Pool nicht verfuegbar")

    try:
        user_guid = _extract_user_guid(operator_user, gcs)
        mandant_guid = _extract_mandant_guid(gcs)
        draft_table_norm, draft_item_table_norm = _resolve_draft_tables(
            draft_table=draft_table,
            draft_item_table=draft_item_table,
        )
        result = await WorkflowDraftService.list_open_drafts(
            gcs._pool_system,
            owner_user_guid=user_guid,
            mandant_guid=mandant_guid,
            draft_table=draft_table_norm,
            draft_item_table=draft_item_table_norm,
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
    draft_item_table: Optional[str] = None,
    gcs=Depends(get_gcs_instance),
    _operator: dict = Depends(require_admin_or_develop_user),
):
    if not getattr(gcs, "_pool_system", None):
        raise HTTPException(status_code=500, detail="Systemdatenbank-Pool nicht verfuegbar")

    try:
        draft_table_norm, draft_item_table_norm = _resolve_draft_tables(
            draft_table=draft_table,
            draft_item_table=draft_item_table,
        )
        result = await WorkflowDraftService.validate_draft(
            gcs._pool_system,
            draft_guid=draft_guid,
            draft_table=draft_table_norm,
            draft_item_table=draft_item_table_norm,
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
    if not getattr(gcs, "_pool_system", None):
        raise HTTPException(status_code=500, detail="Systemdatenbank-Pool nicht verfuegbar")

    try:
        user_guid = _extract_user_guid(operator_user, gcs)
        draft_table_norm, draft_item_table_norm = _resolve_draft_tables(
            draft_table=payload.draft_table,
            draft_item_table=payload.draft_item_table,
        )
        data = await WorkflowDraftService.load_draft(
            gcs._pool_system,
            draft_guid=draft_guid,
            draft_table=draft_table_norm,
            draft_item_table=draft_item_table_norm,
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
        # Standardregel: Nur Edit-Tabs führen zu tabellenbezogener Neuanlage im work-Container.
        if module_norm == "edit" and tab_table:
            table_666 = await _load_table_666(gcs._pool_system, tab_table)
            edit_type_for_root = "pdvm_edit"
            if tab_table == "sys_viewdaten":
                edit_type_for_root = "view"
            elif tab_table == "sys_dialogdaten":
                edit_type_for_root = "work"

            bucket_name = _normalize_bucket_name(tab_table)
            uid_value = _ensure_bucket_record(
                payload=work_payload,
                bucket_name=bucket_name,
                template_666=table_666,
                workflow_name=workflow_name,
                workflow_type=workflow_type,
                target_table=target_table,
                table_for_root=tab_table,
                edit_type_for_root=edit_type_for_root,
            )
            created[bucket_name] = uid_value
        elif not tab_table:
            # Legacy-Fallback ohne Tabellen-Metadaten (bestehende Aufrufer).
            if int(payload.step) >= 3:
                dialog_666 = await _load_table_666(gcs._pool_system, "sys_dialogdaten")
                dialog_uid = _ensure_bucket_record(
                    payload=work_payload,
                    bucket_name="sys_dialogdaten",
                    template_666=dialog_666,
                    workflow_name=workflow_name,
                    workflow_type=workflow_type,
                    target_table=target_table,
                    table_for_root="sys_dialogdaten",
                    edit_type_for_root="work",
                )
                created["sys_dialogdaten"] = dialog_uid

            if int(payload.step) >= 4:
                view_666 = await _load_table_666(gcs._pool_system, "sys_viewdaten")
                view_uid = _ensure_bucket_record(
                    payload=work_payload,
                    bucket_name="sys_viewdaten",
                    template_666=view_666,
                    workflow_name=workflow_name,
                    workflow_type=workflow_type,
                    target_table=target_table,
                    table_for_root="sys_viewdaten",
                    edit_type_for_root="view",
                )
                created["sys_viewdaten"] = view_uid

            if int(payload.step) >= 5:
                frame_666 = await _load_table_666(gcs._pool_system, "sys_framedaten")
                frame_uid = _ensure_bucket_record(
                    payload=work_payload,
                    bucket_name="sys_framedaten",
                    template_666=frame_666,
                    workflow_name=workflow_name,
                    workflow_type=workflow_type,
                    target_table=target_table,
                    table_for_root="sys_framedaten",
                    edit_type_for_root="pdvm_edit",
                )
                created["sys_framedaten"] = frame_uid

        saved = await WorkflowDraftService.save_draft_item(
            gcs._pool_system,
            draft_guid=draft_guid,
            item_type="work",
            item_key="container",
            payload=work_payload,
            updated_by_user_guid=user_guid,
            draft_table=draft_table_norm,
            draft_item_table=draft_item_table_norm,
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

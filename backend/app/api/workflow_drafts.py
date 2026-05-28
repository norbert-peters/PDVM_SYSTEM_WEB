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
_UID_555 = uuid.UUID("55555555-5555-5555-5555-555555555555")
_UID_666 = uuid.UUID("66666666-6666-6666-6666-666666666666")
_WORK_BUCKET_TABLE_MAP = {
    "SYS_DIALOGDATEN": "sys_dialogdaten",
    "SYS_VIEWDATEN": "sys_viewdaten",
    "SYS_FRAMEDATEN": "sys_framedaten",
}


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


def _merge_defined_fields(template_dict: Dict[str, Any], incoming: Dict[str, Any]) -> Dict[str, Any]:
    result = copy.deepcopy(template_dict) if isinstance(template_dict, dict) else {}
    if not isinstance(incoming, dict):
        return result

    for key, value in incoming.items():
        if key not in result:
            continue
        existing = result.get(key)
        if isinstance(existing, dict) and isinstance(value, dict):
            result[key] = _merge_defined_fields(existing, value)
        else:
            result[key] = value
    return result


def _fill_empty_groups_from_template(base: Dict[str, Any], fallback: Dict[str, Any]) -> Dict[str, Any]:
    out = copy.deepcopy(base) if isinstance(base, dict) else {}
    tpl = fallback if isinstance(fallback, dict) else {}

    for key, value in list(out.items()):
        tpl_value = tpl.get(key)
        if not isinstance(value, dict):
            continue
        if not value and isinstance(tpl_value, dict):
            out[key] = copy.deepcopy(tpl_value)
            continue
        if isinstance(tpl_value, dict):
            out[key] = _fill_empty_groups_from_template(value, tpl_value)
    return out


async def _load_row_daten_by_uid(system_pool, *, table_name: str, row_uid: uuid.UUID) -> Dict[str, Any]:
    async with system_pool.acquire() as conn:
        row = await conn.fetchrow(
            f"SELECT daten FROM {table_name} WHERE uid = $1::uuid AND COALESCE(historisch, 0) = 0",
            row_uid,
        )
    if not row:
        raise HTTPException(status_code=500, detail=f"Template fehlt in {table_name}: {row_uid}")

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


async def _build_table_record_from_templates(
    system_pool,
    *,
    table_name: str,
    record_uid: str,
    workflow_name: str,
    workflow_type: str,
    target_table: str,
    incoming_record: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    table_norm = _normalize_table_name(table_name, label="table_name", default=table_name)
    data_555 = await _load_row_daten_by_uid(system_pool, table_name=table_norm, row_uid=_UID_555)
    data_666 = await _load_row_daten_by_uid(system_pool, table_name=table_norm, row_uid=_UID_666)

    templates_666 = data_666.get("TEMPLATES") if isinstance(data_666.get("TEMPLATES"), dict) else {}
    incoming = incoming_record if isinstance(incoming_record, dict) else {}

    out: Dict[str, Any] = {}

    for group_name, group_value in data_555.items():
        if str(group_name).upper() == "ROOT":
            continue
        if not isinstance(group_value, dict):
            continue

        fallback_group = templates_666.get(group_name) if isinstance(templates_666.get(group_name), dict) else {}
        merged_group = _fill_empty_groups_from_template(group_value, fallback_group)

        incoming_group = incoming.get(group_name)
        if isinstance(incoming_group, dict):
            merged_group = _merge_defined_fields(merged_group, incoming_group)

        out[str(group_name)] = merged_group

    root_555 = data_555.get("ROOT") if isinstance(data_555.get("ROOT"), dict) else {}
    incoming_root = incoming.get("ROOT") if isinstance(incoming.get("ROOT"), dict) else {}
    root = _merge_defined_fields(root_555, incoming_root)
    root = _merge_defined_fields(
        root,
        {
            "SELF_GUID": str(record_uid),
            "SELF_NAME": str(workflow_name or "").strip() or "WORKFLOW_DRAFT",
            "WORKFLOW_TYPE": str(workflow_type or "").strip().lower() or "work",
            "TARGET_TABLE": str(target_table or "").strip() or "sys_dialogdaten",
        },
    )
    out["ROOT"] = root

    return out


async def _sanitize_work_container_payload(system_pool, payload: Dict[str, Any], *, draft_guid: str) -> Dict[str, Any]:
    src = payload if isinstance(payload, dict) else {}
    workflow = src.get("WORKFLOW") if isinstance(src.get("WORKFLOW"), dict) else {}
    workflow_name = str(workflow.get("WORKFLOW_NAME") or "").strip() or "WORKFLOW_DRAFT"
    workflow_type = str(workflow.get("WORKFLOW_TYPE") or "work").strip().lower() or "work"
    target_table = str(workflow.get("TARGET_TABLE") or "sys_dialogdaten").strip() or "sys_dialogdaten"

    out: Dict[str, Any] = {
        "WORKFLOW": dict(workflow),
    }

    for bucket_name, table_name in _WORK_BUCKET_TABLE_MAP.items():
        bucket_src = src.get(bucket_name)
        if not isinstance(bucket_src, dict):
            bucket_src = src.get(bucket_name.lower()) if isinstance(src.get(bucket_name.lower()), dict) else {}

        bucket_out: Dict[str, Any] = {}
        for rec_uid_raw, rec_payload in bucket_src.items():
            rec_uid = str(rec_uid_raw or "").strip()
            try:
                rec_uid = str(uuid.UUID(rec_uid))
            except Exception:
                rec_uid = str(uuid.uuid4())

            rec_data = rec_payload if isinstance(rec_payload, dict) else {}
            bucket_out[rec_uid] = await _build_table_record_from_templates(
                system_pool,
                table_name=table_name,
                record_uid=rec_uid,
                workflow_name=workflow_name,
                workflow_type=workflow_type,
                target_table=target_table,
                incoming_record=rec_data,
            )

        out[bucket_name] = bucket_out

    return out


async def _ensure_bucket_record(
    *,
    system_pool,
    payload: Dict[str, Any],
    bucket_name: str,
    table_name: str,
    workflow_name: str,
    workflow_type: str,
    target_table: str,
) -> str:
    bucket_raw = payload.get(bucket_name)
    bucket = bucket_raw if isinstance(bucket_raw, dict) else {}
    if bucket:
        existing_uid = str(next(iter(bucket.keys())))
        existing_data = bucket.get(existing_uid) if isinstance(bucket.get(existing_uid), dict) else {}
        bucket[existing_uid] = await _build_table_record_from_templates(
            system_pool,
            table_name=table_name,
            record_uid=existing_uid,
            workflow_name=workflow_name,
            workflow_type=workflow_type,
            target_table=target_table,
            incoming_record=existing_data,
        )
        payload[bucket_name] = bucket
        return existing_uid

    record_uid = str(uuid.uuid4())
    record_data = await _build_table_record_from_templates(
        system_pool,
        table_name=table_name,
        record_uid=record_uid,
        workflow_name=workflow_name,
        workflow_type=workflow_type,
        target_table=target_table,
        incoming_record={},
    )

    bucket[record_uid] = record_data
    payload[bucket_name] = bucket
    return record_uid


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
            payload_data = await _sanitize_work_container_payload(
                system_pool,
                payload.payload,
                draft_guid=draft_guid,
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
            bucket_name = _normalize_bucket_name(tab_table)
            uid_value = await _ensure_bucket_record(
                system_pool=system_pool,
                payload=work_payload,
                bucket_name=bucket_name,
                table_name=tab_table,
                workflow_name=workflow_name,
                workflow_type=workflow_type,
                target_table=target_table,
            )
            created[bucket_name] = uid_value
        elif not tab_table:
            if int(payload.step) >= 3:
                dialog_uid = await _ensure_bucket_record(
                    system_pool=system_pool,
                    payload=work_payload,
                    bucket_name="SYS_DIALOGDATEN",
                    table_name="sys_dialogdaten",
                    workflow_name=workflow_name,
                    workflow_type=workflow_type,
                    target_table=target_table,
                )
                created["SYS_DIALOGDATEN"] = dialog_uid

            if int(payload.step) >= 4:
                view_uid = await _ensure_bucket_record(
                    system_pool=system_pool,
                    payload=work_payload,
                    bucket_name="SYS_VIEWDATEN",
                    table_name="sys_viewdaten",
                    workflow_name=workflow_name,
                    workflow_type=workflow_type,
                    target_table=target_table,
                )
                created["SYS_VIEWDATEN"] = view_uid

            if int(payload.step) >= 5:
                frame_uid = await _ensure_bucket_record(
                    system_pool=system_pool,
                    payload=work_payload,
                    bucket_name="SYS_FRAMEDATEN",
                    table_name="sys_framedaten",
                    workflow_name=workflow_name,
                    workflow_type=workflow_type,
                    target_table=target_table,
                )
                created["SYS_FRAMEDATEN"] = frame_uid

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

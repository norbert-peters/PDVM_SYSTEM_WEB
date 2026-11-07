"""Dialogs API

Erster MVP-Dialog:
- Dialogdefinition aus sys_dialogdaten
- 2 Tabs: View (uid+name) + Edit (show_json)

Wichtig: Keine SQL im Router. Zugriff über app.core.dialog_service.
"""

from __future__ import annotations

import uuid
import re
import json
import copy
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.security import get_current_user, has_admin_rights, has_develop_rights
from app.core.pdvm_central_systemsteuerung import get_gcs_session
from app.core.dialog_service import (
    build_dialog_draft_from_template,
    create_dialog_record_from_template,
    extract_dialog_runtime_config,
    list_public_table_names,
    load_dialog_definition,
    load_dialog_record,
    load_dialog_rows_uid_name,
    load_frame_definition,
    update_dialog_record_json,
    update_dialog_record_central,
    validate_dialog_daten_generic,
)
from app.core.pdvm_datenbank import PdvmDatabase
from app.core.control_template_service import ControlTemplateService
from app.core.workflow_draft_access import WorkflowDraftAccess
from app.core.workflow_draft_service import WorkflowDraftService
from app.core.dialog_api_helpers import (
    _CONFLICT_MESSAGE,
    _DEFAULT_EDIT_TYPE_CONTRACTS,
    _EDIT_TYPE_POLICY_PATH,
    _SYS_FIELD_DRAFTS,
    _SYS_FIELD_LAST_CALL,
    _SYS_FIELD_UI_STATE,
    _TABLE_NAME_RE,
    _WORK_DIALOG_ROOT_TABLE,
    _as_dict,
    _clear_last_call_for_table,
    _clear_legacy_last_call_map,
    _coerce_dialog_drafts,
    _compute_dialog_ui_state_group,
    _compute_last_call_key,
    _edit_type_contract,
    _ensure_allowed_edit_type,
    _ensure_module_allows_write,
    _get_edit_type_contracts,
    _is_central_edit_type,
    _is_snapshot_conflict,
    _is_work_dialog,
    _normalize_dialog_table,
    _normalize_last_call_payload,
    _normalize_table_name,
    _pick_edit_target,
    _read_dialog_drafts,
    _read_last_call_scoped_by_table,
    _read_ui_state,
    _reload_systemsteuerung_instance,
    _resolve_dialog_scope,
    _resolve_runtime_root_table,
    _should_defer_template_resolution,
    _table_key_upper,
    _use_raw_json_payload,
    _write_dialog_drafts,
)
from app.core.dialog_create_helpers import (
    _bootstrap_workflow_draft_records,
    _build_root_patch_from_create_context,
    _build_workflow_setup_payload,
    _extract_create_required_fields,
    _extract_uuid_or_fail,
    _extract_work_draft_table,
    _missing_required_create_fields,
    _normalize_create_context,
    _normalize_create_context_with_alias,
    _normalize_storage_scope,
    _require_draft_guid_for_scope,
    _resolve_dialog_storage_scope,
    _resolve_effective_root_table,
)
from app.api.dialogs_models import (
    DialogCreateTableOption,
    DialogCreateTableOptionsResponse,
    DialogDefinitionResponse,
    DialogDraftCommitRequest,
    DialogDraftResponse,
    DialogDraftStartRequest,
    DialogDraftUpdateRequest,
    DialogLastCallResponse,
    DialogLastCallUpdateRequest,
    DialogRecordCreateRequest,
    DialogRecordResponse,
    DialogRecordUpdateRequest,
    DialogRow,
    DialogRowsRequest,
    DialogRowsResponse,
    DialogUiStateResponse,
    DialogUiStateUpdateRequest,
    DialogValidationIssue,
    FrameDefinitionResponse,
    ModulSelectionRequest,
    ModulSelectionRequiredResponse,
    ModulSelectionResponse,
)

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


@router.get("/{dialog_guid}/create-table-options", response_model=DialogCreateTableOptionsResponse)
async def get_create_table_options(
    dialog_guid: str,
    gcs=Depends(get_gcs_instance),
    current_user: dict = Depends(get_current_user),
):
    try:
        uuid.UUID(dialog_guid)
    except Exception:
        raise HTTPException(status_code=400, detail="Ungültige dialog_guid")

    is_develop = has_develop_rights(current_user)
    is_admin = has_admin_rights(current_user)
    if not is_admin and not is_develop:
        raise HTTPException(status_code=403, detail="Admin- oder Develop-Recht erforderlich")

    system_tables = await list_public_table_names(getattr(gcs, "_system_pool", None))
    mandant_tables = await list_public_table_names(getattr(gcs, "_mandant_pool", None))

    out: List[DialogCreateTableOption] = []
    seen: set[str] = set()

    def _append_tables(values: List[str], scope: str) -> None:
        for t in values:
            table_name = str(t or "").strip()
            if not table_name:
                continue
            key = table_name.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(
                DialogCreateTableOption(
                    value=table_name,
                    label=f"{table_name} ({scope})",
                    scope=scope,
                )
            )

    # Rollenregel:
    # - admin: nur Mandanten-Tabellen
    # - develop: System + Mandanten-Tabellen
    # - admin+develop: System + Mandanten-Tabellen (Develop-Sicht)
    if is_admin and is_develop:
        _append_tables(system_tables, "system")
        _append_tables(mandant_tables, "mandant")
        role = "admin+develop"
    elif is_admin:
        _append_tables(mandant_tables, "mandant")
        role = "admin"
    elif is_develop:
        _append_tables(system_tables, "system")
        _append_tables(mandant_tables, "mandant")
        role = "develop"
    else:
        role = "unknown"

    return {
        "role": role,
        "tables": out,
    }


@router.get("/frame/{frame_guid}", response_model=FrameDefinitionResponse)
async def get_frame_definition(frame_guid: str, gcs=Depends(get_gcs_instance)):
    try:
        frame_uuid = uuid.UUID(frame_guid)
    except Exception:
        raise HTTPException(status_code=400, detail="Ungültige frame_guid")

    try:
        return await load_frame_definition(gcs, frame_uuid)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Frame nicht gefunden: {frame_guid}")


@router.get("/{dialog_guid}", response_model=DialogDefinitionResponse)
async def get_dialog_definition(dialog_guid: str, dialog_table: Optional[str] = None, gcs=Depends(get_gcs_instance)):
    try:
        dialog_uuid = uuid.UUID(dialog_guid)
    except Exception:
        raise HTTPException(status_code=400, detail="Ungültige dialog_guid")

    try:
        dialog_def = await load_dialog_definition(gcs, dialog_uuid)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Dialog nicht gefunden: {dialog_guid}")

    runtime = extract_dialog_runtime_config(dialog_def)

    dialog_table_norm = _normalize_dialog_table(dialog_table)
    _resolve_runtime_root_table(runtime, dialog_table_norm=dialog_table_norm)

    frame_payload = None
    frame_guid = runtime.get("frame_guid")
    if frame_guid:
        try:
            frame_uuid = uuid.UUID(frame_guid)
            frame_payload = await load_frame_definition(gcs, frame_uuid)
        except Exception:
            # Frame ist optional; Dialog soll trotzdem rendern.
            frame_payload = None

    # last_call aus sys_systemsteuerung (pro User): group = dialog_guid
    # table-scoped: TABLE + LAST_CALL (Objekt: {"LAST_CALL": <uid|null>})
    last_call_key = _compute_last_call_key(runtime, dialog_guid=str(dialog_uuid))
    root_table = _resolve_runtime_root_table(runtime)
    last_call_str = None
    if last_call_key:
        table_key = _table_key_upper(root_table)
        if table_key:
            try:
                existing_raw, _ = gcs.systemsteuerung.get_value(last_call_key, table_key, ab_zeit=gcs.stichtag)
            except Exception:
                existing_raw = None

            # Read-only in GET: fehlendes Feld nicht mehr sofort persistieren,
            # um Snapshot-Konflikte in parallelen Requests zu vermeiden.
            if existing_raw is None:
                last_call_str = None
            else:
                payload = _normalize_last_call_payload(existing_raw)
                value = payload.get(_SYS_FIELD_LAST_CALL) if _SYS_FIELD_LAST_CALL in payload else None
                last_call_str = str(value).strip() if value is not None else None

    return {
        **dialog_def,
        "root_table": runtime.get("root_table") or "",
        "dialog_type": runtime.get("dialog_type") or "norm",
        "view_guid": runtime.get("view_guid"),
        "edit_type": runtime.get("edit_type") or "show_json",
        "selection_mode": runtime.get("selection_mode") or "single",
        "open_edit_mode": runtime.get("open_edit_mode") or "button",
        "frame_guid": frame_guid,
        "frame": frame_payload,
        "tab_modules": runtime.get("tab_modules") or [],
        "meta": {
            "tabs": runtime.get("tabs", 2),
            "dialog_table": dialog_table_norm,
            "expert_mode": bool(gcs.get_expert_mode()),
            "last_call": last_call_str,
            "last_call_key": f"{last_call_key}::{_table_key_upper(root_table)}" if last_call_key and root_table else last_call_key,
            "last_call_scope": "dialog_guid+table",
            "last_call_scope_dialog_guid": str(dialog_uuid),
            "last_call_scope_table": _table_key_upper(root_table),
        },
    }


@router.get("/{dialog_guid}/last-call", response_model=DialogLastCallResponse)
async def get_dialog_last_call(dialog_guid: str, dialog_table: Optional[str] = None, gcs=Depends(get_gcs_instance)):
    try:
        dialog_uuid = uuid.UUID(dialog_guid)
    except Exception:
        raise HTTPException(status_code=400, detail="Ungültige dialog_guid")

    try:
        dialog_def = await load_dialog_definition(gcs, dialog_uuid)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Dialog nicht gefunden: {dialog_guid}")

    runtime = extract_dialog_runtime_config(dialog_def)

    dialog_table_norm = _normalize_dialog_table(dialog_table)
    root_table = _resolve_runtime_root_table(runtime, dialog_table_norm=dialog_table_norm)

    key = _compute_last_call_key(runtime, dialog_guid=str(dialog_uuid))
    if not key:
        return {"key": "", "last_call": None}

    last_call = await _read_last_call_scoped_by_table(gcs, key=key, root_table=root_table)

    return {"key": key, "last_call": last_call}


@router.put("/{dialog_guid}/last-call", response_model=DialogLastCallResponse)
async def put_dialog_last_call(
    dialog_guid: str,
    payload: DialogLastCallUpdateRequest,
    dialog_table: Optional[str] = None,
    gcs=Depends(get_gcs_instance),
):
    try:
        dialog_uuid = uuid.UUID(dialog_guid)
    except Exception:
        raise HTTPException(status_code=400, detail="Ungültige dialog_guid")

    try:
        dialog_def = await load_dialog_definition(gcs, dialog_uuid)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Dialog nicht gefunden: {dialog_guid}")

    runtime = extract_dialog_runtime_config(dialog_def)

    dialog_table_norm = _normalize_dialog_table(dialog_table)
    root_table = _resolve_runtime_root_table(runtime, dialog_table_norm=dialog_table_norm)

    key = _compute_last_call_key(runtime, dialog_guid=str(dialog_uuid))
    if not key:
        raise HTTPException(status_code=400, detail="dialog_guid fehlt/ungueltig - last_call kann nicht gesetzt werden")

    record_uid = payload.record_uid
    if record_uid is not None:
        s = str(record_uid).strip()
        if s == "":
            record_uid = None
        else:
            try:
                uuid.UUID(s)
            except Exception:
                raise HTTPException(status_code=400, detail="Ungültige record_uid")
            record_uid = s

    table_key = _table_key_upper(root_table)
    if not table_key:
        raise HTTPException(status_code=400, detail="ROOT.TABLE ist leer")

    # Persist per dialog_guid + table (payload contains LAST_CALL only).
    payload = {_SYS_FIELD_LAST_CALL: record_uid if record_uid is not None else None}
    gcs.systemsteuerung.set_value(key, table_key, payload, gcs.stichtag)
    await gcs.systemsteuerung.save_all_values()

    return {"key": key, "last_call": record_uid}


@router.post("/{dialog_guid}/draft/start", response_model=DialogDraftResponse)
async def post_dialog_draft_start(
    dialog_guid: str,
    payload: DialogDraftStartRequest,
    dialog_table: Optional[str] = None,
    gcs=Depends(get_gcs_instance),
    current_user: dict = Depends(get_current_user),
):
    try:
        dialog_uuid = uuid.UUID(dialog_guid)
    except Exception:
        raise HTTPException(status_code=400, detail="Ungültige dialog_guid")

    try:
        dialog_def = await load_dialog_definition(gcs, dialog_uuid)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Dialog nicht gefunden: {dialog_guid}")

    runtime = extract_dialog_runtime_config(dialog_def)
    dialog_table_norm = _normalize_dialog_table(dialog_table)
    root_table, edit_type = _pick_edit_target(runtime, dialog_table_norm)

    name = str(payload.name or "").strip()
    if not name:
        fallback_name = str(dialog_def.get("name") or "").strip()
        name = fallback_name if fallback_name else "Neuer Datensatz"

    template_uuid = None
    if payload.template_uid is not None:
        s = str(payload.template_uid).strip()
        if s:
            try:
                template_uuid = uuid.UUID(s)
            except Exception:
                raise HTTPException(status_code=400, detail="Ungültige template_uid")
    if template_uuid is None:
        template_uuid = uuid.UUID("66666666-6666-6666-6666-666666666666")

    root_patch = _build_root_patch_from_create_context(
        create_context=payload.create_context,
        is_template=payload.is_template if str(root_table).strip().lower() == "sys_menudaten" else None,
    )

    effective_root_table = _resolve_effective_root_table(
        runtime_root_table=root_table,
        create_context=payload.create_context,
    )
    if not effective_root_table:
        raise HTTPException(status_code=400, detail="ROOT.TABLE ist leer")

    if str(runtime.get("dialog_type") or "").strip().lower() == "work":
        system_pool = getattr(gcs, "_pool_system", None) or getattr(gcs, "_system_pool", None)
        if not system_pool:
            raise HTTPException(status_code=500, detail="Systemdatenbank-Pool nicht verfuegbar")
        draft_table = _extract_work_draft_table(dialog_def)
        await WorkflowDraftService.ensure_draft_tables(
            system_pool,
            draft_table=draft_table,
        )

    required_create_fields = _extract_create_required_fields(dialog_def)
    missing_create_fields = _missing_required_create_fields(
        create_context=payload.create_context,
        required_fields=required_create_fields,
        draft_name=name,
    )
    if missing_create_fields:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "Pflichtfelder für Create-Kontext fehlen",
                "missing_fields": missing_create_fields,
            },
        )

    try:
        defer_resolution = _should_defer_template_resolution(root_table=root_table, edit_type=edit_type)
        built = await build_dialog_draft_from_template(
            gcs,
            root_table=effective_root_table,
            name=name,
            template_uuid=template_uuid,
            root_patch=root_patch,
            modul_type=payload.modul_type,
            resolve_templates=not defer_resolution,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))

    workflow_bootstrap: Optional[Dict[str, Any]] = None
    if str(runtime.get("dialog_type") or "").strip().lower() == "work":
        draft_table = _extract_work_draft_table(dialog_def)
        workflow_bootstrap = await _bootstrap_workflow_draft_records(
            gcs=gcs,
            current_user=current_user,
            draft_name=name,
            create_context=payload.create_context,
            draft_table=draft_table,
        )

    if workflow_bootstrap:
        daten_obj = built.get("daten") if isinstance(built, dict) else None
        if not isinstance(daten_obj, dict):
            daten_obj = {}

        root_obj = daten_obj.get("ROOT") if isinstance(daten_obj.get("ROOT"), dict) else {}
        root_obj = dict(root_obj)
        root_obj["WORKFLOW_DRAFT_GUID"] = workflow_bootstrap["draft_guid"]
        root_obj["DIALOG_TYPE"] = "work"
        root_obj["TARGET_TABLE"] = workflow_bootstrap["setup"]["TARGET_TABLE"]
        root_obj["WORKFLOW_NAME"] = workflow_bootstrap["setup"]["WORKFLOW_NAME"]
        root_obj["DIALOG_UID"] = workflow_bootstrap["dialog_uid"]
        root_obj["WORK_ITEM_UID"] = workflow_bootstrap.get("work_item_uid") or ""
        daten_obj["ROOT"] = root_obj

        fields_obj = daten_obj.get("FIELDS") if isinstance(daten_obj.get("FIELDS"), dict) else {}
        fields_obj = dict(fields_obj)
        fields_obj["WORKFLOW_NAME"] = workflow_bootstrap["setup"]["WORKFLOW_NAME"]
        fields_obj["TARGET_TABLE"] = workflow_bootstrap["setup"]["TARGET_TABLE"]
        fields_obj["DESCRIPTION"] = workflow_bootstrap["setup"].get("DESCRIPTION") or ""
        daten_obj["FIELDS"] = fields_obj

        built["daten"] = daten_obj

    draft_id = str(uuid.uuid4())
    scope = _resolve_dialog_scope(dialog_guid, runtime)
    drafts = await _read_dialog_drafts(gcs, group=scope)
    drafts[draft_id] = {
        "draft_id": draft_id,
        "name": built["name"],
        "daten": built["daten"],
        "root_table": effective_root_table,
        "edit_type": edit_type,
        "template_uid": built.get("template_uid"),
        "sec_id": built.get("sec_id"),
        "create_context": _normalize_create_context(payload.create_context),
    }
    await _write_dialog_drafts(gcs, group=scope, drafts=drafts)

    issues = [
        DialogValidationIssue(**x)
        for x in validate_dialog_daten_generic(built["daten"], edit_type=edit_type)
    ]
    return {
        "draft_id": draft_id,
        "name": built["name"],
        "daten": built["daten"],
        "root_table": effective_root_table,
        "edit_type": edit_type,
        "validation_errors": issues,
    }


@router.put("/{dialog_guid}/draft/{draft_id}", response_model=DialogDraftResponse)
async def put_dialog_draft(
    dialog_guid: str,
    draft_id: str,
    payload: DialogDraftUpdateRequest,
    dialog_table: Optional[str] = None,
    gcs=Depends(get_gcs_instance),
):
    try:
        dialog_uuid = uuid.UUID(dialog_guid)
    except Exception:
        raise HTTPException(status_code=400, detail="Ungültige dialog_guid")

    try:
        dialog_def = await load_dialog_definition(gcs, dialog_uuid)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Dialog nicht gefunden: {dialog_guid}")

    runtime = extract_dialog_runtime_config(dialog_def)
    dialog_table_norm = _normalize_dialog_table(dialog_table)
    root_table, edit_type = _pick_edit_target(runtime, dialog_table_norm)
    scope = _resolve_dialog_scope(dialog_guid, runtime)
    drafts = await _read_dialog_drafts(gcs, group=scope)
    current = drafts.get(draft_id)
    if not isinstance(current, dict):
        raise HTTPException(status_code=404, detail="Draft nicht gefunden")

    # Draft-Zieltabelle bleibt stabil aus dem Start-Flow.
    root_table = str(current.get("root_table") or root_table).strip()

    daten = payload.daten
    if daten is None or not isinstance(daten, dict):
        raise HTTPException(status_code=400, detail="daten muss ein JSON-Objekt sein")

    current["daten"] = daten
    current["root_table"] = root_table
    current["edit_type"] = edit_type
    drafts[draft_id] = current
    await _write_dialog_drafts(gcs, group=scope, drafts=drafts)

    issues = [
        DialogValidationIssue(**x)
        for x in validate_dialog_daten_generic(daten, edit_type=edit_type)
    ]
    return {
        "draft_id": draft_id,
        "name": str(current.get("name") or ""),
        "daten": daten,
        "root_table": root_table,
        "edit_type": edit_type,
        "validation_errors": issues,
    }


@router.post("/{dialog_guid}/draft/{draft_id}/commit", response_model=DialogRecordResponse)
async def post_dialog_draft_commit(
    dialog_guid: str,
    draft_id: str,
    payload: DialogDraftCommitRequest,
    dialog_table: Optional[str] = None,
    gcs=Depends(get_gcs_instance),
):
    try:
        dialog_uuid = uuid.UUID(dialog_guid)
    except Exception:
        raise HTTPException(status_code=400, detail="Ungültige dialog_guid")

    try:
        dialog_def = await load_dialog_definition(gcs, dialog_uuid)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Dialog nicht gefunden: {dialog_guid}")

    runtime = extract_dialog_runtime_config(dialog_def)
    dialog_table_norm = _normalize_dialog_table(dialog_table)
    root_table, edit_type = _pick_edit_target(runtime, dialog_table_norm)
    scope = _resolve_dialog_scope(dialog_guid, runtime)
    drafts = await _read_dialog_drafts(gcs, group=scope)
    current = drafts.get(draft_id)
    if not isinstance(current, dict):
        raise HTTPException(status_code=404, detail="Draft nicht gefunden")

    # Commit muss gegen dieselbe Zieltabelle laufen wie Draft-Start.
    root_table = str(current.get("root_table") or root_table).strip()

    daten = payload.daten if isinstance(payload.daten, dict) else current.get("daten")
    if daten is None or not isinstance(daten, dict):
        raise HTTPException(status_code=400, detail="daten muss ein JSON-Objekt sein")

    issues_raw = validate_dialog_daten_generic(daten, edit_type=edit_type)
    blocking_issues = [
        issue for issue in issues_raw
        if not str((issue or {}).get("code") or "").strip().lower().startswith("hint_")
    ]
    if blocking_issues:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "Validierung fehlgeschlagen",
                "validation_errors": blocking_issues,
            },
        )

    name = str(current.get("name") or "").strip()
    if not name:
        root_name = str(((daten.get("ROOT") or {}) if isinstance(daten, dict) else {}).get("SELF_NAME") or "").strip()
        name = root_name
    if not name:
        raise HTTPException(status_code=400, detail="name ist leer")

    template_uid_str = str(current.get("template_uid") or "").strip()
    try:
        template_uuid = uuid.UUID(template_uid_str) if template_uid_str else uuid.UUID("66666666-6666-6666-6666-666666666666")
    except Exception:
        template_uuid = uuid.UUID("66666666-6666-6666-6666-666666666666")

    create_context = _normalize_create_context(payload.create_context)
    if not create_context:
        create_context = _normalize_create_context(current.get("create_context"))

    root_patch = _build_root_patch_from_create_context(create_context=create_context)
    root = daten.get("ROOT") if isinstance(daten, dict) else None
    if isinstance(root, dict):
        root_patch = {
            **(root_patch or {}),
            **dict(root),
        }

    try:
        defer_resolution = _should_defer_template_resolution(root_table=root_table, edit_type=edit_type)
        created = await create_dialog_record_from_template(
            gcs,
            root_table=root_table,
            name=name,
            template_uuid=template_uuid,
            root_patch=root_patch,
            modul_type=None,
            resolve_templates=not defer_resolution,
        )
        record_uuid = uuid.UUID(created["uid"])
        daten_to_save = dict(daten)
        root_to_save = daten_to_save.get("ROOT") if isinstance(daten_to_save.get("ROOT"), dict) else {}
        root_to_save = dict(root_to_save)
        root_to_save["SELF_GUID"] = str(record_uuid)
        if not str(root_to_save.get("SELF_NAME") or "").strip():
            root_to_save["SELF_NAME"] = name
        daten_to_save["ROOT"] = root_to_save
        _ensure_module_allows_write(runtime, edit_type=edit_type)
        _ensure_allowed_edit_type(edit_type, operation="write")
        if _is_central_edit_type(edit_type):
            saved = await update_dialog_record_central(gcs, root_table=root_table, record_uuid=record_uuid, daten=daten_to_save)
        else:
            saved = await update_dialog_record_json(
                gcs,
                root_table=root_table,
                record_uuid=record_uuid,
                daten=daten_to_save,
                resolve_response_effective=not _use_raw_json_payload(edit_type),
            )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))

    drafts.pop(draft_id, None)
    await _write_dialog_drafts(gcs, group=scope, drafts=drafts)
    return saved


@router.post("/{dialog_guid}/rows", response_model=DialogRowsResponse)
async def post_dialog_rows(
    dialog_guid: str,
    payload: DialogRowsRequest,
    dialog_table: Optional[str] = None,
    storage_scope: Optional[str] = None,
    draft_guid: Optional[str] = None,
    gcs=Depends(get_gcs_instance),
):
    try:
        dialog_uuid = uuid.UUID(dialog_guid)
    except Exception:
        raise HTTPException(status_code=400, detail="Ungültige dialog_guid")

    try:
        dialog_def = await load_dialog_definition(gcs, dialog_uuid)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Dialog nicht gefunden: {dialog_guid}")

    runtime = extract_dialog_runtime_config(dialog_def)
    dialog_table_norm = _normalize_dialog_table(dialog_table)
    table = _resolve_runtime_root_table(runtime, dialog_table_norm=dialog_table_norm)
    scope_raw = storage_scope if storage_scope is not None else payload.storage_scope
    scope = _resolve_dialog_storage_scope(runtime, scope_raw)
    draft_guid_raw = draft_guid if draft_guid is not None else payload.draft_guid
    draft_guid_value = _require_draft_guid_for_scope(scope, draft_guid_raw)

    if not table:
        raise HTTPException(status_code=400, detail="Dialog ROOT.TABLE ist leer")

    if scope == "draft":
        system_pool = getattr(gcs, "_pool_system", None) or getattr(gcs, "_system_pool", None)
        if not system_pool:
            raise HTTPException(status_code=500, detail="Systemdatenbank-Pool nicht verfuegbar")

        draft_table = _extract_work_draft_table(dialog_def)
        records = await WorkflowDraftAccess.list_table_records(
            system_pool,
            draft_guid=draft_guid_value,
            table_name=table,
            draft_table=draft_table,
        )
        rows = [
            {
                "uid": str(uid),
                "name": str(_as_dict(_as_dict(record).get("ROOT")).get("SELF_NAME") or _as_dict(_as_dict(record).get("ROOT")).get("NAME") or uid),
            }
            for uid, record in records.items()
        ]
        rows = rows[payload.offset : payload.offset + payload.limit]
        return {
            "dialog_guid": dialog_guid,
            "table": table,
            "rows": rows,
            "meta": {
                "limit": payload.limit,
                "offset": payload.offset,
                "storage_scope": scope,
                "draft_guid": draft_guid_value,
            },
        }

    rows = await load_dialog_rows_uid_name(gcs, root_table=table, limit=payload.limit, offset=payload.offset)
    return {
        "dialog_guid": dialog_guid,
        "table": table,
        "rows": rows,
        "meta": {
            "limit": payload.limit,
            "offset": payload.offset,
            "storage_scope": scope,
            "draft_guid": draft_guid_value if scope == "draft" else None,
        },
    }


@router.get("/{dialog_guid}/record/{record_uid}", response_model=DialogRecordResponse)
async def get_dialog_record(
    dialog_guid: str,
    record_uid: str,
    dialog_table: Optional[str] = None,
    storage_scope: Optional[str] = None,
    draft_guid: Optional[str] = None,
    gcs=Depends(get_gcs_instance),
):
    try:
        dialog_uuid = uuid.UUID(dialog_guid)
    except Exception:
        raise HTTPException(status_code=400, detail="Ungültige dialog_guid")

    try:
        record_uuid = uuid.UUID(record_uid)
    except Exception:
        raise HTTPException(status_code=400, detail="Ungültige record uid")

    try:
        dialog_def = await load_dialog_definition(gcs, dialog_uuid)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Dialog nicht gefunden: {dialog_guid}")

    runtime = extract_dialog_runtime_config(dialog_def)
    dialog_table_norm = _normalize_dialog_table(dialog_table)
    table = _resolve_runtime_root_table(runtime, dialog_table_norm=dialog_table_norm)
    scope = _resolve_dialog_storage_scope(runtime, storage_scope)
    draft_guid_value = _require_draft_guid_for_scope(scope, draft_guid)

    if not table:
        raise HTTPException(status_code=400, detail="Dialog ROOT.TABLE ist leer")

    if scope == "draft":
        system_pool = getattr(gcs, "_pool_system", None) or getattr(gcs, "_system_pool", None)
        if not system_pool:
            raise HTTPException(status_code=500, detail="Systemdatenbank-Pool nicht verfuegbar")

        draft_table = _extract_work_draft_table(dialog_def)
        records = await WorkflowDraftAccess.list_table_records(
            system_pool,
            draft_guid=draft_guid_value,
            table_name=table,
            draft_table=draft_table,
        )
        record = records.get(str(record_uuid)) if isinstance(records, dict) else None
        if not isinstance(record, dict):
            raise HTTPException(status_code=404, detail=f"Datensatz nicht gefunden: {record_uid}")

        root = _as_dict(record.get("ROOT"))
        return {
            "uid": str(record_uuid),
            "name": str(root.get("SELF_NAME") or root.get("NAME") or ""),
            "daten": record,
            "historisch": 0,
            "modified_at": None,
        }

    edit_type = str(runtime.get("edit_type") or "show_json").strip().lower()
    resolve_effective = not _use_raw_json_payload(edit_type)

    try:
        return await load_dialog_record(
            gcs,
            root_table=table,
            record_uuid=record_uuid,
            resolve_effective=resolve_effective,
        )
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Datensatz nicht gefunden: {record_uid}")


@router.put("/{dialog_guid}/record/{record_uid}", response_model=DialogRecordResponse)
async def put_dialog_record(
    dialog_guid: str,
    record_uid: str,
    payload: DialogRecordUpdateRequest,
    dialog_table: Optional[str] = None,
    storage_scope: Optional[str] = None,
    draft_guid: Optional[str] = None,
    gcs=Depends(get_gcs_instance),
):
    """Aktualisiert einen Datensatz.

    Unterstützt:
    - EDIT_TYPE=edit_json (JSON Editor)
    - EDIT_TYPE=edit_user (PIC über PdvmCentralDatabase)
    """
    try:
        dialog_uuid = uuid.UUID(dialog_guid)
    except Exception:
        raise HTTPException(status_code=400, detail="Ungültige dialog_guid")

    try:
        record_uuid = uuid.UUID(record_uid)
    except Exception:
        raise HTTPException(status_code=400, detail="Ungültige record uid")

    try:
        dialog_def = await load_dialog_definition(gcs, dialog_uuid)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Dialog nicht gefunden: {dialog_guid}")

    runtime = extract_dialog_runtime_config(dialog_def)
    dialog_table_norm = _normalize_dialog_table(dialog_table)
    table = _resolve_runtime_root_table(runtime, dialog_table_norm=dialog_table_norm)
    scope_raw = storage_scope if storage_scope is not None else payload.storage_scope
    scope = _resolve_dialog_storage_scope(runtime, scope_raw)
    draft_guid_raw = draft_guid if draft_guid is not None else payload.draft_guid
    draft_guid_value = _require_draft_guid_for_scope(scope, draft_guid_raw)

    if not table:
        raise HTTPException(status_code=400, detail="Dialog ROOT.TABLE ist leer")

    if scope == "draft":
        system_pool = getattr(gcs, "_pool_system", None) or getattr(gcs, "_system_pool", None)
        if not system_pool:
            raise HTTPException(status_code=500, detail="Systemdatenbank-Pool nicht verfuegbar")

        user_guid = _extract_uuid_or_fail(label="user_guid", value=str(getattr(gcs, "user_guid", "") or ""))
        draft_table = _extract_work_draft_table(dialog_def)
        saved = await WorkflowDraftAccess.save_table_record(
            system_pool,
            draft_guid=draft_guid_value,
            table_name=table,
            record_uid=str(record_uuid),
            payload=payload.daten,
            updated_by_user_guid=user_guid,
            draft_table=draft_table,
            single_record=False,
        )
        record = _as_dict(saved.get("record"))
        root = _as_dict(record.get("ROOT"))
        return {
            "uid": str(saved.get("record_uid") or record_uuid),
            "name": str(root.get("SELF_NAME") or root.get("NAME") or ""),
            "daten": record,
            "historisch": 0,
            "modified_at": None,
        }

    edit_type = str(runtime.get("edit_type") or "show_json").strip().lower()
    _ensure_module_allows_write(runtime, edit_type=edit_type)
    _ensure_allowed_edit_type(edit_type, operation="write")

    try:
        if _is_central_edit_type(edit_type):
            return await update_dialog_record_central(gcs, root_table=table, record_uuid=record_uuid, daten=payload.daten)
        resolve_response_effective = not _use_raw_json_payload(edit_type)
        return await update_dialog_record_json(
            gcs,
            root_table=table,
            record_uuid=record_uuid,
            daten=payload.daten,
            resolve_response_effective=resolve_response_effective,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Datensatz nicht gefunden: {record_uid}")


# ===== edit_dict: Modul-Auswahl-Endpunkt =====

@router.get("/{dialog_guid}/modul-selection", response_model=ModulSelectionResponse)
async def get_modul_selection(
    dialog_guid: str,
    dialog_table: Optional[str] = None,
    gcs=Depends(get_gcs_instance),
):
    """Prüft ob Template MODUL-Gruppe enthält und returned verfügbare Module.
    
    GENERISCHE FUNKTION: Funktioniert für ALLE Tabellen!
    
    Frontend ruft dies auf BEVOR "Neuer Satz" erstellt wird.
    - Template 666... laden
    - Prüfen ob Gruppe "MODUL" existiert
    - Wenn ja → Template 555... laden und verfügbare Module extrahieren
    - Sonst → requires_modul_selection=False
    """
    try:
        dialog_uuid = uuid.UUID(dialog_guid)
    except Exception:
        raise HTTPException(status_code=400, detail="Ungültige dialog_guid")

    try:
        dialog_def = await load_dialog_definition(gcs, dialog_uuid)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Dialog nicht gefunden: {dialog_guid}")

    runtime = extract_dialog_runtime_config(dialog_def)
    dialog_table_norm = _normalize_dialog_table(dialog_table)
    table = _resolve_runtime_root_table(runtime, dialog_table_norm=dialog_table_norm)

    if not table:
        return ModulSelectionResponse(
            available_moduls=[],
            requires_modul_selection=False
        )
    
    # 1. Template 666... laden
    from app.core.pdvm_datenbank import PdvmDatabase
    db = PdvmDatabase(table, system_pool=gcs._system_pool, mandant_pool=gcs._mandant_pool)
    
    try:
        template_row = await db.get_by_uid(uuid.UUID("66666666-6666-6666-6666-666666666666"))
    except Exception:
        return ModulSelectionResponse(
            available_moduls=[],
            requires_modul_selection=False
        )
    
    if not template_row:
        return ModulSelectionResponse(
            available_moduls=[],
            requires_modul_selection=False
        )
    
    template_daten = template_row.get("daten")
    if isinstance(template_daten, str):
        try:
            template_daten = json.loads(template_daten)
        except Exception:
            template_daten = {}
    
    if not isinstance(template_daten, dict):
        return ModulSelectionResponse(
            available_moduls=[],
            requires_modul_selection=False
        )
    
    # 2. Prüfe: Gibt es Gruppe "MODUL"?
    has_modul = False
    for key, value in template_daten.items():
        if key.upper() == "ROOT":
            continue
        if isinstance(value, dict) and "MODUL" in value:
            has_modul = True
            break
    
    if not has_modul:
        return ModulSelectionResponse(
            available_moduls=[],
            requires_modul_selection=False
        )
    
    # 3. Template 555... laden für verfügbare Module
    try:
        modul_template_row = await db.get_by_uid(uuid.UUID("55555555-5555-5555-5555-555555555555"))
        if not modul_template_row:
            return ModulSelectionResponse(
                available_moduls=[],
                requires_modul_selection=False
            )
        
        modul_template_daten = modul_template_row.get("daten")
        if isinstance(modul_template_daten, str):
            modul_template_daten = json.loads(modul_template_daten)
        
        if not isinstance(modul_template_daten, dict):
            return ModulSelectionResponse(
                available_moduls=[],
                requires_modul_selection=False
            )
        
        modul_section = modul_template_daten.get("MODUL", {})
        if isinstance(modul_section, dict):
            available_moduls = list(modul_section.keys())
            return ModulSelectionResponse(
                available_moduls=available_moduls,
                requires_modul_selection=True
            )
    except Exception:
        pass
    
    return ModulSelectionResponse(
        available_moduls=[],
        requires_modul_selection=False
    )


@router.post("/{dialog_guid}/record", response_model=DialogRecordResponse)
async def post_dialog_record_create(
    dialog_guid: str,
    payload: DialogRecordCreateRequest,
    dialog_table: Optional[str] = None,
    storage_scope: Optional[str] = None,
    draft_guid: Optional[str] = None,
    gcs=Depends(get_gcs_instance),
):
    """Kompatibilitaets-Endpoint: nutzt denselben linearen Neuer-Satz-Flow wie Draft.

    Verbindlicher Ablauf:
    1) Build aus 666... + 5er-TEMPLATE-Gruppenmerge
    2) Validierung
    3) Persistenz ueber denselben Commit-Mechanismus
    """
    try:
        dialog_uuid = uuid.UUID(dialog_guid)
    except Exception:
        raise HTTPException(status_code=400, detail="Ungültige dialog_guid")

    try:
        dialog_def = await load_dialog_definition(gcs, dialog_uuid)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Dialog nicht gefunden: {dialog_guid}")

    runtime = extract_dialog_runtime_config(dialog_def)
    dialog_table_norm = _normalize_dialog_table(dialog_table)
    table = _resolve_runtime_root_table(runtime, dialog_table_norm=dialog_table_norm)
    scope_raw = storage_scope if storage_scope is not None else payload.storage_scope
    scope = _resolve_dialog_storage_scope(runtime, scope_raw)
    draft_guid_raw = draft_guid if draft_guid is not None else payload.draft_guid
    draft_guid_value = _require_draft_guid_for_scope(scope, draft_guid_raw)

    if not table:
        raise HTTPException(status_code=400, detail="Dialog ROOT.TABLE ist leer")

    name = str(payload.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name ist leer")

    template_uuid = None
    if payload.template_uid is not None:
        s = str(payload.template_uid).strip()
        if s:
            try:
                template_uuid = uuid.UUID(s)
            except Exception:
                raise HTTPException(status_code=400, detail="Ungültige template_uid")

    if scope == "draft":
        system_pool = getattr(gcs, "_pool_system", None) or getattr(gcs, "_system_pool", None)
        if not system_pool:
            raise HTTPException(status_code=500, detail="Systemdatenbank-Pool nicht verfuegbar")

        user_guid = _extract_uuid_or_fail(label="user_guid", value=str(getattr(gcs, "user_guid", "") or ""))

        effective_template_uuid = template_uuid or uuid.UUID("66666666-6666-6666-6666-666666666666")
        built = await build_dialog_draft_from_template(
            gcs,
            root_table=table,
            name=name,
            template_uuid=effective_template_uuid,
            root_patch=None,
            modul_type=payload.modul_type,
            resolve_templates=True,
        )
        draft_table = _extract_work_draft_table(dialog_def)
        saved = await WorkflowDraftAccess.save_table_record(
            system_pool,
            draft_guid=draft_guid_value,
            table_name=table,
            record_uid=None,
            payload=_as_dict(built.get("daten")),
            updated_by_user_guid=user_guid,
            draft_table=draft_table,
            single_record=False,
        )
        record = _as_dict(saved.get("record"))
        root = _as_dict(record.get("ROOT"))
        return {
            "uid": str(saved.get("record_uid") or ""),
            "name": str(root.get("SELF_NAME") or root.get("NAME") or name),
            "daten": record,
            "historisch": 0,
            "modified_at": None,
        }

    try:
        root_patch = None
        if str(table).strip().lower() == "sys_menudaten" and payload.is_template is not None:
            root_patch = {"is_template": bool(payload.is_template)}

        edit_type = runtime.get("edit_type") or "show_json"
        defer_resolution = _should_defer_template_resolution(root_table=table, edit_type=edit_type)
        effective_template_uuid = template_uuid or uuid.UUID("66666666-6666-6666-6666-666666666666")

        built = await build_dialog_draft_from_template(
            gcs,
            root_table=table,
            name=name,
            template_uuid=effective_template_uuid,
            root_patch=root_patch,
            modul_type=payload.modul_type,
            resolve_templates=not defer_resolution,
        )

        issues_raw = validate_dialog_daten_generic(built["daten"], edit_type=edit_type)
        blocking_issues = [
            issue for issue in issues_raw
            if not str((issue or {}).get("code") or "").strip().lower().startswith("hint_")
        ]
        if blocking_issues:
            raise HTTPException(
                status_code=422,
                detail={
                    "message": "Validierung fehlgeschlagen",
                    "validation_errors": blocking_issues,
                },
            )

        draft_root = built["daten"].get("ROOT") if isinstance(built["daten"], dict) else None
        created = await create_dialog_record_from_template(
            gcs,
            root_table=table,
            name=built["name"],
            template_uuid=effective_template_uuid,
            root_patch=dict(draft_root) if isinstance(draft_root, dict) else None,
            modul_type=None,
            resolve_templates=not defer_resolution,
        )

        record_uuid = uuid.UUID(created["uid"])
        daten_to_save = dict(built["daten"])
        root_to_save = daten_to_save.get("ROOT") if isinstance(daten_to_save.get("ROOT"), dict) else {}
        root_to_save = dict(root_to_save)
        root_to_save["SELF_GUID"] = str(record_uuid)
        if not str(root_to_save.get("SELF_NAME") or "").strip():
            root_to_save["SELF_NAME"] = built["name"]
        daten_to_save["ROOT"] = root_to_save

        _ensure_module_allows_write(runtime, edit_type=edit_type)
        _ensure_allowed_edit_type(edit_type, operation="write")
        if _is_central_edit_type(edit_type):
            return await update_dialog_record_central(gcs, root_table=table, record_uuid=record_uuid, daten=daten_to_save)
        return await update_dialog_record_json(
            gcs,
            root_table=table,
            record_uuid=record_uuid,
            daten=daten_to_save,
            resolve_response_effective=not _use_raw_json_payload(edit_type),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{dialog_guid}/ui-state", response_model=DialogUiStateResponse)
async def get_dialog_ui_state(dialog_guid: str, dialog_table: Optional[str] = None, gcs=Depends(get_gcs_instance)):
    try:
        dialog_uuid = uuid.UUID(dialog_guid)
    except Exception:
        raise HTTPException(status_code=400, detail="Ungültige dialog_guid")

    try:
        dialog_def = await load_dialog_definition(gcs, dialog_uuid)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Dialog nicht gefunden: {dialog_guid}")

    runtime = extract_dialog_runtime_config(dialog_def)
    dialog_table_norm = _normalize_dialog_table(dialog_table)
    table = _resolve_runtime_root_table(runtime, dialog_table_norm=dialog_table_norm)

    if not table:
        raise HTTPException(status_code=400, detail="Dialog ROOT.TABLE ist leer")

    edit_type = str(runtime.get("edit_type") or "show_json").strip().lower()
    group = _compute_dialog_ui_state_group(dialog_guid=dialog_guid, root_table=table, edit_type=edit_type)
    ui_state = await _read_ui_state(gcs, group=group)
    return {"group": group, "ui_state": ui_state}


@router.put("/{dialog_guid}/ui-state", response_model=DialogUiStateResponse)
async def put_dialog_ui_state(
    dialog_guid: str,
    payload: DialogUiStateUpdateRequest,
    dialog_table: Optional[str] = None,
    gcs=Depends(get_gcs_instance),
):
    try:
        dialog_uuid = uuid.UUID(dialog_guid)
    except Exception:
        raise HTTPException(status_code=400, detail="Ungültige dialog_guid")

    try:
        dialog_def = await load_dialog_definition(gcs, dialog_uuid)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Dialog nicht gefunden: {dialog_guid}")

    runtime = extract_dialog_runtime_config(dialog_def)
    dialog_table_norm = _normalize_dialog_table(dialog_table)
    table = _resolve_runtime_root_table(runtime, dialog_table_norm=dialog_table_norm)

    if not table:
        raise HTTPException(status_code=400, detail="Dialog ROOT.TABLE ist leer")

    edit_type = str(runtime.get("edit_type") or "show_json").strip().lower()
    group = _compute_dialog_ui_state_group(dialog_guid=dialog_guid, root_table=table, edit_type=edit_type)

    existing = await _read_ui_state(gcs, group=group)
    next_state = dict(existing or {})
    incoming = payload.ui_state if isinstance(payload.ui_state, dict) else {}
    next_state.update(incoming)

    gcs.systemsteuerung.set_value(group, _SYS_FIELD_UI_STATE, next_state, gcs.stichtag)
    await gcs.systemsteuerung.save_all_values()
    return {"group": group, "ui_state": next_state}

"""Create-Kontext- und Workflow-Draft-Helfer fuer die Dialogs-API (reine Verschiebung aus app/api/dialogs.py).
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional
from fastapi import HTTPException
from app.core.workflow_draft_service import WorkflowDraftService
from app.core.dialog_api_helpers import _TABLE_NAME_RE, _is_work_dialog, _normalize_table_name


def _normalize_create_context(raw: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        return {}

    out: Dict[str, Any] = {}
    for k, v in raw.items():
        key = str(k or "").strip().upper()
        if not key:
            continue
        out[key] = v
    return out


def _normalize_create_context_with_alias(raw: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    ctx = _normalize_create_context(raw)

    # Kompatible Alias-Auflösung: TABLE ist Pflicht in vielen Dialog-Validierungen.
    if not str(ctx.get("TABLE") or "").strip():
        for alias in ("ROOT_TABLE", "TARGET_TABLE", "DIALOG_TABLE"):
            value = ctx.get(alias)
            if str(value or "").strip():
                ctx["TABLE"] = str(value).strip()
                break

    return ctx


def _extract_create_required_fields(dialog_def: Optional[Dict[str, Any]]) -> List[str]:
    if not isinstance(dialog_def, dict):
        return []

    root = dialog_def.get("root")
    if not isinstance(root, dict):
        root = ((dialog_def.get("daten") or {}) if isinstance(dialog_def.get("daten"), dict) else {}).get("ROOT")
    if not isinstance(root, dict):
        return []

    raw = root.get("CREATE_REQUIRED")
    if raw is None:
        raw = root.get("create_required")

    values: List[str] = []
    if isinstance(raw, list):
        values = [str(x or "").strip().upper() for x in raw]
    elif isinstance(raw, str):
        values = [str(x or "").strip().upper() for x in raw.split(",")]

    out: List[str] = []
    for value in values:
        if not value:
            continue
        if value in out:
            continue
        out.append(value)
    return out


def _missing_required_create_fields(
    *,
    create_context: Optional[Dict[str, Any]],
    required_fields: List[str],
    draft_name: Optional[str] = None,
) -> List[str]:
    if not required_fields:
        return []

    ctx = _normalize_create_context_with_alias(create_context)
    name_value = str(draft_name or "").strip()
    missing: List[str] = []
    for field in required_fields:
        if field == "NAME" and name_value:
            continue
        value = ctx.get(field)
        if value is None:
            missing.append(field)
            continue
        if isinstance(value, str) and not value.strip():
            missing.append(field)
    return missing


def _resolve_effective_root_table(
    *,
    runtime_root_table: str,
    create_context: Optional[Dict[str, Any]],
) -> str:
    runtime_norm = _normalize_table_name(runtime_root_table)
    ctx = _normalize_create_context_with_alias(create_context)
    ctx_table = _normalize_table_name(ctx.get("TABLE"))

    # Wenn TABLE im Create-Kontext gesetzt ist, gilt diese als Zieltabelle.
    # Damit kann der Create-Dialog den Datensatz-Typ dynamisch steuern.
    if ctx_table:
        return ctx_table
    return runtime_norm


def _build_root_patch_from_create_context(
    *,
    create_context: Optional[Dict[str, Any]],
    is_template: Optional[bool] = None,
) -> Optional[Dict[str, Any]]:
    ctx = _normalize_create_context_with_alias(create_context)
    root_patch: Dict[str, Any] = {}

    if is_template is not None:
        # Rückwärtskompatibel: bestehende Daten nutzen das Feld in lowercase.
        root_patch["is_template"] = bool(is_template)

    # Alle Context-Werte als ROOT-Felder übernehmen (datengetriebenes Create-Frame-Verhalten).
    for key, value in ctx.items():
        root_patch[key] = value

    return root_patch or None


def _build_workflow_setup_payload(*, draft_name: str, create_context: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    ctx = _normalize_create_context_with_alias(create_context)
    target_table = str(ctx.get("TARGET_TABLE") or "").strip() or "sys_dialogdaten"
    workflow_name = str(ctx.get("WORKFLOW_NAME") or "").strip() or str(draft_name or "").strip()
    description = str(ctx.get("DESCRIPTION") or "").strip()

    return {
        "WORKFLOW_NAME": workflow_name,
        "DIALOG_TYPE": "work",
        "TARGET_TABLE": target_table,
        "DESCRIPTION": description,
    }


def _extract_work_draft_table(dialog_def: Optional[Dict[str, Any]]) -> str:
    root = (dialog_def or {}).get("root") if isinstance((dialog_def or {}).get("root"), dict) else {}
    if not isinstance(root, dict):
        root = {}

    draft_table = str(root.get("DRAFT_TABLE") or root.get("draft_table") or "dev_workflow_draft").strip().lower()
    if not _TABLE_NAME_RE.match(draft_table):
        raise HTTPException(status_code=422, detail="DRAFT_TABLE enthaelt ungueltige Zeichen")
    return draft_table


def _extract_uuid_or_fail(*, label: str, value: Optional[str]) -> str:
    token = str(value or "").strip()
    if not token:
        raise HTTPException(status_code=400, detail=f"{label} konnte nicht ermittelt werden")
    try:
        return str(uuid.UUID(token))
    except Exception:
        raise HTTPException(status_code=400, detail=f"{label} ist ungueltig")


def _normalize_storage_scope(storage_scope: Optional[str]) -> str:
    scope = str(storage_scope or "").strip().lower()
    if not scope:
        return "live"
    if scope not in {"live", "draft"}:
        raise HTTPException(status_code=400, detail="storage_scope muss 'live' oder 'draft' sein")
    return scope


def _resolve_dialog_storage_scope(runtime: Dict[str, Any], storage_scope: Optional[str]) -> str:
    scope = _normalize_storage_scope(storage_scope)
    # Work-Dialoge laufen standardmäßig im Draft-Scope.
    if (storage_scope is None or str(storage_scope).strip() == "") and _is_work_dialog(runtime):
        return "draft"
    return scope


def _require_draft_guid_for_scope(storage_scope: str, draft_guid: Optional[str]) -> str:
    if storage_scope != "draft":
        return ""
    return _extract_uuid_or_fail(label="draft_guid", value=draft_guid)


async def _bootstrap_workflow_draft_records(
    *,
    gcs,
    current_user: Dict[str, Any],
    draft_name: str,
    create_context: Optional[Dict[str, Any]],
    draft_table: str,
) -> Dict[str, Any]:
    system_pool = getattr(gcs, "_pool_system", None) or getattr(gcs, "_system_pool", None)
    if not system_pool:
        raise HTTPException(status_code=500, detail="Systemdatenbank-Pool nicht verfuegbar")

    user_guid = _extract_uuid_or_fail(
        label="user_guid",
        value=str(getattr(gcs, "user_guid", "") or current_user.get("sub") or ""),
    )
    mandant_guid = _extract_uuid_or_fail(
        label="mandant_guid",
        value=str(getattr(gcs, "mandant_guid", "") or ""),
    )

    setup_payload = _build_workflow_setup_payload(draft_name=draft_name, create_context=create_context)
    created = await WorkflowDraftService.create_draft(
        system_pool,
        workflow_type="work",
        title=str(draft_name).strip(),
        owner_user_guid=user_guid,
        mandant_guid=mandant_guid,
        initial_setup=setup_payload,
        draft_table=draft_table,
    )

    draft_guid = str(created.get("draft_guid") or "").strip()
    if not draft_guid:
        raise HTTPException(status_code=500, detail="Workflow-Draft konnte nicht angelegt werden")

    await WorkflowDraftService.save_draft_item(
        system_pool,
        draft_guid=draft_guid,
        item_type="setup",
        item_key="setup",
        payload=setup_payload,
        updated_by_user_guid=user_guid,
        draft_table=draft_table,
    )

    work_container_payload = {
        "WORKFLOW": {
            "DRAFT_GUID": draft_guid,
            "DRAFT_TABLE": draft_table,
            "WORKFLOW_NAME": setup_payload["WORKFLOW_NAME"],
            "DIALOG_TYPE": "work",
            "TARGET_TABLE": setup_payload["TARGET_TABLE"],
            "DESCRIPTION": setup_payload.get("DESCRIPTION") or "",
        },
        "sys_dialogdaten": {},
        "sys_viewdaten": {},
        "sys_framedaten": {},
    }

    work_item_result = await WorkflowDraftService.save_draft_item(
        system_pool,
        draft_guid=draft_guid,
        item_type="work",
        item_key="container",
        payload=work_container_payload,
        updated_by_user_guid=user_guid,
        draft_table=draft_table,
    )

    await WorkflowDraftService.update_draft_root_fields(
        system_pool,
        draft_guid=draft_guid,
        fields={
            "WORK_ITEM_UID": str(work_item_result.get("item_uid") or ""),
            "WORK_ITEM_TYPE": "work",
            "WORK_ITEM_KEY": "container",
        },
        draft_table=draft_table,
    )

    return {
        "draft_guid": draft_guid,
        "setup": setup_payload,
        "dialog_uid": "",
        "view_uid": "",
        "frame_uid": "",
        "work_item_uid": str(work_item_result.get("item_uid") or ""),
    }

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
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.security import get_current_user, has_admin_rights, has_develop_rights
from app.core.pdvm_central_systemsteuerung import get_gcs_session
from app.core.dialog_service import (
    build_dialog_draft_from_template,
    create_dialog_record_from_template,
    extract_dialog_runtime_config,
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
from app.core.workflow_draft_service import WorkflowDraftService

router = APIRouter()

_SYS_FIELD_LAST_CALL = "LAST_CALL"
_SYS_FIELD_UI_STATE = "UI_STATE"
_SYS_FIELD_DRAFTS = "DRAFTS"
_CENTRAL_EDIT_TYPES = {"edit_user", "import_data", "pdvm_edit", "edit_dict", "edit_control"}


_TABLE_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _normalize_dialog_table(dialog_table: Optional[str]) -> Optional[str]:
    if dialog_table is None:
        return None
    t = str(dialog_table).strip()
    if not t:
        return None
    # Security: PdvmDatabase uses the table name inside f-strings.
    if not _TABLE_NAME_RE.match(t):
        raise HTTPException(status_code=400, detail="Ungültige dialog_table (nur [A-Za-z0-9_] erlaubt)")
    return t


def _ensure_allowed_edit_type(edit_type: str):
    et = str(edit_type or "").strip().lower()
    if et not in {"show_json", "edit_json", "menu", "edit_user", "import_data", "pdvm_edit", "edit_dict", "edit_control"}:
        raise HTTPException(
            status_code=400,
            detail="Nur EDIT_TYPE show_json, edit_json, menu, edit_user, import_data, pdvm_edit, edit_dict und edit_control sind erlaubt",
        )


def _should_defer_template_resolution(*, root_table: str, edit_type: str) -> bool:
    # Neuer-Satz muss den linearen 6er→5er-Merge immer ausführen.
    # Defer wird hier bewusst deaktiviert.
    return False


def _normalize_table_name(value: Optional[str]) -> str:
    return str(value or "").strip().lower()


def _use_raw_json_payload(edit_type: Optional[str]) -> bool:
    et = str(edit_type or "").strip().lower()
    return et in {"show_json", "edit_json"}


def _table_key_upper(root_table: str) -> str:
    return str(root_table or "").strip().upper()


def _normalize_last_call_payload(raw: Any) -> Dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if raw is None:
        return {}
    try:
        import json

        parsed = json.loads(str(raw))
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


async def _clear_last_call_for_table(gcs, *, key: str, root_table: str) -> None:
    table_key = _table_key_upper(root_table)
    if not table_key:
        return

    gcs.systemsteuerung.set_value(key, table_key, {_SYS_FIELD_LAST_CALL: None}, gcs.stichtag)
    await gcs.systemsteuerung.save_all_values()


async def _clear_legacy_last_call_map(gcs, *, key: str) -> None:
    """Removes legacy LAST_CALL map under field LAST_CALL (old structure)."""
    try:
        raw, _ = gcs.systemsteuerung.get_value(key, _SYS_FIELD_LAST_CALL, ab_zeit=gcs.stichtag)
    except Exception:
        raw = None

    legacy = _normalize_last_call_payload(raw)
    if not legacy:
        return

    try:
        gcs.systemsteuerung.delete_field(key, _SYS_FIELD_LAST_CALL)
        await gcs.systemsteuerung.save_all_values()
    except Exception:
        pass


async def _read_last_call_scoped_by_table(
    gcs,
    *,
    key: str,
    root_table: str,
) -> Optional[str]:
    """Liest last_call aus sys_systemsteuerung.

    Datenmodell (vereinfacht):
    - Gruppe: view_guid
    - Feld: TABLE (Großbuchstaben)
    - Wert: {"LAST_CALL": <guid|null>}
    """

    table_norm = _normalize_table_name(root_table)
    if not table_norm:
        return None

    table_key = _table_key_upper(root_table)
    if not table_key:
        return None

    try:
        raw, _ = gcs.systemsteuerung.get_value(key, table_key, ab_zeit=gcs.stichtag)
    except Exception:
        return None

    if raw is None:
        return None

    payload = _normalize_last_call_payload(raw)
    if _SYS_FIELD_LAST_CALL in payload:
        value = payload.get(_SYS_FIELD_LAST_CALL)
    else:
        value = raw

    s = str(value).strip() if value is not None else ""
    if not s:
        return None

    try:
        return str(uuid.UUID(s))
    except Exception:
        return None


def _compute_last_call_key(runtime: Dict[str, Any], *, dialog_guid: Optional[str] = None) -> Optional[str]:
    """Berechnet den Persistenz-Key für last_call.

    PDVM-Dialog-Regel: last_call ist dialog-gebunden.
    Persistenz erfolgt pro dialog_guid + table.

    Returns:
        dialog_guid als String oder None wenn nicht vorhanden/ungültig.
    """

    dg = str(dialog_guid or "").strip()
    if not dg:
        return None

    try:
        return str(uuid.UUID(dg))
    except Exception:
        return None


def _compute_dialog_ui_state_group(*, dialog_guid: str, root_table: str, edit_type: str) -> str:
    """UI-State Persistenz-Key (pro User) für Dialog-spezifische UI-Zustände.

    Vorgabe: Composite-Key ("Kombi-Schlüssel") analog zum View-State, aber mit dialog_guid.
    Format: "{dialog_guid}::{table}::{edit_type}" (lower-case).
    """

    dg = str(dialog_guid or "").strip().lower()
    t = _normalize_table_name(root_table)
    et = str(edit_type or "").strip().lower()
    return f"{dg}::{t}::{et}".strip().lower()


async def _read_ui_state(gcs, *, group: str) -> Dict[str, Any]:
    try:
        raw, _ = gcs.systemsteuerung.get_value(group, _SYS_FIELD_UI_STATE, ab_zeit=gcs.stichtag)
    except Exception:
        return {}


def _coerce_dialog_drafts(raw: Any) -> Dict[str, Dict[str, Any]]:
    if not isinstance(raw, dict):
        return {}
    out: Dict[str, Dict[str, Any]] = {}
    for key, value in raw.items():
        k = str(key or "").strip()
        if not k:
            continue
        if isinstance(value, dict):
            out[k] = dict(value)
    return out


async def _read_dialog_drafts(gcs, *, group: str) -> Dict[str, Dict[str, Any]]:
    try:
        raw, _ = gcs.systemsteuerung.get_value(group, _SYS_FIELD_DRAFTS, ab_zeit=gcs.stichtag)
    except Exception:
        return {}

    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            return _coerce_dialog_drafts(parsed)
        except Exception:
            return {}
    return _coerce_dialog_drafts(raw)


async def _write_dialog_drafts(gcs, *, group: str, drafts: Dict[str, Dict[str, Any]]) -> None:
    gcs.systemsteuerung.set_value(group, _SYS_FIELD_DRAFTS, drafts, gcs.stichtag)
    await gcs.systemsteuerung.save_all_values()


def _resolve_dialog_scope(dialog_guid: str, runtime: Dict[str, Any]) -> str:
    root_table = runtime.get("root_table") or ""
    edit_type = runtime.get("edit_type") or "show_json"
    return _compute_dialog_ui_state_group(dialog_guid=dialog_guid, root_table=root_table, edit_type=edit_type)


def _pick_edit_target(runtime: Dict[str, Any], dialog_table_norm: Optional[str]) -> tuple[str, str]:
    if dialog_table_norm:
        _ensure_allowed_edit_type(runtime.get("edit_type") or "show_json")
        runtime["root_table"] = dialog_table_norm
        runtime["view_guid"] = None

    root_table = str(runtime.get("root_table") or "").strip()
    if not root_table:
        raise HTTPException(status_code=400, detail="Dialog ROOT.TABLE ist leer")
    edit_type = str(runtime.get("edit_type") or "show_json").strip().lower() or "show_json"
    return root_table, edit_type

    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw

    try:
        import json

        parsed = json.loads(str(raw))
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


class DialogUiStateResponse(BaseModel):
    group: str
    ui_state: Dict[str, Any] = Field(default_factory=dict)


class DialogUiStateUpdateRequest(BaseModel):
    ui_state: Dict[str, Any] = Field(default_factory=dict)


async def get_gcs_instance(current_user: dict = Depends(get_current_user)):
    token = current_user.get("token")
    if not token:
        raise HTTPException(status_code=401, detail="Kein Session-Token gefunden")

    gcs = get_gcs_session(token)
    if not gcs:
        raise HTTPException(status_code=404, detail="Keine GCS-Session gefunden. Bitte Mandant auswählen.")

    return gcs


class FrameDefinitionResponse(BaseModel):
    uid: str
    name: str
    daten: Dict[str, Any]
    root: Dict[str, Any]


class DialogDefinitionResponse(BaseModel):
    uid: str
    name: str
    daten: Dict[str, Any]
    root: Dict[str, Any]
    root_table: str
    dialog_type: Optional[str] = None
    view_guid: Optional[str] = None
    edit_type: str
    selection_mode: str = "single"
    open_edit_mode: str = "button"
    frame_guid: Optional[str] = None
    frame: Optional[FrameDefinitionResponse] = None
    tab_modules: List[Dict[str, Any]] = Field(default_factory=list)
    meta: Dict[str, Any] = Field(default_factory=dict)


class DialogRowsRequest(BaseModel):
    limit: int = Field(default=200, ge=1, le=2000)
    offset: int = Field(default=0, ge=0)


class DialogRow(BaseModel):
    uid: str
    name: str


class DialogRowsResponse(BaseModel):
    dialog_guid: str
    table: str
    rows: List[DialogRow]
    meta: Dict[str, Any] = Field(default_factory=dict)


class DialogRecordResponse(BaseModel):
    uid: str
    name: str
    daten: Dict[str, Any]
    historisch: int = 0
    modified_at: Optional[str] = None


class DialogRecordUpdateRequest(BaseModel):
    daten: Dict[str, Any]


class DialogRecordCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    template_uid: Optional[str] = None
    is_template: Optional[bool] = None
    modul_type: Optional[str] = Field(None, description="Für edit_dict: edit, view, tabs")


class DialogValidationIssue(BaseModel):
    group: str
    index: Optional[int] = None
    field: Optional[str] = None
    code: str
    message: str


class DialogDraftStartRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    template_uid: Optional[str] = None
    is_template: Optional[bool] = None
    modul_type: Optional[str] = Field(None, description="Für edit_dict: edit, view, tabs")
    create_context: Optional[Dict[str, Any]] = None


class DialogDraftUpdateRequest(BaseModel):
    daten: Dict[str, Any]


class DialogDraftCommitRequest(BaseModel):
    daten: Optional[Dict[str, Any]] = None
    create_context: Optional[Dict[str, Any]] = None


class DialogDraftResponse(BaseModel):
    draft_id: str
    name: str
    daten: Dict[str, Any]
    root_table: str
    edit_type: str
    validation_errors: List[DialogValidationIssue] = Field(default_factory=list)


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


def _extract_work_draft_tables(dialog_def: Optional[Dict[str, Any]]) -> tuple[str, str]:
    root = (dialog_def or {}).get("root") if isinstance((dialog_def or {}).get("root"), dict) else {}
    if not isinstance(root, dict):
        root = {}

    draft_table = str(root.get("DRAFT_TABLE") or root.get("draft_table") or "dev_workflow_draft").strip().lower()
    draft_item_table = str(root.get("DRAFT_ITEM_TABLE") or root.get("draft_item_table") or "dev_workflow_draft_item").strip().lower()
    if not _TABLE_NAME_RE.match(draft_table):
        raise HTTPException(status_code=422, detail="DRAFT_TABLE enthaelt ungueltige Zeichen")
    if not _TABLE_NAME_RE.match(draft_item_table):
        raise HTTPException(status_code=422, detail="DRAFT_ITEM_TABLE enthaelt ungueltige Zeichen")
    return draft_table, draft_item_table


def _extract_uuid_or_fail(*, label: str, value: Optional[str]) -> str:
    token = str(value or "").strip()
    if not token:
        raise HTTPException(status_code=400, detail=f"{label} konnte nicht ermittelt werden")
    try:
        return str(uuid.UUID(token))
    except Exception:
        raise HTTPException(status_code=400, detail=f"{label} ist ungueltig")


async def _bootstrap_workflow_draft_records(
    *,
    gcs,
    current_user: Dict[str, Any],
    draft_name: str,
    create_context: Optional[Dict[str, Any]],
    draft_table: str,
    draft_item_table: str,
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
        draft_item_table=draft_item_table,
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
        draft_item_table=draft_item_table,
    )

    work_container_payload = {
        "WORKFLOW": {
            "DRAFT_GUID": draft_guid,
            "DRAFT_TABLE": draft_table,
            "DRAFT_ITEM_TABLE": draft_item_table,
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
        draft_item_table=draft_item_table,
    )

    async with system_pool.acquire() as conn:
        row = await conn.fetchrow(
            f"SELECT daten FROM {draft_table} WHERE uid = $1::uuid AND COALESCE(historisch, 0) = 0",
            uuid.UUID(draft_guid),
        )
        if row:
            data = row.get("daten")
            draft_daten = data if isinstance(data, dict) else {}
            if not draft_daten and isinstance(data, str):
                try:
                    parsed = json.loads(data)
                    draft_daten = parsed if isinstance(parsed, dict) else {}
                except Exception:
                    draft_daten = {}
            draft_root = draft_daten.get("ROOT") if isinstance(draft_daten.get("ROOT"), dict) else {}
            draft_root = dict(draft_root)
            draft_root["WORK_ITEM_UID"] = str(work_item_result.get("item_uid") or "")
            draft_root["WORK_ITEM_TYPE"] = "work"
            draft_root["WORK_ITEM_KEY"] = "container"
            draft_daten["ROOT"] = draft_root
            await conn.execute(
                f"""
                UPDATE {draft_table}
                SET daten = $2::jsonb,
                    modified_at = NOW()
                WHERE uid = $1::uuid
                """,
                uuid.UUID(draft_guid),
                json.dumps(draft_daten, ensure_ascii=False),
            )

    return {
        "draft_guid": draft_guid,
        "setup": setup_payload,
        "dialog_uid": "",
        "view_uid": "",
        "frame_uid": "",
        "work_item_uid": str(work_item_result.get("item_uid") or ""),
    }


class ModulSelectionRequiredResponse(BaseModel):
    """Response wenn Modul-Auswahl erforderlich ist"""
    error: str = "modul_selection_required"
    message: str
    available_moduls: List[str]
    modul_group_key: str = Field(default="CONTROL", description="Gruppe wo MODUL gefunden wurde")


class DialogLastCallResponse(BaseModel):
    key: str
    last_call: Optional[str] = None


class DialogLastCallUpdateRequest(BaseModel):
    record_uid: Optional[str] = None


class DialogCreateTableOption(BaseModel):
    value: str
    label: str
    scope: str


class DialogCreateTableOptionsResponse(BaseModel):
    role: str
    tables: List[DialogCreateTableOption] = Field(default_factory=list)


async def _list_public_table_names(pool: Any) -> List[str]:
    if pool is None:
        return []
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            ORDER BY table_name
            """
        )
    return [str(r.get("table_name") or "").strip() for r in rows if str(r.get("table_name") or "").strip()]


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

    system_tables = await _list_public_table_names(getattr(gcs, "_system_pool", None))
    mandant_tables = await _list_public_table_names(getattr(gcs, "_mandant_pool", None))

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
    if dialog_table_norm:
        # Override mode: menu can point to any table.
        # Only JSON editor modes are permitted.
        _ensure_allowed_edit_type(runtime.get("edit_type") or "show_json")
        runtime["root_table"] = dialog_table_norm

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
    root_table = runtime.get("root_table") or ""
    last_call_str = None
    if last_call_key:
        table_key = _table_key_upper(root_table)
        if table_key:
            try:
                existing_raw, _ = gcs.systemsteuerung.get_value(last_call_key, table_key, ab_zeit=gcs.stichtag)
            except Exception:
                existing_raw = None

            # Wenn Feld fehlt → initialisieren mit LAST_CALL = None
            if existing_raw is None:
                gcs.systemsteuerung.set_value(last_call_key, table_key, {_SYS_FIELD_LAST_CALL: None}, gcs.stichtag)
                await gcs.systemsteuerung.save_all_values()
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
    if dialog_table_norm:
        _ensure_allowed_edit_type(runtime.get("edit_type") or "show_json")
        runtime["root_table"] = dialog_table_norm

    key = _compute_last_call_key(runtime, dialog_guid=str(dialog_uuid))
    root_table = runtime.get("root_table") or ""
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
    if dialog_table_norm:
        _ensure_allowed_edit_type(runtime.get("edit_type") or "show_json")
        runtime["root_table"] = dialog_table_norm

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

    root_table = runtime.get("root_table") or ""
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
        raise HTTPException(status_code=400, detail="name ist leer")

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
        draft_table, draft_item_table = _extract_work_draft_tables(dialog_def)
        await WorkflowDraftService.ensure_draft_tables(
            system_pool,
            draft_table=draft_table,
            draft_item_table=draft_item_table,
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
        draft_table, draft_item_table = _extract_work_draft_tables(dialog_def)
        workflow_bootstrap = await _bootstrap_workflow_draft_records(
            gcs=gcs,
            current_user=current_user,
            draft_name=name,
            create_context=payload.create_context,
            draft_table=draft_table,
            draft_item_table=draft_item_table,
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
        if edit_type in _CENTRAL_EDIT_TYPES:
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
async def post_dialog_rows(dialog_guid: str, payload: DialogRowsRequest, dialog_table: Optional[str] = None, gcs=Depends(get_gcs_instance)):
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
    if dialog_table_norm:
        _ensure_allowed_edit_type(runtime.get("edit_type") or "show_json")
        runtime["root_table"] = dialog_table_norm

    table = runtime.get("root_table") or ""
    if not table:
        raise HTTPException(status_code=400, detail="Dialog ROOT.TABLE ist leer")

    rows = await load_dialog_rows_uid_name(gcs, root_table=table, limit=payload.limit, offset=payload.offset)
    return {
        "dialog_guid": dialog_guid,
        "table": table,
        "rows": rows,
        "meta": {"limit": payload.limit, "offset": payload.offset},
    }


@router.get("/{dialog_guid}/record/{record_uid}", response_model=DialogRecordResponse)
async def get_dialog_record(dialog_guid: str, record_uid: str, dialog_table: Optional[str] = None, gcs=Depends(get_gcs_instance)):
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
    if dialog_table_norm:
        _ensure_allowed_edit_type(runtime.get("edit_type") or "show_json")
        runtime["root_table"] = dialog_table_norm

    table = runtime.get("root_table") or ""
    if not table:
        raise HTTPException(status_code=400, detail="Dialog ROOT.TABLE ist leer")

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
    if dialog_table_norm:
        _ensure_allowed_edit_type(runtime.get("edit_type") or "show_json")
        runtime["root_table"] = dialog_table_norm
        runtime["view_guid"] = None

    table = runtime.get("root_table") or ""
    if not table:
        raise HTTPException(status_code=400, detail="Dialog ROOT.TABLE ist leer")

    edit_type = str(runtime.get("edit_type") or "show_json").strip().lower()
    if edit_type not in {"edit_json", "edit_user", "import_data", "pdvm_edit", "edit_dict", "edit_control"}:
        raise HTTPException(
            status_code=400,
            detail="Dialog ist nicht für edit_json, edit_user, import_data, pdvm_edit, edit_dict oder edit_control konfiguriert",
        )

    try:
        if edit_type in _CENTRAL_EDIT_TYPES:
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

class ModulSelectionRequest(BaseModel):
    """Request für Modul-Auswahl bei edit_dict"""
    modul_type: str = Field(..., description="Gewählter MODUL_TYPE: edit, view, tabs")


class ModulSelectionResponse(BaseModel):
    """Response mit verfügbaren Modulen"""
    available_moduls: List[str] = Field(default_factory=list, description="Verfügbare MODUL-Typen")
    requires_modul_selection: bool = Field(default=False, description="True wenn Modul-Auswahl erforderlich ist")


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
    if dialog_table_norm:
        _ensure_allowed_edit_type(runtime.get("edit_type") or "show_json")
        runtime["root_table"] = dialog_table_norm
        runtime["view_guid"] = None

    table = runtime.get("root_table") or ""
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
    if dialog_table_norm:
        _ensure_allowed_edit_type(runtime.get("edit_type") or "show_json")
        runtime["root_table"] = dialog_table_norm
        runtime["view_guid"] = None

    table = runtime.get("root_table") or ""
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

        if edit_type in _CENTRAL_EDIT_TYPES:
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
    if dialog_table_norm:
        _ensure_allowed_edit_type(runtime.get("edit_type") or "show_json")
        runtime["root_table"] = dialog_table_norm

    table = runtime.get("root_table") or ""
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
    if dialog_table_norm:
        _ensure_allowed_edit_type(runtime.get("edit_type") or "show_json")
        runtime["root_table"] = dialog_table_norm

    table = runtime.get("root_table") or ""
    if not table:
        raise HTTPException(status_code=400, detail="Dialog ROOT.TABLE ist leer")

    edit_type = str(runtime.get("edit_type") or "show_json").strip().lower()
    group = _compute_dialog_ui_state_group(dialog_guid=dialog_guid, root_table=table, edit_type=edit_type)

    existing = await _read_ui_state(gcs, group=group)
    next_state = dict(existing)
    incoming = payload.ui_state if isinstance(payload.ui_state, dict) else {}
    next_state.update(incoming)

    gcs.systemsteuerung.set_value(group, _SYS_FIELD_UI_STATE, next_state, gcs.stichtag)
    await gcs.systemsteuerung.save_all_values()
    return {"group": group, "ui_state": next_state}

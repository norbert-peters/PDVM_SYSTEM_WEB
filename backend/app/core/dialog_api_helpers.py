"""Reine Helfer fuer die Dialogs-API: Edit-Type-Contracts, last_call-/UI-State-/Draft-Persistenz (reine Verschiebung aus app/api/dialogs.py).
"""

from __future__ import annotations

import uuid
import re
import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional
from fastapi import HTTPException


_SYS_FIELD_LAST_CALL = "LAST_CALL"
_SYS_FIELD_UI_STATE = "UI_STATE"
_SYS_FIELD_DRAFTS = "DRAFTS"
_CONFLICT_MESSAGE = "Daten zwischenzeitlich geändert. Bitte neu lesen"

_EDIT_TYPE_POLICY_PATH = Path(__file__).resolve().parents[2] / "config" / "dialog_view_frame_analyzer_policy_v1.json"
_DEFAULT_EDIT_TYPE_CONTRACTS: Dict[str, Dict[str, Any]] = {
    "show_json": {
        "status": "transitional",
        "scope": "developer json display",
        "allowed_operations": ["read"],
        "write_backend": "json",
        "raw_payload": True,
        "preferred_modules": ["show"],
    },
    "edit_json": {
        "status": "transitional",
        "scope": "developer json edit",
        "allowed_operations": ["read", "write"],
        "write_backend": "json",
        "raw_payload": True,
    },
    "menu": {
        "status": "stable",
        "scope": "menu management flows",
        "allowed_operations": ["read", "write"],
        "write_backend": "json",
        "raw_payload": False,
    },
    "edit_user": {
        "status": "stable",
        "scope": "user management flows",
        "allowed_operations": ["read", "write"],
        "write_backend": "central",
        "raw_payload": False,
    },
    "import_data": {
        "status": "stable",
        "scope": "import flows",
        "allowed_operations": ["read", "write"],
        "write_backend": "central",
        "raw_payload": False,
    },
    "pdvm_edit": {
        "status": "stable",
        "scope": "default edit modules",
        "allowed_operations": ["read", "write"],
        "write_backend": "central",
        "raw_payload": False,
    },
    "edit_dict": {
        "status": "approved",
        "scope": "dictionary flows",
        "allowed_operations": ["read", "write"],
        "write_backend": "central",
        "raw_payload": False,
    },
    "edit_control": {
        "status": "approved",
        "scope": "control dictionary and control editor flows",
        "allowed_operations": ["read", "write"],
        "write_backend": "central",
        "raw_payload": False,
    },
    "view": {
        "status": "stable",
        "scope": "view modules",
        "allowed_operations": ["read"],
        "write_backend": "json",
        "raw_payload": False,
    },
}


_TABLE_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_WORK_DIALOG_ROOT_TABLE = "dev_workflow_draft"


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


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _is_work_dialog(runtime: Dict[str, Any]) -> bool:
    return str((runtime or {}).get("dialog_type") or "").strip().lower() == "work"


def _resolve_runtime_root_table(runtime: Dict[str, Any], *, dialog_table_norm: Optional[str] = None) -> str:
    # Harte Regel: Work-Dialoge arbeiten immer auf dev_workflow_draft.
    if _is_work_dialog(runtime):
        runtime["root_table"] = _WORK_DIALOG_ROOT_TABLE
        return _WORK_DIALOG_ROOT_TABLE

    if dialog_table_norm:
        _ensure_allowed_edit_type(runtime.get("edit_type") or "show_json", operation="read")
        runtime["root_table"] = dialog_table_norm
        runtime["view_guid"] = None

    return str(runtime.get("root_table") or "").strip()


@lru_cache(maxsize=1)
def _get_edit_type_contracts() -> Dict[str, Dict[str, Any]]:
    contracts: Dict[str, Dict[str, Any]] = {k: dict(v) for k, v in _DEFAULT_EDIT_TYPE_CONTRACTS.items()}
    try:
        payload = json.loads(_EDIT_TYPE_POLICY_PATH.read_text(encoding="utf-8"))
    except Exception:
        payload = {}

    configured = _as_dict(_as_dict(payload).get("edit_type_contracts"))
    for et, contract in configured.items():
        et_norm = str(et or "").strip().lower()
        if not et_norm:
            continue
        merged = dict(contracts.get(et_norm, {}))
        if isinstance(contract, dict):
            merged.update(contract)
        if not isinstance(merged.get("allowed_operations"), list):
            merged["allowed_operations"] = ["read", "write"]
        if str(merged.get("write_backend") or "").strip().lower() not in {"central", "json"}:
            merged["write_backend"] = "json"
        if "raw_payload" not in merged:
            merged["raw_payload"] = et_norm in {"show_json", "edit_json"}
        contracts[et_norm] = merged
    return contracts


def _edit_type_contract(edit_type: str) -> Dict[str, Any]:
    et = str(edit_type or "").strip().lower()
    return _as_dict(_get_edit_type_contracts().get(et))


def _ensure_allowed_edit_type(edit_type: str, *, operation: str = "read"):
    et = str(edit_type or "").strip().lower()
    op = str(operation or "read").strip().lower() or "read"
    contract = _edit_type_contract(et)
    if not contract:
        allowed = ", ".join(sorted(_get_edit_type_contracts().keys()))
        raise HTTPException(
            status_code=400,
            detail=f"EDIT_TYPE '{et}' ist nicht im Contract hinterlegt. Erlaubt: {allowed}",
        )
    allowed_operations = [str(x).strip().lower() for x in contract.get("allowed_operations", [])]
    if op not in allowed_operations:
        raise HTTPException(status_code=400, detail=f"EDIT_TYPE '{et}' erlaubt keine Operation '{op}'")


def _ensure_module_allows_write(runtime: Dict[str, Any], *, edit_type: str) -> None:
    """Blockiert Write-Pfade hart für Modul 'show'."""
    et = str(edit_type or "").strip().lower()
    tabs = runtime.get("tab_modules") if isinstance(runtime, dict) else None
    if not isinstance(tabs, list) or not tabs:
        return

    for tm in tabs:
        if not isinstance(tm, dict):
            continue
        module = str(tm.get("module") or "").strip().lower()
        tab_et = str(tm.get("edit_type") or "").strip().lower()
        if module != "show":
            continue

        # Wenn der Tab den gleichen Edit-Typ trägt (oder show_json implizit ist), ist Write verboten.
        if tab_et == et or (et == "show_json" and not tab_et):
            raise HTTPException(
                status_code=400,
                detail="Write ist fuer MODULE=show nicht erlaubt (display-only).",
            )


def _is_central_edit_type(edit_type: str) -> bool:
    contract = _edit_type_contract(edit_type)
    backend = str(contract.get("write_backend") or "").strip().lower()
    return backend == "central"


def _should_defer_template_resolution(*, root_table: str, edit_type: str) -> bool:
    # Neuer-Satz muss den linearen 6er→5er-Merge immer ausführen.
    # Defer wird hier bewusst deaktiviert.
    return False


def _normalize_table_name(value: Optional[str]) -> str:
    return str(value or "").strip().lower()


def _use_raw_json_payload(edit_type: Optional[str]) -> bool:
    et = str(edit_type or "").strip().lower()
    contract = _edit_type_contract(et)
    if contract:
        return bool(contract.get("raw_payload"))
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

    if isinstance(raw, dict):
        return dict(raw)
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            return {}
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


def _is_snapshot_conflict(exc: Exception) -> bool:
    return _CONFLICT_MESSAGE in str(exc or "")


async def _reload_systemsteuerung_instance(gcs):
    current = gcs.systemsteuerung
    reloaded = await type(current).load(
        table_name=current.table_name,
        guid=str(current.guid),
        no_save=bool(current.no_save),
        stichtag=gcs.stichtag,
        system_pool=getattr(gcs, "_system_pool", None),
        mandant_pool=getattr(gcs, "_mandant_pool", None),
    )
    reloaded.actor_user_uid = getattr(current, "actor_user_uid", None)
    reloaded.actor_ip = getattr(current, "actor_ip", None)
    gcs.systemsteuerung = reloaded
    return reloaded


async def _write_dialog_drafts(gcs, *, group: str, drafts: Dict[str, Dict[str, Any]]) -> None:
    for attempt in range(3):
        gcs.systemsteuerung.set_value(group, _SYS_FIELD_DRAFTS, drafts, gcs.stichtag)
        try:
            await gcs.systemsteuerung.save_all_values()
            return
        except ValueError as exc:
            if not _is_snapshot_conflict(exc):
                raise

            if attempt == 0:
                await _reload_systemsteuerung_instance(gcs)
                continue

            if attempt == 1:
                # Letzter Fallback: ohne Snapshot-Guard speichern,
                # damit reine UI-Draft-States nicht mit 500 abbrechen.
                gcs.systemsteuerung._loaded_snapshot = None
                continue

            raise


def _resolve_dialog_scope(dialog_guid: str, runtime: Dict[str, Any]) -> str:
    root_table = _resolve_runtime_root_table(runtime)
    edit_type = runtime.get("edit_type") or "show_json"
    return _compute_dialog_ui_state_group(dialog_guid=dialog_guid, root_table=root_table, edit_type=edit_type)


def _pick_edit_target(runtime: Dict[str, Any], dialog_table_norm: Optional[str]) -> tuple[str, str]:
    root_table = _resolve_runtime_root_table(runtime, dialog_table_norm=dialog_table_norm)
    if not root_table:
        raise HTTPException(status_code=400, detail="Dialog ROOT.TABLE ist leer")
    edit_type = str(runtime.get("edit_type") or "show_json").strip().lower() or "show_json"
    _ensure_allowed_edit_type(edit_type, operation="read")
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

"""Central write gateway for unified DB update operations.

Provides a single update path that prefers actor context from GCS while
still allowing explicit overrides for non-standard callers.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, Optional, Tuple

from app.core.pdvm_datenbank import PdvmDatabase


def _parse_uuid_optional(value: Any) -> Optional[uuid.UUID]:
    if value is None:
        return None
    try:
        return uuid.UUID(str(value))
    except Exception:
        return None


def _normalize_storage_scope(storage_scope: Optional[str]) -> str:
    scope = str(storage_scope or "live").strip().lower() or "live"
    if scope not in {"live", "draft"}:
        raise ValueError("storage_scope muss 'live' oder 'draft' sein")
    return scope


def _validate_scope_contract(*, storage_scope: Optional[str], draft_guid: Optional[Any]) -> Tuple[str, Optional[uuid.UUID]]:
    scope = _normalize_storage_scope(storage_scope)
    draft_guid_uuid = _parse_uuid_optional(draft_guid)
    if scope == "draft" and draft_guid_uuid is None:
        raise ValueError("Bei storage_scope='draft' ist draft_guid verpflichtend")
    return scope, draft_guid_uuid


def resolve_actor_context(
    *,
    gcs=None,
    actor_user_uid: Optional[Any] = None,
    actor_ip: Optional[str] = None,
) -> Tuple[Optional[uuid.UUID], Optional[str]]:
    """Resolve actor context with GCS as default source of truth.

    Priority:
    1) Explicit parameters
    2) Values from GCS session
    """
    resolved_user_uid = _parse_uuid_optional(actor_user_uid)
    if resolved_user_uid is None and gcs is not None:
        resolved_user_uid = _parse_uuid_optional(getattr(gcs, "user_guid", None))

    resolved_ip = actor_ip
    if resolved_ip is None and gcs is not None:
        resolved_ip = getattr(gcs, "actor_ip", None)

    return resolved_user_uid, resolved_ip


async def update_record_central(
    *,
    table_name: str,
    uid: Any,
    daten: Dict[str, Any],
    name: Optional[str] = None,
    historisch: Optional[int] = None,
    expected_snapshot_daten: Optional[Dict[str, Any]] = None,
    gcs=None,
    system_pool=None,
    mandant_pool=None,
    actor_user_uid: Optional[Any] = None,
    actor_ip: Optional[str] = None,
    storage_scope: Optional[str] = "live",
    draft_guid: Optional[Any] = None,
) -> Optional[Dict[str, Any]]:
    """Unified update path for PDVM writes.

    Uses PdvmDatabase.update and attaches actor metadata from GCS by default.
    """
    scope, _ = _validate_scope_contract(storage_scope=storage_scope, draft_guid=draft_guid)
    if scope != "live":
        raise ValueError("update_record_central unterstützt aktuell nur storage_scope='live'")

    resolved_system_pool = system_pool if system_pool is not None else getattr(gcs, "_system_pool", None)
    resolved_mandant_pool = mandant_pool if mandant_pool is not None else getattr(gcs, "_mandant_pool", None)

    db = PdvmDatabase(
        table_name,
        system_pool=resolved_system_pool,
        mandant_pool=resolved_mandant_pool,
    )

    uid_obj = uid if isinstance(uid, uuid.UUID) else uuid.UUID(str(uid))
    resolved_actor_user_uid, resolved_actor_ip = resolve_actor_context(
        gcs=gcs,
        actor_user_uid=actor_user_uid,
        actor_ip=actor_ip,
    )

    return await db.update(
        uid_obj,
        daten=daten,
        name=name,
        historisch=historisch,
        expected_snapshot_daten=expected_snapshot_daten,
        actor_user_uid=resolved_actor_user_uid,
        actor_ip=resolved_actor_ip,
    )


async def create_record_central(
    *,
    table_name: str,
    daten: Dict[str, Any],
    name: str = "",
    uid: Optional[Any] = None,
    historisch: int = 0,
    sec_id: Optional[Any] = None,
    link_uid: Optional[Any] = None,
    gcs=None,
    system_pool=None,
    mandant_pool=None,
    actor_user_uid: Optional[Any] = None,
    actor_ip: Optional[str] = None,
    storage_scope: Optional[str] = "live",
    draft_guid: Optional[Any] = None,
) -> Dict[str, Any]:
    """Unified create path for PDVM writes."""
    scope, _ = _validate_scope_contract(storage_scope=storage_scope, draft_guid=draft_guid)
    if scope != "live":
        raise ValueError("create_record_central unterstützt aktuell nur storage_scope='live'")

    resolved_system_pool = system_pool if system_pool is not None else getattr(gcs, "_system_pool", None)
    resolved_mandant_pool = mandant_pool if mandant_pool is not None else getattr(gcs, "_mandant_pool", None)

    db = PdvmDatabase(
        table_name,
        system_pool=resolved_system_pool,
        mandant_pool=resolved_mandant_pool,
    )

    uid_obj = uid if isinstance(uid, uuid.UUID) else _parse_uuid_optional(uid)
    if uid_obj is None:
        uid_obj = uuid.uuid4()

    sec_id_obj = _parse_uuid_optional(sec_id)
    link_uid_obj = _parse_uuid_optional(link_uid)

    return await db.create(
        uid=uid_obj,
        daten=daten,
        name=name,
        historisch=historisch,
        sec_id=sec_id_obj,
        link_uid=link_uid_obj,
    )


async def delete_record_central(
    *,
    table_name: str,
    uid: Any,
    soft_delete: bool = True,
    gcs=None,
    system_pool=None,
    mandant_pool=None,
    storage_scope: Optional[str] = "live",
    draft_guid: Optional[Any] = None,
) -> bool:
    """Unified delete path for PDVM writes."""
    scope, _ = _validate_scope_contract(storage_scope=storage_scope, draft_guid=draft_guid)
    if scope != "live":
        raise ValueError("delete_record_central unterstützt aktuell nur storage_scope='live'")

    resolved_system_pool = system_pool if system_pool is not None else getattr(gcs, "_system_pool", None)
    resolved_mandant_pool = mandant_pool if mandant_pool is not None else getattr(gcs, "_mandant_pool", None)

    db = PdvmDatabase(
        table_name,
        system_pool=resolved_system_pool,
        mandant_pool=resolved_mandant_pool,
    )
    uid_obj = uid if isinstance(uid, uuid.UUID) else uuid.UUID(str(uid))
    return await db.delete(uid_obj, soft_delete=soft_delete)

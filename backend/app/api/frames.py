"""
Frames API: Runtime-Modell eines Frames (Frame + aufgeloeste Controls) fuer das generische Rendering.

Funktioniert mit und ohne GCS-Session (Masken vor der Mandantenwahl). Regel 2.15, Spec PDVM_FRAME_INPUT_RENDERING_SPEC_V1.
"""
import uuid
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException

from ..api.auth import get_current_user
from ..core import frame_runtime_service as frames
from ..core.pdvm_central_systemsteuerung import get_gcs_session

router = APIRouter()


@router.get("/{frame_guid}/runtime")
async def get_frame_runtime(
    frame_guid: str, language: Optional[str] = None, current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    try:
        frame_uuid = uuid.UUID(frame_guid)
    except ValueError:
        raise HTTPException(status_code=400, detail="Ungültige frame_guid")

    token = current_user.get("token")
    scope = await frames.resolve_pool_scope(get_gcs_session(token) if token else None)
    try:
        payload = await frames.load_frame_runtime(scope, frame_uuid, language)
    except frames.FrameNotFoundError:
        raise HTTPException(status_code=404, detail=f"Frame nicht gefunden: {frame_guid}")

    frames.ensure_frame_access(current_user, payload["root"])
    return payload

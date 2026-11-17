"""
Frame-Aktionen API: Aktion ausfuehren und Zustaende/Rechte fuer einen Satz laden.

Der Router enthaelt kein SQL (Regel 1.1); Pruefung und Ausfuehrung liegen in `frame_action_service`.
Spezifikation: docs/specs/PDVM_FRAME_ACTIONS_SPEC_V1.md
"""
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..core import frame_action_service as actions
from ..core.pdvm_central_systemsteuerung import get_gcs_session
from ..core.security import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()


class RunRequest(BaseModel):
    table: str = Field(min_length=1, max_length=100)
    uid: str = Field(min_length=1, max_length=64)
    params: Optional[Dict[str, Any]] = None


class StateRequest(BaseModel):
    table: str = Field(min_length=1, max_length=100)
    uid: Optional[str] = Field(default=None, max_length=64)
    ids: List[str] = Field(default_factory=list, max_length=50)


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


@router.post("/state")
async def post_action_states(payload: StateRequest, gcs=Depends(get_gcs_instance)) -> Dict[str, Any]:
    try:
        return {"states": await actions.action_states(gcs=gcs, table=payload.table, uid=payload.uid, ids=payload.ids)}
    except actions.ActionError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/{action_id}/run")
async def post_run_action(action_id: str, payload: RunRequest, gcs=Depends(get_gcs_instance)) -> Dict[str, Any]:
    try:
        return await actions.run_action(action_id, gcs=gcs, table=payload.table, uid=payload.uid, params=payload.params)
    except actions.ActionNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc.args[0]))
    except actions.ActionDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except actions.ActionError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        logger.exception("frame_action %s: unerwarteter Fehler", action_id)
        raise HTTPException(status_code=500, detail="Aktion fehlgeschlagen")

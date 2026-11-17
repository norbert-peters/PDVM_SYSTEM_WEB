"""
Credentials API: Zugangsdaten setzen (write-only) und Status abfragen.

Das Passwort wird nie zurueckgegeben. Nur Administratoren. Funktioniert auch vor der Mandantenwahl
(AUTH-DB). Regel 2.15 / Spec PDVM_FRAME_INPUT_RENDERING_SPEC_V1.md, Abschnitt 9.
"""
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..core import credential_service as service
from ..core import secret_box
from ..core.security import get_current_user, has_admin_rights

router = APIRouter()


class CredentialSetRequest(BaseModel):
    password: str = Field(min_length=1, max_length=512, repr=False)
    user: Optional[str] = Field(default=None, max_length=128)
    ssl: bool = False


def _require_admin(current_user: dict) -> None:
    if not has_admin_rights(current_user):
        raise HTTPException(status_code=403, detail="Admin-Recht erforderlich")


@router.get("/{name}")
async def get_credential_info(name: str, current_user: dict = Depends(get_current_user)) -> Dict[str, Any]:
    _require_admin(current_user)
    try:
        return await service.credential_info(name)
    except service.CredentialError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.put("/{name}")
async def put_credential(
    name: str, payload: CredentialSetRequest, current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    _require_admin(current_user)
    try:
        return await service.set_credential(
            name,
            payload.password,
            user=payload.user,
            ssl=payload.ssl,
            actor_user_uid=current_user.get("sub"),
            actor_ip=current_user.get("client_ip"),
        )
    except service.CredentialError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except secret_box.SecretKeyError as exc:
        raise HTTPException(status_code=500, detail=str(exc))

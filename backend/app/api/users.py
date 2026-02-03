"""User administration endpoints (password reset, account lock)."""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.security import get_current_user
from app.core.pdvm_central_systemsteuerung import get_gcs_session
from app.core.password_reset_service import issue_password_reset, update_account_lock

router = APIRouter()


async def get_gcs_instance(current_user: dict = Depends(get_current_user)):
    token = current_user.get("token")
    if not token:
        raise HTTPException(status_code=401, detail="Kein Session-Token gefunden")

    gcs = get_gcs_session(token)
    if not gcs:
        raise HTTPException(status_code=404, detail="Keine GCS-Session gefunden. Bitte Mandant auswählen.")

    return gcs


class PasswordResetResponse(BaseModel):
    user_uid: str
    email: str
    email_sent: bool
    email_error: Optional[str] = None
    expires_at: str


class LockAccountRequest(BaseModel):
    reason: Optional[str] = None


@router.post("/{user_uid}/password-reset", response_model=PasswordResetResponse)
async def post_password_reset(user_uid: str, gcs=Depends(get_gcs_instance)):
    try:
        uuid.UUID(str(user_uid))
    except Exception:
        raise HTTPException(status_code=400, detail="Ungültige User-GUID")

    try:
        result = await issue_password_reset(gcs=gcs, user_uid=user_uid)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{user_uid}/lock")
async def post_lock_account(user_uid: str, payload: LockAccountRequest, gcs=Depends(get_gcs_instance)):
    try:
        await update_account_lock(user_uid=user_uid, locked=True, reason=payload.reason)
        return {"success": True, "message": "Account gesperrt"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{user_uid}/unlock")
async def post_unlock_account(user_uid: str, gcs=Depends(get_gcs_instance)):
    try:
        await update_account_lock(user_uid=user_uid, locked=False, reason=None)
        return {"success": True, "message": "Account entsperrt"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

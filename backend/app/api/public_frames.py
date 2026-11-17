"""
Oeffentliche Frames (ohne Token) fuer die Anmeldung. Spec: docs/specs/PDVM_LOGIN_FRAME_SPEC_V1.md.

Der Router enthaelt kein SQL (Regel 1.1); Allowlist, Pruefung und Laden liegen in `public_frame_service`.
"""
import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Request, Response

from ..core import public_frame_service as service
from ..core.rate_limit import RateLimiter

router = APIRouter()
logger = logging.getLogger(__name__)

# Je IP und Minute; der Endpunkt liefert nur kleine, nicht geheime Konfiguration, soll aber kein Verstaerker sein
_limiter = RateLimiter(limit=60, window_seconds=60)


@router.get("/login-frames")
async def get_login_frames(request: Request, response: Response, language: Optional[str] = None) -> Dict[str, Any]:
    client_ip = request.client.host if request.client else "unknown"
    if not _limiter.allow(client_ip):
        raise HTTPException(status_code=429, detail="Zu viele Anfragen. Bitte später erneut versuchen.")
    try:
        frames = await service.load_login_frames(language)
    except service.PublicFrameError as exc:
        logger.error("Login-Frames nicht verfuegbar: %s", exc)
        raise HTTPException(status_code=503, detail="Anmeldemaske nicht verfügbar")
    except Exception as exc:  # z. B. Systempool nicht bereit; Details nur im Log
        logger.error("Login-Frames konnten nicht geladen werden: %s", exc)
        raise HTTPException(status_code=503, detail="Anmeldemaske nicht verfügbar")
    response.headers["Cache-Control"] = "public, max-age=300"
    return {"frames": frames}

"""
Oeffentliche Frames fuer die Anmeldung (ohne Token): Anmeldung, Passwort vergessen, Passwort aendern.

Spec: docs/specs/PDVM_LOGIN_FRAME_SPEC_V1.md. Der tokenpflichtige Endpunkt `/api/frames/{uid}/runtime` bleibt unveraendert.
Sicherheit: feste Allowlist der Frame-UIDs (kein Parameter waehlt einen Frame), feste Menge erlaubter Feldtypen, keine
Aktionen, Dropdown-Quellen oder Tabellenbezuege in der Antwort. Nur Frame-Konfiguration, keine Mandanten- oder Benutzerdaten.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, Optional

from app.core import frame_runtime_service as frames

logger = logging.getLogger(__name__)

# Gleicher Namensraum wie die Seed-Tools (deterministische UIDs, damit Code und Seed dieselben Frames meinen)
_NS = uuid.UUID("6f1a5b0e-2a0c-4d6b-9b3e-5d1f0c7a9e11")
LOGIN_FRAME_UIDS: Dict[str, uuid.UUID] = {
    "login": uuid.uuid5(_NS, "frame:login"),
    "forgot": uuid.uuid5(_NS, "frame:login_forgot_password"),
    "change": uuid.uuid5(_NS, "frame:login_change_password"),
}
ALLOWED_FIELD_TYPES = frozenset({"string", "password_input"})


class PublicFrameError(Exception):
    """Ein Login-Frame fehlt oder verletzt die Regeln fuer oeffentliche Frames (Details nur im Log)."""


def _sanitize(name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    if str(payload["root"].get("FRAME_TYPE") or "").strip().lower() != frames.PUBLIC_FORM_FRAME_TYPE:
        raise PublicFrameError(f"Frame '{name}' hat nicht FRAME_TYPE '{frames.PUBLIC_FORM_FRAME_TYPE}'")
    for field in payload["fields"]:
        if field["type"] not in ALLOWED_FIELD_TYPES:
            raise PublicFrameError(f"Frame '{name}': Feldtyp '{field['type']}' ist oeffentlich nicht erlaubt ({field['feld']})")
        if field.get("resolution_warning"):
            raise PublicFrameError(f"Frame '{name}': {field['feld']}: {field['resolution_warning']}")
        # Keine internen Verweise nach aussen
        field["table"] = None
        field["control_uid"] = None
        field["options"] = []
    return payload


async def load_login_frames(language: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
    """Runtime-Modelle der drei Login-Frames (Schluessel `login`, `forgot`, `change`), ohne Sitzung."""
    scope = await frames.resolve_pool_scope(None)
    result: Dict[str, Dict[str, Any]] = {}
    for name, frame_uid in LOGIN_FRAME_UIDS.items():
        try:
            payload = await frames.load_frame_runtime(scope, frame_uid, language)
        except frames.FrameNotFoundError as exc:
            raise PublicFrameError(str(exc))
        result[name] = _sanitize(name, payload)
    return result

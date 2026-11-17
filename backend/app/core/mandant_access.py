"""
Mandanten-Zulassung eines Benutzers (`MANDANTEN.LIST`, ersatzweise `MANDANTEN.DEFAULT` im Benutzersatz).

Eine Regel fuer Login (Auswahlliste), Mandantenwahl (`/api/mandanten/select`) und die Listen-Endpunkte.
Die Pruefung liest den Benutzersatz frisch aus der Datenbank, nicht aus dem JWT (Aenderungen wirken sofort).
Der Mandant muss zusaetzlich `MANDANT.IS_ALLOWED` haben (`MandantDataManager.check_access`).
"""
from __future__ import annotations

import uuid
from typing import Any, Dict, List


def _norm(value: Any) -> str:
    try:
        return str(uuid.UUID(str(value).strip())).lower()
    except (ValueError, TypeError, AttributeError):
        return str(value or "").strip().lower()


def allowed_mandant_ids(user_daten: Dict[str, Any] | None) -> List[str]:
    """Zugelassene Mandanten-UIDs (normalisiert): `LIST`, bei leerer Liste `[DEFAULT]`; sonst leer."""
    config = (user_daten or {}).get("MANDANTEN") or {}
    if not isinstance(config, dict):
        return []
    raw = config.get("LIST") or []
    if not isinstance(raw, (list, tuple)):
        raw = []
    ids = [_norm(m) for m in raw if str(m or "").strip()]
    if not ids and str(config.get("DEFAULT") or "").strip():
        ids = [_norm(config.get("DEFAULT"))]
    return ids


def is_mandant_allowed(user_daten: Dict[str, Any] | None, mandant_id: Any) -> bool:
    return _norm(mandant_id) in set(allowed_mandant_ids(user_daten))


async def load_user_daten(user_uid: Any) -> Dict[str, Any]:
    """Benutzerdaten (`asy_benutzer.daten`) frisch aus der Datenbank; leer, wenn der Benutzer fehlt."""
    from app.core.pdvm_central_benutzer import PdvmCentralBenutzer

    try:
        uid = uuid.UUID(str(user_uid))
    except (ValueError, TypeError):
        return {}
    user = await PdvmCentralBenutzer(uid).get_user()
    return dict((user or {}).get("daten") or {})

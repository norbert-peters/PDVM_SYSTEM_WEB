"""Password Reset Service

Implements OTP generation, persistence and email delivery.
"""
from __future__ import annotations

import secrets
import string
import uuid
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Tuple

from app.core.user_manager import UserManager
from app.core.pdvm_central_benutzer import PdvmCentralBenutzer
from app.core.pdvm_datenbank import PdvmDatabase
from app.core.email_service import send_email

logger = logging.getLogger(__name__)


def _now_utc() -> datetime:
    return datetime.utcnow()


def _to_iso(dt: datetime) -> str:
    return dt.isoformat() + "Z"


def _parse_iso(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    s = str(value).replace("Z", "").strip()
    try:
        return datetime.fromisoformat(s)
    except Exception:
        return None


def _generate_strong_password(length: int = 12) -> str:
    if length < 12:
        length = 12

    lower = string.ascii_lowercase
    upper = string.ascii_uppercase
    digits = string.digits
    special = "@$!%*?&"

    # ensure complexity
    chars = [
        secrets.choice(lower),
        secrets.choice(upper),
        secrets.choice(digits),
        secrets.choice(special),
    ]

    pool = lower + upper + digits + special
    while len(chars) < length:
        chars.append(secrets.choice(pool))

    secrets.SystemRandom().shuffle(chars)
    return "".join(chars)


def _extract_user_email(user: Dict[str, Any]) -> Optional[str]:
    try:
        daten = user.get("daten")
        if isinstance(daten, str) and daten.strip().startswith("{"):
            try:
                import json

                daten = json.loads(daten)
            except Exception:
                daten = None
        if isinstance(daten, dict):
            user_group = daten.get("USER") or daten.get("user") or {}
            if isinstance(user_group, dict):
                if user_group.get("EMAIL"):
                    return str(user_group.get("EMAIL")).strip()
                if user_group.get("email"):
                    return str(user_group.get("email")).strip()
    except Exception:
        return None
    if user.get("benutzer"):
        return str(user.get("benutzer")).strip()
    if user.get("email"):
        return str(user.get("email")).strip()
    if user.get("EMAIL"):
        return str(user.get("EMAIL")).strip()
    return None


def _get_rate_limit_config(send_cfg: Dict[str, Any]) -> int:
    raw = send_cfg.get("OTP_RATE_LIMIT")
    try:
        value = int(raw)
        if value <= 0:
            return 4
        return value
    except Exception:
        return 4


def _get_send_email_config(gcs) -> Dict[str, Any]:
    if not gcs or not getattr(gcs, "mandant", None):
        return {}

    try:
        cfg = gcs.mandant.get_value_by_group("SEND_EMAIL")
        if isinstance(cfg, dict) and cfg:
            return cfg
    except Exception:
        pass

    # Fallback: case-insensitive lookup in mandant data
    try:
        data = gcs.mandant.data if isinstance(gcs.mandant.data, dict) else {}
    except Exception:
        data = {}

    if not isinstance(data, dict):
        return {}

    for key, value in data.items():
        if str(key).strip().upper() == "SEND_EMAIL" and isinstance(value, dict):
            return value

    return {}


def _extract_send_email_from_data(data: Any) -> Dict[str, Any]:
    if isinstance(data, str) and data.strip().startswith("{"):
        try:
            import json

            data = json.loads(data)
        except Exception:
            data = None
    if not isinstance(data, dict):
        return {}
    for key, value in data.items():
        if str(key).strip().upper() == "SEND_EMAIL" and isinstance(value, dict):
            return value
    return {}


async def _get_send_email_config_async(gcs) -> Dict[str, Any]:
    cfg = _get_send_email_config(gcs)
    if cfg:
        return cfg

    try:
        from app.core.data_managers import MandantDataManager

        manager = MandantDataManager()
        mandanten = await manager.list_all(include_inactive=False)
        for mandant in mandanten:
            data = mandant.get("daten") if isinstance(mandant, dict) else None
            cfg = _extract_send_email_from_data(data)
            if cfg:
                return cfg
    except Exception:
        return {}

    return {}


def _update_security(daten: Dict[str, Any], updates: Dict[str, Any]) -> Dict[str, Any]:
    next_data = dict(daten or {})
    sec = next_data.get("SECURITY") if isinstance(next_data.get("SECURITY"), dict) else {}
    sec = dict(sec)
    sec.update(updates)
    next_data["SECURITY"] = sec
    return next_data


async def issue_password_reset(
    *,
    gcs,
    user_uid: str,
    otp_length: int = 12,
    expires_minutes: int = 120,
) -> Dict[str, Any]:
    try:
        user_uuid = uuid.UUID(str(user_uid))
    except Exception:
        raise ValueError("Ungültige User-GUID")

    benutzer_mgr = PdvmCentralBenutzer(user_uuid)
    user = await benutzer_mgr.get_user()
    if not user:
        raise ValueError("Benutzer nicht gefunden")

    user_email = _extract_user_email(user)
    if not user_email:
        raise ValueError("Benutzer hat keine E-Mail-Adresse")

    # Mandant SMTP config
    send_cfg = await _get_send_email_config_async(gcs)

    rate_limit = _get_rate_limit_config(send_cfg)

    now = _now_utc()
    window_start = None
    security = user.get("daten", {}).get("SECURITY", {}) if isinstance(user.get("daten"), dict) else {}
    if isinstance(security, dict):
        window_start = _parse_iso(security.get("PASSWORD_RESET_SEND_WINDOW_START"))

    if window_start is None or (now - window_start) > timedelta(minutes=expires_minutes):
        send_count = 0
        window_start = now
    else:
        try:
            send_count = int(security.get("PASSWORD_RESET_SEND_COUNT") or 0)
        except Exception:
            send_count = 0

    if send_count >= rate_limit:
        raise ValueError(f"OTP Rate-Limit erreicht ({rate_limit}).")

    otp = _generate_strong_password(otp_length)
    otp_hash = UserManager.hash_password(otp)

    # Update passwort (auth DB)
    await benutzer_mgr.change_password(otp_hash)

    expires_at = now + timedelta(minutes=expires_minutes)
    updated = _update_security(
        user.get("daten") or {},
        {
            "PASSWORD_CHANGE_REQUIRED": True,
            "PASSWORD_RESET_ISSUED_AT": _to_iso(now),
            "PASSWORD_RESET_EXPIRES_AT": _to_iso(expires_at),
            "PASSWORD_RESET_TOKEN_HASH": otp_hash,
            "PASSWORD_RESET_SEND_COUNT": int(send_count) + 1,
            "PASSWORD_RESET_SEND_WINDOW_START": _to_iso(window_start),
        },
    )

    db = PdvmDatabase("sys_benutzer")
    await db.update(user_uuid, updated, name=user.get("name"), historisch=user.get("historisch"))

    # Send email
    subject = "PDVM Passwort zurücksetzen"
    body = (
        "Ihr neues einmaliges Passwort wurde erzeugt.\n\n"
        f"Passwort: {otp}\n"
        f"Gültigkeit: {expires_minutes} Minuten\n\n"
        "Bitte melden Sie sich an und ändern Sie Ihr Passwort sofort."
    )

    email_sent = False
    email_error = None
    try:
        send_email(send_cfg, user_email, subject, body)
        email_sent = True
    except Exception as e:
        email_error = str(e)

    return {
        "user_uid": str(user_uuid),
        "email": user_email,
        "email_sent": email_sent,
        "email_error": email_error,
        "expires_at": _to_iso(expires_at),
    }


async def update_account_lock(*, user_uid: str, locked: bool, reason: Optional[str] = None) -> None:
    try:
        user_uuid = uuid.UUID(str(user_uid))
    except Exception:
        raise ValueError("Ungültige User-GUID")

    benutzer_mgr = PdvmCentralBenutzer(user_uuid)
    user = await benutzer_mgr.get_user()
    if not user:
        raise ValueError("Benutzer nicht gefunden")

    updated = _update_security(
        user.get("daten") or {},
        {
            "ACCOUNT_LOCKED": bool(locked),
            "LOCK_REASON": str(reason or "").strip() if locked else None,
        },
    )

    db = PdvmDatabase("sys_benutzer")
    await db.update(user_uuid, updated, name=user.get("name"), historisch=user.get("historisch"))


async def clear_password_reset_flags(*, user_uid: str) -> None:
    try:
        user_uuid = uuid.UUID(str(user_uid))
    except Exception:
        raise ValueError("Ungültige User-GUID")

    benutzer_mgr = PdvmCentralBenutzer(user_uuid)
    user = await benutzer_mgr.get_user()
    if not user:
        raise ValueError("Benutzer nicht gefunden")

    updated = _update_security(
        user.get("daten") or {},
        {
            "PASSWORD_CHANGE_REQUIRED": False,
            "PASSWORD_RESET_ISSUED_AT": None,
            "PASSWORD_RESET_EXPIRES_AT": None,
            "PASSWORD_RESET_TOKEN_HASH": None,
        },
    )

    db = PdvmDatabase("sys_benutzer")
    await db.update(user_uuid, updated, name=user.get("name"), historisch=user.get("historisch"))

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
from app.core.central_write_service import update_record_central
from app.core.pdvm_central_benutzer import PdvmCentralBenutzer
from app.core.email_service import send_email
from app.core.pdvm_datetime import datetime_to_pdvm, pdvm_to_datetime

logger = logging.getLogger(__name__)


def _now_utc() -> datetime:
    return datetime.utcnow()


def _to_pdvm(dt: datetime) -> float:
    return float(datetime_to_pdvm(dt))


def _parse_security_time(value: Any) -> Optional[datetime]:
    if not value:
        return None

    # Primär: PDVM float/timestamp
    try:
        pdvm_val = float(value)
        if pdvm_val >= 1001.0:
            return pdvm_to_datetime(pdvm_val)
    except Exception:
        pass

    # Fallback: legacy ISO-String
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


def stored_user_email(user: Dict[str, Any]) -> Optional[str]:
    """Nur die im Benutzersatz hinterlegte Adresse (`USER.EMAIL`), ohne Rueckgriff auf den Anmeldenamen."""
    daten = user.get("daten")
    if isinstance(daten, str) and daten.strip().startswith("{"):
        try:
            import json

            daten = json.loads(daten)
        except Exception:
            return None
    group = daten.get("USER") if isinstance(daten, dict) else None
    if isinstance(group, dict):
        value = group.get("EMAIL") or group.get("email")
        if value and str(value).strip():
            return str(value).strip()
    return None


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


async def _load_mandant_daten_fresh(gcs) -> Dict[str, Any]:
    """Aktuelle Daten des Session-Mandanten direkt aus asy_mandanten (statt der Login-Daten der Session)."""
    guid = getattr(getattr(gcs, "mandant", None), "guid", None) if gcs else None
    if not guid:
        return {}
    try:
        from app.core.pdvm_datenbank import PdvmDatabase

        row = await PdvmDatabase("asy_mandanten").get_by_uid(uuid.UUID(str(guid)))
    except Exception:
        return {}
    daten = row.get("daten") if row else None
    return daten if isinstance(daten, dict) else {}


async def _load_send_email_config_fresh(gcs) -> Dict[str, Any]:
    """Aktuelle SEND_EMAIL-Konfiguration des Session-Mandanten direkt aus asy_mandanten.

    Die GCS-Session haelt die Mandantendaten vom Anmeldezeitpunkt; Aenderungen (z. B. neues SMTP-Passwort)
    wuerden sonst erst nach erneuter Mandantenwahl wirken. Der Versand ist selten, die Abfrage billig.
    """
    return _extract_send_email_from_data(await _load_mandant_daten_fresh(gcs))


PASSWORD_RESET_TEMPLATE_KEY = "PASSWORD_RESET"


def _user_language(user: Dict[str, Any]) -> Optional[str]:
    daten = user.get("daten") if isinstance(user.get("daten"), dict) else {}
    settings_group = daten.get("SETTINGS") if isinstance(daten.get("SETTINGS"), dict) else {}
    return settings_group.get("LANGUAGE") or None


async def _load_reset_template(gcs, user: Dict[str, Any], mandant_daten: Optional[Dict[str, Any]] = None, mandant_pool: Any = None):
    """Textvorlage und freigegebene Sprache fuer die Reset-Mail (vor jeder Aenderung am Benutzer, damit Fehler folgenlos bleiben).

    Ohne Sitzung (Login: Passwort vergessen) kommen Mandantendaten und -pool vom Mandanten des Benutzers (`mandant_daten`, `mandant_pool`).
    """
    from app.core import text_template_service as texts

    system_pool = getattr(gcs, "_system_pool", None) if gcs else None
    if system_pool is None:
        from app.core.frame_runtime_service import resolve_pool_scope

        system_pool = (await resolve_pool_scope(None))._system_pool
    if mandant_daten is None:
        mandant_daten = await _load_mandant_daten_fresh(gcs)
    if mandant_pool is None and gcs:
        mandant_pool = getattr(gcs, "_mandant_pool", None)
    try:
        candidates = await texts.load_candidates(
            PASSWORD_RESET_TEMPLATE_KEY,
            system_pool=system_pool,
            mandant_pool=mandant_pool,
        )
        mandant_language = _as_dict_or_empty(mandant_daten.get("CONFIG")).get("DEFAULT_LANGUAGE")
        return texts.select_group(candidates, texts.language_chain(_user_language(user), mandant_language))
    except texts.TextTemplateError as exc:
        raise ValueError(f"E-Mail-Text nicht verfügbar: {exc}")


def _as_dict_or_empty(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _smtp_usable(cfg: Dict[str, Any]) -> bool:
    return bool(str(cfg.get("SMTP_HOST") or "").strip())


async def _resolve_user_mandant(user: Dict[str, Any]) -> Dict[str, Any]:
    """Mandant des Benutzers fuer Aufrufe ohne Sitzung (Passwort vergessen): `MANDANTEN.DEFAULT`, dann `MANDANTEN.LIST`.

    Gewaehlt wird der erste dieser Mandanten mit nutzbarer SEND_EMAIL-Konfiguration (SMTP_HOST gesetzt); gibt es keinen,
    der erste vorhandene (Sprache/Vorlage) mit leerer Konfiguration. Nie ein Mandant, der dem Benutzer nicht zugeordnet ist.
    Ergebnis: {"uid", "daten", "send_email", "pool"} (Pool nur, wenn die Mandanten-DB erreichbar ist, sonst None).
    """
    from app.core.mandant_access import allowed_mandant_ids
    from app.core.pdvm_datenbank import PdvmDatabase

    daten = user.get("daten") if isinstance(user.get("daten"), dict) else {}
    config = daten.get("MANDANTEN") if isinstance(daten.get("MANDANTEN"), dict) else {}
    ordered: list = []
    for uid in [str(config.get("DEFAULT") or "").strip().lower()] + allowed_mandant_ids(daten):
        if uid and uid not in ordered:
            ordered.append(uid)

    first: Optional[Dict[str, Any]] = None
    for uid in ordered:
        try:
            row = await PdvmDatabase("asy_mandanten").get_by_uid(uuid.UUID(uid))
        except Exception:
            continue
        mandant_daten = row.get("daten") if row and isinstance(row.get("daten"), dict) else None
        if not mandant_daten:
            continue
        found = {"uid": uid, "daten": mandant_daten, "send_email": _extract_send_email_from_data(mandant_daten), "pool": None}
        if _smtp_usable(found["send_email"]):
            first = found
            break
        first = first or found
    if first is None:
        return {"uid": None, "daten": {}, "send_email": {}, "pool": None}

    try:  # Aktive Vorlagenkopie des Mandanten (best effort; sonst gilt die Systemvorlage)
        from app.core import mandant_db_provisioning_service as provisioning
        from app.core.connection_manager import ConnectionManager

        _, mandant_config = await ConnectionManager.get_mandant_config(first["uid"])
        first["pool"] = await provisioning.get_shared_pool(mandant_config.to_url())
    except Exception as exc:
        logger.info("Passwort-Reset: Mandanten-DB nicht erreichbar, Systemvorlage wird verwendet (%s)", exc)
    return first


async def _get_send_email_config_async(gcs) -> Dict[str, Any]:
    """SEND_EMAIL des Session-Mandanten (frisch aus der DB, sonst aus der Session). Kein Rueckgriff auf fremde Mandanten."""
    cfg = await _load_send_email_config_fresh(gcs)
    if cfg:
        return cfg
    return _get_send_email_config(gcs)


def _update_security(daten: Dict[str, Any], updates: Dict[str, Any]) -> Dict[str, Any]:
    next_data = dict(daten or {})
    sec = next_data.get("SECURITY") if isinstance(next_data.get("SECURITY"), dict) else {}
    sec = dict(sec)
    sec.update(updates)
    next_data["SECURITY"] = sec
    return next_data


def _actor_user_uid_from_gcs(gcs) -> Optional[uuid.UUID]:
    try:
        return uuid.UUID(str(getattr(gcs, "user_guid", "") or ""))
    except Exception:
        return None


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

    # Mandant SMTP config (Zugangsdaten frisch aus dem Store). Mit Sitzung: Session-Mandant; ohne Sitzung
    # (Passwort vergessen im Login): Mandant des Benutzers (MANDANTEN.DEFAULT/LIST).
    from app.core.credential_service import ensure_fresh
    await ensure_fresh()
    if gcs is None:
        ctx = await _resolve_user_mandant(user)
        send_cfg = ctx["send_email"]
        if not _smtp_usable(send_cfg):
            raise ValueError("Für den Mandanten des Benutzers ist kein E-Mail-Versand konfiguriert")
        template, language = await _load_reset_template(None, user, mandant_daten=ctx["daten"], mandant_pool=ctx["pool"])
    else:
        send_cfg = await _get_send_email_config_async(gcs)
        template, language = await _load_reset_template(gcs, user)
    rate_limit = _get_rate_limit_config(send_cfg)

    now = _now_utc()
    window_start = None
    security = user.get("daten", {}).get("SECURITY", {}) if isinstance(user.get("daten"), dict) else {}
    if isinstance(security, dict):
        window_start = _parse_security_time(security.get("PASSWORD_RESET_SEND_WINDOW_START"))

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
            "PASSWORD_RESET_ISSUED_AT": _to_pdvm(now),
            "PASSWORD_RESET_EXPIRES_AT": _to_pdvm(expires_at),
            "PASSWORD_RESET_TOKEN_HASH": otp_hash,
            "PASSWORD_RESET_SEND_COUNT": int(send_count) + 1,
            "PASSWORD_RESET_SEND_WINDOW_START": _to_pdvm(window_start),
        },
    )

    await update_record_central(
        table_name="asy_benutzer",
        uid=user_uuid,
        daten=updated,
        name=user.get("name"),
        historisch=user.get("historisch"),
        gcs=gcs,
        actor_user_uid=_actor_user_uid_from_gcs(gcs),
        actor_ip=getattr(gcs, "actor_ip", None) if gcs else None,
    )

    # Send email (Text aus der Textvorlage PASSWORD_RESET; der gerenderte Text enthaelt das OTP und wird nicht geloggt)
    email_sent = False
    email_error = None
    try:
        from app.core import text_template_service as texts

        message = texts.render_message(
            template,
            language,
            {"otp": otp, "expires_minutes": expires_minutes, "user_email": user_email},
        )
        send_email(send_cfg, user_email, message["subject"], message["body"], html=message["body_html"])
        email_sent = True
    except Exception as e:
        email_error = str(e)

    return {
        "user_uid": str(user_uuid),
        "email": user_email,
        "email_sent": email_sent,
        "email_error": email_error,
        "expires_at": str(_to_pdvm(expires_at)),
    }


async def update_account_lock(
    *,
    user_uid: str,
    locked: bool,
    reason: Optional[str] = None,
    actor_user_uid: Optional[uuid.UUID] = None,
    actor_ip: Optional[str] = None,
) -> None:
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

    await update_record_central(
        table_name="asy_benutzer",
        uid=user_uuid,
        daten=updated,
        name=user.get("name"),
        historisch=user.get("historisch"),
        gcs=None,
        actor_user_uid=actor_user_uid,
        actor_ip=actor_ip,
    )


async def clear_password_reset_flags(
    *,
    user_uid: str,
    actor_user_uid: Optional[uuid.UUID] = None,
    actor_ip: Optional[str] = None,
) -> None:
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

    await update_record_central(
        table_name="asy_benutzer",
        uid=user_uuid,
        daten=updated,
        name=user.get("name"),
        historisch=user.get("historisch"),
        gcs=None,
        actor_user_uid=actor_user_uid,
        actor_ip=actor_ip,
    )


async def mark_password_changed(
    *,
    user_uid: str,
    actor_user_uid: Optional[uuid.UUID] = None,
    actor_ip: Optional[str] = None,
) -> None:
    """Setzt LAST_PASSWORD_CHANGE im SECURITY-Block auf den aktuellen PDVM-Zeitstempel."""
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
            "LAST_PASSWORD_CHANGE": _to_pdvm(_now_utc()),
        },
    )

    await update_record_central(
        table_name="asy_benutzer",
        uid=user_uuid,
        daten=updated,
        name=user.get("name"),
        historisch=user.get("historisch"),
        gcs=None,
        actor_user_uid=actor_user_uid,
        actor_ip=actor_ip,
    )


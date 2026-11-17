"""
Authentication API Routes
Login, register, token management

Nach Desktop-Vorbild: pdvm_login_dialog.py
"""
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from datetime import timedelta
import asyncio
import uuid
import logging
from app.models.schemas import Token, UserLogin, UserCreate
from pydantic import BaseModel, Field
from app.core.security import (
    create_access_token,
    get_current_user
)
from app.core.pdvm_central_systemsteuerung import get_gcs_session, rotate_gcs_session_token
from app.core.config import settings
from app.core.rate_limit import RateLimiter
from app.core.user_manager import UserManager
from app.core.password_reset_service import issue_password_reset, stored_user_email

router = APIRouter()
logger = logging.getLogger(__name__)

PASSWORD_CHANGE_TOKEN_MINUTES = 15
GENERIC_LOGIN_ERROR = "E-Mail oder Passwort falsch"
FORGOT_PASSWORD_REPLY = "Falls die Adresse bekannt ist, wurde ein maschinelles Passwort versendet."

# Fehlversuche je IP (zusaetzlich zur Kontosperre nach 5 Fehlversuchen) und Anfragen "Passwort vergessen" je IP
_login_failures = RateLimiter(limit=20, window_seconds=300)
_forgot_requests = RateLimiter(limit=5, window_seconds=900)
_DUMMY_HASH: list = []
_background_tasks: set = set()


def _dummy_password_hash() -> str:
    """Platzhalter-Hash, damit auch bei unbekanntem Benutzer eine bcrypt-Pruefung laeuft (gleiche Laufzeit)."""
    if not _DUMMY_HASH:
        _DUMMY_HASH.append(UserManager.hash_password(uuid.uuid4().hex))
    return _DUMMY_HASH[0]


class PasswordChangeRequest(BaseModel):
    new_password: str = Field(..., min_length=12)
    confirm_password: str = Field(..., min_length=12)


class ForgotPasswordRequest(BaseModel):
    benutzer: str = Field(..., min_length=3)
    email: str = Field(..., min_length=3)

@router.post("/login", response_model=Token)
async def login(request: Request, form_data: OAuth2PasswordRequestForm = Depends()):
    """
    Login endpoint nach Desktop-Vorbild
    
    Features:
    - Email-Normalisierung (case-insensitive)
    - bcrypt Password-Verifizierung
    - Account-Lock nach 5 Fehlversuchen
    - Last-Login Tracking
    - Failed-Login Counter
    - Einheitliche Fehlermeldung (keine Benutzer-Aufzaehlung), Begrenzung der Fehlversuche je IP (Login-Frame-Spec F3)
    
    Returns JWT token on success
    """
    user_manager = UserManager()
    client_ip = request.client.host if request.client else "unknown"
    if _login_failures.is_blocked(client_ip):
        logger.warning(f"❌ Zu viele Fehlversuche von {client_ip}")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Zu viele Anmeldeversuche. Bitte später erneut versuchen.",
        )
    
    # Email normalisieren (case-insensitive)
    email = user_manager.normalize_email(form_data.username)
    password = form_data.password
    
    logger.info(f"🔍 Login-Versuch: {email}")
    
    # 1. User laden; das Passwort wird immer geprueft (bei unbekanntem Benutzer gegen einen Platzhalter-Hash,
    #    damit Antwort und Laufzeit nicht verraten, ob es das Konto gibt)
    user = await user_manager.get_user_by_email(email)
    locked = await user_manager.is_account_locked(email) if user else False
    password_ok = user_manager.verify_password(password, user['passwort'] if user else _dummy_password_hash())
    
    if not user or not password_ok:
        logger.warning(f"❌ Anmeldung fehlgeschlagen ({'unbekannter Benutzer' if not user else 'falsches Passwort'}): {email}")
        _login_failures.record(client_ip)
        if user and not locked:
            failed_count = await user_manager.increment_failed_login(email)
            if failed_count >= 5:
                logger.warning(f"❌ Account gesperrt nach {failed_count} Fehlversuchen: {email}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=GENERIC_LOGIN_ERROR,
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 2. Passwort stimmt: nur der Kontoinhaber erfaehrt, dass der Account gesperrt ist
    if locked:
        logger.warning(f"❌ Account gesperrt: {email}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Der Account ist gesperrt. Bitte wenden Sie sich an den Administrator.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # 4. ✅ LOGIN ERFOLGREICH
    logger.info(f"✅ Login erfolgreich: {user['name']} ({email})")
    
    # 5. Last-Login aktualisieren + Failed-Attempts zurücksetzen
    await user_manager.update_last_login(email)

    # 5b. User nach Security-Update neu laden, damit Token/GCS aktuelle Daten erhalten
    refreshed_user = await user_manager.get_user_by_email(email)
    if refreshed_user:
        user = refreshed_user
    
    # 6. Prüfe ob Passwort geändert werden muss
    password_change_required = await user_manager.check_password_change_required(email)
    if password_change_required and await user_manager.is_password_reset_expired(email):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Maschinelles Passwort ist abgelaufen. Bitte wenden Sie sich an den Administrator.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # 7. Lade Mandanten-Liste für User (mit Berechtigungs-Filter)
    from app.core.data_managers import MandantDataManager
    from app.core.mandant_access import allowed_mandant_ids
    from app.api.mandanten import SYSTEM_MANDANT_UIDS
    
    # Extrahiere Berechtigungen aus User-Daten
    user_daten = user.get('daten', {})
    mandanten_config = user_daten.get('MANDANTEN', {})
    allowed_mandanten_list = mandanten_config.get('LIST', [])  # Liste der erlaubten Mandanten-UIDs
    default_mandant = mandanten_config.get('DEFAULT', None)     # Standard-Mandant (falls nur einer)
    
    logger.info(f"🔍 User {user['name']} - Berechtigungen: LIST={len(allowed_mandanten_list)}, DEFAULT={default_mandant}")
    
    # CASE 1: Keine Berechtigung (LIST leer UND kein DEFAULT)
    if not allowed_mandanten_list and not default_mandant:
        logger.warning(f"❌ User {user['name']} hat keine Mandanten-Zulassung!")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Keine Zulassung zu einem Mandanten. Bitte kontaktieren Sie einen Administrator.",
        )
    
    # CASE 2a: LIST leer, aber DEFAULT gesetzt → Verwende DEFAULT als Liste
    if not allowed_mandanten_list and default_mandant:
        logger.info(f"✅ User {user['name']} - Auto-Select-Kandidat: LIST leer, DEFAULT={default_mandant}")
    allowed_mandanten_list = allowed_mandant_ids(user_daten)  # gleiche Regel wie /api/mandanten/select
    
    # Lade und filtere Mandanten
    mandanten_manager = MandantDataManager()
    all_mandanten = await mandanten_manager.list_all(include_inactive=False)
    
    # Filter: Nur erlaubte Mandanten (LIST) + keine System-Mandanten
    filtered_mandanten = [
        {
            "id": str(m["uid"]),
            "name": m["name"],
            "is_allowed": m["daten"].get("MANDANT", {}).get("IS_ALLOWED", False),
            "description": m["daten"].get("MANDANT", {}).get("DESCRIPTION", "")
        }
        for m in all_mandanten
        if str(m["uid"]).lower() in allowed_mandanten_list and str(m["uid"]) not in SYSTEM_MANDANT_UIDS
    ]
    
    # Alphabetisch sortieren
    filtered_mandanten = sorted(filtered_mandanten, key=lambda x: x["name"].lower())
    
    # Auto-Select Logic: Wenn nach dem Filtern nur 1 Mandant übrig bleibt
    auto_select_mandant = None
    if len(filtered_mandanten) == 1:
        auto_select_mandant = filtered_mandanten[0]["id"]
        logger.info(f"✅ User {user['name']} - Auto-Select aktiviert: {auto_select_mandant} ({filtered_mandanten[0]['name']})")
    else:
        logger.info(f"ℹ️ User {user['name']} - Mandanten-Auswahl erforderlich ({len(filtered_mandanten)} Mandanten)")
    
    logger.info(f"✅ {len(filtered_mandanten)} erlaubte Mandanten für User {user['name']}")
    
    # 8. JWT Token erstellen mit vollständigen User-Daten (für GCS!)
    user_daten = user.get('daten', {})
    start_menu_guid = user_daten.get('MEINEAPPS', {}).get('START', {}).get('MENU')
    logger.info(f"🔍 DEBUG: User {user['name']} hat START.MENU GUID: {start_menu_guid}")
    
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    token_data = {
        "sub": str(user['uid']),  # User-ID (Primary Key)
        "email": email,
        "name": user['name'],
        "user_data": user_daten  # Vollständige JSONB-Daten (MEINEAPPS, SETTINGS, etc.)
    }
    if password_change_required:
        # Eingeschränktes Token: nur Passwortwechsel und Abmeldung (security.get_current_user), kurze Laufzeit
        token_data["pwc"] = True
        access_token_expires = timedelta(minutes=PASSWORD_CHANGE_TOKEN_MINUTES)
    access_token = create_access_token(data=token_data, expires_delta=access_token_expires)
    
    # 9. Return: Token + User-Daten + Mandanten-Liste (für Frontend-Caching)
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user_id": str(user['uid']),
        "email": email,
        "name": user['name'],
        "password_change_required": password_change_required,
        # NEU: Auto-Select Flag (falls nur ein Mandant oder DEFAULT gesetzt)
        "auto_select_mandant": auto_select_mandant,
        # NEU: Vollständige User-Daten und gefilterte Mandanten-Liste
        "user_data": user.get('daten', {}),
        "mandanten": filtered_mandanten
    }


@router.post("/password-change")
async def change_password(payload: PasswordChangeRequest, current_user: dict = Depends(get_current_user)):
    """
    Ändert Passwort des aktuellen Users (erforderlich bei PASSWORD_CHANGE_REQUIRED).
    """
    from app.core.pdvm_central_benutzer import PdvmCentralBenutzer
    from app.core.password_reset_service import clear_password_reset_flags, mark_password_changed

    new_password = str(payload.new_password or "").strip()
    confirm_password = str(payload.confirm_password or "").strip()
    if new_password != confirm_password:
        raise HTTPException(status_code=400, detail="Passwörter stimmen nicht überein")

    user_id = current_user.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Ungültiger Benutzer")

    user_manager = UserManager()
    ok, msg = user_manager.validate_password_complexity(new_password)
    if not ok:
        raise HTTPException(status_code=400, detail=msg or "Passwort erfüllt die Richtlinie nicht")

    # Locked accounts cannot change passwords
    user = await user_manager.get_user_by_id(user_id)
    if user and isinstance(user.get('daten'), dict):
        security = user['daten'].get('SECURITY', {})
        if isinstance(security, dict) and security.get('ACCOUNT_LOCKED'):
            raise HTTPException(status_code=403, detail="Der Account ist gesperrt. Bitte wenden Sie sich an den Administrator.")

    new_hash = user_manager.hash_password(new_password)
    mgr = PdvmCentralBenutzer(uuid.UUID(str(user_id)))
    await mgr.change_password(new_hash)

    await clear_password_reset_flags(user_uid=str(user_id))
    await mark_password_changed(user_uid=str(user_id))

    response = {"success": True, "message": "Passwort wurde geändert"}
    if current_user.get("pwc"):
        # Das eingeschränkte Token wird durch ein vollwertiges ersetzt (frische Benutzerdaten, normale Laufzeit)
        fresh = await user_manager.get_user_by_id(user_id) or user
        response["access_token"] = create_access_token(
            data={
                "sub": str(user_id),
                "email": current_user.get("email"),
                "name": current_user.get("name"),
                "user_data": (fresh or {}).get("daten") or {},
            },
            expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
        )
        response["token_type"] = "bearer"
    return response


@router.post("/forgot-password")
async def forgot_password(payload: ForgotPasswordRequest, request: Request):
    """
    Vergisst-Passwort-Flow: Benutzer (Anmeldename) und die dort hinterlegte E-Mail-Adresse (USER.EMAIL) muessen beide stimmen.
    Dann laeuft derselbe Vorgang wie bei der Aktion "Maschinelles Passwort setzen": maschinelles Passwort erzeugen,
    per E-Mail senden und "Passwortwechsel erforderlich" setzen (`issue_password_reset`).

    Die Antwort ist immer dieselbe (keine Benutzer-Aufzaehlung, Login-Frame-Spec F3); der Versand laeuft im Hintergrund,
    damit die Laufzeit nicht verraet, ob die Angaben stimmen. Fehler stehen nur im Log. Begrenzung je IP.
    """
    client_ip = request.client.host if request.client else "unknown"
    if not _forgot_requests.allow(client_ip):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Zu viele Anfragen. Bitte später erneut versuchen.")

    user_manager = UserManager()
    benutzer = user_manager.normalize_email(str(payload.benutzer or "").strip())
    email = user_manager.normalize_email(str(payload.email or "").strip())

    if not user_manager.validate_email(benutzer) or not user_manager.validate_email(email):
        raise HTTPException(status_code=400, detail="Ungültige E-Mail-Adresse")

    async def _send() -> None:
        try:
            user = await user_manager.get_user_by_email(benutzer)
            if not user:
                logger.info("Passwort vergessen: Benutzer unbekannt (%s)", benutzer)
                return
            stored = stored_user_email(user)
            if not stored:
                logger.warning("Passwort vergessen: Konto %s hat keine E-Mail-Adresse hinterlegt", benutzer)
                return
            if user_manager.normalize_email(stored) != email:
                logger.info("Passwort vergessen: E-Mail-Adresse passt nicht zum Konto %s", benutzer)
                return
            result = await issue_password_reset(gcs=None, user_uid=str(user["uid"]))
            if not result.get("email_sent"):
                logger.warning("Passwort vergessen: E-Mail fuer %s nicht versendet: %s", benutzer, result.get("email_error"))
        except Exception as exc:
            logger.error("Passwort vergessen fehlgeschlagen (%s): %s", benutzer, exc)

    task = asyncio.create_task(_send())
    _background_tasks.add(task)  # Referenz halten, bis der Versand fertig ist
    task.add_done_callback(_background_tasks.discard)
    return {"email_sent": True, "message": FORGOT_PASSWORD_REPLY}


@router.post("/keep-alive")
async def keep_alive(current_user: dict = Depends(get_current_user)):
    """Aktualisiert Session-Aktivität und liefert Idle-Status (Mandant ROOT)."""
    token = current_user.get("token")
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Kein Session-Token gefunden")

    gcs = get_gcs_session(token)
    if not gcs:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Keine GCS-Session gefunden. Bitte Mandant auswählen.")

    try:
        gcs.touch()

        # Sliding Session: solange der User aktiv ist, JWT erneuern.
        user_id = str(current_user.get("sub") or "").strip()
        refreshed_token = None
        if user_id:
            refreshed_token = create_access_token(
                data={
                    "sub": user_id,
                    "email": current_user.get("email"),
                    "name": current_user.get("name"),
                    "user_data": current_user.get("user_data", {}),
                },
                expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
            )

            if refreshed_token:
                rotate_gcs_session_token(token, refreshed_token)

        payload = {"ok": True, **gcs.get_idle_status()}
        if refreshed_token:
            payload["access_token"] = refreshed_token
        return payload
    except Exception:
        return {"ok": True}

@router.get("/me")
async def read_users_me(current_user: dict = Depends(get_current_user)):
    """Get current user info (frisch aus DB für user_data/SECURITY)."""
    user_id = str(current_user.get("sub") or "").strip()
    if not user_id:
        return current_user

    user_manager = UserManager()
    fresh_user = await user_manager.get_user_by_id(user_id)
    if not fresh_user:
        return current_user

    return {
        **current_user,
        "email": fresh_user.get("benutzer") or current_user.get("email"),
        "name": fresh_user.get("name") or current_user.get("name"),
        "user_data": fresh_user.get("daten") or {},
    }


@router.post("/logout")
async def logout(current_user: dict = Depends(get_current_user)):
    """
    Logout endpoint - Löscht GCS-Session
    
    Returns:
        Success-Nachricht
    """
    from app.core.pdvm_central_systemsteuerung import close_gcs_session
    
    # Token aus current_user holen
    token = current_user.get("token")
    
    if token:
        try:
            # GCS-Session schließen (Pools schließen, Session löschen)
            await close_gcs_session(token)
            logger.info(f"✅ Logout erfolgreich: User {current_user.get('sub')}")
        except Exception as e:
            logger.error(f"Fehler beim Logout: {e}")
    
    return {"success": True, "message": "Erfolgreich abgemeldet"}


@router.get("/debug/me")
async def debug_current_user(current_user: dict = Depends(get_current_user)):
    """Debug endpoint: Show current_user dict structure"""
    import json
    return {
        "current_user": current_user,
        "has_sub": "sub" in current_user,
        "has_uid": "uid" in current_user,
        "sub_value": current_user.get("sub"),
        "uid_value": current_user.get("uid"),
        "all_keys": list(current_user.keys()),
        "json_dump": json.dumps(current_user, default=str, indent=2)
    }

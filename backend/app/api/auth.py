"""
Authentication API Routes
Login, register, token management

Nach Desktop-Vorbild: pdvm_login_dialog.py
"""
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from datetime import timedelta
import logging
from app.models.schemas import Token, UserLogin, UserCreate
from app.core.security import (
    create_access_token,
    get_current_user
)
from app.core.config import settings
from app.core.user_manager import UserManager

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post("/login", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    """
    Login endpoint nach Desktop-Vorbild
    
    Features:
    - Email-Normalisierung (case-insensitive)
    - bcrypt Password-Verifizierung
    - Account-Lock nach 5 Fehlversuchen
    - Last-Login Tracking
    - Failed-Login Counter
    
    Returns JWT token on success
    """
    user_manager = UserManager()
    
    # Email normalisieren (case-insensitive)
    email = user_manager.normalize_email(form_data.username)
    password = form_data.password
    
    logger.info(f"🔍 Login-Versuch: {email}")
    
    # 1. SECURITY CHECK: Account gesperrt?
    if await user_manager.is_account_locked(email):
        logger.warning(f"❌ Account gesperrt: {email}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account gesperrt nach zu vielen Fehlversuchen. Bitte kontaktieren Sie einen Administrator.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # 2. User aus Datenbank laden
    user = await user_manager.get_user_by_email(email)
    
    if not user:
        logger.warning(f"❌ Benutzer nicht gefunden: {email}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Falsche Email oder Passwort",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # 3. Passwort mit bcrypt verifizieren
    if not user_manager.verify_password(password, user['passwort']):
        logger.warning(f"❌ Falsches Passwort für: {email}")
        
        # Failed-Login Counter erhöhen
        failed_count = await user_manager.increment_failed_login(email)
        
        if failed_count >= 5:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Account gesperrt nach {failed_count} Fehlversuchen.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Falsches Passwort. Verbleibende Versuche: {5 - failed_count}",
                headers={"WWW-Authenticate": "Bearer"},
            )
    
    # 4. ✅ LOGIN ERFOLGREICH
    logger.info(f"✅ Login erfolgreich: {user['name']} ({email})")
    
    # 5. Last-Login aktualisieren + Failed-Attempts zurücksetzen
    await user_manager.update_last_login(email)
    
    # 6. Prüfe ob Passwort geändert werden muss
    password_change_required = await user_manager.check_password_change_required(email)
    
    # 7. Lade Mandanten-Liste für User (mit Berechtigungs-Filter)
    from app.core.data_managers import MandantDataManager
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
        allowed_mandanten_list = [default_mandant]
    
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
        if str(m["uid"]) in allowed_mandanten_list and str(m["uid"]) not in SYSTEM_MANDANT_UIDS
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
    access_token = create_access_token(
        data={
            "sub": str(user['uid']),  # User-ID (Primary Key)
            "email": email,
            "name": user['name'],
            "user_data": user_daten  # Vollständige JSONB-Daten (MEINEAPPS, SETTINGS, etc.)
        },
        expires_delta=access_token_expires
    )
    
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

@router.get("/me")
async def read_users_me(current_user: dict = Depends(get_current_user)):
    """Get current user info"""
    return current_user


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

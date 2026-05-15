"""
Authentication and Security
JWT tokens, password hashing
"""
from datetime import datetime, timedelta
import uuid
from typing import Optional, Set
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from app.core.config import settings

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# OAuth2 scheme
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify password against hash"""
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    """Hash password"""
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create JWT access token"""
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    # Make tokens unique per login/session.
    # Without iat/jti, two logins within the same second can produce identical JWTs,
    # which can accidentally reuse in-memory GCS sessions.
    now = datetime.utcnow()
    to_encode.update(
        {
            "exp": expire,
            "iat": int(now.timestamp()),
            "jti": str(uuid.uuid4()),
        }
    )
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    
    return encoded_jwt

async def get_current_user(request: Request, token: str = Depends(oauth2_scheme)) -> dict:
    """
    Validate JWT token and return user data from token payload.
    
    NO DATABASE LOOKUPS - all user data comes from JWT payload.
    This makes token validation fast and stateless.
    
    Returns:
        User-dict mit sub (user_id), email, name aus JWT payload
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        # JWT Token dekodieren und Signatur verifizieren
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        
        # User-ID ist zwingend erforderlich
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
        
        # User-Daten aus Token-Payload extrahieren (no DB lookup!)
        user_data = {
            "sub": user_id,  # User-ID (UUID)
            "email": payload.get("email"),
            "name": payload.get("name"),
            "user_data": payload.get("user_data", {}),  # Vollständige JSONB-Daten (MEINEAPPS, etc.)
            "token": token,  # JWT-Token für GCS-Session-Lookup
            "client_ip": request.client.host if request and request.client else None,
            "user_agent": request.headers.get("user-agent") if request else None,
        }
        
        return user_data
    
    except JWTError:
        raise credentials_exception


def has_admin_rights(current_user: dict) -> bool:
    """
    Zentraler Admin-Check fuer API-Guards.

    Unterstützte Quellen:
    - user_data.SECURITY.IS_ADMIN
    - normalisierte Rollen aus SECURITY/PERMISSIONS/SETTINGS
    """
    if not isinstance(current_user, dict):
        return False

    user_data = current_user.get("user_data")
    if not isinstance(user_data, dict):
        return False

    security = user_data.get("SECURITY") if isinstance(user_data.get("SECURITY"), dict) else {}
    is_admin = security.get("IS_ADMIN")
    roles = _normalized_security_roles(current_user)
    return is_admin in (True, 1, "1", "true", "TRUE") or bool(roles.intersection({"admin", "superadmin"}))


def _normalized_security_roles(current_user: dict) -> Set[str]:
    """Liest und normalisiert Rollen aus user_data.SECURITY, PERMISSIONS und SETTINGS."""
    if not isinstance(current_user, dict):
        return set()

    user_data = current_user.get("user_data")
    if not isinstance(user_data, dict):
        return set()

    security = user_data.get("SECURITY")
    permissions = user_data.get("PERMISSIONS")
    settings_node = user_data.get("SETTINGS")

    security = security if isinstance(security, dict) else {}
    permissions = permissions if isinstance(permissions, dict) else {}
    settings_node = settings_node if isinstance(settings_node, dict) else {}

    roles: Set[str] = set()

    role = str(security.get("ROLE") or "").strip().lower()
    if role:
        roles.add(role)

    roles_raw = security.get("ROLES")
    if isinstance(roles_raw, list):
        for item in roles_raw:
            item_norm = str(item or "").strip().lower()
            if item_norm:
                roles.add(item_norm)
    elif isinstance(roles_raw, str):
        for item in roles_raw.split(","):
            item_norm = str(item or "").strip().lower()
            if item_norm:
                roles.add(item_norm)

    # Zusätzliche Rollenquelle: PERMISSIONS.ROLES
    permissions_roles = permissions.get("ROLES")
    if isinstance(permissions_roles, list):
        for item in permissions_roles:
            item_norm = str(item or "").strip().lower()
            if item_norm:
                roles.add(item_norm)
    elif isinstance(permissions_roles, str):
        for item in permissions_roles.split(","):
            item_norm = str(item or "").strip().lower()
            if item_norm:
                roles.add(item_norm)

    # Fallback aus SETTINGS.MODE (z. B. admin/develop)
    mode = str(settings_node.get("MODE") or "").strip().lower()
    if mode:
        roles.add(mode)

    return roles


def has_develop_rights(current_user: dict) -> bool:
    """
    Zentraler Develop-Check fuer API-Guards.

    Unterstuetzte Quellen:
    - user_data.SECURITY.ROLE (develop|developer)
    - user_data.SECURITY.ROLES (Liste oder CSV)
    """
    roles = _normalized_security_roles(current_user)
    return bool(roles.intersection({"develop", "developer"}))


def has_admin_or_develop_rights(current_user: dict) -> bool:
    """Erlaubt Zugriff fuer Admin oder Develop-Rollen."""
    return has_admin_rights(current_user) or has_develop_rights(current_user)


async def require_admin_user(current_user: dict = Depends(get_current_user)) -> dict:
    """Dependency: erlaubt nur Admin-User."""
    if has_admin_rights(current_user):
        return current_user

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Admin-Recht erforderlich",
    )


async def require_admin_or_develop_user(current_user: dict = Depends(get_current_user)) -> dict:
    """Dependency: erlaubt Admin- oder Develop-User."""
    if has_admin_or_develop_rights(current_user):
        return current_user

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Admin- oder Develop-Recht erforderlich",
    )

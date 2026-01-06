"""
Authentication and Security
JWT tokens, password hashing
"""
from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
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
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    
    return encoded_jwt

async def get_current_user(token: str = Depends(oauth2_scheme)) -> dict:
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
            "token": token  # JWT-Token für GCS-Session-Lookup
        }
        
        return user_data
    
    except JWTError:
        raise credentials_exception

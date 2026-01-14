"""
Pydantic Models for API Request/Response
"""
from pydantic import BaseModel, EmailStr, Field
from typing import Dict, Any, Optional, List
from datetime import datetime

# Auth Models
class UserLogin(BaseModel):
    """User login credentials"""
    email: EmailStr
    password: str

class Token(BaseModel):
    """JWT token response - erweitert mit User-Daten und Mandanten-Liste"""
    access_token: str
    token_type: str = "bearer"
    user_id: str
    email: str
    name: Optional[str] = None
    password_change_required: bool = False
    # NEU: Cached data for frontend
    user_data: Dict[str, Any] = {}
    mandanten: List[Dict[str, Any]] = []

class UserCreate(BaseModel):
    """Create new user"""
    email: EmailStr
    password: str
    name: str

# Table Models
class RecordCreate(BaseModel):
    """Create new record"""
    daten: Dict[str, Any]
    name: Optional[str] = ""

class RecordUpdate(BaseModel):
    """Update record"""
    daten: Dict[str, Any]
    name: Optional[str] = None

class RecordResponse(BaseModel):
    """Record response"""
    uid: str
    daten: Dict[str, Any]
    name: str
    historisch: int = 0
    sec_id: Optional[str] = None
    gilt_bis: str = "9999365.00000"
    created_at: Optional[str] = None
    modified_at: Optional[str] = None

class RecordListItem(BaseModel):
    """Record list item (minimal)"""
    uid: str
    name: str
    modified_at: Optional[str] = None

# Mandanten Models
class MandantResponse(BaseModel):
    """Mandant in list"""
    id: str
    name: str
    is_allowed: bool
    description: str

class MandantSelectRequest(BaseModel):
    """Select mandant request"""
    mandant_id: str

class MandantSelectResponse(BaseModel):
    """Mandant selection response"""
    mandant_id: str
    mandant_name: str
    mandant_town: Optional[str] = None
    mandant_street: Optional[str] = None
    database: str
    message: str

# Error Response
class ErrorResponse(BaseModel):
    """Error response"""
    detail: str

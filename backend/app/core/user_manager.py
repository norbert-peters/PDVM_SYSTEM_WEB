"""
User Management System für PDVM Web
Nach Desktop-Vorbild: PdvmUserDatenbank

Features:
- bcrypt Password Hashing
- Email-Validierung
- Password-Komplexität
- Account-Lock nach Fehlversuchen
- Last-Login Tracking
"""
import re
import json
import bcrypt
import logging
from typing import Optional, Tuple, Dict, Any
from datetime import datetime
from app.core.config import settings
from app.core.database import DatabasePool

logger = logging.getLogger(__name__)

# Validierungs-Patterns
EMAIL_REGEX = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
PASSWORD_MIN_LENGTH = 8
PASSWORD_REGEX = r'^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&])[A-Za-z\d@$!%*?&]{8,}$'


class UserManager:
    """User-Management nach Desktop-Vorbild"""
    
    def __init__(self):
        """Initialisiere User-Manager mit auth-Datenbank"""
        logger.info("UserManager initialisiert")
    
    @staticmethod
    def normalize_email(email: str) -> str:
        """
        Normalisiert Email (case-insensitive)
        
        Args:
            email: Email-Adresse
            
        Returns:
            Email in Kleinbuchstaben
        """
        if email:
            return email.strip().lower()
        return email
    
    @staticmethod
    def validate_email(email: str) -> bool:
        """
        Validiert Email-Format
        
        Args:
            email: Email-Adresse
            
        Returns:
            True wenn gültig
        """
        if not email:
            return False
        return bool(re.match(EMAIL_REGEX, email))
    
    @staticmethod
    def validate_password_complexity(password: str) -> Tuple[bool, Optional[str]]:
        """
        Prüft Passwort-Komplexität
        
        Anforderungen:
        - Min. 8 Zeichen
        - Min. 1 Großbuchstabe
        - Min. 1 Kleinbuchstabe
        - Min. 1 Zahl
        - Min. 1 Sonderzeichen (@$!%*?&)
        
        Args:
            password: Passwort im Klartext
            
        Returns:
            (gültig, Fehlermeldung oder None)
        """
        if not password:
            return False, "Passwort darf nicht leer sein"
        
        if len(password) < PASSWORD_MIN_LENGTH:
            return False, f"Passwort muss mindestens {PASSWORD_MIN_LENGTH} Zeichen lang sein"
        
        if not re.search(r'[a-z]', password):
            return False, "Passwort muss mindestens einen Kleinbuchstaben enthalten"
        
        if not re.search(r'[A-Z]', password):
            return False, "Passwort muss mindestens einen Großbuchstaben enthalten"
        
        if not re.search(r'\d', password):
            return False, "Passwort muss mindestens eine Zahl enthalten"
        
        if not re.search(r'[@$!%*?&]', password):
            return False, "Passwort muss mindestens ein Sonderzeichen (@$!%*?&) enthalten"
        
        return True, None
    
    @staticmethod
    def hash_password(password: str) -> str:
        """
        Erstellt bcrypt-Hash eines Passworts
        
        Args:
            password: Passwort im Klartext
            
        Returns:
            Gehashtes Passwort
        """
        if not password:
            raise ValueError("Passwort darf nicht leer sein")
        
        password_bytes = password.encode('utf-8')
        salt = bcrypt.gensalt()
        hashed = bcrypt.hashpw(password_bytes, salt)
        
        return hashed.decode('utf-8')
    
    @staticmethod
    def verify_password(password: str, hashed_password: str) -> bool:
        """
        Verifiziert Passwort gegen Hash
        
        Args:
            password: Passwort im Klartext
            hashed_password: Gehashtes Passwort aus DB
            
        Returns:
            True wenn Passwort korrekt
        """
        if not password or not hashed_password:
            return False
        
        try:
            password_bytes = password.encode('utf-8')
            hashed_bytes = hashed_password.encode('utf-8')
            return bcrypt.checkpw(password_bytes, hashed_bytes)
        except Exception as e:
            logger.error(f"Fehler bei Passwort-Verifizierung: {e}")
            return False
    
    async def get_user_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        Lädt Benutzer aus Datenbank via UID
        
        Args:
            user_id: User UUID
            
        Returns:
            User-Daten oder None
        """
        try:
            pool = DatabasePool._pool_auth
            
            async with pool.acquire() as conn:
                user = await conn.fetchrow("""
                    SELECT uid, benutzer, passwort, name, daten
                    FROM sys_benutzer
                    WHERE uid = $1::uuid
                """, user_id)
                
                if user:
                    user_dict = dict(user)
                    # Parse JSONB daten field wenn String
                    if user_dict.get('daten') and isinstance(user_dict['daten'], str):
                        try:
                            user_dict['daten'] = json.loads(user_dict['daten'])
                        except:
                            user_dict['daten'] = {}
                    elif not user_dict.get('daten'):
                        user_dict['daten'] = {}
                    return user_dict
                return None
            
        except Exception as e:
            logger.error(f"Fehler beim Laden des Benutzers {user_id}: {e}")
            return None
    
    async def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """
        Lädt Benutzer aus Datenbank
        
        Args:
            email: Email-Adresse (wird normalisiert)
            
        Returns:
            User-Daten oder None
        """
        email = self.normalize_email(email)
        
        try:
            pool = DatabasePool._pool_auth
            
            async with pool.acquire() as conn:
                user = await conn.fetchrow("""
                    SELECT uid, benutzer, passwort, name, daten
                    FROM sys_benutzer
                    WHERE benutzer = $1
                """, email)
                
                if user:
                    user_dict = dict(user)
                    # Parse JSONB daten field wenn String
                    if user_dict.get('daten') and isinstance(user_dict['daten'], str):
                        try:
                            user_dict['daten'] = json.loads(user_dict['daten'])
                        except:
                            user_dict['daten'] = {}
                    elif not user_dict.get('daten'):
                        user_dict['daten'] = {}
                    return user_dict
                return None
            
        except Exception as e:
            logger.error(f"Fehler beim Laden des Benutzers {email}: {e}")
            return None
    
    async def is_account_locked(self, email: str) -> bool:
        """
        Prüft ob Account gesperrt ist
        
        Args:
            email: Email-Adresse
            
        Returns:
            True wenn gesperrt
        """
        user = await self.get_user_by_email(email)
        if not user or not user['daten']:
            return False
        
        security = user['daten'].get('SECURITY', {})
        return security.get('ACCOUNT_LOCKED', False)
    
    async def increment_failed_login(self, email: str) -> int:
        """
        Erhöht Failed-Login Counter
        
        Args:
            email: Email-Adresse
            
        Returns:
            Neue Anzahl Failed-Attempts
        """
        email = self.normalize_email(email)
        
        try:
            pool = DatabasePool._pool_auth
            
            async with pool.acquire() as conn:
                # Aktuellen Counter holen
                current = await conn.fetchval("""
                    SELECT daten->'SECURITY'->>'FAILED_LOGIN_ATTEMPTS'
                    FROM sys_benutzer
                    WHERE benutzer = $1
                """, email)
                
                failed_count = int(current) if current else 0
                failed_count += 1
                
                # Account sperren nach 5 Fehlversuchen
                account_locked = failed_count >= 5
                
                # Update
                await conn.execute("""
                UPDATE sys_benutzer
                SET daten = jsonb_set(
                    jsonb_set(
                        daten,
                        '{SECURITY,FAILED_LOGIN_ATTEMPTS}',
                        to_jsonb($2::int)
                    ),
                    '{SECURITY,ACCOUNT_LOCKED}',
                    to_jsonb($3::boolean)
                )
                WHERE benutzer = $1
            """, email, failed_count, account_locked)
            
            if account_locked:
                logger.warning(f"⚠️ Account gesperrt nach {failed_count} Fehlversuchen: {email}")
            
            return failed_count
            
        except Exception as e:
            logger.error(f"Fehler beim Increment Failed-Login für {email}: {e}")
            return 0
    
    async def update_last_login(self, email: str):
        """
        Aktualisiert Last-Login Timestamp (PDVM-Format YYYYDDD.decimal) und setzt Failed-Attempts zurück
        
        Args:
            email: Email-Adresse
        """
        email = self.normalize_email(email)
        
        try:
            from app.core.pdvm_time import datetime_to_pdvm
            pool = DatabasePool._pool_auth
            
            async with pool.acquire() as conn:
                # PDVM Timestamp-Format: YYYYDDD.Zeitanteil (z.B. 2025366.235959)
                current_timestamp = datetime_to_pdvm(datetime.utcnow())
                
                # Update Last-Login und Reset Failed-Attempts
                await conn.execute("""
                UPDATE sys_benutzer
                SET daten = jsonb_set(
                    jsonb_set(
                        daten,
                        '{SECURITY,LAST_LOGIN}',
                        to_jsonb($2::numeric)
                    ),
                    '{SECURITY,FAILED_LOGIN_ATTEMPTS}',
                    '0'::jsonb
                )
                WHERE benutzer = $1
            """, email, current_timestamp)
            
            logger.info(f"✅ Last-Login aktualisiert für {email}")
            
        except Exception as e:
            logger.error(f"Fehler beim Update Last-Login für {email}: {e}")
    
    async def check_password_change_required(self, email: str) -> bool:
        """
        Prüft ob Passwort geändert werden muss
        
        Args:
            email: Email-Adresse
            
        Returns:
            True wenn Änderung erforderlich
        """
        user = await self.get_user_by_email(email)
        if not user or not user['daten']:
            return False
        
        security = user['daten'].get('SECURITY', {})
        return security.get('PASSWORD_CHANGE_REQUIRED', False)
    
    async def unlock_account(self, email: str) -> bool:
        """
        Entsperrt Account (nur durch Admin)
        
        Args:
            email: Email-Adresse
            
        Returns:
            True bei Erfolg
        """
        email = self.normalize_email(email)
        
        try:
            pool = DatabasePool._pool_auth
            
            async with pool.acquire() as conn:
                # Reset Account-Lock und Failed-Attempts
                await conn.execute("""
                    UPDATE sys_benutzer
                    SET daten = jsonb_set(
                        jsonb_set(
                            daten,
                            '{SECURITY,ACCOUNT_LOCKED}',
                            'false'::jsonb
                        ),
                        '{SECURITY,FAILED_LOGIN_ATTEMPTS}',
                        '0'::jsonb
                    )
                    WHERE benutzer = $1
                """, email)
                
                logger.info(f"✅ Account entsperrt: {email}")
                return True
            
        except Exception as e:
            logger.error(f"Fehler beim Entsperren von {email}: {e}")
            return False

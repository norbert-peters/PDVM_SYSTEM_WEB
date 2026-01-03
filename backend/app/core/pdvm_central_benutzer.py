"""
PDVM Central Benutzer
Benutzer-Management für sys_benutzer

Besonderheit: sys_benutzer hat Zusatzspalten 'benutzer' und 'passwort'
Wird vom Administrator für Benutzerverwaltung verwendet
"""
import uuid
from typing import Optional, Dict, List
from app.core.pdvm_central_datenbank import PdvmCentralDatabase
from app.core.database import DatabasePool
import json


class PdvmCentralBenutzer(PdvmCentralDatabase):
    """
    Benutzer-Management
    Wird vom Administrator für Benutzerverwaltung verwendet
    
    Besonderheit: sys_benutzer hat Zusatzspalten 'benutzer' und 'passwort'
    """
    
    def __init__(self, user_guid: uuid.UUID):
        """
        Initialisiert Benutzer-Manager für spezifischen User
        
        Args:
            user_guid: UUID des Benutzers
        """
        super().__init__("sys_benutzer", user_guid)
        self.user_guid = user_guid
    
    async def get_user(self) -> Optional[Dict]:
        """
        Lädt kompletten User mit allen Spalten
        
        Returns:
            Dict mit uid, email, benutzer, passwort, daten, historisch, etc.
            None wenn nicht gefunden
        """
        pool = DatabasePool._pool_auth
        async with pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT uid, email, benutzer, passwort, daten,
                       historisch, sec_id, created_at, modified_at
                FROM sys_benutzer 
                WHERE uid = $1
            """, self.user_guid)
            
            if not row:
                return None
            
            result = dict(row)
            
            # Parse JSONB daten
            if result['daten'] and isinstance(result['daten'], str):
                result['daten'] = json.loads(result['daten'])
            
            return result
    
    async def get_user_by_email(self, email: str) -> Optional[Dict]:
        """
        Lädt User anhand Email
        
        Args:
            email: Email-Adresse
        
        Returns:
            User-Dict oder None
        """
        pool = DatabasePool._pool_auth
        async with pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT uid, email, benutzer, passwort, daten,
                       historisch, sec_id, created_at, modified_at
                FROM sys_benutzer 
                WHERE email = $1
            """, email)
            
            if not row:
                return None
            
            result = dict(row)
            if result['daten'] and isinstance(result['daten'], str):
                result['daten'] = json.loads(result['daten'])
            
            return result
    
    async def change_password(self, new_password_hash: str):
        """
        Ändert Passwort des Users
        
        Args:
            new_password_hash: Bcrypt-Hash des neuen Passworts
        """
        pool = DatabasePool._pool_auth
        async with pool.acquire() as conn:
            await conn.execute("""
                UPDATE sys_benutzer 
                SET passwort = $1, modified_at = NOW() 
                WHERE uid = $2
            """, new_password_hash, self.user_guid)
    
    async def update_email(self, new_email: str):
        """
        Ändert Email-Adresse des Users
        
        Args:
            new_email: Neue Email-Adresse
        """
        pool = DatabasePool._pool_auth
        async with pool.acquire() as conn:
            await conn.execute("""
                UPDATE sys_benutzer 
                SET email = $1, modified_at = NOW() 
                WHERE uid = $2
            """, new_email, self.user_guid)
    
    async def update_benutzer(self, new_benutzer: str):
        """
        Ändert Benutzername
        
        Args:
            new_benutzer: Neuer Benutzername
        """
        pool = DatabasePool._pool_auth
        async with pool.acquire() as conn:
            await conn.execute("""
                UPDATE sys_benutzer 
                SET benutzer = $1, modified_at = NOW() 
                WHERE uid = $2
            """, new_benutzer, self.user_guid)
    
    async def deactivate(self):
        """Deaktiviert User (soft delete via historisch=1)"""
        pool = DatabasePool._pool_auth
        async with pool.acquire() as conn:
            await conn.execute("""
                UPDATE sys_benutzer 
                SET historisch = 1, modified_at = NOW() 
                WHERE uid = $1
            """, self.user_guid)
    
    async def reactivate(self):
        """Reaktiviert deaktivierten User"""
        pool = DatabasePool._pool_auth
        async with pool.acquire() as conn:
            await conn.execute("""
                UPDATE sys_benutzer 
                SET historisch = 0, modified_at = NOW() 
                WHERE uid = $1
            """, self.user_guid)
    
    @staticmethod
    async def get_all_users(include_inactive: bool = False) -> List[Dict]:
        """
        Lädt alle Benutzer (für Admin)
        
        Args:
            include_inactive: True = auch deaktivierte User
        
        Returns:
            Liste von User-Dicts
        """
        pool = DatabasePool._pool_auth
        async with pool.acquire() as conn:
            if include_inactive:
                where_clause = ""
            else:
                where_clause = "WHERE historisch = 0"
            
            rows = await conn.fetch(f"""
                SELECT uid, email, benutzer, daten, historisch, created_at
                FROM sys_benutzer
                {where_clause}
                ORDER BY benutzer
            """)
            
            result = []
            for row in rows:
                row_dict = dict(row)
                if row_dict['daten'] and isinstance(row_dict['daten'], str):
                    row_dict['daten'] = json.loads(row_dict['daten'])
                result.append(row_dict)
            
            return result
    
    @staticmethod
    async def create_user(
        email: str, 
        benutzer: str, 
        passwort_hash: str,
        daten: Optional[Dict] = None,
        sec_id: Optional[uuid.UUID] = None
    ) -> uuid.UUID:
        """
        Erstellt neuen Benutzer (für Admin)
        
        Args:
            email: Email-Adresse
            benutzer: Benutzername
            passwort_hash: Bcrypt-Hash des Passworts
            daten: Optional JSONB-Daten
            sec_id: Optional Security Profile
        
        Returns:
            UUID des neuen Users
        """
        pool = DatabasePool._pool_auth
        user_guid = uuid.uuid4()
        
        daten_json = json.dumps(daten) if daten else json.dumps({})
        
        async with pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO sys_benutzer 
                (uid, email, benutzer, passwort, daten, historisch, sec_id, gilt_bis)
                VALUES ($1, $2, $3, $4, $5, 0, $6, '9999365.00000')
            """, user_guid, email, benutzer, passwort_hash, daten_json, sec_id)
        
        return user_guid
    
    @staticmethod
    async def email_exists(email: str) -> bool:
        """
        Prüft ob Email bereits existiert
        
        Returns:
            True wenn Email bereits verwendet
        """
        pool = DatabasePool._pool_auth
        async with pool.acquire() as conn:
            count = await conn.fetchval("""
                SELECT COUNT(*) 
                FROM sys_benutzer 
                WHERE email = $1 AND historisch = 0
            """, email)
            return count > 0

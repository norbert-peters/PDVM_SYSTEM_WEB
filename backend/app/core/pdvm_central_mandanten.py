"""
PDVM Central Mandanten
Mandanten-Management für sys_mandanten

Zentrale Stelle für Mandanten-Datenbanksteuerung
Regelt Zugriff auf mandantenspezifische Datenbanken
"""
import uuid
from typing import Optional, Dict, List
from app.core.pdvm_central_datenbank import PdvmCentralDatabase
from app.core.database import DatabasePool
import json


class PdvmCentralMandanten(PdvmCentralDatabase):
    """
    Mandanten-Management
    Regelt Zugriff auf mandantenspezifische Datenbanken
    
    sys_mandanten in auth.db enthält Pfade zu mandant.db und system.db
    """
    
    def __init__(self, mandant_guid: uuid.UUID):
        """
        Initialisiert Mandanten-Manager
        
        Args:
            mandant_guid: UUID des Mandanten
        """
        super().__init__("sys_mandanten", mandant_guid)
        self.mandant_guid = mandant_guid
    
    async def get_mandant(self) -> Optional[Dict]:
        """
        Lädt kompletten Mandanten-Datensatz
        
        Returns:
            Dict mit uid, name, daten, etc.
            None wenn nicht gefunden
        """
        pool = DatabasePool._pool_auth
        async with pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT uid, name, daten, historisch, 
                       sec_id, created_at, modified_at
                FROM sys_mandanten
                WHERE uid = $1
            """, self.mandant_guid)
            
            if not row:
                return None
            
            result = dict(row)
            
            # Parse JSONB daten
            if result['daten'] and isinstance(result['daten'], str):
                result['daten'] = json.loads(result['daten'])
            
            return result
    
    async def get_database_info(self) -> Optional[Dict]:
        """
        Liest Datenbank-Verbindungsinfo aus daten JSONB
        
        Returns:
            {
                'mandant_db': 'mandant_firma_xyz',
                'system_db': 'pdvm_system',
                'host': 'localhost',
                'port': 5432,
                'user': 'postgres',
                'password': '***'
            }
            None wenn nicht gefunden
        """
        row = await self.db.get_row(self.mandant_guid)
        if not row or not row['daten']:
            return None
        
        daten = row['daten']
        
        return {
            'mandant_db': daten.get('DATABASE'),
            'system_db': daten.get('SYSTEM_DATABASE', 'pdvm_system'),
            'host': daten.get('HOST', 'localhost'),
            'port': daten.get('PORT', 5432),
            'user': daten.get('USER', 'postgres'),
            'password': daten.get('PASSWORD', 'Polari$55')
        }
    
    async def create_database_pool(self):
        """
        Erstellt Connection Pool für diesen Mandanten
        Registriert Pool bei DatabasePool für spätere Verwendung
        """
        db_info = await self.get_database_info()
        if not db_info:
            raise ValueError(f"Keine Datenbankinfo für Mandant {self.mandant_guid}")
        
        if not db_info['mandant_db']:
            raise ValueError(f"Keine mandant_db für Mandant {self.mandant_guid}")
        
        # Baue Connection URL
        db_url = (
            f"postgresql://{db_info['user']}:{db_info['password']}"
            f"@{db_info['host']}:{db_info['port']}/{db_info['mandant_db']}"
        )
        
        # NOTE: Pool registration removed - pools now managed in GCS per session
    
    async def get_mandant_name(self) -> Optional[str]:
        """
        Gibt Namen des Mandanten zurück
        
        Returns:
            Mandantenname oder None
        """
        row = await self.db.get_row(self.mandant_guid)
        return row['name'] if row else None
    
    @staticmethod
    async def get_all_mandanten(include_inactive: bool = False) -> List[Dict]:
        """
        Lädt alle Mandanten (für Auswahl beim Login)
        
        Args:
            include_inactive: True = auch deaktivierte Mandanten
        
        Returns:
            Liste von Mandanten-Dicts
        """
        pool = DatabasePool._pool_auth
        async with pool.acquire() as conn:
            if include_inactive:
                where_clause = ""
            else:
                where_clause = "WHERE historisch = 0"
            
            rows = await conn.fetch(f"""
                SELECT uid, name, daten, historisch, created_at
                FROM sys_mandanten
                {where_clause}
                ORDER BY name
            """)
            
            result = []
            for row in rows:
                row_dict = dict(row)
                if row_dict['daten'] and isinstance(row_dict['daten'], str):
                    row_dict['daten'] = json.loads(row_dict['daten'])
                result.append(row_dict)
            
            return result
    
    @staticmethod
    async def create_mandant(
        name: str,
        mandant_db: str,
        system_db: str = "pdvm_system",
        host: str = "localhost",
        port: int = 5432,
        user: str = "postgres",
        password: str = "Polari$55"
    ) -> uuid.UUID:
        """
        Erstellt neuen Mandanten (für Admin)
        
        Args:
            name: Mandantenname
            mandant_db: Name der Mandanten-Datenbank
            system_db: Name der System-Datenbank
            host: Datenbank-Host
            port: Datenbank-Port
            user: Datenbank-User
            password: Datenbank-Passwort
        
        Returns:
            UUID des neuen Mandanten
        """
        pool = DatabasePool._pool_auth
        mandant_guid = uuid.uuid4()
        
        daten = {
            'DATABASE': mandant_db,
            'SYSTEM_DATABASE': system_db,
            'HOST': host,
            'PORT': port,
            'USER': user,
            'PASSWORD': password
        }
        
        async with pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO sys_mandanten
                (uid, name, daten, historisch, gilt_bis)
                VALUES ($1, $2, $3, 0, '9999365.00000')
            """, mandant_guid, name, json.dumps(daten))
        
        return mandant_guid
    
    async def update_database_info(
        self,
        mandant_db: Optional[str] = None,
        system_db: Optional[str] = None,
        host: Optional[str] = None,
        port: Optional[int] = None,
        user: Optional[str] = None,
        password: Optional[str] = None
    ):
        """
        Aktualisiert Datenbank-Verbindungsinfo
        
        Args:
            Nur übergebene Parameter werden aktualisiert
        """
        row = await self.db.get_row(self.mandant_guid)
        if not row:
            raise ValueError(f"Mandant {self.mandant_guid} nicht gefunden")
        
        daten = row['daten'] or {}
        
        if mandant_db is not None:
            daten['DATABASE'] = mandant_db
        if system_db is not None:
            daten['SYSTEM_DATABASE'] = system_db
        if host is not None:
            daten['HOST'] = host
        if port is not None:
            daten['PORT'] = port
        if user is not None:
            daten['USER'] = user
        if password is not None:
            daten['PASSWORD'] = password
        
        await self.db.update(self.mandant_guid, daten)
    
    async def deactivate(self):
        """Deaktiviert Mandanten (soft delete via historisch=1)"""
        pool = DatabasePool._pool_auth
        async with pool.acquire() as conn:
            await conn.execute("""
                UPDATE sys_mandanten
                SET historisch = 1, modified_at = NOW()
                WHERE uid = $1
            """, self.mandant_guid)
    
    async def reactivate(self):
        """Reaktiviert deaktivierten Mandanten"""
        pool = DatabasePool._pool_auth
        async with pool.acquire() as conn:
            await conn.execute("""
                UPDATE sys_mandanten
                SET historisch = 0, modified_at = NOW()
                WHERE uid = $1
            """, self.mandant_guid)

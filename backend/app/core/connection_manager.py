"""
Zentrale Connection-Verwaltung für Multi-Tenant Architektur

Alle Datenbank-Verbindungen (außer auth) werden dynamisch aus sys_mandanten geladen.
Dies ermöglicht:
- Mehrere PostgreSQL-Server (11, 18, etc.)
- Verschiedene Hosts/Ports pro Mandant
- Zentrale Verwaltung aller Connection-Parameter
"""
from typing import Optional, Dict, Tuple
import asyncpg
from .config import settings
import logging

logger = logging.getLogger(__name__)


class ConnectionConfig:
    """Dataclass für Connection-Parameter"""
    def __init__(self, host: str, port: int, user: str, password: str, database: str):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.database = database
    
    def to_url(self) -> str:
        """Baut PostgreSQL Connection URL"""
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"
    
    def to_dict(self) -> Dict[str, any]:
        """Gibt Connection-Parameter als Dict zurück (mit SSL disabled für PostgreSQL 18)"""
        return {
            "host": self.host,
            "port": self.port,
            "user": self.user,
            "password": self.password,
            "database": self.database,
            "ssl": False  # PostgreSQL 18 Windows: SSL deaktivieren
        }


class ConnectionManager:
    """
    Zentrale Verwaltung aller Datenbank-Verbindungen
    
    Hierarchie:
    1. AUTH-DB: Fix in config.py (global, einmalig)
    2. SYSTEM-DB (pdvm_system): Name aus sys_mandanten.MANDANT.SYSTEM_DB + Connection aus MANDANT.*
    3. MANDANTEN-DB: Alle Daten aus sys_mandanten.MANDANT.*
    """
    
    @staticmethod
    async def get_auth_config() -> ConnectionConfig:
        """
        AUTH-DB ist die einzige fix konfigurierte Datenbank.
        Diese wird für Login/Token-Validierung verwendet.
        """
        # Parse URL from settings
        url = settings.DATABASE_URL_AUTH
        # Format: postgresql://user:password@host:port/database
        parts = url.replace("postgresql://", "").split("@")
        user_pass = parts[0].split(":")
        host_port_db = parts[1].split("/")
        host_port = host_port_db[0].split(":")
        
        return ConnectionConfig(
            host=host_port[0],
            port=int(host_port[1]),
            user=user_pass[0],
            password=user_pass[1],
            database=host_port_db[1]
        )
    
    @staticmethod
    async def get_mandant_config(mandant_id: str) -> Tuple[ConnectionConfig, ConnectionConfig]:
        """
        Lädt Connection-Config für einen Mandanten aus sys_mandanten.
        
        Returns:
            Tuple[system_config, mandant_config]
            - system_config: Connection zur System-DB (z.B. pdvm_system)
            - mandant_config: Connection zur Mandanten-DB
        
        Raises:
            ValueError: Wenn Mandant nicht gefunden oder Daten unvollständig
        """
        # Verbinde mit auth DB um Mandanten-Daten zu laden
        auth_config = await ConnectionManager.get_auth_config()
        
        # Hole Mandanten-Daten aus sys_mandanten (in auth DB)
        conn = await asyncpg.connect(**auth_config.to_dict())
        try:
            # Lade Mandanten-Record
            mandant = await conn.fetchrow(
                "SELECT daten FROM sys_mandanten WHERE uid = $1",
                mandant_id
            )
            
            if not mandant:
                raise ValueError(f"Mandant '{mandant_id}' nicht gefunden")
            
            daten = mandant['daten']
            mandant_info = daten.get('MANDANT', {})
            
            # Extrahiere Connection-Parameter
            host = mandant_info.get('HOST')
            port = mandant_info.get('PORT')
            user = mandant_info.get('USER')
            password = mandant_info.get('PASSWORD')
            database = mandant_info.get('DATABASE')
            system_db = mandant_info.get('SYSTEM_DB', 'pdvm_system')
            
            # Validierung
            missing = []
            if not host: missing.append('HOST')
            if not port: missing.append('PORT')
            if not user: missing.append('USER')
            if not password: missing.append('PASSWORD')
            if not database: missing.append('DATABASE')
            
            if missing:
                raise ValueError(f"Mandant '{mandant_id}' hat fehlende Connection-Daten: {', '.join(missing)}")
            
            # Baue Connection-Configs
            system_config = ConnectionConfig(
                host=host,
                port=int(port),
                user=user,
                password=password,
                database=system_db
            )
            
            mandant_config = ConnectionConfig(
                host=host,
                port=int(port),
                user=user,
                password=password,
                database=database
            )
            
            logger.info(f"✅ Connection-Config für Mandant '{mandant_id}' geladen: "
                       f"System={system_db}, Mandant={database}, Host={host}:{port}")
            
            return system_config, mandant_config
            
        finally:
            await conn.close()
    
    @staticmethod
    async def get_system_config(system_db_name: str = "pdvm_system") -> ConnectionConfig:
        """
        Lädt Connection-Config für eine System-DB.
        Nutzt die Connection-Parameter des ersten aktiven Mandanten.
        
        WICHTIG: Für Login (vor Mandanten-Auswahl) verwenden wir die auth-DB Connection-Parameter
        mit system_db_name als Datenbank.
        
        Args:
            system_db_name: Name der System-DB (default: pdvm_system)
        
        Returns:
            ConnectionConfig für die System-DB
        """
        # Für pdvm_system verwenden wir die gleichen Connection-Parameter wie auth
        auth_config = await ConnectionManager.get_auth_config()
        
        return ConnectionConfig(
            host=auth_config.host,
            port=auth_config.port,
            user=auth_config.user,
            password=auth_config.password,
            database=system_db_name
        )
    
    @staticmethod
    async def test_connection(config: ConnectionConfig) -> bool:
        """
        Testet ob eine Connection funktioniert.
        
        Returns:
            True wenn Connection erfolgreich, False sonst
        """
        try:
            conn = await asyncpg.connect(**config.to_dict(), timeout=5)
            await conn.close()
            logger.info(f"✅ Connection-Test erfolgreich: {config.database}@{config.host}")
            return True
        except Exception as e:
            logger.error(f"❌ Connection-Test fehlgeschlagen: {config.database}@{config.host} - {e}")
            return False


# Singleton-Instance für globalen Zugriff
connection_manager = ConnectionManager()

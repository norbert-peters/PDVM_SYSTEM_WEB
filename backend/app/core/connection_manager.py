"""
Zentrale Connection-Verwaltung für Multi-Tenant Architektur

Alle Datenbank-Verbindungen (außer auth) werden dynamisch aus asy_mandanten geladen.
Dies ermöglicht:
- Mehrere PostgreSQL-Server (11, 18, etc.)
- Verschiedene Hosts/Ports pro Mandant
- Zentrale Verwaltung aller Connection-Parameter
"""
from typing import Optional, Dict, Tuple
import asyncpg
import json
from .config import settings
from .database import DatabasePool
from .mandant_tombstone import is_deleted_mandant_row
import logging
from urllib.parse import urlparse, unquote, quote
from .credential_store import Credential, DEFAULT_CREDENTIAL, get_credential

logger = logging.getLogger(__name__)


class ConnectionConfig:
    """Dataclass für Connection-Parameter"""
    def __init__(self, host: str, port: int, user: str, password: str, database: str, ssl: bool = False):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.database = database
        self.ssl = ssl

    def __repr__(self) -> str:  # Passwort nie in Logs oder Tracebacks
        return f"ConnectionConfig({self.user}@{self.host}:{self.port}/{self.database})"

    def to_url(self) -> str:
        """Baut PostgreSQL Connection URL (Benutzer und Passwort URL-kodiert)"""
        url = (
            f"postgresql://{quote(str(self.user), safe='')}:{quote(str(self.password), safe='')}"
            f"@{self.host}:{self.port}/{self.database}"
        )
        return f"{url}?sslmode=require" if self.ssl else url

    def to_dict(self) -> Dict[str, any]:
        """Gibt Connection-Parameter als Dict zurück (SSL nur, wenn der Credential es verlangt)"""
        return {
            "host": self.host,
            "port": self.port,
            "user": self.user,
            "password": self.password,
            "database": self.database,
            "ssl": "require" if self.ssl else False  # PostgreSQL 18 Windows: SSL standardmaessig deaktiviert
        }


class ConnectionManager:
    """
    Zentrale Verwaltung aller Datenbank-Verbindungen
    
    Hierarchie:
    1. AUTH-DB: Fix in config.py (global, einmalig)
    2. SYSTEM-DB (pdvm_system): Name aus asy_mandanten.MANDANT.SYSTEM_DB + Connection aus MANDANT.*
    3. MANDANTEN-DB: Alle Daten aus asy_mandanten.MANDANT.*
    """
    
    @staticmethod
    def _normalize_mandant_daten(raw_daten) -> Dict[str, object]:
        """Normalisiert asy_mandanten.daten auf Dict (JSON-String kompatibel)."""
        if isinstance(raw_daten, dict):
            return raw_daten
        if isinstance(raw_daten, str):
            try:
                parsed = json.loads(raw_daten)
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                logger.warning("⚠️ asy_mandanten.daten ist kein gültiges JSON-Objekt")
        return {}

    @staticmethod
    def _auth_config_sync() -> ConnectionConfig:
        parsed = urlparse(settings.DATABASE_URL_AUTH)

        return ConnectionConfig(
            host=parsed.hostname or "localhost",
            port=int(parsed.port or 5432),
            user=parsed.username or "postgres",
            password=unquote(parsed.password or ""),
            database=(parsed.path or "/auth").lstrip("/")
        )

    @staticmethod
    async def get_auth_config() -> ConnectionConfig:
        """
        AUTH-DB ist die einzige fix konfigurierte Datenbank.
        Diese wird für Login/Token-Validierung verwendet.
        """
        return ConnectionManager._auth_config_sync()

    @staticmethod
    def _is_local(host: str) -> bool:
        return host.strip().lower() in {"localhost", "127.0.0.1", "::1"}

    @staticmethod
    def same_instance(a: ConnectionConfig, b: ConnectionConfig) -> bool:
        """True, wenn beide Konfigurationen auf dieselbe PostgreSQL-Instanz zeigen (Host und Port)."""
        if int(a.port) != int(b.port):
            return False
        ha, hb = a.host.strip().lower(), b.host.strip().lower()
        return ha == hb or (ConnectionManager._is_local(ha) and ConnectionManager._is_local(hb))

    @staticmethod
    def _resolve_connection(
        *,
        host: str,
        port: int,
        user_field: Optional[str],
        credential_name: Optional[str],
        legacy_password: Optional[str],
        database: str,
        auth: ConnectionConfig,
        label: str,
    ) -> ConnectionConfig:
        """
        Zugangsdaten je Verbindung (Spezifikation PDVM_DB_VERBINDUNGEN_UND_ZUGANGSDATEN_SPEC_V1, 3.2):
        1. genannter Credential, 2. Altwert MANDANT.PASSWORD (Uebergang), 3. Credential 'default',
        4. AUTH-Zugangsdaten, aber nur auf derselben Instanz wie die AUTH-DB.
        """
        target = ConnectionConfig(host, port, user_field or "", "", database)
        user = user_field
        password: Optional[str] = None
        ssl = False

        if credential_name:
            cred = get_credential(credential_name)
            if cred is None:
                raise ValueError(f"{label}: Credential '{credential_name}' ist nicht konfiguriert (PDVM_DB_CREDENTIALS)")
            password, ssl, user = cred.password, cred.ssl, user or cred.user
        elif legacy_password and legacy_password != "postgres":
            logger.warning("⚠️ %s: MANDANT.PASSWORD ist veraltet; bitte CREDENTIAL verwenden oder das Feld leeren", label)
            password = legacy_password
        else:
            cred = get_credential(DEFAULT_CREDENTIAL)
            if cred is not None:
                password, ssl, user = cred.password, cred.ssl, user or cred.user
            elif ConnectionManager.same_instance(target, auth):
                password, user = auth.password, user or auth.user
            else:
                raise ValueError(
                    f"{label}: keine Zugangsdaten fuer {host}:{port} (CREDENTIAL oder Credential 'default' fehlt)"
                )

        return ConnectionConfig(host, port, user or auth.user, password, database, ssl=ssl)

    @staticmethod
    def resolve_mandant_connections(
        mandant_info: Dict[str, object],
        auth_config: Optional[ConnectionConfig] = None,
        fallback_database: Optional[str] = None,
    ) -> Tuple[ConnectionConfig, ConnectionConfig]:
        """
        Baut (system_config, mandant_config) aus asy_mandanten.daten.MANDANT.

        Adressen: HOST/PORT/USER (Standard: AUTH-Instanz) fuer die Mandanten-DB; SYSTEM_HOST/SYSTEM_PORT/SYSTEM_USER
        fuer die System-DB (Standard: Mandanten-DB). Zugangsdaten: CREDENTIAL bzw. SYSTEM_CREDENTIAL (Standard: CREDENTIAL).
        Das Passwort steht nicht im Mandantensatz (Altfeld PASSWORD gilt nur im Uebergang).
        """
        info = mandant_info if isinstance(mandant_info, dict) else {}
        auth = auth_config or ConnectionManager._auth_config_sync()

        def text(key: str) -> Optional[str]:
            value = info.get(key)
            return str(value).strip() if value not in (None, "") else None

        host = text("HOST") or auth.host
        port = int(text("PORT") or auth.port)
        database = text("DATABASE") or fallback_database or ""
        credential = text("CREDENTIAL")

        mandant_config = ConnectionManager._resolve_connection(
            host=host, port=port, user_field=text("USER"), credential_name=credential,
            legacy_password=text("PASSWORD"), database=database, auth=auth, label="Mandanten-DB",
        )

        system_host = text("SYSTEM_HOST") or host
        system_port = int(text("SYSTEM_PORT") or port)
        system_db = text("SYSTEM_DB") or text("SYSTEM_DATABASE") or "pdvm_system"
        probe = ConnectionConfig(system_host, system_port, "", "", system_db)
        shares_address = ConnectionManager.same_instance(probe, mandant_config)
        system_config = ConnectionManager._resolve_connection(
            host=system_host, port=system_port,
            user_field=text("SYSTEM_USER") or (mandant_config.user if shares_address else None),
            credential_name=text("SYSTEM_CREDENTIAL") or credential,
            legacy_password=text("PASSWORD") if shares_address else None,
            database=system_db, auth=auth, label="System-DB",
        )
        return system_config, mandant_config
    
    @staticmethod
    async def get_mandant_config(mandant_id: str) -> Tuple[ConnectionConfig, ConnectionConfig]:
        """
        Lädt Connection-Config für einen Mandanten aus asy_mandanten.
        
        Returns:
            Tuple[system_config, mandant_config]
            - system_config: Connection zur System-DB (z.B. pdvm_system)
            - mandant_config: Connection zur Mandanten-DB
        
        Raises:
            ValueError: Wenn Mandant nicht gefunden oder Daten unvollständig
        """
        # Verbinde mit auth DB um Mandanten-Daten zu laden
        auth_config = await ConnectionManager.get_auth_config()
        
        # Hole Mandanten-Daten aus asy_mandanten (in auth DB) - ueber den Auth-Pool statt per Einzelverbindung
        pool = DatabasePool._pool_auth
        use_pool = pool is not None
        conn = await pool.acquire() if use_pool else await asyncpg.connect(**auth_config.to_dict())
        try:
            # Lade Mandanten-Record
            mandant = await conn.fetchrow(
                "SELECT daten, gilt_bis, created_at FROM asy_mandanten WHERE uid = $1",
                mandant_id
            )
            
            if not mandant or is_deleted_mandant_row(dict(mandant)):
                raise ValueError(f"Mandant '{mandant_id}' nicht gefunden")
            
            daten = ConnectionManager._normalize_mandant_daten(mandant['daten'])
            mandant_info = daten.get('MANDANT', {})

            from app.core.credential_service import ensure_fresh
            await ensure_fresh()
            system_config, mandant_config = ConnectionManager.resolve_mandant_connections(mandant_info, auth_config)
            if not mandant_config.database:
                raise ValueError(f"Mandant '{mandant_id}' hat fehlende Connection-Daten: DATABASE")

            logger.info(f"✅ Connection-Config für Mandant '{mandant_id}' geladen: "
                       f"System={system_config.database}@{system_config.host}:{system_config.port}, "
                       f"Mandant={mandant_config.database}@{mandant_config.host}:{mandant_config.port}")

            return system_config, mandant_config
            
        finally:
            if use_pool:
                await pool.release(conn)
            else:
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

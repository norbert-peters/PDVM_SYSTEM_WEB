"""
Database Connection Helpers
PostgreSQL with async support - Multi-Database Architecture

Die alte CRUD-Klasse `PdvmDatabase` wurde stillgelegt (Phase 3, siehe
docs/PDVM_PLAN_OPTIMIERUNG_SYSTEMDATEN_V1.md). Datenzugriff laeuft ueber
app.core.pdvm_datenbank.PdvmDatabase (Lesen) und app.core.central_write_service (Schreiben).
"""
import asyncpg
from typing import Optional
import logging
from app.core.config import settings

logger = logging.getLogger(__name__)

KNOWN_PREFIXES = {"asy_", "sys_", "dev_", "msy_"}


def resolve_db_name_by_prefix(table_name: str) -> str:
    table = str(table_name or "").strip().lower()
    if not table:
        raise ValueError("Leerer Tabellenname ist nicht erlaubt")

    if "_" not in table:
        logger.error(f"❌ Tabellennamen ohne Praefix sind unzulaessig: table={table}")
        raise ValueError(f"Tabellenname ohne Praefix ist unzulaessig: {table}")

    prefix = table.split("_", 1)[0] + "_"

    if prefix == "asy_":
        return "auth"
    if prefix in {"sys_", "dev_"}:
        return "system"
    if prefix == "msy_":
        return "mandant"

    if prefix:
        if prefix not in KNOWN_PREFIXES:
            logger.info(f"🔎 App-Praefix erkannt, route nach mandant: table={table} prefix={prefix}")
        return "mandant"

    logger.info(f"🔎 App-Praefix erkannt, route nach mandant: table={table} prefix={prefix}")
    return "mandant"

class DatabasePool:
    """
    Async PostgreSQL connection pool - SIMPLIFIED for Auth only
    
    Only used for Login/Token validation from auth database.
    System and Mandant databases are managed per-session in GCS.
    """
    # Single pool for auth database (login/token validation)
    _pool_auth: Optional[asyncpg.Pool] = None

    @classmethod
    async def create_pool(cls):
        """Create auth connection pool for login/token validation"""
        if cls._pool_auth is None:
            cls._pool_auth = await asyncpg.create_pool(settings.DATABASE_URL_AUTH)
    
    @classmethod
    async def close_pool(cls):
        """Close auth connection pool"""
        if cls._pool_auth:
            await cls._pool_auth.close()
            cls._pool_auth = None


# Helper function for direct database connections
async def get_db_connection(db_name: str = "mandant"):
    """
    Get a direct database connection (not from pool).
    Useful for simple scripts and one-off operations.
    
    Args:
        db_name: Database name ('system', 'auth', 'mandant')
        
    Returns:
        asyncpg.Connection
    """
    if db_name == "auth":
        url = settings.DATABASE_URL_AUTH
        return await asyncpg.connect(url)

    # Fuer andere DBs: URL von Auth ableiten
    from urllib.parse import urlparse, urlunparse
    parsed = urlparse(settings.DATABASE_URL_AUTH)
    
    target_db = None
    if db_name == "system" or db_name == "pdvm_system":
        target_db = "pdvm_system"
    elif db_name == "mandant":
        target_db = "mandant"
    else:
        # Versuche direkten DB-Namen
        target_db = db_name
        
    url = urlunparse((parsed.scheme, parsed.netloc, f'/{target_db}', '', '', ''))
    return await asyncpg.connect(url)


def get_database_url(db_name: str = "mandant") -> str:
    """
    Get database connection string by name.
    Derived from AUTH connection to ensure single source of config.
    
    Args:
        db_name: Database name ('system', 'auth', 'mandant')
        
    Returns:
        PostgreSQL connection string
    """
    if db_name == "auth":
        return settings.DATABASE_URL_AUTH

    from urllib.parse import urlparse, urlunparse
    parsed = urlparse(settings.DATABASE_URL_AUTH)
    
    target_db = None
    if db_name == "system" or db_name == "pdvm_system":
        target_db = "pdvm_system"
    elif db_name == "mandant":
        target_db = "mandant"
    else:
        target_db = db_name
        
    return urlunparse((parsed.scheme, parsed.netloc, f'/{target_db}', '', '', ''))

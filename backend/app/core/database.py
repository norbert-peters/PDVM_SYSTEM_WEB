"""
Database Connection and CRUD Operations
PostgreSQL with async support - Multi-Database Architecture
"""
import asyncpg
from typing import Dict, List, Optional, Any
from datetime import datetime
import json
from app.core.config import settings

# Mapping: table_name -> database pool name
TABLE_DATABASE_MAP = {
    # System tables (pdvm_system database)
    "sys_beschreibungen": "system",
    "sys_dialogdaten": "system",
    "sys_framedaten": "system",
    "sys_viewdaten": "system",
    "sys_menudaten": "system",
    "sys_layout": "system",
    "sys_dropdowndaten": "system",
    
    # Auth tables (auth database)
    "sys_benutzer": "auth",
    "sys_mandanten": "auth",
    
    # Mandant tables (mandant database)
    "sys_anwendungsdaten": "mandant",
    "sys_systemsteuerung": "mandant",
    "sys_security": "mandant",
    "sys_error_log": "mandant",
    "sys_error_acknowledgments": "mandant",
    "persondaten": "mandant",
    "finanzdaten": "mandant",
        "sys_systemdaten": "system",
}

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

class PdvmDatabase:
    """
    PDVM Database Layer - PostgreSQL Multi-Database

    Unified table structure:
    - uid: UUID primary key
    - daten: JSONB main data
    - name: Display name
    - historisch: 0 or 1
    - sec_id: Security profile UUID
    - gilt_bis: Valid until date
    - created_at: Timestamp
    - modified_at: Timestamp
    - daten_backup: JSONB backup
    """

    def __init__(self, table_name: str):
        self.table_name = table_name
        # Determine which database this table belongs to
        self.db_name = TABLE_DATABASE_MAP.get(table_name, "mandant")
    
    def _get_pool(self) -> asyncpg.Pool:
        """Get the appropriate pool for this table's database"""
        if self.db_name == "auth":
            if DatabasePool._pool_auth is None:
                raise RuntimeError("Auth pool not initialized")
            return DatabasePool._pool_auth
        else:
            raise RuntimeError(
                f"PdvmDatabase for '{self.db_name}' tables requires GCS context. "
                f"Use DataManagers or GCS pools instead of PdvmDatabase for non-auth tables."
            )

    async def create(self, daten: Dict[str, Any], name: str = "") -> str:
        """Create new record"""
        pool = self._get_pool()

        query = f"""
            INSERT INTO {self.table_name} (daten, name, created_at, modified_at)
            VALUES ($1, $2, NOW(), NOW())
            RETURNING uid::text
        """

        async with pool.acquire() as conn:
            uid = await conn.fetchval(query, json.dumps(daten), name)
            return uid

    async def read(self, uid: str) -> Optional[Dict[str, Any]]:
        """Read single record"""
        pool = self._get_pool()

        query = f"""
            SELECT uid::text, daten, name, historisch, sec_id::text,
                   gilt_bis, created_at, modified_at
            FROM {self.table_name}
            WHERE uid = $1::uuid
        """

        async with pool.acquire() as conn:
            row = await conn.fetchrow(query, uid)

            if row:
                return {
                    "uid": row["uid"],
                    "daten": json.loads(row["daten"]) if isinstance(row["daten"], str) else row["daten"],
                    "name": row["name"],
                    "historisch": row["historisch"],
                    "sec_id": row["sec_id"],
                    "gilt_bis": row["gilt_bis"],
                    "created_at": row["created_at"].isoformat() if row["created_at"] else None,
                    "modified_at": row["modified_at"].isoformat() if row["modified_at"] else None,
                }
            return None

    async def read_all(self, sec_ids: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """Read all records (with optional security filter)"""
        pool = self._get_pool()

        if sec_ids:
            query = f"""
                SELECT uid::text, daten, name, modified_at
                FROM {self.table_name}
                WHERE sec_id IS NULL OR sec_id = ANY($1::uuid[])
                ORDER BY modified_at DESC
            """
            async with pool.acquire() as conn:
                rows = await conn.fetch(query, sec_ids)
        else:
            query = f"""
                SELECT uid::text, daten, name, modified_at
                FROM {self.table_name}
                WHERE sec_id IS NULL
                ORDER BY modified_at DESC
            """
            async with pool.acquire() as conn:
                rows = await conn.fetch(query)

        return [
            {
                "uid": row["uid"],
                "daten": json.loads(row["daten"]) if isinstance(row["daten"], str) else row["daten"],
                "name": row["name"] or "",
                "modified_at": row["modified_at"].isoformat() if row["modified_at"] else None,
            }
            for row in rows
        ]

    async def update(self, uid: str, daten: Dict[str, Any], name: Optional[str] = None) -> bool:
        """Update record"""
        pool = self._get_pool()

        if name is not None:
            query = f"""
                UPDATE {self.table_name}
                SET daten = $1, name = $2, modified_at = NOW()
                WHERE uid = $3::uuid
            """
            async with pool.acquire() as conn:
                result = await conn.execute(query, json.dumps(daten), name, uid)
        else:
            query = f"""
                UPDATE {self.table_name}
                SET daten = $1, modified_at = NOW()
                WHERE uid = $2::uuid
            """
            async with pool.acquire() as conn:
                result = await conn.execute(query, json.dumps(daten), uid)

        return result != "UPDATE 0"

    async def delete(self, uid: str) -> bool:
        """Delete record"""
        pool = self._get_pool()

        query = f"DELETE FROM {self.table_name} WHERE uid = $1::uuid"

        async with pool.acquire() as conn:
            result = await conn.execute(query, uid)
            return result != "DELETE 0"


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

    # Für andere DBs: URL von Auth ableiten
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


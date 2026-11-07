"""
Mandanten-DB-Provisioning-Service

Datenbankzugriffe fuer das Anlegen/Pruefen/Loeschen von Mandantendatenbanken
(app/api/mandanten.py): CREATE DATABASE, Extensions, _db_init-Marker,
Schema-Skripte, DROP DATABASE sowie Wartungs-Pool.

Gemaess ARCHITECTURE_RULES.md 1.1 gibt es in den Routern keinen direkten
Datenbankzugriff. Der Router steuert den Ablauf (Logging, HTTP-Mapping) und
nutzt dafuer die schlanke Verbindungs-Huelle `ProvisioningConnection`.
PostgreSQL-Fehler werden in einfache Python-Exceptions uebersetzt
(Meldungstext bleibt unveraendert).
"""
import functools
from datetime import datetime
from typing import Optional

import asyncpg

from app.core.pool_registry import PoolRegistry, acquire_pooled_connection

# _db_init-Marker je Ablauf (SQL unveraendert aus dem bisherigen Router-Code)
_INIT_TABLE_AUTO_CREATE_SQL = """
    CREATE TABLE IF NOT EXISTS _db_init (
        id SERIAL PRIMARY KEY,
        created_at TIMESTAMP DEFAULT NOW(),
        info TEXT DEFAULT 'Database initialization marker'
    )
"""
_INIT_TABLE_SETUP_SQL = """
    CREATE TABLE IF NOT EXISTS _db_init (
        id SERIAL PRIMARY KEY,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        description TEXT
    )
"""

INIT_MARKER_AUTO_CREATE = "auto_create"
INIT_MARKER_SETUP = "setup"


class ProvisioningError(Exception):
    """Basisklasse der Provisioning-Fehler."""


class ProvisioningDatabaseError(ProvisioningError):
    """PostgreSQL-Fehler (uebersetzt aus asyncpg.PostgresError)."""


class ProvisioningConnectionError(ProvisioningDatabaseError):
    """Verbindungsfehler zu PostgreSQL (uebersetzt aus asyncpg.PostgresConnectionError)."""


def _translate_postgres_errors(func):
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except asyncpg.PostgresConnectionError as e:
            raise ProvisioningConnectionError(str(e)) from e
        except asyncpg.PostgresError as e:
            raise ProvisioningDatabaseError(str(e)) from e
    return wrapper


class ProvisioningConnection:
    """Direkte (Nicht-Pool-)Verbindung fuer Provisioning-Operationen."""

    def __init__(self, conn):
        self._conn = conn

    @_translate_postgres_errors
    async def lookup_database(self, db_name: str):
        """Liefert 1, wenn die Datenbank in pg_database existiert, sonst None."""
        return await self._conn.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = $1",
            db_name
        )

    @_translate_postgres_errors
    async def create_database(self, db_name: str, from_template0: bool = False) -> None:
        if from_template0:
            # template0 garantiert keine aktiven Verbindungen auf der Vorlage
            await self._conn.execute(f'CREATE DATABASE "{db_name}" WITH TEMPLATE template0')
        else:
            await self._conn.execute(f'CREATE DATABASE "{db_name}"')

    @_translate_postgres_errors
    async def drop_database_if_exists(self, db_name: str) -> None:
        await self._conn.execute(f'DROP DATABASE IF EXISTS "{db_name}"')

    @_translate_postgres_errors
    async def install_uuid_ossp(self) -> None:
        await self._conn.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')

    @_translate_postgres_errors
    async def write_init_marker(self, style: str) -> None:
        """Legt die Init-Tabelle `_db_init` an und schreibt den Marker-Eintrag."""
        if style == INIT_MARKER_AUTO_CREATE:
            await self._conn.execute(_INIT_TABLE_AUTO_CREATE_SQL)
            await self._conn.execute(
                "INSERT INTO _db_init (info) VALUES ($1)",
                f"Database created at {datetime.utcnow().isoformat()}"
            )
        elif style == INIT_MARKER_SETUP:
            await self._conn.execute(_INIT_TABLE_SETUP_SQL)
            await self._conn.execute(
                "INSERT INTO _db_init (description) VALUES ($1)",
                f"Database initialized at {datetime.utcnow().isoformat()}"
            )
        else:
            raise ValueError(f"Unbekannter Init-Marker-Stil: {style}")

    @_translate_postgres_errors
    async def execute_script(self, sql: str) -> None:
        await self._conn.execute(sql)

    async def close(self) -> None:
        await self._conn.close()


@_translate_postgres_errors
async def connect(dsn: Optional[str] = None, **params) -> ProvisioningConnection:
    """Oeffnet eine direkte Verbindung (DSN oder Einzelparameter, z.B. ConnectionConfig.to_dict())."""
    if dsn is not None:
        conn = await asyncpg.connect(dsn, **params)
    else:
        conn = await asyncpg.connect(**params)
    return ProvisioningConnection(conn)


async def create_maintenance_pool(mandant_db_url: str):
    """Temporaerer Connection Pool (1-2 Verbindungen) fuer die Mandanten-Wartung."""
    return await asyncpg.create_pool(mandant_db_url, min_size=1, max_size=2)


async def get_shared_pool(db_url: str):
    """Gemeinsamer Pool je URL (derselbe wie in der GCS-Session); wird nicht vom Aufrufer geschlossen."""
    return await PoolRegistry.get_pool(db_url, dsn=db_url, min_size=1, max_size=10)


@_translate_postgres_errors
async def connect_pooled(db_url: str) -> ProvisioningConnection:
    """Verbindung aus dem gemeinsamen Pool (spart den ca. 150 ms langen Verbindungsaufbau).

    `close()` gibt die Verbindung an den Pool zurueck.
    """
    return ProvisioningConnection(await acquire_pooled_connection(db_url, dsn=db_url, min_size=1, max_size=10))

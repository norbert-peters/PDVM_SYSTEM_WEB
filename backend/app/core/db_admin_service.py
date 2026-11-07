"""
DB-Admin-Service

Datenbankzugriffe fuer die Admin-API (app/api/admin.py):
Datenbanken auflisten/anlegen/loeschen sowie Tabellen anlegen/auflisten.

Gemaess ARCHITECTURE_RULES.md 1.1 gibt es in den Routern keinen direkten
Datenbankzugriff. Dieser Service kapselt Verbindungen und SQL und wirft
einfache Python-Exceptions; die Router uebersetzen diese in HTTP-Status/Details.
"""
from pathlib import Path
from typing import List
from urllib.parse import urlparse, urlunparse

import asyncpg

from app.core.config import settings
from app.core.database import get_database_url


class DatabaseAlreadyExistsError(Exception):
    """Datenbank existiert bereits (-> 409)."""


class DatabaseNotFoundError(Exception):
    """Datenbank existiert nicht (-> 404)."""


class DatabaseDeletionNotAllowedError(Exception):
    """Nur Mandantendatenbanken duerfen geloescht werden (-> 403)."""


class TableAlreadyExistsError(Exception):
    """Tabelle existiert bereits (-> 409)."""


class InvalidDatabaseNameError(ValueError):
    """Datenbankname enthaelt ungueltige Zeichen (-> 400)."""


class InvalidTableNameError(ValueError):
    """Tabellenname enthaelt ungueltige Zeichen (-> 400)."""


class UnknownDatabaseError(ValueError):
    """Unbekannter Datenbank-Alias (system, auth, mandant) (-> 400)."""


def build_mandant_db_name(name: str) -> str:
    """Leitet den Datenbanknamen aus dem Mandantennamen ab."""
    return f"mandant_{name.lower().replace(' ', '_').replace('-', '_')}"


def is_valid_db_name(db_name: str) -> bool:
    """Nur alphanumerische Zeichen und Unterstrich."""
    return all(c.isalnum() or c == '_' for c in db_name)


def is_valid_table_name(table_name: str) -> bool:
    return table_name.replace('_', '').isalnum()


def is_mandant_db_name(db_name: str) -> bool:
    return db_name.startswith("mandant_")


def _server_admin_url() -> str:
    """Server-Verbindung (Datenbank 'postgres') abgeleitet aus der AUTH-URL."""
    parsed = urlparse(settings.DATABASE_URL_AUTH)
    return urlunparse((parsed.scheme, parsed.netloc, '/postgres', '', '', ''))


async def list_databases() -> List[str]:
    """Alle Nicht-Template-Datenbanken ausser 'postgres'."""
    conn = await asyncpg.connect(_server_admin_url())
    try:
        rows = await conn.fetch("""
            SELECT datname 
            FROM pg_database 
            WHERE datistemplate = false 
            AND datname NOT IN ('postgres')
            ORDER BY datname
        """)
        return [row['datname'] for row in rows]
    finally:
        await conn.close()


async def create_mandant_database(name: str, copy_from_template: bool = True) -> str:
    """
    Legt eine Mandantendatenbank an (optional inkl. schema_mandant.sql).

    Returns:
        Name der angelegten Datenbank

    Raises:
        InvalidDatabaseNameError: Name enthaelt ungueltige Zeichen
        DatabaseAlreadyExistsError: Datenbank existiert bereits
    """
    db_name = build_mandant_db_name(name)

    if not is_valid_db_name(db_name):
        raise InvalidDatabaseNameError("Mandantenname enthält ungültige Zeichen")

    parsed = urlparse(settings.DATABASE_URL_AUTH)

    admin_conn = await asyncpg.connect(_server_admin_url())
    try:
        exists = await admin_conn.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = $1",
            db_name
        )

        if exists:
            raise DatabaseAlreadyExistsError(f"Datenbank '{db_name}' existiert bereits")

        await admin_conn.execute(f'CREATE DATABASE "{db_name}"')
    finally:
        await admin_conn.close()

    if copy_from_template:
        mandant_url = urlunparse((parsed.scheme, parsed.netloc, f'/{db_name}', '', '', ''))
        schema_file = Path(__file__).parent.parent.parent / 'database' / 'schema_mandant.sql'

        if schema_file.exists():
            mandant_conn = await asyncpg.connect(mandant_url)
            try:
                sql = schema_file.read_text(encoding='utf-8')
                await mandant_conn.execute(sql)
            finally:
                await mandant_conn.close()

    return db_name


async def create_table(table_name: str, database: str) -> None:
    """
    Legt per create_pdvm_table() eine Tabelle in der Ziel-Datenbank an.

    Raises:
        InvalidTableNameError: Tabellenname enthaelt ungueltige Zeichen
        UnknownDatabaseError: Datenbank-Alias unbekannt
        TableAlreadyExistsError: Tabelle existiert bereits
    """
    if not is_valid_table_name(table_name):
        raise InvalidTableNameError("Tabellenname enthält ungültige Zeichen")

    try:
        db_url = get_database_url(database)
    except ValueError as e:
        raise UnknownDatabaseError(str(e)) from e

    conn = await asyncpg.connect(db_url)
    try:
        exists = await conn.fetchval("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = $1
            )
        """, table_name)

        if exists:
            raise TableAlreadyExistsError(f"Tabelle '{table_name}' existiert bereits")

        await conn.execute(f"SELECT create_pdvm_table('{table_name}')")
    finally:
        await conn.close()


async def list_tables(database: str) -> List[str]:
    """
    Listet alle Basistabellen (Schema public) der Ziel-Datenbank.

    Raises:
        UnknownDatabaseError: Datenbank-Alias unbekannt
    """
    try:
        db_url = get_database_url(database)
    except ValueError as e:
        raise UnknownDatabaseError(str(e)) from e

    conn = await asyncpg.connect(db_url)
    try:
        rows = await conn.fetch("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_type = 'BASE TABLE'
            ORDER BY table_name
        """)
        return [row['table_name'] for row in rows]
    finally:
        await conn.close()


async def delete_database(db_name: str) -> None:
    """
    Loescht eine Mandantendatenbank (inkl. Beenden aktiver Verbindungen).

    Raises:
        DatabaseDeletionNotAllowedError: Name beginnt nicht mit 'mandant_'
        DatabaseNotFoundError: Datenbank existiert nicht
    """
    if not is_mandant_db_name(db_name):
        raise DatabaseDeletionNotAllowedError("Nur Mandantendatenbanken können gelöscht werden")

    admin_conn = await asyncpg.connect(_server_admin_url())
    try:
        exists = await admin_conn.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = $1",
            db_name
        )

        if not exists:
            raise DatabaseNotFoundError(f"Datenbank '{db_name}' nicht gefunden")

        await admin_conn.execute(f"""
            SELECT pg_terminate_backend(pg_stat_activity.pid)
            FROM pg_stat_activity
            WHERE pg_stat_activity.datname = '{db_name}'
            AND pid <> pg_backend_pid()
        """)

        await admin_conn.execute(f'DROP DATABASE "{db_name}"')
    finally:
        await admin_conn.close()

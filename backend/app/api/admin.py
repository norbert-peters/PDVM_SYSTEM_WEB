"""
Admin API Routes
Database and tenant management (requires admin role)
"""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import List, Optional
from pathlib import Path
import asyncpg
from urllib.parse import urlparse, urlunparse
from app.core.security import get_current_user
from app.core.config import settings
from app.core.database import DatabasePool, PdvmDatabase

router = APIRouter()


class DatabaseInfo(BaseModel):
    """Database information"""
    name: str
    exists: bool
    tables: Optional[List[str]] = None


class MandantCreate(BaseModel):
    """Create new mandant database"""
    name: str
    description: Optional[str] = None
    copy_from_template: bool = True


class TableCreate(BaseModel):
    """Create new table in database"""
    table_name: str
    database: str = "mandant"  # system, auth, or mandant


async def require_admin(current_user: dict = Depends(get_current_user)):
    """Dependency to require admin role"""
    # TODO: Check actual admin role from database
    # For now: all authenticated users are considered admins
    return current_user


@router.get("/databases", response_model=List[DatabaseInfo])
async def list_databases(admin: dict = Depends(require_admin)):
    """List all databases in PostgreSQL instance"""
    parsed = urlparse(settings.DATABASE_URL_SYSTEM)
    admin_url = urlunparse((parsed.scheme, parsed.netloc, '/postgres', '', '', ''))
    
    try:
        conn = await asyncpg.connect(admin_url)
        
        # Get all databases
        rows = await conn.fetch("""
            SELECT datname 
            FROM pg_database 
            WHERE datistemplate = false 
            AND datname NOT IN ('postgres')
            ORDER BY datname
        """)
        
        databases = []
        for row in rows:
            db_name = row['datname']
            
            # Check if it's one of our managed databases
            is_managed = db_name in ['pdvm_system', 'auth'] or db_name.startswith('mandant')
            
            databases.append(DatabaseInfo(
                name=db_name,
                exists=True,
                tables=None  # Could be populated if needed
            ))
        
        await conn.close()
        return databases
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Fehler beim Abrufen der Datenbanken: {str(e)}"
        )


@router.post("/databases/mandant", status_code=status.HTTP_201_CREATED)
async def create_mandant_database(
    mandant: MandantCreate,
    admin: dict = Depends(require_admin)
):
    """Create new mandant database"""
    
    # Generate database name
    db_name = f"mandant_{mandant.name.lower().replace(' ', '_').replace('-', '_')}"
    
    # Validate database name (only alphanumeric and underscore)
    if not all(c.isalnum() or c == '_' for c in db_name):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Mandantenname enthält ungültige Zeichen"
        )
    
    parsed = urlparse(settings.DATABASE_URL_SYSTEM)
    admin_url = urlunparse((parsed.scheme, parsed.netloc, '/postgres', '', '', ''))
    
    try:
        # Connect as admin
        admin_conn = await asyncpg.connect(admin_url)
        
        # Check if database already exists
        exists = await admin_conn.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = $1",
            db_name
        )
        
        if exists:
            await admin_conn.close()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Datenbank '{db_name}' existiert bereits"
            )
        
        # Create database
        await admin_conn.execute(f'CREATE DATABASE "{db_name}"')
        await admin_conn.close()
        
        # Execute schema if requested
        if mandant.copy_from_template:
            mandant_url = urlunparse((parsed.scheme, parsed.netloc, f'/{db_name}', '', '', ''))
            schema_file = Path(__file__).parent.parent.parent / 'database' / 'schema_mandant.sql'
            
            if schema_file.exists():
                mandant_conn = await asyncpg.connect(mandant_url)
                sql = schema_file.read_text(encoding='utf-8')
                await mandant_conn.execute(sql)
                await mandant_conn.close()
        
        # Register in sys_mandanten table
        db = PdvmDatabase("sys_mandanten")
        await db.create(
            daten={
                "database_name": db_name,
                "description": mandant.description or mandant.name,
                "created_by": admin.get("email", "admin")
            },
            name=mandant.name
        )
        
        return {
            "success": True,
            "database_name": db_name,
            "message": f"Mandantendatenbank '{db_name}' erfolgreich erstellt"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Fehler beim Erstellen der Datenbank: {str(e)}"
        )


@router.post("/tables", status_code=status.HTTP_201_CREATED)
async def create_table(
    table_data: TableCreate,
    admin: dict = Depends(require_admin)
):
    """Create new table in specified database"""
    
    # Validate table name
    if not table_data.table_name.replace('_', '').isalnum():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tabellenname enthält ungültige Zeichen"
        )
    
    # Get database URL
    if table_data.database == "system":
        db_url = settings.DATABASE_URL_SYSTEM
    elif table_data.database == "auth":
        db_url = settings.DATABASE_URL_AUTH
    elif table_data.database == "mandant":
        db_url = settings.DATABASE_URL_MANDANT
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ungültige Datenbank. Erlaubt: system, auth, mandant"
        )
    
    try:
        conn = await asyncpg.connect(db_url)
        
        # Check if table exists
        exists = await conn.fetchval("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = $1
            )
        """, table_data.table_name)
        
        if exists:
            await conn.close()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Tabelle '{table_data.table_name}' existiert bereits"
            )
        
        # Call create_pdvm_table function
        await conn.execute(f"SELECT create_pdvm_table('{table_data.table_name}')")
        await conn.close()
        
        return {
            "success": True,
            "table_name": table_data.table_name,
            "database": table_data.database,
            "message": f"Tabelle '{table_data.table_name}' erfolgreich erstellt"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Fehler beim Erstellen der Tabelle: {str(e)}"
        )


@router.get("/tables/{database}")
async def list_tables(
    database: str,
    admin: dict = Depends(require_admin)
):
    """List all tables in specified database"""
    
    # Get database URL
    if database == "system":
        db_url = settings.DATABASE_URL_SYSTEM
    elif database == "auth":
        db_url = settings.DATABASE_URL_AUTH
    elif database == "mandant":
        db_url = settings.DATABASE_URL_MANDANT
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ungültige Datenbank"
        )
    
    try:
        conn = await asyncpg.connect(db_url)
        
        rows = await conn.fetch("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_type = 'BASE TABLE'
            ORDER BY table_name
        """)
        
        await conn.close()
        
        return {
            "database": database,
            "tables": [row['table_name'] for row in rows]
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Fehler beim Abrufen der Tabellen: {str(e)}"
        )


@router.delete("/databases/{db_name}")
async def delete_database(
    db_name: str,
    admin: dict = Depends(require_admin)
):
    """Delete database (only mandant databases allowed)"""
    
    # Security check: only allow deletion of mandant databases
    if not db_name.startswith("mandant_"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Nur Mandantendatenbanken können gelöscht werden"
        )
    
    parsed = urlparse(settings.DATABASE_URL_SYSTEM)
    admin_url = urlunparse((parsed.scheme, parsed.netloc, '/postgres', '', '', ''))
    
    try:
        admin_conn = await asyncpg.connect(admin_url)
        
        # Check if database exists
        exists = await admin_conn.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = $1",
            db_name
        )
        
        if not exists:
            await admin_conn.close()
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Datenbank '{db_name}' nicht gefunden"
            )
        
        # Terminate all connections to the database
        await admin_conn.execute(f"""
            SELECT pg_terminate_backend(pg_stat_activity.pid)
            FROM pg_stat_activity
            WHERE pg_stat_activity.datname = '{db_name}'
            AND pid <> pg_backend_pid()
        """)
        
        # Drop database
        await admin_conn.execute(f'DROP DATABASE "{db_name}"')
        await admin_conn.close()
        
        return {
            "success": True,
            "message": f"Datenbank '{db_name}' erfolgreich gelöscht"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Fehler beim Löschen der Datenbank: {str(e)}"
        )

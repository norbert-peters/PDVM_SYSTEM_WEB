"""
Admin API Routes
Database and tenant management (requires admin role)
"""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import List, Optional
from app.core.security import require_admin_user
from app.core import db_admin_service
from app.core.central_write_service import create_record_central

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


async def require_admin(admin_user: dict = Depends(require_admin_user)):
    """Zentraler Admin-Guard aus app.core.security."""
    return admin_user


@router.get("/databases", response_model=List[DatabaseInfo])
async def list_databases(admin: dict = Depends(require_admin)):
    """List all databases in PostgreSQL instance"""
    try:
        db_names = await db_admin_service.list_databases()

        return [
            DatabaseInfo(
                name=db_name,
                exists=True,
                tables=None  # Could be populated if needed
            )
            for db_name in db_names
        ]
        
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
    
    try:
        db_name = await db_admin_service.create_mandant_database(
            mandant.name,
            copy_from_template=mandant.copy_from_template,
        )
        
        # Register in asy_mandanten table
        await create_record_central(
            table_name="asy_mandanten",
            daten={
                "database_name": db_name,
                "description": mandant.description or mandant.name,
                "created_by": admin.get("email", "admin"),
            },
            name=mandant.name,
            actor_user_uid=admin.get("sub"),
            actor_ip=admin.get("client_ip"),
        )
        
        return {
            "success": True,
            "database_name": db_name,
            "message": f"Mandantendatenbank '{db_name}' erfolgreich erstellt"
        }
        
    except db_admin_service.InvalidDatabaseNameError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Mandantenname enthält ungültige Zeichen"
        )
    except db_admin_service.DatabaseAlreadyExistsError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e)
        )
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
    
    try:
        await db_admin_service.create_table(table_data.table_name, table_data.database)
        
        return {
            "success": True,
            "table_name": table_data.table_name,
            "database": table_data.database,
            "message": f"Tabelle '{table_data.table_name}' erfolgreich erstellt"
        }
        
    except db_admin_service.InvalidTableNameError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tabellenname enthält ungültige Zeichen"
        )
    except db_admin_service.UnknownDatabaseError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ungültige Datenbank. Erlaubt: system, auth, mandant"
        )
    except db_admin_service.TableAlreadyExistsError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e)
        )
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
    
    try:
        tables = await db_admin_service.list_tables(database)
        
        return {
            "database": database,
            "tables": tables
        }
        
    except db_admin_service.UnknownDatabaseError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ungültige Datenbank"
        )
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
    
    try:
        await db_admin_service.delete_database(db_name)
        
        return {
            "success": True,
            "message": f"Datenbank '{db_name}' erfolgreich gelöscht"
        }
        
    except db_admin_service.DatabaseDeletionNotAllowedError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Nur Mandantendatenbanken können gelöscht werden"
        )
    except db_admin_service.DatabaseNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Fehler beim Löschen der Datenbank: {str(e)}"
        )

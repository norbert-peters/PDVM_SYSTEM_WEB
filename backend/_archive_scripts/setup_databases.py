"""
Automated Database Setup Script
Creates all required databases and executes schema files
"""
import asyncio
import asyncpg
from pathlib import Path
import sys
from urllib.parse import urlparse, urlunparse

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from app.core.config import settings


async def database_exists(conn, db_name: str) -> bool:
    """Check if database exists"""
    result = await conn.fetchval(
        "SELECT 1 FROM pg_database WHERE datname = $1",
        db_name
    )
    return result is not None


async def create_database(conn, db_name: str):
    """Create database if it doesn't exist"""
    exists = await database_exists(conn, db_name)
    
    if exists:
        print(f"✓ Datenbank '{db_name}' existiert bereits")
        return False
    
    # Create database
    await conn.execute(f'CREATE DATABASE "{db_name}"')
    print(f"✓ Datenbank '{db_name}' erfolgreich erstellt")
    return True


async def execute_schema(db_url: str, schema_file: Path):
    """Execute SQL schema file on database"""
    if not schema_file.exists():
        print(f"✗ Schema-Datei nicht gefunden: {schema_file}")
        return False
    
    try:
        # Connect to target database
        conn = await asyncpg.connect(db_url)
        
        # Read and execute schema
        sql = schema_file.read_text(encoding='utf-8')
        await conn.execute(sql)
        
        await conn.close()
        print(f"✓ Schema ausgeführt: {schema_file.name}")
        return True
    
    except Exception as e:
        print(f"✗ Fehler beim Ausführen von {schema_file.name}: {e}")
        return False


async def setup_all_databases():
    """Main setup function"""
    print("=" * 60)
    print("PDVM Multi-Database Setup")
    print("=" * 60)
    
    # Parse connection URL to get postgres admin DB
    parsed = urlparse(settings.DATABASE_URL_SYSTEM)
    admin_url = urlunparse((
        parsed.scheme,
        parsed.netloc,
        '/postgres',  # Connect to postgres database
        '', '', ''
    ))
    
    try:
        # Connect to postgres database for admin operations
        print("\n[1] Verbinde zu PostgreSQL Server...")
        admin_conn = await asyncpg.connect(admin_url)
        print("✓ Verbindung erfolgreich")
        
        # Define databases to create
        databases = [
            {
                'name': 'pdvm_system',
                'url': settings.DATABASE_URL_SYSTEM,
                'schema': Path(__file__).parent.parent / 'database' / 'schema_pdvm_system.sql',
                'description': 'System-Konfiguration (UI, Menüs, Dialoge)'
            },
            {
                'name': 'auth',
                'url': settings.DATABASE_URL_AUTH,
                'schema': Path(__file__).parent.parent / 'database' / 'schema_auth.sql',
                'description': 'Authentifizierung (Benutzer, Mandanten)'
            },
            {
                'name': 'mandant',
                'url': settings.DATABASE_URL_MANDANT,
                'schema': Path(__file__).parent.parent / 'database' / 'schema_mandant.sql',
                'description': 'Mandantendaten (Anwendungsdaten)'
            }
        ]
        
        # Create databases
        print("\n[2] Erstelle Datenbanken...")
        created_dbs = []
        for db in databases:
            print(f"\n  → {db['name']}: {db['description']}")
            was_created = await create_database(admin_conn, db['name'])
            if was_created:
                created_dbs.append(db)
        
        await admin_conn.close()
        
        # Execute schemas
        if created_dbs:
            print("\n[3] Führe Schema-Dateien aus...")
            for db in created_dbs:
                print(f"\n  → {db['name']}...")
                await execute_schema(db['url'], db['schema'])
        else:
            print("\n[3] Keine neuen Datenbanken - Schema-Ausführung übersprungen")
            print("    Tipp: Zum erneuten Ausführen der Schemas, Datenbanken in pgAdmin löschen")
        
        # Verify setup
        print("\n[4] Überprüfe Setup...")
        admin_conn = await asyncpg.connect(admin_url)
        
        for db in databases:
            exists = await database_exists(admin_conn, db['name'])
            status = "✓" if exists else "✗"
            print(f"  {status} {db['name']}")
        
        await admin_conn.close()
        
        print("\n" + "=" * 60)
        print("Setup abgeschlossen!")
        print("=" * 60)
        print("\nNächste Schritte:")
        print("1. Backend starten: python -m uvicorn app.main:app --reload")
        print("2. API testen: http://localhost:8000/docs")
        print("3. Login: admin@example.com / admin")
        
        return True
        
    except Exception as e:
        print(f"\n✗ Fehler beim Setup: {e}")
        print(f"\nTipp: Stelle sicher, dass PostgreSQL läuft und die .env Datei korrekt ist")
        return False


async def create_mandant_database(mandant_name: str, schema_file: Path = None) -> bool:
    """
    Create a new mandant database dynamically
    Can be called from API endpoints later
    """
    db_name = f"mandant_{mandant_name.lower().replace(' ', '_')}"
    
    # Parse connection URL
    parsed = urlparse(settings.DATABASE_URL_SYSTEM)
    admin_url = urlunparse((parsed.scheme, parsed.netloc, '/postgres', '', '', ''))
    
    # New mandant database URL
    mandant_url = urlunparse((parsed.scheme, parsed.netloc, f'/{db_name}', '', '', ''))
    
    try:
        # Create database
        admin_conn = await asyncpg.connect(admin_url)
        await create_database(admin_conn, db_name)
        await admin_conn.close()
        
        # Execute schema if provided
        if schema_file and schema_file.exists():
            await execute_schema(mandant_url, schema_file)
        else:
            # Use default mandant schema
            default_schema = Path(__file__).parent.parent / 'database' / 'schema_mandant.sql'
            if default_schema.exists():
                await execute_schema(mandant_url, default_schema)
        
        print(f"✓ Mandantendatenbank '{db_name}' erstellt")
        return True
        
    except Exception as e:
        print(f"✗ Fehler beim Erstellen der Mandantendatenbank: {e}")
        return False


if __name__ == "__main__":
    print("\nStarte automatisches Datenbank-Setup...\n")
    success = asyncio.run(setup_all_databases())
    sys.exit(0 if success else 1)

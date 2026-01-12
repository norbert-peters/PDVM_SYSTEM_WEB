"""
Import sys_menudaten from old SQLite database to PostgreSQL
Imports menu data from old pdvm_system.db
"""
import asyncio
import sqlite3
import asyncpg
from pathlib import Path
import sys
import json
from typing import Dict, Any

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from app.core.config import settings


OLD_DB_PATH = r"C:\Users\norbe\OneDrive\Dokumente\MyApplication\Daten\pdvm_system.db"


def read_menu_data_from_sqlite() -> list[tuple]:
    """Read all menu data from old SQLite database"""
    if not Path(OLD_DB_PATH).exists():
        raise FileNotFoundError(f"Alte Datenbank nicht gefunden: {OLD_DB_PATH}")
    
    conn = sqlite3.connect(OLD_DB_PATH)
    cursor = conn.cursor()
    
    try:
        # Check if table exists
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='sys_menudaten'
        """)
        if not cursor.fetchone():
            raise Exception("Tabelle 'sys_menudaten' nicht in alter Datenbank gefunden")
        
        # Check table structure
        cursor.execute("PRAGMA table_info(sys_menudaten)")
        columns = cursor.fetchall()
        print(f"Spalten in sys_menudaten: {[col[1] for col in columns]}")
        
        # Read all menu data (uid = menu identifier)
        cursor.execute("""
            SELECT uid, daten, name
            FROM sys_menudaten
            ORDER BY uid
        """)
        
        rows = cursor.fetchall()
        print(f"✓ {len(rows)} Menü-Einträge aus SQLite-DB gelesen")
        return rows
        
    finally:
        conn.close()


async def import_to_postgresql(menu_data: list[tuple]):
    """Import menu data to PostgreSQL pdvm_system database"""
    
    # Use DATABASE_URL_SYSTEM from settings
    pg_url = settings.DATABASE_URL_SYSTEM
    
    conn = await asyncpg.connect(pg_url)
    
    try:
        # Check if table exists
        table_exists = await conn.fetchval("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = 'sys_menudaten'
            )
        """)
        
        if not table_exists:
            print("✗ Tabelle 'sys_menudaten' existiert nicht in pdvm_system")
            print("  Führe zuerst 'python setup_databases.py' aus")
            return
        
        # Clear existing data
        deleted = await conn.fetchval("SELECT COUNT(*) FROM sys_menudaten")
        if deleted:
            await conn.execute("DELETE FROM sys_menudaten")
            print(f"✓ {deleted} alte Einträge aus sys_menudaten gelöscht")
        
        # Insert menu data
        inserted = 0
        for menu_uid, daten_json, name in menu_data:
            # Parse JSON if it's a string
            if isinstance(daten_json, str):
                daten = json.loads(daten_json)
            else:
                daten = daten_json
            
            # Set default name if None
            if name is None:
                name = f"menu_{menu_uid}"
            
            await conn.execute("""
                INSERT INTO sys_menudaten (uid, daten, name)
                VALUES ($1::uuid, $2::jsonb, $3)
                ON CONFLICT (uid) DO UPDATE
                SET daten = EXCLUDED.daten, name = EXCLUDED.name
            """, menu_uid, json.dumps(daten), name)
            inserted += 1
        
        print(f"✓ {inserted} Menü-Einträge in PostgreSQL importiert")
        
        # Show imported menu UIDs
        menus = await conn.fetch("SELECT uid FROM sys_menudaten ORDER BY uid")
        print(f"\nImportierte Menüs:")
        for menu in menus:
            print(f"  - {menu['uid']}")
        
    finally:
        await conn.close()


async def main():
    """Main import function"""
    print("=" * 60)
    print("Menüdaten-Import: SQLite → PostgreSQL")
    print("=" * 60)
    print(f"Quelle: {OLD_DB_PATH}")
    print(f"Ziel:   PostgreSQL pdvm_system")
    print()
    
    try:
        # Read from SQLite
        menu_data = read_menu_data_from_sqlite()
        
        if not menu_data:
            print("✗ Keine Menüdaten gefunden")
            return
        
        # Import to PostgreSQL
        await import_to_postgresql(menu_data)
        
        print("\n" + "=" * 60)
        print("✓ Import erfolgreich abgeschlossen")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n✗ Fehler beim Import: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())

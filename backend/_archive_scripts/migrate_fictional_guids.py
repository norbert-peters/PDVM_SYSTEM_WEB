#!/usr/bin/env python3
"""
GUID-Standardisierungs-Migration

Stellt sicher dass alle Tabellen in auth, pdvm_system, mandant und pdvm_standard
die drei fiktiven System-Sätze enthalten:
- 00000000-0000-0000-0000-000000000000 (Tabellen-Metadaten)
- 66666666-6666-6666-6666-666666666666 (Template neuer Satz)
- 55555555-5555-5555-5555-555555555555 (Modul-Templates)

Datum: 14. Februar 2026
"""

import asyncpg
import asyncio
import sys
import json
from pathlib import Path
from datetime import datetime
from uuid import UUID
from typing import List, Dict, Tuple

# Datenbank-Verbindungsparameter
DB_CONNECTIONS = {
    'auth': 'postgresql://postgres:Polari$55@localhost:5432/auth',
    'pdvm_system': 'postgresql://postgres:Polari$55@localhost:5432/pdvm_system',
    'mandant': 'postgresql://postgres:Polari$55@localhost:5432/mandant',
    'pdvm_standard': 'postgresql://postgres:Polari$55@localhost:5432/pdvm_standard'
}

# Fiktive GUIDs (System-reserviert)
FICTIONAL_GUID_000 = UUID('00000000-0000-0000-0000-000000000000')
FICTIONAL_GUID_666 = UUID('66666666-6666-6666-6666-666666666666')
FICTIONAL_GUID_555 = UUID('55555555-5555-5555-5555-555555555555')

FICTIONAL_GUIDS = [
    (FICTIONAL_GUID_000, 'Tabellen-Metadaten', {
        'TABLE_INFO': {
            'description': '',
            'version': '2.0',
            'schema_migrated': True,
            'created_by': 'system',
            'created_at': datetime.now().isoformat()
        }
    }),
    (FICTIONAL_GUID_666, 'Template neuer Satz', {
        'ROOT': {
            'TABLE': '',
            'SELF_GUID': '',
            'SELF_NAME': ''
        },
        'FIELDS': {},
        'TABS': []
    }),
    (FICTIONAL_GUID_555, 'Templates', {
        'TEMPLATES': {}
    })
]


async def get_all_tables(conn: asyncpg.Connection, schema: str = 'public') -> List[str]:
    """
    Holt alle Tabellen aus einem Schema die eine uid-Spalte haben
    """
    query = """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = $1
          AND table_type = 'BASE TABLE'
          AND EXISTS (
              SELECT 1 
              FROM information_schema.columns 
              WHERE table_schema = $1 
                AND table_name = tables.table_name 
                AND column_name = 'uid'
          )
        ORDER BY table_name
    """
    
    rows = await conn.fetch(query, schema)
    return [row['table_name'] for row in rows]


async def check_fictional_guid_exists(
    conn: asyncpg.Connection,
    table_name: str,
    guid: UUID
) -> bool:
    """
    Prüft ob fiktive GUID in Tabelle existiert
    """
    query = f'SELECT EXISTS(SELECT 1 FROM {table_name} WHERE uid = $1)'
    return await conn.fetchval(query, guid)


async def get_table_columns(conn: asyncpg.Connection, table_name: str) -> List[str]:
    """
    Holt alle Spalten einer Tabelle
    """
    query = """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = $1
        ORDER BY ordinal_position
    """
    rows = await conn.fetch(query, table_name)
    return [row['column_name'] for row in rows]


async def insert_fictional_guid(
    conn: asyncpg.Connection,
    table_name: str,
    guid: UUID,
    name: str,
    daten: dict
) -> bool:
    """
    Fügt fiktive GUID in Tabelle ein
    
    Passt sich an vorhandene Spalten an:
    - uid (required)
    - daten (JSONB, required)
    - name (text, optional)
    - historisch (integer, optional - default 0)
    - sec_id (integer, optional - default NULL)
    - gilt_bis (date, optional - default NULL)
    - created_at (timestamp, optional - default now())
    - modified_at (timestamp, optional - default now())
    """
    columns = await get_table_columns(conn, table_name)
    
    # Basis-Felder (immer vorhanden)
    fields = ['uid', 'daten']
    values = [guid, json.dumps(daten)]  # JSON serialisieren!
    placeholders = ['$1', '$2']
    param_idx = 3
    
    # Optionale Felder
    if 'name' in columns:
        fields.append('name')
        values.append(name)
        placeholders.append(f'${param_idx}')
        param_idx += 1
    
    if 'historisch' in columns:
        fields.append('historisch')
        values.append(0)  # Fiktive Sätze niemals historisch
        placeholders.append(f'${param_idx}')
        param_idx += 1
    
    if 'sec_id' in columns:
        fields.append('sec_id')
        values.append(None)
        placeholders.append(f'${param_idx}')
        param_idx += 1
    
    if 'gilt_bis' in columns:
        fields.append('gilt_bis')
        values.append(None)
        placeholders.append(f'${param_idx}')
        param_idx += 1
    
    if 'created_at' in columns:
        fields.append('created_at')
        values.append(datetime.now())
        placeholders.append(f'${param_idx}')
        param_idx += 1
    
    if 'modified_at' in columns:
        fields.append('modified_at')
        values.append(datetime.now())
        placeholders.append(f'${param_idx}')
        param_idx += 1
    
    # Insert Query erstellen
    query = f"""
        INSERT INTO {table_name} ({', '.join(fields)})
        VALUES ({', '.join(placeholders)})
    """
    
    try:
        await conn.execute(query, *values)
        return True
    except Exception as e:
        print(f"  ❌ Fehler beim Insert in {table_name}: {e}")
        return False


async def migrate_database(db_name: str, conn_string: str) -> Tuple[int, int, int]:
    """
    Migriert eine Datenbank
    
    Returns: (tables_processed, records_inserted, errors)
    """
    print(f"\n🔧 Datenbank: {db_name}")
    print("=" * 70)
    
    try:
        conn = await asyncpg.connect(conn_string)
    except Exception as e:
        print(f"❌ Verbindung fehlgeschlagen: {e}")
        return (0, 0, 1)
    
    try:
        # Alle relevanten Tabellen holen
        tables = await get_all_tables(conn)
        
        if not tables:
            print("⚠️  Keine Tabellen mit uid-Spalte gefunden")
            return (0, 0, 0)
        
        print(f"📋 Gefundene Tabellen: {len(tables)}")
        print()
        
        tables_processed = 0
        records_inserted = 0
        errors = 0
        
        for table_name in tables:
            print(f"📂 Tabelle: {table_name}")
            table_inserts = 0
            
            # Prüfe und füge jede fiktive GUID ein
            for guid, name, daten in FICTIONAL_GUIDS:
                exists = await check_fictional_guid_exists(conn, table_name, guid)
                
                if exists:
                    print(f"  ✓ {name} ({guid}) - bereits vorhanden")
                else:
                    success = await insert_fictional_guid(conn, table_name, guid, name, daten)
                    if success:
                        print(f"  ✅ {name} ({guid}) - eingefügt")
                        table_inserts += 1
                        records_inserted += 1
                    else:
                        print(f"  ❌ {name} ({guid}) - Fehler")
                        errors += 1
            
            if table_inserts > 0:
                print(f"  → {table_inserts} Sätze eingefügt")
            
            tables_processed += 1
            print()
        
        return (tables_processed, records_inserted, errors)
        
    finally:
        await conn.close()


async def main():
    """
    Hauptfunktion - migriert alle Datenbanken
    """
    print("🚀 GUID-Standardisierungs-Migration")
    print("=" * 70)
    print("Datum:", datetime.now().strftime('%d.%m.%Y %H:%M:%S'))
    print()
    print("Fiktive GUIDs:")
    print("  • 00000000... → Tabellen-Metadaten")
    print("  • 66666666... → Template neuer Satz")
    print("  • 55555555... → Modul-Templates")
    print()
    
    # Statistiken
    total_tables = 0
    total_inserts = 0
    total_errors = 0
    
    # Datenbanken durchgehen
    for db_name, conn_string in DB_CONNECTIONS.items():
        tables, inserts, errors = await migrate_database(db_name, conn_string)
        total_tables += tables
        total_inserts += inserts
        total_errors += errors
    
    # Zusammenfassung
    print("\n" + "=" * 70)
    print("📊 Gesamt-Statistik")
    print("=" * 70)
    print(f"Datenbanken geprüft:  {len(DB_CONNECTIONS)}")
    print(f"Tabellen verarbeitet: {total_tables}")
    print(f"Sätze eingefügt:      {total_inserts}")
    print(f"Fehler:               {total_errors}")
    print()
    
    if total_errors == 0:
        print("✅ Migration erfolgreich abgeschlossen!")
        return 0
    else:
        print(f"⚠️  Migration mit {total_errors} Fehler(n) abgeschlossen")
        return 1


if __name__ == '__main__':
    exit_code = asyncio.run(main())
    sys.exit(exit_code)

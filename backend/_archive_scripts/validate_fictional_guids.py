#!/usr/bin/env python3
"""
GUID-Standardisierungs-Validator

Prüft ob alle Tabellen in auth, pdvm_system, mandant und pdvm_standard
die drei fiktiven System-Sätze enthalten.

Datum: 14. Februar 2026
"""

import asyncpg
import asyncio
import sys
from uuid import UUID
from typing import Dict, List, Tuple
from datetime import datetime

# Datenbank-Verbindungsparameter
DB_CONNECTIONS = {
    'auth': 'postgresql://postgres:Polari$55@localhost:5432/auth',
    'pdvm_system': 'postgresql://postgres:Polari$55@localhost:5432/pdvm_system',
    'mandant': 'postgresql://postgres:Polari$55@localhost:5432/mandant',
    'pdvm_standard': 'postgresql://postgres:Polari$55@localhost:5432/pdvm_standard'
}

# Fiktive GUIDs
FICTIONAL_GUIDS = {
    UUID('00000000-0000-0000-0000-000000000000'): 'Tabellen-Metadaten',
    UUID('66666666-6666-6666-6666-666666666666'): 'Template neuer Satz',
    UUID('55555555-5555-5555-5555-555555555555'): 'Modul-Templates'
}


async def get_all_tables(conn: asyncpg.Connection, schema: str = 'public') -> List[str]:
    """Holt alle Tabellen mit uid-Spalte"""
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


async def check_fictional_guids(
    conn: asyncpg.Connection,
    table_name: str
) -> Dict[UUID, bool]:
    """
    Prüft welche fiktiven GUIDs in Tabelle vorhanden sind
    Returns: dict {guid: exists}
    """
    results = {}
    
    for guid in FICTIONAL_GUIDS.keys():
        query = f'SELECT EXISTS(SELECT 1 FROM {table_name} WHERE uid = $1)'
        exists = await conn.fetchval(query, guid)
        results[guid] = exists
    
    return results


async def validate_database(db_name: str, conn_string: str) -> Tuple[int, int, List[str]]:
    """
    Validiert eine Datenbank
    
    Returns: (tables_valid, tables_invalid, missing_tables)
    """
    print(f"\n🔍 Datenbank: {db_name}")
    print("=" * 70)
    
    try:
        conn = await asyncpg.connect(conn_string)
    except Exception as e:
        print(f"❌ Verbindung fehlgeschlagen: {e}")
        return (0, 0, [])
    
    try:
        tables = await get_all_tables(conn)
        
        if not tables:
            print("⚠️  Keine Tabellen mit uid-Spalte gefunden")
            return (0, 0, [])
        
        print(f"📋 Tabellen gefunden: {len(tables)}")
        print()
        
        tables_valid = 0
        tables_invalid = 0
        missing_tables = []
        
        for table_name in tables:
            guid_status = await check_fictional_guids(conn, table_name)
            
            # Prüfe ob alle GUIDs vorhanden
            all_present = all(guid_status.values())
            missing_guids = [
                FICTIONAL_GUIDS[guid] 
                for guid, exists in guid_status.items() 
                if not exists
            ]
            
            if all_present:
                print(f"✅ {table_name} - vollständig")
                tables_valid += 1
            else:
                print(f"❌ {table_name} - fehlend: {', '.join(missing_guids)}")
                tables_invalid += 1
                missing_tables.append(table_name)
        
        print()
        print(f"Zusammenfassung: {tables_valid} vollständig | {tables_invalid} unvollständig")
        
        return (tables_valid, tables_invalid, missing_tables)
        
    finally:
        await conn.close()


async def check_invalid_fictional_guids(db_name: str, conn_string: str) -> List[Tuple[str, UUID]]:
    """
    Prüft ob es reguläre Datensätze gibt die verbotenerweise fiktive GUIDs verwenden
    (außer den drei erlaubten System-Sätzen)
    
    AUSNAHMEN (Beispiel-Templates in sys_framedaten):
    - 55555555-0001-4001-8001-000000000001 (FIELDS Template)
    - 55555555-0002-4001-8001-000000000002 (TABS Template)
    """
    print(f"\n🔎 Prüfe ungültige GUID-Verwendung in: {db_name}")
    print("=" * 70)
    
    # Beispiel-Templates die ignoriert werden (temporär bis manuelle Bereinigung)
    EXAMPLE_TEMPLATES = [
        UUID('55555555-0001-4001-8001-000000000001'),  # FIELDS Template
        UUID('55555555-0002-4001-8001-000000000002')   # TABS Template
    ]
    
    try:
        conn = await asyncpg.connect(conn_string)
    except Exception as e:
        print(f"❌ Verbindung fehlgeschlagen: {e}")
        return []
    
    invalid_usages = []
    
    try:
        tables = await get_all_tables(conn)
        
        for table_name in tables:
            # Prüfe auf GUIDs die Patterns matchen aber nicht die exakten System-GUIDs sind
            query = f"""
                SELECT uid, name
                FROM {table_name}
                WHERE (
                    -- Pattern 000000... aber nicht die exakte System-GUID
                    (CAST(uid AS TEXT) LIKE '00000000-%' AND uid != '00000000-0000-0000-0000-000000000000')
                    OR
                    -- Pattern 666666... aber nicht die exakte System-GUID
                    (CAST(uid AS TEXT) LIKE '66666666-%' AND uid != '66666666-6666-6666-6666-666666666666')
                    OR
                    -- Pattern 555555... aber nicht die exakte System-GUID
                    (CAST(uid AS TEXT) LIKE '55555555-%' AND uid != '55555555-5555-5555-5555-555555555555')
                )
            """
            
            rows = await conn.fetch(query)
            
            for row in rows:
                # Skip Beispiel-Templates
                if row['uid'] in EXAMPLE_TEMPLATES:
                    print(f"ℹ️  {table_name}: {row['uid']} ({row.get('name', 'N/A')}) - Beispiel-Template (ignoriert)")
                    continue
                
                invalid_usages.append((table_name, row['uid'], row.get('name', 'N/A')))
                print(f"⚠️  {table_name}: {row['uid']} ({row.get('name', 'N/A')})")
        
        if not invalid_usages:
            print("✅ Keine ungültigen GUID-Verwendungen gefunden")
        else:
            print(f"\n❌ {len(invalid_usages)} ungültige GUID-Verwendungen gefunden!")
        
        return invalid_usages
        
    finally:
        await conn.close()


async def main():
    """
    Hauptfunktion - validiert alle Datenbanken
    """
    print("🔍 GUID-Standardisierungs-Validator")
    print("=" * 70)
    print("Datum:", datetime.now().strftime('%d.%m.%Y %H:%M:%S'))
    print()
    print("Prüfe auf fiktive GUIDs:")
    print("  • 00000000-0000-0000-0000-000000000000 → Tabellen-Metadaten")
    print("  • 66666666-6666-6666-6666-666666666666 → Template neuer Satz")
    print("  • 55555555-5555-5555-5555-555555555555 → Modul-Templates")
    print()
    
    # Statistiken
    total_valid = 0
    total_invalid = 0
    all_missing_tables = {}
    
    # Phase 1: Prüfe ob fiktive Sätze vorhanden sind
    print("\n" + "=" * 70)
    print("Phase 1: Fiktive System-Sätze prüfen")
    print("=" * 70)
    
    for db_name, conn_string in DB_CONNECTIONS.items():
        valid, invalid, missing = await validate_database(db_name, conn_string)
        total_valid += valid
        total_invalid += invalid
        if missing:
            all_missing_tables[db_name] = missing
    
    # Phase 2: Prüfe auf ungültige GUID-Verwendungen
    print("\n" + "=" * 70)
    print("Phase 2: Ungültige GUID-Verwendungen prüfen")
    print("=" * 70)
    
    all_invalid_usages = []
    for db_name, conn_string in DB_CONNECTIONS.items():
        invalid_usages = await check_invalid_fictional_guids(db_name, conn_string)
        all_invalid_usages.extend(invalid_usages)
    
    # Zusammenfassung
    print("\n" + "=" * 70)
    print("📊 Gesamt-Statistik")
    print("=" * 70)
    print(f"Datenbanken geprüft:      {len(DB_CONNECTIONS)}")
    print(f"Tabellen vollständig:     {total_valid}")
    print(f"Tabellen unvollständig:   {total_invalid}")
    print(f"Ungültige GUID-Nutzung:   {len(all_invalid_usages)}")
    print()
    
    # Details zu fehlenden Tabellen
    if all_missing_tables:
        print("❌ Tabellen mit fehlenden fiktiven Sätzen:")
        for db_name, tables in all_missing_tables.items():
            print(f"\n  {db_name}:")
            for table in tables:
                print(f"    • {table}")
        print()
        print("➡️  Führe 'python backend/migrate_fictional_guids.py' aus")
        print()
    
    # Validierungs-Ergebnis
    if total_invalid == 0 and len(all_invalid_usages) == 0:
        print("✅ Validierung erfolgreich - alle Tabellen konform!")
        return 0
    else:
        print("⚠️  Validierung fehlgeschlagen - Inkonsistenzen gefunden")
        return 1


if __name__ == '__main__':
    exit_code = asyncio.run(main())
    sys.exit(exit_code)

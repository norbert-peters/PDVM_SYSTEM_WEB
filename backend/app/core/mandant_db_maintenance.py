"""
Mandanten-Datenbank Wartung
Wird nach Mandant-Login ausgeführt, bevor PdvmCentralSystemsteuerung initialisiert wird.

Verantwortlich für:
1. Prüfung und Anlage fehlender Tabellen (aus CONFIGS.FEATURES und CONFIGS.SYS_TABLES)
2. Prüfung und Korrektur der Spalten-Struktur
3. Korrektur von gilt_bis Werten (Standard: 9999-12-31 23:59:59)
"""
import logging
import asyncpg
from typing import List, Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

# Standard-Datum für unbegrenzte Gültigkeit
GILT_BIS_MAX = "9999-12-31 23:59:59"

# Standard PDVM-Tabellen-Struktur
PDVM_TABLE_COLUMNS = {
    'uid': 'UUID PRIMARY KEY DEFAULT uuid_generate_v4()',
    'daten': 'JSONB NOT NULL',
    'name': 'TEXT',
    'historisch': 'INTEGER DEFAULT 0',
    'source_hash': 'TEXT',
    'sec_id': 'UUID',
    'gilt_bis': f"TIMESTAMP DEFAULT '{GILT_BIS_MAX}'",
    'created_at': 'TIMESTAMP DEFAULT NOW()',
    'modified_at': 'TIMESTAMP DEFAULT NOW()',
    'daten_backup': 'JSONB DEFAULT \'{}\'::jsonb'
}

# Standard-Indizes für PDVM-Tabellen
PDVM_TABLE_INDEXES = [
    'sec_id',
    'historisch',
    'name',
    'modified_at',
    'daten'  # GIN Index
]


class MandantDatabaseMaintenance:
    """
    Mandanten-Datenbank Wartungsklasse
    """
    
    def __init__(self, mandant_pool: asyncpg.Pool, mandant_uid: str):
        """
        Args:
            mandant_pool: Connection Pool zur Mandanten-DB
            mandant_uid: UID des Mandanten
        """
        self.pool = mandant_pool
        self.mandant_uid = mandant_uid
    
    async def run_maintenance(self) -> Dict[str, Any]:
        """
        Führt komplette Wartung aus
        
        Returns:
            Dict mit Statistiken über durchgeführte Aktionen
        """
        logger.info(f"🔧 Starte Datenbank-Wartung für Mandant {self.mandant_uid}")
        
        stats = {
            'tables_created': [],
            'tables_updated': [],
            'records_updated': 0,
            'errors': []
        }
        
        async with self.pool.acquire() as conn:
            # 1. Hole erforderliche Tabellen aus sys_anwendungsdaten
            required_tables = await self._get_required_tables(conn)
            logger.info(f"📋 Erforderliche Tabellen: {required_tables}")
            
            # 2. Prüfe und erstelle fehlende Tabellen
            for table_name in required_tables:
                try:
                    exists = await self._table_exists(conn, table_name)
                    if not exists:
                        await self._create_pdvm_table(conn, table_name)
                        stats['tables_created'].append(table_name)
                        logger.info(f"✅ Tabelle {table_name} erstellt")
                    else:
                        # Tabelle existiert - prüfe Spalten
                        updated = await self._verify_and_fix_columns(conn, table_name)
                        if updated:
                            stats['tables_updated'].append(table_name)
                            logger.info(f"✅ Tabelle {table_name} aktualisiert")
                except Exception as e:
                    logger.error(f"❌ Fehler bei Tabelle {table_name}: {e}")
                    stats['errors'].append(f"{table_name}: {e}")
            
            # 3. Korrigiere gilt_bis für alte Datensätze
            records_updated = await self._fix_gilt_bis_values(conn, required_tables)
            stats['records_updated'] = records_updated
            
        logger.info(f"✅ Wartung abgeschlossen: {stats}")
        return stats
    
    async def _get_required_tables(self, conn: asyncpg.Connection) -> List[str]:
        """
        Liest erforderliche Tabellen aus sys_anwendungsdaten (CONFIGS.FEATURES, CONFIGS.SYS_TABLES)
        
        Returns:
            Liste der Tabellennamen
        """
        tables = set()
        
        try:
            # Hole sys_anwendungsdaten für diesen Mandanten
            row = await conn.fetchrow("""
                SELECT daten FROM sys_anwendungsdaten
                WHERE uid = $1
            """, self.mandant_uid)
            
            if row and row['daten']:
                daten = row['daten']
                
                # CONFIGS.FEATURES
                if 'CONFIGS' in daten:
                    configs = daten['CONFIGS']
                    if 'FEATURES' in configs and isinstance(configs['FEATURES'], list):
                        tables.update(configs['FEATURES'])
                    if 'SYS_TABLES' in configs and isinstance(configs['SYS_TABLES'], list):
                        tables.update(configs['SYS_TABLES'])
        
        except Exception as e:
            logger.warning(f"⚠️ Fehler beim Lesen der Tabellen-Config: {e}")
        
        # Standard-System-Tabellen immer hinzufügen
        standard_tables = [
            'sys_anwendungsdaten',
            'sys_systemsteuerung',
            'sys_layout',
            'sys_security',
            'sys_error_log',
            'sys_error_acknowledgments'
        ]
        tables.update(standard_tables)
        
        return list(tables)
    
    async def _table_exists(self, conn: asyncpg.Connection, table_name: str) -> bool:
        """Prüft ob Tabelle existiert"""
        return await conn.fetchval("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = $1
            )
        """, table_name)
    
    async def _create_pdvm_table(self, conn: asyncpg.Connection, table_name: str):
        """
        Erstellt PDVM-Standard-Tabelle mit allen Spalten und Indizes
        """
        # Spalten-Definitionen
        columns = ', '.join([f"{col} {definition}" for col, definition in PDVM_TABLE_COLUMNS.items()])
        
        # Tabelle erstellen
        await conn.execute(f"""
            CREATE TABLE {table_name} (
                {columns}
            )
        """)
        
        # Indizes erstellen
        for idx_col in PDVM_TABLE_INDEXES:
            if idx_col == 'daten':
                # GIN Index für JSONB
                await conn.execute(f"""
                    CREATE INDEX IF NOT EXISTS idx_{table_name}_{idx_col} 
                    ON {table_name} USING GIN({idx_col})
                """)
            else:
                # Standard B-Tree Index
                await conn.execute(f"""
                    CREATE INDEX IF NOT EXISTS idx_{table_name}_{idx_col} 
                    ON {table_name}({idx_col})
                """)
    
    async def _verify_and_fix_columns(self, conn: asyncpg.Connection, table_name: str) -> bool:
        """
        Prüft Spalten einer Tabelle und fügt fehlende hinzu
        
        Returns:
            True wenn Änderungen vorgenommen wurden
        """
        updated = False
        
        # Hole existierende Spalten
        existing_columns = await conn.fetch("""
            SELECT column_name, data_type, column_default
            FROM information_schema.columns
            WHERE table_name = $1
        """, table_name)
        
        existing_column_names = {row['column_name'] for row in existing_columns}
        
        # Prüfe jede erforderliche Spalte
        for col_name, col_definition in PDVM_TABLE_COLUMNS.items():
            if col_name not in existing_column_names:
                # Spalte fehlt - hinzufügen
                try:
                    # Extrahiere Datentyp und Default aus Definition
                    parts = col_definition.split()
                    data_type = parts[0]
                    
                    # Finde DEFAULT clause
                    default_clause = ""
                    if 'DEFAULT' in col_definition:
                        default_idx = col_definition.upper().find('DEFAULT')
                        default_clause = col_definition[default_idx:]
                    
                    await conn.execute(f"""
                        ALTER TABLE {table_name}
                        ADD COLUMN {col_name} {data_type} {default_clause}
                    """)
                    
                    logger.info(f"  ➕ Spalte {col_name} zu {table_name} hinzugefügt")
                    updated = True
                    
                except Exception as e:
                    logger.error(f"  ❌ Fehler beim Hinzufügen von {col_name}: {e}")
        
        return updated
    
    async def _fix_gilt_bis_values(self, conn: asyncpg.Connection, tables: List[str]) -> int:
        """
        Korrigiert gilt_bis Werte für alte Datensätze
        Setzt gilt_bis = '9999-12-31 23:59:59' für alle Datensätze mit modified_at < 2026-01-08
        
        Returns:
            Anzahl aktualisierter Datensätze
        """
        cutoff_date = datetime(2026, 1, 8)
        total_updated = 0
        
        for table_name in tables:
            try:
                # Prüfe ob Tabelle gilt_bis Spalte hat
                has_gilt_bis = await conn.fetchval("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.columns
                        WHERE table_name = $1 AND column_name = 'gilt_bis'
                    )
                """, table_name)
                
                if not has_gilt_bis:
                    continue
                
                # Update alte Datensätze
                result = await conn.execute(f"""
                    UPDATE {table_name}
                    SET gilt_bis = $1
                    WHERE modified_at < $2
                    AND (gilt_bis IS NULL OR gilt_bis != $1)
                """, GILT_BIS_MAX, cutoff_date)
                
                # Parse "UPDATE X" result
                count = int(result.split()[-1]) if result.startswith('UPDATE') else 0
                if count > 0:
                    logger.info(f"  🔄 {table_name}: {count} Datensätze aktualisiert")
                    total_updated += count
                    
            except Exception as e:
                logger.error(f"  ❌ Fehler bei gilt_bis Update für {table_name}: {e}")
        
        if total_updated > 0:
            logger.info(f"✅ Gesamt {total_updated} Datensätze mit gilt_bis korrigiert")
        
        return total_updated


async def run_mandant_maintenance(mandant_pool: asyncpg.Pool, mandant_uid: str) -> Dict[str, Any]:
    """
    Convenience-Funktion für Wartung
    
    Args:
        mandant_pool: Connection Pool zur Mandanten-DB
        mandant_uid: UID des Mandanten
        
    Returns:
        Statistiken über durchgeführte Aktionen
    """
    maintenance = MandantDatabaseMaintenance(mandant_pool, mandant_uid)
    return await maintenance.run_maintenance()

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
from app.core.pdvm_table_schema import PDVM_TABLE_COLUMNS, PDVM_TABLE_INDEXES, GILT_BIS_MAX

logger = logging.getLogger(__name__)


class MandantDatabaseMaintenance:
    """
    Mandanten-Datenbank Wartungsklasse
    """
    
    def __init__(self, mandant_pool: asyncpg.Pool, mandant_uid: str, mandant_daten: Dict[str, Any]):
        """
        Args:
            mandant_pool: Connection Pool zur Mandanten-DB
            mandant_uid: UID des Mandanten
            mandant_daten: Mandanten-Daten aus sys_mandanten (bereits geladen beim Login)
        """
        self.pool = mandant_pool
        self.mandant_uid = mandant_uid
        self.mandant_daten = mandant_daten
    
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
            # PHASE 1: Standard-System-Tabellen zuerst prüfen und warten
            # Diese müssen existieren bevor wir CONFIGS lesen können
            standard_tables = [
                'sys_anwendungsdaten',
                'sys_systemsteuerung',
                'sys_layout',
                'sys_security',
                'sys_error_log',
                'sys_error_acknowledgments'
            ]
            
            logger.info(f"📋 Phase 1: Standard-System-Tabellen ({len(standard_tables)})")
            for table_name in standard_tables:
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
            
            # PHASE 2: Jetzt FEATURES/SYS_TABLES aus Mandanten-Daten lesen (OHNE DB-Query!)
            feature_tables = await self._get_feature_tables()
            logger.info(f"📋 Phase 2: Feature-Tabellen aus CONFIGS ({len(feature_tables)})")
            
            # PHASE 3: Feature-Tabellen prüfen und warten
            # WICHTIG: sys_benutzer überspringen (hat Sonderschema mit benutzer + passwort)
            feature_tables_filtered = [t for t in feature_tables if t != 'sys_benutzer']
            logger.info(f"📋 Phase 3: Feature-Tabellen warten ({len(feature_tables_filtered)} Tabellen)")
            if 'sys_benutzer' in feature_tables:
                logger.info(f"⚠️ sys_benutzer übersprungen (Sonderschema)")
            
            for table_name in feature_tables_filtered:
                try:
                    exists = await self._table_exists(conn, table_name)
                    if not exists:
                        await self._create_pdvm_table(conn, table_name)
                        stats['tables_created'].append(table_name)
                        logger.info(f"✅ Feature-Tabelle {table_name} erstellt")
                    else:
                        # Tabelle existiert - prüfe Spalten
                        updated = await self._verify_and_fix_columns(conn, table_name)
                        if updated:
                            stats['tables_updated'].append(table_name)
                            logger.info(f"✅ Feature-Tabelle {table_name} aktualisiert")
                except Exception as e:
                    logger.error(f"❌ Fehler bei Feature-Tabelle {table_name}: {e}")
                    stats['errors'].append(f"{table_name}: {e}")
            
            # PHASE 4: Korrigiere gilt_bis für alle Tabellen (außer sys_benutzer)
            all_tables = list(set(standard_tables + feature_tables_filtered))
            records_updated = await self._fix_gilt_bis_values(conn, all_tables)
            stats['records_updated'] = records_updated
            
        logger.info(f"✅ Wartung abgeschlossen: {stats}")
        return stats
    
    async def _get_feature_tables(self) -> List[str]:
        """
        Extrahiert Feature-Tabellen aus Mandanten-Daten (CONFIG.FEATURES, CONFIG.SYS_TABLES)
        
        Nutzt die bereits beim Login geladenen Mandanten-Daten - KEINE DB-Abfrage!
        
        Returns:
            Liste der Tabellennamen aus FEATURES und SYS_TABLES
        """
        tables = set()
        
        try:
            logger.debug(f"📖 Mandanten-Daten Gruppen: {list(self.mandant_daten.keys())}")
            
            # CONFIG.FEATURES und CONFIG.SYS_TABLES
            if 'CONFIG' in self.mandant_daten:
                configs = self.mandant_daten['CONFIG']
                logger.debug(f"📖 CONFIG gefunden, Keys: {list(configs.keys())}")
                
                if 'FEATURES' in configs:
                    features = configs['FEATURES']
                    logger.info(f"📋 FEATURES gefunden: {features}")
                    if isinstance(features, list):
                        tables.update(features)
                    elif isinstance(features, dict):
                        # Manchmal als Dict gespeichert
                        tables.update(features.keys())
                
                if 'SYS_TABLES' in configs:
                    sys_tables = configs['SYS_TABLES']
                    logger.info(f"📋 SYS_TABLES gefunden: {sys_tables}")
                    if isinstance(sys_tables, list):
                        tables.update(sys_tables)
                    elif isinstance(sys_tables, dict):
                        # Manchmal als Dict gespeichert
                        tables.update(sys_tables.keys())
            else:
                logger.warning(f"⚠️ Keine CONFIG Gruppe in Mandanten-Daten gefunden")
                logger.warning(f"   Verfügbare Gruppen: {list(self.mandant_daten.keys())}")
        
        except Exception as e:
            logger.warning(f"⚠️ Fehler beim Extrahieren der Feature-Tabellen: {e}")
            import traceback
            logger.warning(traceback.format_exc())
        
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
        # UUID-Extension aktivieren (falls noch nicht vorhanden)
        await conn.execute("CREATE EXTENSION IF NOT EXISTS \"uuid-ossp\"")
        
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
    
    def _get_expected_pg_type(self, col_name: str, col_definition: str) -> str:
        """
        Extrahiert erwarteten PostgreSQL-Datentyp aus Spalten-Definition
        
        Returns:
            Normalisierter PostgreSQL-Datentyp (z.B. 'uuid', 'jsonb', 'text', 'timestamp without time zone')
        """
        col_def_lower = col_definition.lower()
        
        # Mapping von Definition zu PostgreSQL data_type
        if 'uuid' in col_def_lower:
            return 'uuid'
        elif 'jsonb' in col_def_lower:
            return 'jsonb'
        elif 'timestamp' in col_def_lower:
            return 'timestamp without time zone'
        elif 'integer' in col_def_lower or 'int' in col_def_lower:
            return 'integer'
        elif 'text' in col_def_lower:
            return 'text'
        
        return 'unknown'
    
    async def _verify_and_fix_columns(self, conn: asyncpg.Connection, table_name: str) -> bool:
        """
        Prüft ALLE Spalten einer Tabelle:
        1. Fügt fehlende Spalten hinzu
        2. Korrigiert falsche Datentypen (via temp column)
        
        Returns:
            True wenn Änderungen vorgenommen wurden
        """
        updated = False
        
        # Hole existierende Spalten mit Datentyp
        existing_columns = await conn.fetch("""
            SELECT column_name, data_type, column_default, udt_name
            FROM information_schema.columns
            WHERE table_name = $1
        """, table_name)
        
        existing_column_dict = {
            row['column_name']: {
                'data_type': row['data_type'],
                'udt_name': row['udt_name'],
                'column_default': row['column_default']
            } 
            for row in existing_columns
        }
        
        # Prüfe jede erforderliche Spalte
        for col_name, col_definition in PDVM_TABLE_COLUMNS.items():
            if col_name not in existing_column_dict:
                # Spalte fehlt - hinzufügen
                try:
                    await conn.execute(f"""
                        ALTER TABLE {table_name}
                        ADD COLUMN {col_name} {col_definition}
                    """)
                    
                    logger.info(f"  ➕ Spalte {col_name} zu {table_name} hinzugefügt")
                    updated = True
                    
                except Exception as e:
                    logger.error(f"  ❌ Fehler beim Hinzufügen von {col_name}: {e}")
            
            else:
                # Spalte existiert - prüfe Datentyp
                col_info = existing_column_dict[col_name]
                actual_type = col_info['data_type'].lower()
                expected_type = self._get_expected_pg_type(col_name, col_definition)
                
                # Normalisierung für Vergleich
                type_mismatch = False
                
                if expected_type == 'timestamp without time zone' and actual_type in ['text', 'character varying']:
                    type_mismatch = True
                elif expected_type == 'jsonb' and actual_type in ['text', 'json']:
                    type_mismatch = True
                elif expected_type == 'uuid' and actual_type in ['text', 'character varying']:
                    type_mismatch = True
                elif expected_type == 'integer' and actual_type in ['text', 'character varying', 'bigint']:
                    type_mismatch = True
                elif expected_type == 'text' and actual_type in ['character varying']:
                    # varchar zu text ist ok, keine Konvertierung nötig
                    pass
                
                if type_mismatch:
                    try:
                        logger.info(f"  🔄 Konvertiere {table_name}.{col_name} von {actual_type} zu {expected_type}")
                        
                        # Temporäre Spalte mit korrektem Typ erstellen
                        await conn.execute(f"""
                            ALTER TABLE {table_name}
                            ADD COLUMN {col_name}_temp {col_definition.split('DEFAULT')[0].strip()}
                        """)
                        
                        # Daten konvertieren/kopieren
                        if expected_type == 'timestamp without time zone':
                            # Timestamp: Alles auf Standard-Wert setzen
                            await conn.execute(f"""
                                UPDATE {table_name}
                                SET {col_name}_temp = '9999-12-31 23:59:59'::TIMESTAMP
                            """)
                        elif expected_type == 'jsonb':
                            # JSONB: Versuche zu parsen, sonst leeres Object
                            await conn.execute(f"""
                                UPDATE {table_name}
                                SET {col_name}_temp = CASE
                                    WHEN {col_name} IS NOT NULL AND {col_name}::text != '' 
                                    THEN {col_name}::jsonb
                                    ELSE '{{}}'::jsonb
                                END
                            """)
                        elif expected_type == 'uuid':
                            # UUID: Nur gültige UUIDs übernehmen, sonst NULL
                            await conn.execute(f"""
                                UPDATE {table_name}
                                SET {col_name}_temp = CASE
                                    WHEN {col_name} ~ '^[0-9a-f]{{8}}-[0-9a-f]{{4}}-[0-9a-f]{{4}}-[0-9a-f]{{4}}-[0-9a-f]{{12}}$'
                                    THEN {col_name}::uuid
                                    ELSE NULL
                                END
                            """)
                        elif expected_type == 'integer':
                            # Integer: Versuche zu parsen, sonst 0
                            await conn.execute(f"""
                                UPDATE {table_name}
                                SET {col_name}_temp = CASE
                                    WHEN {col_name} ~ '^[0-9]+$'
                                    THEN {col_name}::integer
                                    ELSE 0
                                END
                            """)
                        else:
                            # Text oder unbekannt: Direkt kopieren
                            await conn.execute(f"""
                                UPDATE {table_name}
                                SET {col_name}_temp = {col_name}
                            """)
                        
                        # Alte Spalte löschen
                        await conn.execute(f"""
                            ALTER TABLE {table_name}
                            DROP COLUMN {col_name}
                        """)
                        
                        # Neue Spalte umbenennen
                        await conn.execute(f"""
                            ALTER TABLE {table_name}
                            RENAME COLUMN {col_name}_temp TO {col_name}
                        """)
                        
                        logger.info(f"  ✅ {table_name}.{col_name} erfolgreich zu {expected_type} konvertiert")
                        updated = True
                        
                    except Exception as e:
                        logger.error(f"  ❌ Fehler bei {col_name} Konvertierung: {e}")
                        import traceback
                        logger.error(traceback.format_exc())
        
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
                
                # Konvertiere GILT_BIS_MAX String zu datetime
                gilt_bis_dt = datetime.strptime(GILT_BIS_MAX, '%Y-%m-%d %H:%M:%S')
                
                # Update alte Datensätze
                result = await conn.execute(f"""
                    UPDATE {table_name}
                    SET gilt_bis = $1
                    WHERE modified_at < $2
                    AND (gilt_bis IS NULL OR gilt_bis != $1)
                """, gilt_bis_dt, cutoff_date)
                
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


async def run_system_maintenance(system_pool: asyncpg.Pool) -> Dict[str, Any]:
    """
    Wartung für pdvm_system Datenbank
    
    Prüft und korrigiert System-Tabellen (sys_menudaten, sys_layout, etc.)
    
    Args:
        system_pool: Connection Pool zur pdvm_system Datenbank
        
    Returns:
        Statistiken über durchgeführte Aktionen
    """
    from app.core.pdvm_table_schema import PDVM_SYSTEM_TABLES
    
    logger.info(f"🔧 Starte System-Datenbank-Wartung (pdvm_system)")
    
    stats = {
        'tables_created': [],
        'tables_updated': [],
        'records_updated': 0,
        'errors': []
    }
    
    # Erstelle temporäre Maintenance-Instanz (ohne mandant_uid und mandant_daten)
    # Wir nutzen nur die Hilfsmethoden
    temp_maintenance = MandantDatabaseMaintenance(system_pool, "", {})
    
    async with system_pool.acquire() as conn:
        # System-Tabellen prüfen und warten
        for table_name in PDVM_SYSTEM_TABLES:
            try:
                exists = await temp_maintenance._table_exists(conn, table_name)
                if not exists:
                    await temp_maintenance._create_pdvm_table(conn, table_name)
                    stats['tables_created'].append(table_name)
                    logger.info(f"✅ System-Tabelle {table_name} erstellt")
                else:
                    # Tabelle existiert - prüfe Spalten
                    updated = await temp_maintenance._verify_and_fix_columns(conn, table_name)
                    if updated:
                        stats['tables_updated'].append(table_name)
                        logger.info(f"✅ System-Tabelle {table_name} aktualisiert")
            except Exception as e:
                logger.error(f"❌ Fehler bei System-Tabelle {table_name}: {e}")
                stats['errors'].append(f"{table_name}: {e}")
        
        # gilt_bis Werte korrigieren
        records_updated = await temp_maintenance._fix_gilt_bis_values(conn, PDVM_SYSTEM_TABLES)
        stats['records_updated'] = records_updated
    
    logger.info(f"✅ System-Wartung abgeschlossen: {stats}")
    return stats


async def run_mandant_maintenance(
    mandant_pool: asyncpg.Pool, 
    mandant_uid: str,
    mandant_daten: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Convenience-Funktion für Wartung
    
    Args:
        mandant_pool: Connection Pool zur Mandanten-DB
        mandant_uid: UID des Mandanten
        mandant_daten: Mandanten-Daten aus Login (enthält CONFIGS.FEATURES)
        
    Returns:
        Statistiken über durchgeführte Aktionen
    """
    maintenance = MandantDatabaseMaintenance(mandant_pool, mandant_uid, mandant_daten)
    return await maintenance.run_maintenance()

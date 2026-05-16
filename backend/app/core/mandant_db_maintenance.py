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
import json
import uuid
import os
from typing import List, Dict, Any, Optional
from datetime import datetime
from app.core.pdvm_table_schema import PDVM_TABLE_COLUMNS, PDVM_TABLE_INDEXES, GILT_BIS_MAX
from app.core.pdvm_datetime import datetime_to_pdvm, pdvm_to_str
from app.core.feld_aenderungshistorie_service import FieldChangeHistoryService

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
            'link_uid_synced': 0,
            'root_self_synced': 0,
            'link_uid_columns_added': 0,
            'row_uids_rekeyed': 0,
            'history_rows_deleted': 0,
            'errors': []
        }
        
        async with self.pool.acquire() as conn:
            # PHASE 1: Standard-System-Tabellen zuerst prüfen und warten
            # Diese müssen existieren bevor wir CONFIGS lesen können
            standard_tables = [
                'msy_anwendungsdaten',
                'msy_systemsteuerung',
                'msy_layout',
                'msy_security',
                'msy_error_log',
                'msy_error_acknowledgments',
                'msy_control_dict',
                'msy_control_dict_audit',
                'msy_systemdaten',
                'msy_ext_table',
                'msy_feld_aenderungshistorie',
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
            legacy_to_canonical = {
                'sys_anwendungsdaten': 'msy_anwendungsdaten',
                'sys_systemsteuerung': 'msy_systemsteuerung',
                'sys_layout': 'msy_layout',
                'sys_security': 'msy_security',
                'sys_error_log': 'msy_error_log',
                'sys_error_acknowledgements': 'msy_error_acknowledgments',
                'sys_error_acknowledgments': 'msy_error_acknowledgments',
                'sys_contr_dict_man': 'msy_control_dict',
                'sys_contr_dict_man_audit': 'msy_control_dict_audit',
                'sys_ext_table_man': 'msy_ext_table',
                'sys_feld_aenderungshistorie': 'msy_feld_aenderungshistorie',
            }
            feature_tables = [legacy_to_canonical.get(str(t), str(t)) for t in feature_tables]
            logger.info(f"📋 Phase 2: Feature-Tabellen aus CONFIGS ({len(feature_tables)})")
            
            # PHASE 3: Feature-Tabellen prüfen und warten
            # WICHTIG: Auth-Tabellen überspringen (haben Sonderschema)
            skip_auth_tables = {'sys_benutzer', 'asy_benutzer'}
            feature_tables_filtered = [t for t in feature_tables if t not in skip_auth_tables]
            logger.info(f"📋 Phase 3: Feature-Tabellen warten ({len(feature_tables_filtered)} Tabellen)")
            if any(t in feature_tables for t in skip_auth_tables):
                logger.info(f"⚠️ Auth-Tabelle in Features übersprungen (Sonderschema)")
            
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
            
            # PHASE 4: Korrigiere gilt_bis für alle Tabellen (außer Auth-Sondertabellen)
            all_tables = list(set(standard_tables + feature_tables_filtered))
            records_updated = await self._fix_gilt_bis_values(conn, all_tables)
            stats['records_updated'] = records_updated

            # PHASE 5: link_uid auf uid synchronisieren (nur wenn Spalte existiert)
            link_uid_synced = await self._sync_link_uid_values(conn, all_tables)
            stats['link_uid_synced'] = link_uid_synced

            # PHASE 5b: msy_systemsteuerung/msy_anwendungsdaten auf Row-UID umstellen
            row_uids_rekeyed = await self._rekey_row_uids_for_link_tables(
                conn,
                ["msy_systemsteuerung", "msy_anwendungsdaten"],
            )
            stats['row_uids_rekeyed'] = row_uids_rekeyed

            # PHASE 6: Voll-Normalisierung über ALLE Tabellen dieser DB
            all_public_tables = await self._get_public_tables(conn)
            logger.info(f"📋 Phase 6: Voll-Normalisierung ({len(all_public_tables)} Tabellen)")
            link_uid_cols_added = await self._ensure_link_uid_columns(conn, all_public_tables)
            root_self_synced = await self._sync_root_self_fields(conn, all_public_tables)
            link_uid_synced_all = await self._sync_link_uid_values(conn, all_public_tables)

            stats['link_uid_columns_added'] = link_uid_cols_added
            stats['root_self_synced'] = root_self_synced
            stats['link_uid_synced'] = stats['link_uid_synced'] + link_uid_synced_all

            # PHASE 7: Retention-Cleanup für Feld-Aenderungshistorie
            stats['history_rows_deleted'] = await self._cleanup_history_retention(conn)
            
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

    async def _get_public_tables(self, conn: asyncpg.Connection) -> List[str]:
        """Liefert alle Tabellen im public-Schema."""
        rows = await conn.fetch(
            """
            SELECT tablename
            FROM pg_tables
            WHERE schemaname = 'public'
            ORDER BY tablename
            """
        )
        return [str(r['tablename']) for r in rows]

    async def _get_column_types(self, conn: asyncpg.Connection, table_name: str) -> Dict[str, str]:
        """Liefert Spaltennamen -> Datentyp für eine Tabelle."""
        rows = await conn.fetch(
            """
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = $1
            """,
            table_name,
        )
        return {str(r['column_name']): str(r['data_type']).lower() for r in rows}

    @staticmethod
    def _quote_ident(identifier: str) -> str:
        """Sicheres Quoting für SQL-Identifier."""
        return '"' + str(identifier).replace('"', '""') + '"'

    @staticmethod
    def _build_safe_index_name(table_name: str, suffix: str) -> str:
        """Erzeugt PostgreSQL-kompatiblen Indexnamen (max 63 Zeichen)."""
        import hashlib

        base = f"idx_{table_name}_{suffix}".lower()
        if len(base) <= 63:
            return base
        digest = hashlib.md5(base.encode('utf-8')).hexdigest()[:10]
        return f"idx_{digest}_{suffix}"[:63]
    
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

    async def _ensure_link_uid_columns(self, conn: asyncpg.Connection, tables: List[str]) -> int:
        """Fügt link_uid + Index in allen Tabellen mit uid-Spalte hinzu (falls fehlend)."""
        added = 0

        for table_name in tables:
            try:
                col_types = await self._get_column_types(conn, table_name)
                if 'uid' not in col_types:
                    continue

                q_table = self._quote_ident(table_name)

                if 'link_uid' not in col_types:
                    await conn.execute(f"ALTER TABLE {q_table} ADD COLUMN link_uid UUID")
                    added += 1
                    logger.info(f"➕ {table_name}: Spalte link_uid ergänzt")

                idx_name = self._build_safe_index_name(table_name, 'link_uid')
                q_idx = self._quote_ident(idx_name)
                await conn.execute(
                    f"CREATE INDEX IF NOT EXISTS {q_idx} ON {q_table}(link_uid)"
                )

            except Exception as e:
                logger.warning(f"⚠️ link_uid-Spaltenprüfung fehlgeschlagen ({table_name}): {e}")

        return added
    
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

    async def _sync_link_uid_values(self, conn: asyncpg.Connection, tables: List[str]) -> int:
        """Synchronisiert link_uid = uid für Datensätze ohne link_uid."""
        total_synced = 0

        for table_name in tables:
            try:
                has_link_uid = await conn.fetchval(
                    """
                    SELECT EXISTS (
                        SELECT FROM information_schema.columns
                        WHERE table_name = $1 AND column_name = 'link_uid'
                    )
                    """,
                    table_name,
                )

                if not has_link_uid:
                    continue

                result = await conn.execute(
                    f"""
                    UPDATE {table_name}
                    SET link_uid = uid
                    WHERE link_uid IS NULL
                    """
                )

                # asyncpg liefert z.B. "UPDATE 12"
                synced = int(result.split(" ")[-1])
                total_synced += synced

                if synced > 0:
                    logger.info(f"🔗 {table_name}: {synced} link_uid Werte synchronisiert")

            except Exception as e:
                logger.warning(f"⚠️ link_uid Sync in {table_name} fehlgeschlagen: {e}")

        return total_synced

    async def _rekey_row_uids_for_link_tables(self, conn: asyncpg.Connection, table_names: List[str]) -> int:
        """Entkoppelt uid von link_uid für Tabellen mit exakter link_uid-Adressierung."""
        total_rekeyed = 0

        for table_name in table_names:
            try:
                exists = await self._table_exists(conn, table_name)
                if not exists:
                    continue

                col_types = await self._get_column_types(conn, table_name)
                if 'uid' not in col_types or 'link_uid' not in col_types:
                    continue

                q_table = self._quote_ident(table_name)
                rows = await conn.fetch(
                    f"""
                    SELECT uid
                    FROM {q_table}
                    WHERE link_uid IS NOT NULL
                      AND uid = link_uid
                    """
                )

                rekeyed = 0
                for r in rows:
                    old_uid = r['uid']
                    new_uid = uuid.uuid4()
                    await conn.execute(
                        f"UPDATE {q_table} SET uid = $1 WHERE uid = $2",
                        new_uid,
                        old_uid,
                    )
                    rekeyed += 1

                total_rekeyed += rekeyed
                if rekeyed > 0:
                    logger.info(f"🆔 {table_name}: {rekeyed} Row-UIDs von link_uid entkoppelt")

            except Exception as e:
                logger.warning(f"⚠️ Row-UID Rekey fehlgeschlagen ({table_name}): {e}")

        return total_rekeyed

    async def _cleanup_history_retention(self, conn: asyncpg.Connection) -> int:
        """Bereinigt alte Einträge aus sys_feld_aenderungshistorie."""
        try:
            exists = await self._table_exists(conn, FieldChangeHistoryService.HISTORY_TABLE)
            if not exists:
                return 0

            retention_raw = str(os.getenv("PDVM_HISTORY_RETENTION_MONTHS", "36")).strip()
            try:
                retention_months = int(retention_raw)
            except Exception:
                retention_months = 36

            # V1-Rahmen: 12-36 Monate
            retention_months = max(12, min(36, retention_months))
            deleted = await FieldChangeHistoryService.cleanup_retention(conn, retention_months)
            if deleted > 0:
                logger.info(
                    f"🧹 Historie-Cleanup: {deleted} Zeilen älter als {retention_months} Monate gelöscht"
                )
            return deleted
        except Exception as e:
            logger.warning(f"⚠️ Historie-Cleanup fehlgeschlagen: {e}")
            return 0

    async def _sync_root_self_fields(self, conn: asyncpg.Connection, tables: List[str]) -> int:
        """Synchronisiert ROOT.SELF_* Felder in daten JSONB (Zeitwerte immer im PDVM-Format)."""
        total_synced = 0

        for table_name in tables:
            try:
                col_types = await self._get_column_types(conn, table_name)
                if 'uid' not in col_types or 'daten' not in col_types:
                    continue
                if col_types.get('daten') != 'jsonb':
                    continue

                q_table = self._quote_ident(table_name)

                select_cols = ["uid", "daten"]
                if 'link_uid' in col_types:
                    select_cols.append("link_uid")
                if 'created_at' in col_types:
                    select_cols.append("created_at")
                if 'modified_at' in col_types:
                    select_cols.append("modified_at")
                if 'gilt_bis' in col_types:
                    select_cols.append("gilt_bis")

                rows = await conn.fetch(
                    f"SELECT {', '.join(select_cols)} FROM {q_table} WHERE uid IS NOT NULL"
                )

                synced = 0

                def _to_pdvm_string(dt_val: Any) -> Optional[str]:
                    if dt_val is None:
                        return None
                    try:
                        return pdvm_to_str(datetime_to_pdvm(dt_val))
                    except Exception:
                        return None

                for row in rows:
                    uid_val = row['uid']
                    link_uid_val = row['link_uid'] if 'link_uid' in row else None

                    daten_obj = row['daten']
                    if isinstance(daten_obj, str):
                        try:
                            daten_obj = json.loads(daten_obj)
                        except Exception:
                            daten_obj = {}
                    if not isinstance(daten_obj, dict):
                        daten_obj = {}

                    root = daten_obj.get('ROOT')
                    if not isinstance(root, dict):
                        root = {}
                    else:
                        root = dict(root)

                    before_root = dict(root)

                    root['SELF_GUID'] = str(uid_val)
                    root['SELF_LINK_UID'] = str(link_uid_val or uid_val)

                    if 'created_at' in row:
                        root['SELF_CREATED_AT'] = _to_pdvm_string(row['created_at'])
                    if 'modified_at' in row:
                        root['SELF_MODIFIED_AT'] = _to_pdvm_string(row['modified_at'])
                    if 'gilt_bis' in row:
                        root['SELF_GILT_BIS'] = _to_pdvm_string(row['gilt_bis'])

                    duplicate_pairs = [
                        ("GUID", "SELF_GUID"),
                        ("LINK_UID", "SELF_LINK_UID"),
                        ("CREATED_AT", "SELF_CREATED_AT"),
                        ("MODIFIED_AT", "SELF_MODIFIED_AT"),
                        ("GILT_BIS", "SELF_GILT_BIS"),
                    ]
                    for legacy_key, self_key in duplicate_pairs:
                        if legacy_key in root and self_key in root and str(root.get(legacy_key)) == str(root.get(self_key)):
                            root.pop(legacy_key, None)

                    # Einmal-Bereinigung: In sys_mandanten sind SELF_* Zeitfelder führend.
                    # Legacy ROOT.CREATED_AT/MODIFIED_AT werden entfernt, sobald SELF vorhanden ist.
                    if str(table_name).strip().lower() == 'sys_mandanten':
                        if 'SELF_CREATED_AT' in root:
                            root.pop('CREATED_AT', None)
                        if 'SELF_MODIFIED_AT' in root:
                            root.pop('MODIFIED_AT', None)

                    if root != before_root or daten_obj.get('ROOT') != root:
                        daten_obj['ROOT'] = root
                        await conn.execute(
                            f"UPDATE {q_table} SET daten = $1::jsonb WHERE uid = $2",
                            json.dumps(daten_obj, ensure_ascii=False),
                            uid_val,
                        )
                        synced += 1

                total_synced += synced

                if synced > 0:
                    logger.info(f"🧩 {table_name}: {synced} ROOT.SELF Felder synchronisiert und Duplikate bereinigt")

            except Exception as e:
                logger.warning(f"⚠️ ROOT.SELF Sync in {table_name} fehlgeschlagen: {e}")

        return total_synced
    
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
        'link_uid_synced': 0,
        'root_self_synced': 0,
        'link_uid_columns_added': 0,
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

        # link_uid Werte synchronisieren
        link_uid_synced = await temp_maintenance._sync_link_uid_values(conn, PDVM_SYSTEM_TABLES)
        stats['link_uid_synced'] = link_uid_synced

        # Voll-Normalisierung für alle Tabellen in pdvm_system
        all_public_tables = await temp_maintenance._get_public_tables(conn)
        link_uid_cols_added = await temp_maintenance._ensure_link_uid_columns(conn, all_public_tables)
        root_self_synced = await temp_maintenance._sync_root_self_fields(conn, all_public_tables)
        link_uid_synced_all = await temp_maintenance._sync_link_uid_values(conn, all_public_tables)

        stats['link_uid_columns_added'] = link_uid_cols_added
        stats['root_self_synced'] = root_self_synced
        stats['link_uid_synced'] = stats['link_uid_synced'] + link_uid_synced_all
    
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


async def run_auth_maintenance(auth_pool: asyncpg.Pool) -> Dict[str, Any]:
    """
    Wartung für auth Datenbank (insb. sys_benutzer, sys_mandanten).
    Führt Voll-Normalisierung für alle Tabellen aus.
    """
    logger.info("🔧 Starte Auth-Datenbank-Wartung (auth)")

    stats = {
        'tables_created': [],
        'tables_updated': [],
        'records_updated': 0,
        'link_uid_synced': 0,
        'root_self_synced': 0,
        'link_uid_columns_added': 0,
        'errors': [],
    }

    temp_maintenance = MandantDatabaseMaintenance(auth_pool, "", {})

    async with auth_pool.acquire() as conn:
        # Historie-Tabelle in auth-DB sicherstellen (für Änderungen an auth-Tabellen).
        history_table = FieldChangeHistoryService.HISTORY_TABLE
        try:
            exists = await temp_maintenance._table_exists(conn, history_table)
            if not exists:
                await temp_maintenance._create_pdvm_table(conn, history_table)
                stats['tables_created'].append(history_table)
                logger.info(f"✅ Auth-Tabelle {history_table} erstellt")
            else:
                updated = await temp_maintenance._verify_and_fix_columns(conn, history_table)
                if updated:
                    stats['tables_updated'].append(history_table)
                    logger.info(f"✅ Auth-Tabelle {history_table} aktualisiert")
        except Exception as e:
            logger.error(f"❌ Fehler bei Auth-Tabelle {history_table}: {e}")
            stats['errors'].append(f"{history_table}: {e}")

        all_public_tables = await temp_maintenance._get_public_tables(conn)
        link_uid_cols_added = await temp_maintenance._ensure_link_uid_columns(conn, all_public_tables)
        root_self_synced = await temp_maintenance._sync_root_self_fields(conn, all_public_tables)
        link_uid_synced = await temp_maintenance._sync_link_uid_values(conn, all_public_tables)

        stats['link_uid_columns_added'] = link_uid_cols_added
        stats['root_self_synced'] = root_self_synced
        stats['link_uid_synced'] = link_uid_synced

    logger.info(f"✅ Auth-Wartung abgeschlossen: {stats}")
    return stats

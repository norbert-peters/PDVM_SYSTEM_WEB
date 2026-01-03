"""
PDVM Database Service
Generischer CRUD-Service für alle PDVM-Standard-Tabellen

Nach Desktop-Vorbild: PdvmDatenbank
Unterstützt die Standard-Tabellenstruktur mit uid, daten (JSONB), name, etc.
"""
import asyncpg
import json
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
from uuid import UUID, uuid4

logger = logging.getLogger(__name__)


class PdvmDatabaseService:
    """
    Generischer Database Service für PDVM-Tabellen
    
    Standard-Spalten:
    - uid: UUID (Primary Key)
    - daten: JSONB (Hauptdaten, verschachtelt)
    - name: TEXT (Anzeigename)
    - historisch: INTEGER (0=aktiv, 1+=historisch)
    - source_hash: TEXT (Änderungsverfolgung)
    - sec_id: UUID (Security/Verknüpfung)
    - gilt_bis: TEXT (Gültigkeitsdatum)
    - created_at: TIMESTAMP
    - modified_at: TIMESTAMP
    - daten_backup: JSONB
    """
    
    def __init__(self, database: str, table: str, password: str = "Polari$55"):
        """
        Initialisiert Database Service für spezifische Tabelle
        
        Args:
            database: Datenbank-Name (z.B. "auth", "mandant")
            table: Tabellen-Name (z.B. "sys_mandanten", "persondaten")
            password: PostgreSQL Passwort
        """
        self.database = database
        self.table = table
        self.db_url = f"postgresql://postgres:{password}@localhost:5432/{database}"
        
    async def _get_connection(self) -> asyncpg.Connection:
        """Erstellt DB-Connection"""
        return await asyncpg.connect(self.db_url)
    
    async def list_all(
        self, 
        historisch: Optional[int] = 0,
        limit: Optional[int] = None,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Liste aller Datensätze
        
        Args:
            historisch: Filter (0=nur aktive, None=alle)
            limit: Max Anzahl
            offset: Offset für Pagination
            
        Returns:
            Liste von Datensätzen
        """
        conn = await self._get_connection()
        
        try:
            query = f"SELECT * FROM {self.table}"
            params = []
            
            if historisch is not None:
                query += " WHERE historisch = $1"
                params.append(historisch)
            
            query += f" ORDER BY modified_at DESC"
            
            if limit:
                query += f" LIMIT ${len(params) + 1}"
                params.append(limit)
            
            if offset > 0:
                query += f" OFFSET ${len(params) + 1}"
                params.append(offset)
            
            rows = await conn.fetch(query, *params)
            
            result = []
            for row in rows:
                record = dict(row)
                # Parse JSONB fields wenn String
                if record.get('daten') and isinstance(record['daten'], str):
                    record['daten'] = json.loads(record['daten'])
                if record.get('daten_backup') and isinstance(record['daten_backup'], str):
                    record['daten_backup'] = json.loads(record['daten_backup'])
                result.append(record)
            
            return result
            
        finally:
            await conn.close()
    
    async def get_by_uid(self, uid: str | UUID) -> Optional[Dict[str, Any]]:
        """
        Lädt Datensatz per UID
        
        Args:
            uid: UUID des Datensatzes
            
        Returns:
            Datensatz oder None
        """
        conn = await self._get_connection()
        
        try:
            row = await conn.fetchrow(
                f"SELECT * FROM {self.table} WHERE uid = $1",
                UUID(str(uid))
            )
            
            if not row:
                return None
            
            record = dict(row)
            # Parse JSONB
            if record.get('daten') and isinstance(record['daten'], str):
                record['daten'] = json.loads(record['daten'])
            if record.get('daten_backup') and isinstance(record['daten_backup'], str):
                record['daten_backup'] = json.loads(record['daten_backup'])
            
            return record
            
        finally:
            await conn.close()
    
    async def create(
        self,
        daten: Dict[str, Any],
        name: str = "",
        uid: Optional[UUID] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Erstellt neuen Datensatz
        
        Args:
            daten: Hauptdaten (JSONB)
            name: Anzeigename
            uid: Optional eigene UID
            **kwargs: Weitere Spalten (sec_id, gilt_bis, etc.)
            
        Returns:
            Erstellter Datensatz
        """
        conn = await self._get_connection()
        
        try:
            if uid is None:
                uid = uuid4()
            
            # Standard-Werte
            values = {
                'uid': uid,
                'daten': json.dumps(daten) if isinstance(daten, dict) else daten,
                'name': name,
                'historisch': kwargs.get('historisch', 0),
                'source_hash': kwargs.get('source_hash'),
                'sec_id': kwargs.get('sec_id'),
                'gilt_bis': kwargs.get('gilt_bis', '9999365.00000'),
                'created_at': datetime.now(),
                'modified_at': datetime.now(),
                'daten_backup': None
            }
            
            # INSERT
            columns = ', '.join(values.keys())
            placeholders = ', '.join(f'${i+1}' for i in range(len(values)))
            
            query = f"""
                INSERT INTO {self.table} ({columns})
                VALUES ({placeholders})
                RETURNING *
            """
            
            row = await conn.fetchrow(query, *values.values())
            
            record = dict(row)
            if record.get('daten') and isinstance(record['daten'], str):
                record['daten'] = json.loads(record['daten'])
            
            logger.info(f"✅ Datensatz erstellt in {self.database}.{self.table}: {uid}")
            return record
            
        finally:
            await conn.close()
    
    async def update(
        self,
        uid: str | UUID,
        daten: Optional[Dict[str, Any]] = None,
        name: Optional[str] = None,
        backup_old: bool = True,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Aktualisiert Datensatz
        
        Args:
            uid: UUID des Datensatzes
            daten: Neue Hauptdaten (optional)
            name: Neuer Name (optional)
            backup_old: Alte Daten in daten_backup sichern
            **kwargs: Weitere zu aktualisierende Spalten
            
        Returns:
            Aktualisierter Datensatz
        """
        conn = await self._get_connection()
        
        try:
            uid = UUID(str(uid))
            
            # Lade alte Daten für Backup
            if backup_old and daten is not None:
                old_record = await conn.fetchrow(
                    f"SELECT daten FROM {self.table} WHERE uid = $1",
                    uid
                )
                if old_record:
                    old_daten = old_record['daten']
                    if isinstance(old_daten, str):
                        old_daten = json.loads(old_daten)
                    kwargs['daten_backup'] = json.dumps(old_daten)
            
            # Prepare UPDATE
            updates = {}
            if daten is not None:
                updates['daten'] = json.dumps(daten) if isinstance(daten, dict) else daten
            if name is not None:
                updates['name'] = name
            
            updates['modified_at'] = datetime.now()
            updates.update(kwargs)
            
            # Build UPDATE query
            set_clause = ', '.join(f"{col} = ${i+1}" for i, col in enumerate(updates.keys()))
            query = f"""
                UPDATE {self.table}
                SET {set_clause}
                WHERE uid = ${len(updates) + 1}
                RETURNING *
            """
            
            row = await conn.fetchrow(query, *updates.values(), uid)
            
            if not row:
                raise ValueError(f"Datensatz nicht gefunden: {uid}")
            
            record = dict(row)
            if record.get('daten') and isinstance(record['daten'], str):
                record['daten'] = json.loads(record['daten'])
            
            logger.info(f"✅ Datensatz aktualisiert in {self.database}.{self.table}: {uid}")
            return record
            
        finally:
            await conn.close()
    
    async def delete(self, uid: str | UUID, soft: bool = True) -> bool:
        """
        Löscht Datensatz
        
        Args:
            uid: UUID des Datensatzes
            soft: True=historisch setzen, False=wirklich löschen
            
        Returns:
            True wenn erfolgreich
        """
        conn = await self._get_connection()
        
        try:
            uid = UUID(str(uid))
            
            if soft:
                # Soft Delete: historisch = 1
                await conn.execute(
                    f"UPDATE {self.table} SET historisch = 1, modified_at = $1 WHERE uid = $2",
                    datetime.now(), uid
                )
                logger.info(f"🗑️  Datensatz markiert als historisch: {uid}")
            else:
                # Hard Delete
                await conn.execute(
                    f"DELETE FROM {self.table} WHERE uid = $1",
                    uid
                )
                logger.info(f"🗑️  Datensatz gelöscht: {uid}")
            
            return True
            
        finally:
            await conn.close()
    
    async def search(
        self,
        search_term: str,
        search_fields: List[str] = ['name'],
        historisch: Optional[int] = 0
    ) -> List[Dict[str, Any]]:
        """
        Suche in Datensätzen
        
        Args:
            search_term: Suchbegriff
            search_fields: Zu durchsuchende Felder
            historisch: Filter
            
        Returns:
            Gefundene Datensätze
        """
        conn = await self._get_connection()
        
        try:
            conditions = []
            params = [f"%{search_term}%"]
            
            for field in search_fields:
                conditions.append(f"{field} ILIKE $1")
            
            where_clause = " OR ".join(conditions)
            
            if historisch is not None:
                where_clause = f"({where_clause}) AND historisch = $2"
                params.append(historisch)
            
            query = f"SELECT * FROM {self.table} WHERE {where_clause} ORDER BY modified_at DESC"
            
            rows = await conn.fetch(query, *params)
            
            result = []
            for row in rows:
                record = dict(row)
                if record.get('daten') and isinstance(record['daten'], str):
                    record['daten'] = json.loads(record['daten'])
                result.append(record)
            
            return result
            
        finally:
            await conn.close()
    
    async def count(self, historisch: Optional[int] = 0) -> int:
        """
        Zählt Datensätze
        
        Args:
            historisch: Filter
            
        Returns:
            Anzahl
        """
        conn = await self._get_connection()
        
        try:
            if historisch is not None:
                count = await conn.fetchval(
                    f"SELECT COUNT(*) FROM {self.table} WHERE historisch = $1",
                    historisch
                )
            else:
                count = await conn.fetchval(f"SELECT COUNT(*) FROM {self.table}")
            
            return count
            
        finally:
            await conn.close()

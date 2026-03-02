"""
PDVM Database Manager
Zentraler Datenbankmanager für alle PDVM-Tabellen (außer sys_benutzer Sonderfall)

Nach Desktop-Vorbild: pdvm_datenbank.py
- Einheitlicher Zugriff auf alle Tabellen
- JSONB-basierte Datenstruktur mit uid + daten
- Unterstützt System-, Auth- und Mandanten-Datenbanken
- Historie-Support für zeitbasierte Daten
"""
import uuid
import json
import asyncio
import re
import copy
from typing import Dict, List, Optional, Any
from datetime import datetime
import asyncpg
from app.core.database import DatabasePool
from app.core.pdvm_table_schema import PDVM_TABLE_COLUMNS, PDVM_TABLE_INDEXES


class PdvmDatabase:
    """
    PDVM Datenbankmanager - Einheitlicher Zugriff auf alle PDVM-Tabellen
    
    Standard-Struktur aller Tabellen (außer sys_benutzer):
    - uid: UUID (Primary Key)
    - daten: JSONB (Hauptdaten mit Gruppe → Feld → Wert Struktur)
    - name: TEXT (Anzeigename)
    - historisch: INTEGER (0 = aktuell, 1 = historische Daten)
    - source_hash: TEXT (Änderungsverfolgung)
    - sec_id: UUID (Security Profile)
    - gilt_bis: TEXT (Gültigkeitsdatum im PDVM-Format)
    - created_at: TIMESTAMP
    - modified_at: TIMESTAMP
    - daten_backup: JSONB
    
    Datenbank-Routing:
    - auth.db: sys_benutzer, sys_mandanten
    - system.db: sys_beschreibungen, sys_dropdowndaten, sys_menudaten, 
                 sys_dialogdaten, sys_viewdaten, sys_framedaten, sys_layout
    - mandant.db: sys_anwendungsdaten, sys_systemsteuerung, Fachdaten
    """
    
    def __init__(self, table_name: str, system_pool: Optional[asyncpg.Pool] = None, mandant_pool: Optional[asyncpg.Pool] = None):
        """
        Initialisiert PdvmDatabase für eine bestimmte Tabelle
        
        Args:
            table_name: Name der Tabelle (z.B. 'sys_systemsteuerung', 'persondaten')
            system_pool: Pool für pdvm_system Datenbank (REQUIRED for system tables)
            mandant_pool: Pool für mandanten Datenbank (REQUIRED for mandant tables)
        """
        self.table_name = table_name
        self.db_name = self._find_database(table_name)
        self._system_pool = system_pool
        self._mandant_pool = mandant_pool
    
    def _find_database(self, table_name: str) -> str:
        """
        Ermittelt Datenbank anhand Tabellenname
        
        Returns:
            'auth', 'system' oder 'mandant'
        """
        # AUTH: Benutzer und Mandanten (zentral, einmalig)
        if table_name in ["sys_benutzer", "sys_mandanten"]:
            return "auth"
        
        # SYSTEM: Strukturdaten und Layouts (mandantenübergreifend)
        elif table_name in [
            "sys_beschreibungen",
            "sys_ext_table",
            "sys_dropdowndaten",
            "sys_menudaten",
            "sys_dialogdaten",
            "sys_viewdaten",
            "sys_framedaten",
            "sys_layout",
            "sys_systemdaten",
            "sys_control_dict",
            "sys_control_dict_audit",
        ]:
            return "system"
        
        # MANDANT: Anwendungsdaten und Fachdaten (pro Mandant)
        else:
            return "mandant"

    _AUDIT_TABLE_MAP = {
        "sys_control_dict": "sys_control_dict_audit",
        "sys_contr_dict_man": "sys_contr_dict_man_audit",
    }

    _GUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")

    @staticmethod
    def _is_guid_key(value: str) -> bool:
        if not value:
            return False
        return bool(PdvmDatabase._GUID_RE.match(str(value).strip()))

    @staticmethod
    def _collect_guid_field_values(
        data: Any,
        out: Optional[Dict[str, Any]] = None,
        group: Optional[str] = None,
    ) -> Dict[str, Any]:
        if out is None:
            out = {}
        if isinstance(data, dict):
            for key, value in data.items():
                if PdvmDatabase._is_guid_key(key):
                    group_name = group or "ROOT"
                    entry = out.setdefault(str(key).strip().lower(), {})
                    entry[group_name] = {str(key): value}
                next_group = group
                if group is None and isinstance(key, str) and not PdvmDatabase._is_guid_key(key):
                    next_group = key
                if isinstance(value, dict) or isinstance(value, list):
                    PdvmDatabase._collect_guid_field_values(value, out, next_group)
        elif isinstance(data, list):
            for item in data:
                PdvmDatabase._collect_guid_field_values(item, out, group)
        return out

    def _get_audit_table(self) -> Optional[str]:
        return self._AUDIT_TABLE_MAP.get(self.table_name)

    async def _write_audit_entry(
        self,
        *,
        audit_table: str,
        feld_guid: str,
        payload_after: Any,
    ) -> None:
        audit_db = PdvmDatabase(audit_table, system_pool=self._system_pool, mandant_pool=self._mandant_pool)
        audit_uid = uuid.UUID(feld_guid)
        existing = await audit_db.get_by_uid(audit_uid)
        if existing:
            await audit_db.update(uid=audit_uid, daten=payload_after, historisch=1)
        else:
            await audit_db.create(uid=audit_uid, daten=payload_after, name="", historisch=1)

    @staticmethod
    async def _load_control_template_defaults(
        *,
        modul_type: str,
        system_pool: Optional[asyncpg.Pool],
        mandant_pool: Optional[asyncpg.Pool],
    ) -> Dict[str, Any]:
        modul_norm = str(modul_type or "").strip().lower()
        if not modul_norm:
            return {}

        template_uid = uuid.UUID("55555555-5555-5555-5555-555555555555")
        db = PdvmDatabase("sys_control_dict", system_pool=system_pool, mandant_pool=mandant_pool)
        template_row = await db.get_by_uid(template_uid)
        if not template_row:
            return {}

        template_daten = template_row.get("daten") or {}
        if isinstance(template_daten, str):
            try:
                template_daten = json.loads(template_daten)
            except Exception:
                template_daten = {}
        if not isinstance(template_daten, dict):
            return {}

        defaults: Dict[str, Any] = {}

        templates = template_daten.get("TEMPLATES")
        if isinstance(templates, dict):
            tpl_control = templates.get("CONTROL")
            if isinstance(tpl_control, dict):
                defaults.update(copy.deepcopy(tpl_control))

        modul_map = template_daten.get("MODUL")
        if isinstance(modul_map, dict):
            ci_map = {str(k).strip().lower(): k for k in modul_map.keys()}
            real_key = ci_map.get(modul_norm)
            if real_key is not None:
                modul_defaults = modul_map.get(real_key)
                if isinstance(modul_defaults, dict):
                    defaults.update(copy.deepcopy(modul_defaults))

        defaults["modul_type"] = modul_norm
        return defaults

    @staticmethod
    async def _resolve_control_data_with_templates(
        *,
        control_data: Dict[str, Any],
        system_pool: Optional[asyncpg.Pool],
        mandant_pool: Optional[asyncpg.Pool],
    ) -> Dict[str, Any]:
        if not isinstance(control_data, dict):
            return {}

        modul_type = str(control_data.get("modul_type") or "").strip().lower()
        if not modul_type:
            return dict(control_data)

        defaults = await PdvmDatabase._load_control_template_defaults(
            modul_type=modul_type,
            system_pool=system_pool,
            mandant_pool=mandant_pool,
        )
        if not defaults:
            return dict(control_data)

        resolved = copy.deepcopy(defaults)
        resolved.update(control_data)
        return resolved

    @staticmethod
    async def load_control_definition(
        feld_guid: uuid.UUID,
        *,
        system_pool: Optional[asyncpg.Pool],
        mandant_pool: Optional[asyncpg.Pool],
    ) -> Optional[Dict[str, Any]]:
        """Lädt Control-Definition (Mandant zuerst, dann System)."""
        mandant_db = PdvmDatabase("sys_contr_dict_man", system_pool=system_pool, mandant_pool=mandant_pool)
        row = await mandant_db.get_by_uid(feld_guid)
        if not row:
            system_db = PdvmDatabase("sys_control_dict", system_pool=system_pool, mandant_pool=mandant_pool)
            row = await system_db.get_by_uid(feld_guid)

        if not row:
            return None

        out = dict(row)
        daten = out.get("daten") or {}
        if isinstance(daten, str):
            try:
                daten = json.loads(daten)
            except Exception:
                daten = {}

        if isinstance(daten, dict):
            out["daten"] = await PdvmDatabase._resolve_control_data_with_templates(
                control_data=daten,
                system_pool=system_pool,
                mandant_pool=mandant_pool,
            )
        else:
            out["daten"] = {}

        return out
    
    def get_pool(self) -> asyncpg.Pool:
        """Holt den richtigen Connection Pool für diese Tabelle"""
        if self.db_name == "auth":
            if DatabasePool._pool_auth is None:
                raise RuntimeError("Auth pool not initialized")
            return DatabasePool._pool_auth
        
        elif self.db_name == "system":
            if self._system_pool is None:
                raise RuntimeError(
                    f"System pool required for table '{self.table_name}'. "
                    f"Must be provided via PdvmCentralSystemsteuerung."
                )
            return self._system_pool
        
        else:  # mandant
            if self._mandant_pool is None:
                raise RuntimeError(
                    f"Mandant pool required for table '{self.table_name}'. "
                    f"Must be provided via PdvmCentralSystemsteuerung."
                )
            return self._mandant_pool
    
    async def get_by_uid(self, uid: uuid.UUID) -> Optional[Dict[str, Any]]:
        """
        Lädt einen vollständigen Datensatz anhand der UID
        
        Args:
            uid: UUID des Datensatzes
            
        Returns:
            Dict mit allen Spalten oder None wenn nicht gefunden
        """
        pool = self.get_pool()
        async with pool.acquire() as conn:
            # Nur die Spalten lesen die garantiert existieren
            # daten_backup wird bei Wartung hinzugefügt falls fehlend
            row = await conn.fetchrow(f"""
                SELECT uid, daten, name, historisch, sec_id, gilt_bis, 
                       created_at, modified_at
                FROM {self.table_name}
                WHERE uid = $1
            """, uid)
            
            if not row:
                return None
            
            result = dict(row)
            
            # Parse JSONB fields (asyncpg gibt als String zurück)
            if result['daten'] and isinstance(result['daten'], str):
                result['daten'] = json.loads(result['daten'])
            
            return result
    
    async def get_row(self, uid: uuid.UUID) -> Optional[Dict[str, Any]]:
        """
        Lädt Datensatz mit den wichtigsten Feldern für CentralDatabase
        
        Returns:
            {'uid', 'daten', 'historisch', 'name'} oder None
        """
        row = await self.get_by_uid(uid)
        if not row:
            return None
        
        return {
            'uid': row['uid'],
            'daten': row['daten'],
            'historisch': row['historisch'],
            'name': row['name']
        }
    
    async def get_all(
        self,
        where: str = "",
        params: tuple = (),
        order_by: str = "created_at DESC",
        limit: Optional[int] = None,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """
        Lädt alle Datensätze (mit optionaler WHERE-Klausel)
        
        Args:
            where: WHERE-Bedingung (z.B. "historisch = 0")
            params: Parameter für WHERE ($1, $2, ...)
            order_by: ORDER BY Klausel
            limit: Optionales LIMIT (Performance-Schutz)
            
        Returns:
            Liste von Datensätzen
        """
        pool = self.get_pool()
        async with pool.acquire() as conn:
            query = f"""
                SELECT uid, daten, name, historisch, sec_id, gilt_bis,
                       created_at, modified_at
                FROM {self.table_name}
            """
            
            if where:
                query += f" WHERE {where}"
            
            query += f" ORDER BY {order_by}"

            if limit is not None:
                try:
                    limit_int = int(limit)
                except Exception:
                    raise ValueError("limit must be an int")
                if limit_int <= 0:
                    raise ValueError("limit must be > 0")
                query += f" LIMIT {limit_int}"

            if offset:
                try:
                    offset_int = int(offset)
                except Exception:
                    raise ValueError("offset must be an int")
                if offset_int < 0:
                    raise ValueError("offset must be >= 0")
                if limit is None:
                    # OFFSET ohne LIMIT ist erlaubt, aber kann sehr teuer sein.
                    pass
                query += f" OFFSET {offset_int}"
            
            rows = await conn.fetch(query, *params)
            
            result = []
            for row in rows:
                row_dict = dict(row)
                # Parse JSONB
                if row_dict['daten'] and isinstance(row_dict['daten'], str):
                    row_dict['daten'] = json.loads(row_dict['daten'])
                result.append(row_dict)
            
            return result

    async def get_modified_since(
        self,
        modified_after: datetime,
        where: str = "",
        params: tuple = (),
        order_by: str = "modified_at ASC",
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Lädt Datensätze, die nach einem bestimmten Zeitpunkt geändert wurden.

        Ziel: Delta-Refresh für Session-Cache (statt Vollscan).
        """
        if not isinstance(modified_after, datetime):
            raise ValueError("modified_after must be a datetime")

        pool = self.get_pool()
        async with pool.acquire() as conn:
            # Parameter-Reihenfolge: existing params + modified_after
            # WHERE-Klausel sicher zusammensetzen
            clauses: List[str] = []
            if where:
                clauses.append(f"({where})")

            # modified_at > $n
            clauses.append(f"modified_at > ${len(params) + 1}")
            full_where = " AND ".join(clauses)

            query = f"""
                SELECT uid, daten, name, historisch, sec_id, gilt_bis,
                       created_at, modified_at
                FROM {self.table_name}
                WHERE {full_where}
                ORDER BY {order_by}
            """

            if limit is not None:
                try:
                    limit_int = int(limit)
                except Exception:
                    raise ValueError("limit must be an int")
                if limit_int <= 0:
                    raise ValueError("limit must be > 0")
                query += f" LIMIT {limit_int}"

            rows = await conn.fetch(query, *(params + (modified_after,)))

            result: List[Dict[str, Any]] = []
            for row in rows:
                row_dict = dict(row)
                if row_dict.get('daten') and isinstance(row_dict['daten'], str):
                    row_dict['daten'] = json.loads(row_dict['daten'])
                result.append(row_dict)
            return result
    
    async def create(
        self, 
        uid: uuid.UUID, 
        daten: Dict, 
        name: str = "", 
        historisch: int = 0, 
        sec_id: Optional[uuid.UUID] = None
    ) -> Dict[str, Any]:
        """
        Erstellt einen neuen Datensatz
        
        Args:
            uid: UUID des Datensatzes
            daten: JSONB-Daten (als dict)
            name: Anzeigename
            historisch: 0 = aktuell, 1 = historische Daten
            sec_id: Security Profile UUID
            
        Returns:
            Erstellter Datensatz
        """
        pool = self.get_pool()
        async with pool.acquire() as conn:
            # gilt_bis wird automatisch auf '9999-12-31 23:59:59' gesetzt (DB-Default)
            await conn.execute(f"""
                INSERT INTO {self.table_name} 
                (uid, daten, name, historisch, sec_id)
                VALUES ($1, $2, $3, $4, $5)
            """, uid, json.dumps(daten), name, historisch, sec_id)
            
            return await self.get_by_uid(uid)
    
    async def update(
        self, 
        uid: uuid.UUID, 
        daten: Dict, 
        name: Optional[str] = None,
        historisch: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Aktualisiert einen Datensatz
        
        Args:
            uid: UUID des Datensatzes
            daten: Neue JSONB-Daten (als dict)
            name: Optional neuer Name
            historisch: Optional neuer historisch-Wert
            
        Returns:
            Aktualisierter Datensatz
        """
        pool = self.get_pool()
        before_row = await self.get_by_uid(uid)
        async with pool.acquire() as conn:
            # gilt_bis wird immer auf höchstes Datum gesetzt
            if name is not None and historisch is not None:
                await conn.execute(f"""
                    UPDATE {self.table_name}
                    SET daten = $1, name = $2, historisch = $3, 
                        gilt_bis = '9999-12-31 23:59:59', modified_at = NOW()
                    WHERE uid = $4
                """, json.dumps(daten), name, historisch, uid)
            elif name is not None:
                await conn.execute(f"""
                    UPDATE {self.table_name}
                    SET daten = $1, name = $2, 
                        gilt_bis = '9999-12-31 23:59:59', modified_at = NOW()
                    WHERE uid = $3
                """, json.dumps(daten), name, uid)
            elif historisch is not None:
                await conn.execute(f"""
                    UPDATE {self.table_name}
                    SET daten = $1, historisch = $2, 
                        gilt_bis = '9999-12-31 23:59:59', modified_at = NOW()
                    WHERE uid = $3
                """, json.dumps(daten), historisch, uid)
            else:
                await conn.execute(f"""
                    UPDATE {self.table_name}
                    SET daten = $1, 
                        gilt_bis = '9999-12-31 23:59:59', modified_at = NOW()
                    WHERE uid = $2
                """, json.dumps(daten), uid)
            
            updated = await self.get_by_uid(uid)

        audit_table = self._get_audit_table()
        if audit_table and updated:
            after_guid_values = self._collect_guid_field_values(updated.get("daten"))
            for key, payload in after_guid_values.items():
                await self._write_audit_entry(
                    audit_table=audit_table,
                    feld_guid=key,
                    payload_after=payload,
                )

        return updated
    
    async def delete(self, uid: uuid.UUID, soft_delete: bool = True) -> bool:
        """
        Löscht einen Datensatz (soft oder hard)
        
        Args:
            uid: UUID des Datensatzes
            soft_delete: True = markiere als historisch, False = echtes DELETE
            
        Returns:
            True wenn erfolgreich
        """
        pool = self.get_pool()
        async with pool.acquire() as conn:
            if soft_delete:
                result = await conn.execute(f"""
                    UPDATE {self.table_name}
                    SET historisch = 1, modified_at = NOW()
                    WHERE uid = $1
                """, uid)
            else:
                result = await conn.execute(f"""
                    DELETE FROM {self.table_name}
                    WHERE uid = $1
                """, uid)
            
            return "1" in result
    
    async def exists(self, uid: uuid.UUID) -> bool:
        """
        Prüft ob Datensatz existiert
        
        Returns:
            True wenn vorhanden
        """
        pool = self.get_pool()
        async with pool.acquire() as conn:
            result = await conn.fetchval(f"""
                SELECT COUNT(*) FROM {self.table_name}
                WHERE uid = $1
            """, uid)
            return result > 0
    
    @staticmethod
    async def ensure_mandant_tables(mandant_id: str, mandant_db_url: str, mandant_record: dict):
        """
        Prüft und erstellt fehlende Tabellen für einen Mandanten beim Login
        
        Verwendet direkte Connection statt DatabasePool.
        Lädt CONFIG.SYS_TABLES und CONFIG.FEATURES aus mandant_record
        und erstellt alle fehlenden Tabellen in der Mandanten-Datenbank.
        
        Args:
            mandant_id: UUID des Mandanten
            mandant_db_url: Connection-URL zur Mandanten-Datenbank
            mandant_record: Mandanten-Datensatz aus sys_mandanten (mit daten JSONB)
        """
        import logging
        import asyncpg
        logger = logging.getLogger(__name__)
        
        # 1. Tabellen-Liste aus Mandanten-Config laden
        daten = mandant_record.get("daten", {})
        config = daten.get("CONFIG", {})
        sys_tables = config.get("SYS_TABLES", [])
        features = config.get("FEATURES", [])
        
        if not isinstance(sys_tables, list):
            sys_tables = []
        if not isinstance(features, list):
            features = []
        
        mandatory_tables = [
            "sys_anwendungsdaten",
            "sys_systemsteuerung",
            "sys_security",
            "sys_error_log",
            "sys_error_acknowledgments",
            "sys_contr_dict_man",
            "sys_contr_dict_man_audit",
        ]

        all_tables = list(dict.fromkeys(mandatory_tables + sys_tables + features))
        
        if not all_tables:
            logger.info(f"Keine Tabellen für Mandant {mandant_id} konfiguriert")
            return
        
        # 2. Direkte Connection zur Mandanten-DB (mit Retry)
        max_retries = 3
        retry_delay = 0.5
        conn = None
        
        for attempt in range(max_retries):
            try:
                conn = await asyncpg.connect(mandant_db_url, timeout=10)
                break  # Erfolgreich verbunden
            except Exception as e:
                if attempt < max_retries - 1:
                    logger.warning(f"⚠️ Connection-Versuch {attempt + 1} fehlgeschlagen: {e}, retry in {retry_delay}s...")
                    await asyncio.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                else:
                    logger.error(f"❌ Alle {max_retries} Connection-Versuche fehlgeschlagen")
                    raise
        
        if not conn:
            raise Exception("Konnte keine Connection zur Mandanten-DB herstellen")
        
        try:
            # 3. Existierende Tabellen ermitteln
            existing_tables = await conn.fetch("""
                SELECT tablename 
                FROM pg_tables 
                WHERE schemaname = 'public'
            """)
            existing_table_names = {row['tablename'] for row in existing_tables}
            
            # 4. Fehlende Tabellen erstellen
            created_count = 0
            for table_name in all_tables:
                if table_name in existing_table_names:
                    logger.info(f"✓ Tabelle '{table_name}' existiert bereits")
                    continue
                
                try:
                    # Standard PDVM-Tabellenschema (einheitlich für ALLE Tabellen)
                    columns = ', '.join([f"{col} {definition}" for col, definition in PDVM_TABLE_COLUMNS.items()])
                    
                    create_sql = f"""
                    CREATE TABLE {table_name} (
                        {columns}
                    )
                    """
                    
                    await conn.execute(create_sql)
                    
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
                    
                    created_count += 1
                    logger.info(f"✅ Tabelle '{table_name}' mit Standard-Schema erstellt")
                
                except Exception as e:
                    logger.error(f"❌ Fehler beim Erstellen von '{table_name}': {e}")
            
            if created_count > 0:
                logger.info(f"🎉 {created_count} Tabelle(n) für Mandant '{mandant_record['name']}' erstellt")
            else:
                logger.info(f"✓ Alle Tabellen für Mandant '{mandant_record['name']}' bereits vorhanden")
        
        finally:
            await conn.close()

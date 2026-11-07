"""
PDVM Database Manager
Zentraler Datenbankmanager fÃ¼r alle PDVM-Tabellen (auÃŸer asy_benutzer Sonderfall)

Nach Desktop-Vorbild: pdvm_datenbank.py
- Einheitlicher Zugriff auf alle Tabellen
- JSONB-basierte Datenstruktur mit uid + daten
- UnterstÃ¼tzt System-, Auth- und Mandanten-Datenbanken
- Historie-Support fÃ¼r zeitbasierte Daten
"""
import uuid
import json
import asyncio
import re
import time
import copy
import logging
from app.core.pdvm_datetime import SENTINEL_MAX, datetime_to_pdvm, pdvm_to_datetime, pdvm_to_str
from app.core.feld_aenderungshistorie_service import FieldChangeHistoryService
from typing import Dict, List, Optional, Any
from datetime import datetime
import asyncpg
from app.core.database import DatabasePool
from app.core.pdvm_table_schema import PDVM_TABLE_COLUMNS, PDVM_TABLE_INDEXES
from app.core import pdvm_mandant_provisioning

logger = logging.getLogger(__name__)


class PdvmDatabase:
    """
    PDVM Datenbankmanager - Einheitlicher Zugriff auf alle PDVM-Tabellen
    
    Standard-Struktur aller Tabellen (auÃŸer asy_benutzer):
    - uid: UUID (Primary Key)
    - daten: JSONB (Hauptdaten mit Gruppe â†’ Feld â†’ Wert Struktur)
    - name: TEXT (Anzeigename)
    - historisch: INTEGER (0 = aktuell, 1 = historische Daten)
    - source_hash: TEXT (Ã„nderungsverfolgung)
    - sec_id: UUID (Security Profile)
    - gilt_bis: TEXT (GÃ¼ltigkeitsdatum im PDVM-Format)
    - created_at: TIMESTAMP
    - modified_at: TIMESTAMP
    - backup_daten: JSONB
    
    Datenbank-Routing (praefixbasiert, verbindlich):
    - auth.db: asy_*
    - system.db (pdvm_system): sys_*
    - mandant.db: msy_* sowie applikationsspezifische Praefixe (<prefix>_*)
    - Tabellen ohne '_' sind ungueltig
    """

    _SYSTEM_PREFIX = "sys_"
    _SYSTEM_DEV_PREFIX = "dev_"
    _AUTH_PREFIX = "asy_"
    _MANDANT_SYSTEM_PREFIX = "msy_"
    # Tabellennamen fliessen in SQL-Statements; nur einfache Bezeichner zulassen.
    _TABLE_IDENTIFIER_RE = re.compile(r"^[a-z_][a-z0-9_]*$")
    
    def __init__(self, table_name: str, system_pool: Optional[asyncpg.Pool] = None, mandant_pool: Optional[asyncpg.Pool] = None):
        """
        Initialisiert PdvmDatabase fÃ¼r eine bestimmte Tabelle
        
        Args:
            table_name: Name der Tabelle (z.B. 'sys_systemsteuerung', 'persondaten')
            system_pool: Pool fÃ¼r pdvm_system Datenbank (REQUIRED for system tables)
            mandant_pool: Pool fÃ¼r mandanten Datenbank (REQUIRED for mandant tables)
        """
        self.table_name = table_name
        self.db_name = self._find_database(table_name)
        self._system_pool = system_pool
        self._mandant_pool = mandant_pool
    
    def _find_database(self, table_name: str) -> str:
        """
        Ermittelt Datenbank praefixbasiert anhand Tabellenname.

        Routing-Regeln:
        - asy_* -> auth
        - sys_* -> system
        - msy_* -> mandant
        - <app>_* -> mandant
        - ohne '_' -> expliziter Fehler
        
        Returns:
            'auth', 'system' oder 'mandant'
        """
        table = str(table_name or "").strip().lower()
        if not table:
            raise ValueError("Leerer Tabellenname ist nicht erlaubt")

        if not self._TABLE_IDENTIFIER_RE.match(table):
            raise ValueError(f"Ungueltiger Tabellenname: {table_name!r}")

        if "_" not in table:
            logger.error(f"âŒ Tabellennamen ohne Praefix sind unzulaessig: table={table}")
            raise ValueError(f"Tabellenname ohne Praefix ist unzulaessig: {table}")

        prefix = table.split("_", 1)[0] + "_"

        if prefix == self._AUTH_PREFIX:
            return "auth"
        if prefix in {self._SYSTEM_PREFIX, self._SYSTEM_DEV_PREFIX}:
            return "system"
        if prefix == self._MANDANT_SYSTEM_PREFIX:
            return "mandant"

        # App-spezifische Praefixe (z.B. crm_, hrm_, pps_) laufen in Mandanten-DB.
        logger.info(f"ðŸ”Ž App-Praefix erkannt, route nach mandant: table={table} prefix={prefix}")
        return "mandant"

    _AUDIT_TABLE_MAP = {}

    # Kurzlebiger Cache fuer die reservierten Control-Templates (555/666 in sys_control_dict).
    # Die Templates werden fuer jedes Control gebraucht (vorher 1-2 Abfragen je Control).
    _TEMPLATE_CACHE_TTL_SECONDS = 30.0
    _template_cache: Dict[tuple, tuple] = {}

    @staticmethod
    def _template_cache_get(db: "PdvmDatabase", key: tuple) -> Optional[Dict[str, Any]]:
        pool = db.get_pool()
        entry = PdvmDatabase._template_cache.get((id(pool),) + key)
        if entry is None:
            return None
        expires, cached_pool, value = entry
        if cached_pool is not pool or time.monotonic() > expires:
            PdvmDatabase._template_cache.pop((id(pool),) + key, None)
            return None
        return copy.deepcopy(value)

    @staticmethod
    def _template_cache_put(db: "PdvmDatabase", key: tuple, value: Dict[str, Any]) -> None:
        pool = db.get_pool()
        PdvmDatabase._template_cache[(id(pool),) + key] = (
            time.monotonic() + PdvmDatabase._TEMPLATE_CACHE_TTL_SECONDS,
            pool,
            copy.deepcopy(value),
        )

    @staticmethod
    def invalidate_template_cache() -> None:
        PdvmDatabase._template_cache.clear()

    def _invalidate_caches_after_write(self) -> None:
        # Vor dem Schreiben leeren: auch bei Fehlern bleibt so kein veralteter Stand im Cache.
        if str(self.table_name or "").strip().lower() == "sys_control_dict":
            PdvmDatabase.invalidate_template_cache()

    _GUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")

    @staticmethod
    def _normalize_storage_scope(storage_scope: Optional[str]) -> str:
        scope = str(storage_scope or "live").strip().lower() or "live"
        if scope not in {"live", "draft"}:
            raise ValueError("storage_scope muss 'live' oder 'draft' sein")
        return scope

    @staticmethod
    def _validate_storage_scope_contract(*, storage_scope: Optional[str], draft_guid: Optional[Any]) -> tuple[str, Optional[uuid.UUID]]:
        scope = PdvmDatabase._normalize_storage_scope(storage_scope)
        draft_guid_uuid: Optional[uuid.UUID] = None
        if draft_guid is not None and str(draft_guid).strip() != "":
            try:
                draft_guid_uuid = uuid.UUID(str(draft_guid))
            except Exception:
                raise ValueError("draft_guid ist ungueltig")
        if scope == "draft" and draft_guid_uuid is None:
            raise ValueError("Bei storage_scope='draft' ist draft_guid verpflichtend")
        return scope, draft_guid_uuid

    @staticmethod
    def _inject_root_meta_fields(row_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Projiziert Spaltenwerte kompatibel in daten.ROOT als SELF_* Felder."""
        if not isinstance(row_dict, dict):
            return row_dict

        daten = row_dict.get("daten")
        if not isinstance(daten, dict):
            daten = {}

        root = daten.get("ROOT") if isinstance(daten.get("ROOT"), dict) else {}
        root = dict(root)

        uid_value = row_dict.get("uid")
        link_uid_value = row_dict.get("link_uid") or uid_value
        created_at_value = row_dict.get("created_at")
        modified_at_value = row_dict.get("modified_at")
        gilt_bis_value = row_dict.get("gilt_bis")

        if uid_value is not None:
            root["SELF_GUID"] = str(uid_value)
        if link_uid_value is not None:
            root["SELF_LINK_UID"] = str(link_uid_value)

        def _to_pdvm_str(dt_val: Any) -> Optional[str]:
            if dt_val is None:
                return None
            try:
                return pdvm_to_str(datetime_to_pdvm(dt_val))
            except Exception:
                return str(dt_val)

        if created_at_value is not None:
            root["SELF_CREATED_AT"] = _to_pdvm_str(created_at_value)
        if modified_at_value is not None:
            root["SELF_MODIFIED_AT"] = _to_pdvm_str(modified_at_value)
        if gilt_bis_value is not None:
            root["SELF_GILT_BIS"] = _to_pdvm_str(gilt_bis_value)

        daten["ROOT"] = root
        row_dict["daten"] = daten
        return row_dict

    @staticmethod
    async def _persist_synced_root_meta_fields(
        conn,
        *,
        table_name: str,
        row_dict: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Spiegelt ROOT.SELF_* aus Row-Metadaten und persistiert daten einmalig."""
        projected = PdvmDatabase._inject_root_meta_fields(dict(row_dict or {}))
        uid_value = projected.get("uid")
        if uid_value is None:
            return projected

        await conn.execute(
            f"""
            UPDATE {table_name}
            SET daten = $2
            WHERE uid = $1
            """,
            uid_value,
            json.dumps(projected.get("daten") or {}),
        )

        return projected

    @staticmethod
    def _extract_self_name_for_name_column(daten: Any) -> Optional[str]:
        """Liest ROOT.SELF_NAME case-insensitive fuer die name-Spalte."""
        if not isinstance(daten, dict):
            return None
        root = daten.get("ROOT") if isinstance(daten.get("ROOT"), dict) else None
        if not isinstance(root, dict):
            return None

        ci_map = {str(k).strip().lower(): k for k in root.keys()}
        self_name_key = ci_map.get("self_name")
        if self_name_key is None:
            return None

        value = root.get(self_name_key)
        if value is None:
            return None

        name_norm = str(value).strip()
        return name_norm or None

    @staticmethod
    def _extract_self_gilt_bis_for_column(daten: Any) -> Optional[datetime]:
        """Liest ROOT.SELF_GILT_BIS case-insensitive und konvertiert nach datetime."""
        if not isinstance(daten, dict):
            return None
        root = daten.get("ROOT") if isinstance(daten.get("ROOT"), dict) else None
        if not isinstance(root, dict):
            return None

        ci_map = {str(k).strip().lower(): k for k in root.keys()}
        self_gilt_bis_key = ci_map.get("self_gilt_bis")
        if self_gilt_bis_key is None:
            return None

        raw_value = root.get(self_gilt_bis_key)
        if raw_value is None:
            return None

        text = str(raw_value).strip()
        if not text:
            return None

        try:
            return pdvm_to_datetime(float(text))
        except Exception:
            pass

        try:
            return datetime.fromisoformat(text)
        except Exception:
            return None

    @staticmethod
    def _strip_runtime_root_meta_fields(daten: Any) -> Any:
        """Entfernt nur zur Laufzeit injizierte ROOT-SELF_* Metafelder.

        Wichtig für Snapshot-Compare (Optimistic Lock):
        - get_by_uid() injiziert SELF_* aus Tabellen-Spalten in daten.ROOT
        - Der DB-Vergleich in update() nutzt rohe JSONB-Daten ohne diese Injektion
        - Ohne Strip entstehen False-Positive-Konflikte.
        """
        if not isinstance(daten, dict):
            return daten

        out = copy.deepcopy(daten)
        root = out.get("ROOT")
        if not isinstance(root, dict):
            return out

        root_out = dict(root)
        for key in (
            "SELF_GUID",
            "SELF_LINK_UID",
            "SELF_CREATED_AT",
            "SELF_MODIFIED_AT",
            "SELF_GILT_BIS",
            # Legacy-/Kompatibilitätsfelder ebenfalls ignorieren.
            "CREATED_AT",
            "MODIFIED_AT",
            "GILT_BIS",
        ):
            root_out.pop(key, None)

        out["ROOT"] = root_out
        return out

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
        cache_key = ("defaults", modul_norm)
        cached = PdvmDatabase._template_cache_get(db, cache_key)
        if cached is not None:
            return cached
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
        PdvmDatabase._template_cache_put(db, cache_key, defaults)
        return defaults

    @staticmethod
    async def _load_control_base_template(
        *,
        system_pool: Optional[asyncpg.Pool],
        mandant_pool: Optional[asyncpg.Pool],
    ) -> Dict[str, Any]:
        template_uid = uuid.UUID("66666666-6666-6666-6666-666666666666")
        db = PdvmDatabase("sys_control_dict", system_pool=system_pool, mandant_pool=mandant_pool)
        cache_key = ("base",)
        cached = PdvmDatabase._template_cache_get(db, cache_key)
        if cached is not None:
            return cached
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
        PdvmDatabase._template_cache_put(db, cache_key, template_daten)
        return template_daten

    @staticmethod
    async def _resolve_control_data_with_templates(
        *,
        control_data: Dict[str, Any],
        system_pool: Optional[asyncpg.Pool],
        mandant_pool: Optional[asyncpg.Pool],
    ) -> Dict[str, Any]:
        if not isinstance(control_data, dict):
            return {}

        # Legacy/Standard-Format: verschachtelte ROOT+CONTROL-Struktur.
        # Diese wird immer auf 666...-Templatebasis ergÃ¤nzt, damit fehlende
        # Standard-Keys (z.B. in CONTROL) konsistent vorhanden sind.
        has_root = isinstance(control_data.get("ROOT"), dict)
        has_control = isinstance(control_data.get("CONTROL"), dict)
        root_in = control_data.get("ROOT") if has_root else {}
        control_in = control_data.get("CONTROL") if has_control else {}
        if has_root or has_control:
            base = await PdvmDatabase._load_control_base_template(
                system_pool=system_pool,
                mandant_pool=mandant_pool,
            )
            base_root = base.get("ROOT") if isinstance(base.get("ROOT"), dict) else {}
            base_control = base.get("CONTROL") if isinstance(base.get("CONTROL"), dict) else {}

            resolved_nested = copy.deepcopy(control_data)

            merged_root = copy.deepcopy(base_root)
            if isinstance(root_in, dict):
                merged_root.update(root_in)
            resolved_nested["ROOT"] = merged_root

            merged_control = copy.deepcopy(base_control)
            if isinstance(control_in, dict):
                merged_control.update(control_in)
            resolved_nested["CONTROL"] = merged_control

            return resolved_nested

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
    async def _finalize_control_row(
        row: Dict[str, Any],
        *,
        system_pool: Optional[asyncpg.Pool],
        mandant_pool: Optional[asyncpg.Pool],
    ) -> Dict[str, Any]:
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

    @staticmethod
    async def load_control_definition(
        feld_guid: uuid.UUID,
        *,
        system_pool: Optional[asyncpg.Pool],
        mandant_pool: Optional[asyncpg.Pool],
    ) -> Optional[Dict[str, Any]]:
        """Laedt Control-Definition aus der zentralen sys_control_dict."""
        system_db = PdvmDatabase("sys_control_dict", system_pool=system_pool, mandant_pool=mandant_pool)
        row = await system_db.get_by_uid(feld_guid)

        if not row:
            return None

        return await PdvmDatabase._finalize_control_row(
            row, system_pool=system_pool, mandant_pool=mandant_pool
        )

    @staticmethod
    async def load_control_definitions(
        feld_guids: List[uuid.UUID],
        *,
        system_pool: Optional[asyncpg.Pool],
        mandant_pool: Optional[asyncpg.Pool],
    ) -> Dict[uuid.UUID, Dict[str, Any]]:
        """Laedt mehrere Control-Definitionen mit einer Abfrage (statt N Einzelabfragen).

        Liefert je gefundener UID dasselbe Ergebnis wie load_control_definition.
        """
        unique = list(dict.fromkeys(feld_guids))
        if not unique:
            return {}

        system_db = PdvmDatabase("sys_control_dict", system_pool=system_pool, mandant_pool=mandant_pool)
        pool = system_db.get_pool()
        async with pool.acquire() as conn:
            try:
                rows = await conn.fetch(
                    """
                    SELECT uid, link_uid, daten, name, historisch, sec_id, gilt_bis, created_at, modified_at
                    FROM sys_control_dict
                    WHERE uid = ANY($1::uuid[])
                    """,
                    unique,
                )
            except asyncpg.UndefinedColumnError:
                rows = await conn.fetch(
                    """
                    SELECT uid, daten, name, historisch, sec_id, gilt_bis, created_at, modified_at
                    FROM sys_control_dict
                    WHERE uid = ANY($1::uuid[])
                    """,
                    unique,
                )

        result: Dict[uuid.UUID, Dict[str, Any]] = {}
        for raw in rows:
            row = dict(raw)
            if row.get("daten") and isinstance(row["daten"], str):
                row["daten"] = json.loads(row["daten"])
            row = system_db._inject_root_meta_fields(row)
            result[row["uid"]] = await PdvmDatabase._finalize_control_row(
                row, system_pool=system_pool, mandant_pool=mandant_pool
            )
        return result
    
    def get_pool(self) -> asyncpg.Pool:
        """Holt den richtigen Connection Pool fÃ¼r diese Tabelle"""
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
    
    async def get_by_uid(
        self,
        uid: uuid.UUID,
        *,
        storage_scope: Optional[str] = "live",
        draft_guid: Optional[Any] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        LÃ¤dt einen vollstÃ¤ndigen Datensatz anhand der UID
        
        Args:
            uid: UUID des Datensatzes
            
        Returns:
            Dict mit allen Spalten oder None wenn nicht gefunden
        """
        scope, _ = self._validate_storage_scope_contract(storage_scope=storage_scope, draft_guid=draft_guid)
        if scope != "live":
            raise ValueError("PdvmDatabase.get_by_uid unterstÃ¼tzt aktuell nur storage_scope='live'")

        pool = self.get_pool()
        async with pool.acquire() as conn:
            # link_uid ist optional (Altstaende ohne Spalte duerfen nicht brechen).
            try:
                row = await conn.fetchrow(f"""
                    SELECT uid, link_uid, daten, name, historisch, sec_id, gilt_bis,
                           created_at, modified_at
                    FROM {self.table_name}
                    WHERE uid = $1
                """, uid)
            except Exception:
                row = await conn.fetchrow(f"""
                    SELECT uid, daten, name, historisch, sec_id, gilt_bis,
                           created_at, modified_at
                    FROM {self.table_name}
                    WHERE uid = $1
                """, uid)
            
            if not row:
                return None
            
            result = dict(row)
            
            # Parse JSONB fields (asyncpg gibt als String zurÃ¼ck)
            if result['daten'] and isinstance(result['daten'], str):
                result['daten'] = json.loads(result['daten'])

            return self._inject_root_meta_fields(result)

    async def get_by_link_uid(self, link_uid: uuid.UUID) -> Optional[Dict[str, Any]]:
        """LÃ¤dt den neuesten Datensatz anhand link_uid (fachliche IdentitÃ¤t)."""
        pool = self.get_pool()
        async with pool.acquire() as conn:
            try:
                row = await conn.fetchrow(
                    f"""
                    SELECT uid, link_uid, daten, name, historisch, sec_id, gilt_bis,
                           created_at, modified_at
                    FROM {self.table_name}
                    WHERE link_uid = $1
                    ORDER BY modified_at DESC, created_at DESC
                    LIMIT 1
                    """,
                    link_uid,
                )
            except Exception:
                # Fallback fÃ¼r AltstÃ¤nde ohne link_uid-Spalte
                row = await conn.fetchrow(
                    f"""
                    SELECT uid, daten, name, historisch, sec_id, gilt_bis,
                           created_at, modified_at
                    FROM {self.table_name}
                    WHERE uid = $1
                    """,
                    link_uid,
                )

            if not row:
                return None

            result = dict(row)
            if result.get('daten') and isinstance(result['daten'], str):
                result['daten'] = json.loads(result['daten'])
            return self._inject_root_meta_fields(result)
    
    async def get_row(self, uid: uuid.UUID) -> Optional[Dict[str, Any]]:
        """
        LÃ¤dt Datensatz mit den wichtigsten Feldern fÃ¼r CentralDatabase
        
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

    async def get_modified_at_by_uid(self, uid: uuid.UUID) -> Optional[datetime]:
        """Liest nur `modified_at` eines Datensatzes (schneller Stale-Check)."""
        pool = self.get_pool()
        async with pool.acquire() as conn:
            return await conn.fetchval(
                f"""
                SELECT modified_at
                FROM {self.table_name}
                WHERE uid = $1
                """,
                uid,
            )
    
    async def get_all(
        self,
        where: str = "",
        params: tuple = (),
        order_by: str = "created_at DESC",
        limit: Optional[int] = None,
        offset: int = 0,
        *,
        storage_scope: Optional[str] = "live",
        draft_guid: Optional[Any] = None,
    ) -> List[Dict[str, Any]]:
        """
        LÃ¤dt alle DatensÃ¤tze (mit optionaler WHERE-Klausel)
        
        Args:
            where: WHERE-Bedingung (z.B. "historisch = 0")
            params: Parameter fÃ¼r WHERE ($1, $2, ...)
            order_by: ORDER BY Klausel
            limit: Optionales LIMIT (Performance-Schutz)
            
        Returns:
            Liste von DatensÃ¤tzen
        """
        scope, _ = self._validate_storage_scope_contract(storage_scope=storage_scope, draft_guid=draft_guid)
        if scope != "live":
            raise ValueError("PdvmDatabase.get_all unterstÃ¼tzt aktuell nur storage_scope='live'")

        pool = self.get_pool()
        async with pool.acquire() as conn:
            select_columns = "uid, link_uid, daten, name, historisch, sec_id, gilt_bis, created_at, modified_at"
            query = f"""
                SELECT {select_columns}
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
            
            try:
                rows = await conn.fetch(query, *params)
            except Exception:
                select_columns = "uid, daten, name, historisch, sec_id, gilt_bis, created_at, modified_at"
                query = f"""
                    SELECT {select_columns}
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
                        pass
                    query += f" OFFSET {offset_int}"

                rows = await conn.fetch(query, *params)
            
            result = []
            for row in rows:
                row_dict = dict(row)
                # Parse JSONB
                if row_dict['daten'] and isinstance(row_dict['daten'], str):
                    row_dict['daten'] = json.loads(row_dict['daten'])
                row_dict = self._inject_root_meta_fields(row_dict)
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
        """LÃ¤dt DatensÃ¤tze, die nach einem bestimmten Zeitpunkt geÃ¤ndert wurden.

        Ziel: Delta-Refresh fÃ¼r Session-Cache (statt Vollscan).
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
                SELECT uid, link_uid, daten, name, historisch, sec_id, gilt_bis,
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

            try:
                rows = await conn.fetch(query, *(params + (modified_after,)))
            except Exception:
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
                row_dict = self._inject_root_meta_fields(row_dict)
                result.append(row_dict)
            return result
    
    async def create(
        self, 
        uid: uuid.UUID, 
        daten: Dict, 
        name: str = "", 
        historisch: int = 0, 
        sec_id: Optional[uuid.UUID] = None,
        link_uid: Optional[uuid.UUID] = None,
        *,
        storage_scope: Optional[str] = "live",
        draft_guid: Optional[Any] = None,
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
        scope, _ = self._validate_storage_scope_contract(storage_scope=storage_scope, draft_guid=draft_guid)
        if scope != "live":
            raise ValueError("PdvmDatabase.create unterstÃ¼tzt aktuell nur storage_scope='live'")

        name_from_self = self._extract_self_name_for_name_column(daten)
        effective_name = name_from_self if name_from_self is not None else name
        gilt_bis_from_self = self._extract_self_gilt_bis_for_column(daten)
        effective_gilt_bis = gilt_bis_from_self
        if effective_gilt_bis is None:
            try:
                effective_gilt_bis = pdvm_to_datetime(float(SENTINEL_MAX))
            except Exception:
                effective_gilt_bis = datetime(9999, 12, 31, 23, 59, 59)

        self._invalidate_caches_after_write()
        pool = self.get_pool()
        async with pool.acquire() as conn:
            # gilt_bis wird automatisch auf '9999-12-31 23:59:59' gesetzt (DB-Default)
            await conn.execute(f"""
                INSERT INTO {self.table_name} 
                (uid, daten, name, historisch, sec_id, gilt_bis)
                VALUES ($1, $2, $3, $4, $5, $6)
            """, uid, json.dumps(daten), effective_name, historisch, sec_id, effective_gilt_bis)

            # Kompatibel: link_uid nur setzen wenn Spalte bereits vorhanden ist.
            try:
                await conn.execute(
                    f"""
                    UPDATE {self.table_name}
                    SET link_uid = COALESCE($2, link_uid, uid)
                    WHERE uid = $1
                    """,
                    uid,
                    link_uid,
                )
            except Exception:
                # Tabellen ohne link_uid (vor Migration) dÃ¼rfen nicht brechen.
                pass

            # Unmittelbar nach Anlegen SELF_* in daten aus DB-Metadaten synchronisieren.
            try:
                created_raw = await conn.fetchrow(
                    f"""
                    SELECT uid, link_uid, daten, name, historisch, sec_id, gilt_bis,
                           created_at, modified_at
                    FROM {self.table_name}
                    WHERE uid = $1
                    """,
                    uid,
                )
            except Exception:
                created_raw = await conn.fetchrow(
                    f"""
                    SELECT uid, daten, name, historisch, sec_id, gilt_bis,
                           created_at, modified_at
                    FROM {self.table_name}
                    WHERE uid = $1
                    """,
                    uid,
                )

            if created_raw:
                created_dict = dict(created_raw)
                if created_dict.get("daten") and isinstance(created_dict.get("daten"), str):
                    created_dict["daten"] = json.loads(created_dict["daten"])
                await self._persist_synced_root_meta_fields(
                    conn,
                    table_name=self.table_name,
                    row_dict=created_dict,
                )
            
            return await self.get_by_uid(uid)

    async def rekey_uid(self, old_uid: uuid.UUID, new_uid: uuid.UUID) -> bool:
        """Ã„ndert die technische Row-UID eines Datensatzes."""
        pool = self.get_pool()
        async with pool.acquire() as conn:
            result = await conn.execute(
                f"""
                UPDATE {self.table_name}
                SET uid = $1, modified_at = NOW()
                WHERE uid = $2
                """,
                new_uid,
                old_uid,
            )
            return result != "UPDATE 0"
    
    async def update(
        self, 
        uid: uuid.UUID, 
        daten: Dict, 
        name: Optional[str] = None,
        historisch: Optional[int] = None,
        expected_snapshot_daten: Optional[Dict[str, Any]] = None,
        actor_user_uid: Optional[uuid.UUID] = None,
        actor_ip: Optional[str] = None,
        *,
        storage_scope: Optional[str] = "live",
        draft_guid: Optional[Any] = None,
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
        scope, _ = self._validate_storage_scope_contract(storage_scope=storage_scope, draft_guid=draft_guid)
        if scope != "live":
            raise ValueError("PdvmDatabase.update unterstÃ¼tzt aktuell nur storage_scope='live'")

        name_from_self = self._extract_self_name_for_name_column(daten)
        effective_name = name_from_self if name_from_self is not None else name
        effective_gilt_bis = self._extract_self_gilt_bis_for_column(daten)

        self._invalidate_caches_after_write()
        pool = self.get_pool()

        def _normalize_for_compare(value: Any) -> str:
            return json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)

        def _parse_row(row: asyncpg.Record, *, inject_root_meta: bool = True) -> Dict[str, Any]:
            row_dict = dict(row)
            if row_dict.get('daten') and isinstance(row_dict['daten'], str):
                row_dict['daten'] = json.loads(row_dict['daten'])
            if inject_root_meta:
                return self._inject_root_meta_fields(row_dict)
            return row_dict

        uid_obj = uid if isinstance(uid, uuid.UUID) else uuid.UUID(str(uid))

        async with pool.acquire() as conn:
            async with conn.transaction():
                before_raw = await conn.fetchrow(
                    f"""
                    SELECT uid, link_uid, daten, name, historisch, sec_id, gilt_bis,
                           created_at, modified_at
                    FROM {self.table_name}
                    WHERE uid = $1
                    FOR UPDATE
                    """,
                    uid_obj,
                )

                if not before_raw:
                    return None

                before_row = _parse_row(before_raw)
                before_row_plain = _parse_row(before_raw, inject_root_meta=False)

                # KonfliktprÃ¼fung (optimistisches Concurrency-Guarding)
                if expected_snapshot_daten is not None:
                    before_compare = self._strip_runtime_root_meta_fields(before_row_plain.get('daten'))
                    expected_compare = self._strip_runtime_root_meta_fields(expected_snapshot_daten)
                    if _normalize_for_compare(before_compare) != _normalize_for_compare(expected_compare):
                        raise ValueError(FieldChangeHistoryService.CONFLICT_MESSAGE)

                # Linearer Write-Builder: name/historisch/gilt_bis nur setzen, wenn Werte geliefert sind.
                set_parts: List[str] = ["daten = $1"]
                params: List[Any] = [json.dumps(daten)]

                if effective_name is not None:
                    params.append(effective_name)
                    set_parts.append(f"name = ${len(params)}")

                if historisch is not None:
                    params.append(historisch)
                    set_parts.append(f"historisch = ${len(params)}")

                if effective_gilt_bis is not None:
                    params.append(effective_gilt_bis)
                    set_parts.append(f"gilt_bis = ${len(params)}")

                set_parts.append("modified_at = NOW()")
                params.append(uid_obj)

                await conn.execute(
                    f"""
                        UPDATE {self.table_name}
                        SET {", ".join(set_parts)}
                        WHERE uid = ${len(params)}
                    """,
                    *params,
                )

                after_raw = await conn.fetchrow(
                    f"""
                    SELECT uid, link_uid, daten, name, historisch, sec_id, gilt_bis,
                           created_at, modified_at
                    FROM {self.table_name}
                    WHERE uid = $1
                    """,
                    uid_obj,
                )

                # Nach jedem Update ROOT.SELF_* in daten auf DB-Metadaten synchronisieren.
                if after_raw:
                    after_sync_source = dict(after_raw)
                    if after_sync_source.get("daten") and isinstance(after_sync_source.get("daten"), str):
                        after_sync_source["daten"] = json.loads(after_sync_source["daten"])
                    synced = await self._persist_synced_root_meta_fields(
                        conn,
                        table_name=self.table_name,
                        row_dict=after_sync_source,
                    )
                    synced_raw = {
                        "uid": synced.get("uid"),
                        "link_uid": synced.get("link_uid"),
                        "daten": synced.get("daten"),
                        "name": synced.get("name"),
                        "historisch": synced.get("historisch"),
                        "sec_id": synced.get("sec_id"),
                        "gilt_bis": synced.get("gilt_bis"),
                        "created_at": synced.get("created_at"),
                        "modified_at": synced.get("modified_at"),
                    }
                    updated = _parse_row(synced_raw, inject_root_meta=True)
                    updated_plain = _parse_row(synced_raw, inject_root_meta=False)
                else:
                    updated = None
                    updated_plain = None

                # V1 Ã„nderungsnachweis: insert-only, nur geÃ¤nderte Felder.
                # Gilt fÃ¼r alle DB-Kontexte (auth/system/mandant) und schreibt
                # jeweils lokal in die DB, in der auch die Zieltabelle liegt.
                is_history_table = await FieldChangeHistoryService.is_history_table(conn, self.table_name)
                if updated and not is_history_table:
                    await FieldChangeHistoryService.write_history_entries(
                        conn,
                        target_table=self.table_name,
                        target_uid=uid_obj,
                        old_data=before_row_plain.get("daten") or {},
                        new_data=updated_plain.get("daten") or {},
                        actor_user_uid=actor_user_uid,
                        actor_ip=actor_ip,
                    )

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
    
    async def delete(
        self,
        uid: uuid.UUID,
        soft_delete: bool = True,
        *,
        storage_scope: Optional[str] = "live",
        draft_guid: Optional[Any] = None,
    ) -> bool:
        """
        LÃ¶scht einen Datensatz (soft oder hard)
        
        Args:
            uid: UUID des Datensatzes
            soft_delete: True = markiere als historisch, False = echtes DELETE
            
        Returns:
            True wenn erfolgreich
        """
        scope, _ = self._validate_storage_scope_contract(storage_scope=storage_scope, draft_guid=draft_guid)
        if scope != "live":
            raise ValueError("PdvmDatabase.delete unterstÃ¼tzt aktuell nur storage_scope='live'")

        self._invalidate_caches_after_write()
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
        PrÃ¼ft ob Datensatz existiert
        
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
        """Delegiert an app.core.pdvm_mandant_provisioning.ensure_mandant_tables."""
        await pdvm_mandant_provisioning.ensure_mandant_tables(mandant_id, mandant_db_url, mandant_record)


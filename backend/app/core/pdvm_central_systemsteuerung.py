"""
PDVM Central Systemsteuerung
Global Configuration System fÃ¼r Benutzer- und Mandantendaten

Nach Desktop-Vorbild: pdvm_central_systemsteuerung.py
- Verwaltet sys_systemsteuerung (Benutzereinstellungen)
- Verwaltet sys_anwendungsdaten (Mandantendaten)
- Session-Cache fÃ¼r Performance
- Session-Storage: get_gcs() fÃ¼r direkten Zugriff
"""
import uuid
import json
import logging
import time
import copy
from typing import Optional, Dict, Any
from app.core.pdvm_central_datenbank import PdvmCentralDatabase
from app.core.central_write_service import create_record_central, update_record_central
from app.core.pdvm_datenbank import PdvmDatabase
from app.core import theme_service
from app.core import layout_schema

logger = logging.getLogger(__name__)

# Reservierte Basissaetze (000/555/666) sind keine waehlbaren Theme-Pakete
_RESERVED_BASE_UIDS = {
    "00000000-0000-0000-0000-000000000000",
    "55555555-5555-5555-5555-555555555555",
    "66666666-6666-6666-6666-666666666666",
}


# ============================================
# SESSION STORAGE (In-Memory fÃ¼r MVP)
# ============================================
_gcs_sessions: Dict[str, 'PdvmCentralSystemsteuerung'] = {}


def _parse_idle_seconds(value: Any) -> Optional[int]:
    try:
        n = int(float(str(value).strip()))
        if n <= 0:
            return None
        return n
    except Exception:
        return None


def get_gcs() -> Optional['PdvmCentralSystemsteuerung']:
    """
    Holt aktive GCS-Instanz aus Session
    
    ULTRA-VEREINFACHT: Import via `from pdvm_central_systemsteuerung import get_gcs as gcs`
    Verwendung: `expert_mode = gcs().expert_mode`
    
    Returns:
        PdvmCentralSystemsteuerung-Instanz oder None wenn keine Session aktiv
    """
    # TODO: Session-Token aus Context holen (FastAPI Dependency)
    # FÃ¼r MVP: Erste verfÃ¼gbare Session zurÃ¼ckgeben
    if _gcs_sessions:
        return next(iter(_gcs_sessions.values()))
    return None


async def create_gcs_session(
    session_token: str,
    user_guid: uuid.UUID,
    mandant_guid: uuid.UUID,
    user_data: Dict[str, Any],  # NEU: User-Daten aus Login
    mandant_data: Dict[str, Any],  # NEU: Mandant-Daten aus Login
    system_db_url: str,
    mandant_db_url: str,
    stichtag: Optional[float] = None
) -> 'PdvmCentralSystemsteuerung':
    """
    Erstellt neue GCS-Session mit Pools
    
    Args:
        session_token: JWT-Token als Session-Key
        user_guid: UUID des Benutzers
        mandant_guid: UUID des Mandanten
        user_data: Komplette User-Daten aus asy_benutzer (aus Login)
        mandant_data: Komplette Mandant-Daten aus asy_mandanten (aus Login)
        system_db_url: Connection-String zur System-DB
        mandant_db_url: Connection-String zur Mandanten-DB
        stichtag: PDVM-Datum (optional, default = aktuell)
        
    Returns:
        PdvmCentralSystemsteuerung-Instanz
    """
    # Pools: gemeinsam genutzt (je URL einmal pro Prozess), nicht je Session neu aufgebaut
    from app.core.pool_registry import PoolRegistry
    import asyncio
    from app.core.pdvm_datetime import now_pdvm

    system_pool, mandant_pool = await asyncio.gather(
        PoolRegistry.get_pool(system_db_url, dsn=system_db_url, min_size=1, max_size=10),
        PoolRegistry.get_pool(mandant_db_url, dsn=mandant_db_url, min_size=1, max_size=10),
    )
    
    # Stichtag aus DB oder aktuell
    if stichtag is None:
        stichtag = now_pdvm()
    
    # Normalize GUID types early (caller often passes strings)
    try:
        user_guid = uuid.UUID(str(user_guid))
    except Exception:
        raise ValueError("UngÃ¼ltige user_guid")
    try:
        mandant_guid = uuid.UUID(str(mandant_guid))
    except Exception:
        raise ValueError("UngÃ¼ltige mandant_guid")

    # Replace any existing session with the same token (defensive)
    try:
        existing = _gcs_sessions.get(session_token)
        if existing is not None:
            await close_gcs_session(session_token)
    except Exception:
        pass

    # GCS-Instanz erstellen mit User/Mandant-Daten
    gcs = PdvmCentralSystemsteuerung(
        user_guid=user_guid,
        mandant_guid=mandant_guid,
        user_data=user_data,
        mandant_data=mandant_data,
        stichtag=stichtag,
        system_pool=system_pool,
        mandant_pool=mandant_pool
    )

    # Linear init: ensure DB-backed instances are loaded before the session is used.
    await gcs.initialize_from_db()
    
    # Idle-Konfiguration aus Mandant (ROOT.IDLE_TIMEOUT / IDLE_WARNING)
    try:
        gcs.set_idle_config(mandant_data)
    except Exception:
        pass
    gcs.touch()

    # In Session-Store ablegen
    _gcs_sessions[session_token] = gcs
    
    logger.info(f"âœ… GCS-Session erstellt: User={user_guid}, Mandant={mandant_guid}")
    return gcs


def get_gcs_session(session_token: str) -> Optional['PdvmCentralSystemsteuerung']:
    """
    Holt GCS-Session aus Store
    
    Args:
        session_token: JWT-Token
        
    Returns:
        PdvmCentralSystemsteuerung-Instanz oder None
    """
    gcs = _gcs_sessions.get(session_token)
    if not gcs:
        return None

    try:
        if gcs.is_idle_expired():
            # Session abgelaufen â†’ schlieÃŸen
            try:
                # fire-and-forget: close pools
                import asyncio

                asyncio.create_task(close_gcs_session(session_token))
            except Exception:
                _gcs_sessions.pop(session_token, None)
            return None
        gcs.touch()
    except Exception:
        pass

    return gcs


def rotate_gcs_session_token(old_token: str, new_token: str) -> bool:
    """Verschiebt eine bestehende GCS-Session auf einen neuen JWT-Token-Key."""
    if not old_token or not new_token or old_token == new_token:
        return False

    gcs = _gcs_sessions.pop(old_token, None)
    if gcs is None:
        return False

    _gcs_sessions[new_token] = gcs
    return True


async def close_gcs_session(session_token: str):
    """
    SchlieÃŸt GCS-Session (Logout)
    
    Args:
        session_token: JWT-Token
    """
    gcs = _gcs_sessions.pop(session_token, None)
    if gcs:
        # Gemeinsam genutzte Pools bleiben offen (Shutdown: PoolRegistry.close_all);
        # nur nicht registrierte (eigene) Pools werden geschlossen.
        from app.core.pool_registry import PoolRegistry

        for pool in (gcs._system_pool, gcs._mandant_pool):
            if pool and not PoolRegistry.is_shared(pool):
                await pool.close()
        logger.info(f"âœ… GCS-Session geschlossen: {session_token[:8]}...")


class PdvmCentralSystemsteuerung:
    """
    Global Configuration System
    Verwaltet Benutzer- und Mandantendaten in Session
    
    Desktop-Pattern: Separate PdvmCentralDatenbank-Instanzen fÃ¼r:
    - Benutzer (aus Login, no_change)
    - Mandant (aus Login, no_change)
    - Systemsteuerung (Benutzereinstellungen)
    - Anwendungsdaten (Mandanteneinstellungen)
    """
    
    def __init__(
        self, 
        user_guid: uuid.UUID, 
        mandant_guid: uuid.UUID,
        user_data: Dict[str, Any],  # User-Daten aus Login
        mandant_data: Dict[str, Any],  # Mandant-Daten aus Login
        stichtag: float = 9999365.00000,
        system_pool: Optional[Any] = None,
        mandant_pool: Optional[Any] = None
    ):
        """
        Initialisiert GCS fÃ¼r User und Mandant
        
        Args:
            user_guid: UUID des Benutzers
            mandant_guid: UUID des Mandanten
            user_data: Komplette User-Daten aus asy_benutzer (aus Login)
            mandant_data: Komplette Mandant-Daten aus asy_mandanten (aus Login)
            stichtag: Aktueller Stichtag (default = aktuell)
            system_pool: Connection pool fÃ¼r pdvm_system Datenbank
            mandant_pool: Connection pool fÃ¼r mandanten Datenbank
        """
        self.user_guid = user_guid
        self.mandant_guid = mandant_guid
        self.stichtag = stichtag
        self.actor_ip: Optional[str] = None
        self._system_pool = system_pool
        self._mandant_pool = mandant_pool

        # Session-Cache: Base-Rows fÃ¼r Views (DB-Rohdaten), damit Stichtag-Wechsel nicht jedes Mal DB lesen muss.
        # Key: (table_name, include_historisch, limit)
        self._view_base_rows_cache: Dict[tuple[str, bool, int], Any] = {}

        # Session-Cache: Tabellen-Cache (raw rows by uid + modified_at delta refresh)
        # Key: (table_name, include_historisch)
        # Value: {
        #   by_uid: {uid: raw_row_dict},
        #   max_modified_at: datetime|None,
        #   version: int,
        #   max_rows: int,
        #   last_refresh_ts: float,
        #   truncated: bool,
        # }
        self._pdvm_table_cache: Dict[tuple[str, bool], Any] = {}

        # Session-Cache: Matrix-Result (UID-Reihenfolge / Group-Meta) pro View-State
        # Key: string (stable hash)
        self._view_matrix_result_cache: Dict[str, Any] = {}

        # Session-Cache: Dropdown-Datasets (sys_dropdowndaten)
        # Key: (table_name, dataset_uid, language)
        # Value: {ts, default_language, maps:{field->{key:label}}, options:{field->[...]} }
        self._pdvm_dropdown_cache: Dict[tuple[str, str, str], Any] = {}

        # Session-Cache: sys_control_dict Template 555 (nicht persistent)
        self._control_template_555_cache: Dict[str, Any] = {}

        # Session-Cache: aufgeloeste Control-Listen (Phase 5)
        # Key: CACHE.CONTROL_DICT::<table>::<edit_type>::<frame_guid>
        self._pdvm_control_dict_cache: Dict[str, Any] = {}
        self._pdvm_control_dict_cache_stats: Dict[str, int] = {
            "hits": 0,
            "persistent_hits": 0,
            "misses": 0,
            "rebuilds": 0,
        }

        # Idle-Session-Management (Sekunden)
        self._idle_timeout_seconds: Optional[int] = None
        self._idle_warning_seconds: Optional[int] = None
        self._last_activity_ts: Optional[float] = None

        self.layout = None
        # Fuer den Mandanten freigegebene Theme-Pakete: guid -> {"name": str, "data": dict}; self.layout ist das Standard-Paket
        self.layout_packages: Dict[str, Dict[str, Any]] = {}
        # Mandanten-Overlay (nur Abweichungen zum Theme-Paket), msy_layout-Zeile mit link_uid = Mandant
        self.layout_overlay: Dict[str, Any] = {}
        
        # ===== DESKTOP-PATTERN: Separate Instanzen =====
        
        # 1. Benutzer-Instanz (no_save=True, Daten aus Login)
        self.benutzer = PdvmCentralDatabase(
            "asy_benutzer",
            guid=None,  # Keine GUID â†’ kein DB-Lesen
            no_save=True,  # Read-only
            stichtag=stichtag,
            system_pool=system_pool,
            mandant_pool=mandant_pool
        )
        self.benutzer.set_data(user_data)  # Daten aus Login setzen
        self.benutzer.set_guid(str(user_guid))  # GUID nachtrÃ¤glich setzen
        
        # 2. Mandant-Instanz (no_save=True, Daten aus Login)
        self.mandant = PdvmCentralDatabase(
            "asy_mandanten",
            guid=None,  # Keine GUID â†’ kein DB-Lesen
            no_save=True,  # Read-only
            stichtag=stichtag,
            system_pool=system_pool,
            mandant_pool=mandant_pool
        )
        self.mandant.set_data(mandant_data)  # Daten aus Login setzen
        self.mandant.set_guid(str(mandant_guid))  # GUID nachtrÃ¤glich setzen
        
        # 3. Systemsteuerung-Instanz (Benutzereinstellungen, read/write)
        self.systemsteuerung = PdvmCentralDatabase(
            "msy_systemsteuerung",
            guid=None,  # Keine GUID â†’ kein DB-Lesen
            no_save=False,  # Speicherbar
            stichtag=stichtag,
            system_pool=system_pool,
            mandant_pool=mandant_pool
        )
        
        # 4. Anwendungsdaten-Instanz (Mandanteneinstellungen, read/write)
        self.anwendungsdaten = PdvmCentralDatabase(
            "msy_anwendungsdaten",
            guid=None,  # Keine GUID â†’ kein DB-Lesen
            no_save=False,  # Speicherbar
            stichtag=stichtag,
            system_pool=system_pool,
            mandant_pool=mandant_pool
        )
        self.systemsteuerung.actor_user_uid = str(self.user_guid)
        self.anwendungsdaten.actor_user_uid = str(self.user_guid)
        
        # 5. Layout wird in initialize_from_db() geladen (linear)

    def set_idle_config(self, mandant_data: Dict[str, Any]) -> None:
        root = mandant_data.get("ROOT", {}) if isinstance(mandant_data, dict) else {}
        if not isinstance(root, dict):
            root = {}

        timeout = _parse_idle_seconds(root.get("IDLE_TIMEOUT"))
        warning = _parse_idle_seconds(root.get("IDLE_WARNING"))

        self._idle_timeout_seconds = timeout
        self._idle_warning_seconds = warning

    def touch(self) -> None:
        self._last_activity_ts = time.time()

    def is_idle_expired(self, now_ts: Optional[float] = None) -> bool:
        timeout = self._idle_timeout_seconds or 0
        if timeout <= 0:
            return False
        last = self._last_activity_ts
        if last is None:
            return False
        now = now_ts if now_ts is not None else time.time()
        return (now - last) >= timeout

    def idle_remaining_seconds(self, now_ts: Optional[float] = None) -> Optional[int]:
        timeout = self._idle_timeout_seconds or 0
        if timeout <= 0:
            return None
        last = self._last_activity_ts
        if last is None:
            return None
        now = now_ts if now_ts is not None else time.time()
        remaining = timeout - (now - last)
        return int(remaining) if remaining > 0 else 0

    def get_idle_status(self) -> Dict[str, Any]:
        return {
            "idle_timeout": self._idle_timeout_seconds,
            "idle_warning": self._idle_warning_seconds,
            "last_activity": self._last_activity_ts,
            "idle_remaining": self.idle_remaining_seconds(),
        }

    @staticmethod
    def _truthy(value: Any) -> bool:
        if value is None:
            return False
        if isinstance(value, bool):
            return bool(value)
        if isinstance(value, (int, float)):
            try:
                return float(value) != 0.0
            except Exception:
                return False
        s = str(value).strip().lower()
        return s in {"1", "true", "yes", "y", "on"}

    async def initialize_from_db(self) -> None:
        """Lineare Initialisierung: lÃ¤dt systemsteuerung/anwendungsdaten/layout aus DB.

        WICHTIG: Keine create_task() / parallel init. Nach RÃ¼ckkehr ist der GCS konsistent.
        """
        from app.core.pdvm_datetime import now_pdvm

        user_guid_str = str(self.user_guid)
        mandant_guid_str = str(self.mandant_guid)

        try:
            user_uuid = uuid.UUID(user_guid_str)
        except Exception:
            raise ValueError("UngÃ¼ltige user_guid")

        try:
            mandant_uuid = uuid.UUID(mandant_guid_str)
        except Exception:
            raise ValueError("UngÃ¼ltige mandant_guid")

        def _apply_stichtag_to_all_instances(new_stichtag: float) -> None:
            self.stichtag = float(new_stichtag)
            for inst in (self.benutzer, self.mandant, self.systemsteuerung, self.anwendungsdaten, self.layout):
                if inst is not None:
                    inst.stichtag = float(new_stichtag)

        async def _ensure_row_identity_via_link_uid(db: PdvmDatabase, row: Dict[str, Any], target_link_uuid: uuid.UUID, table_label: str) -> Dict[str, Any]:
            """Stellt sicher: uid ist reine Row-ID; fachliche IdentitÃ¤t liegt in link_uid."""
            try:
                row_uid = row.get("uid") if isinstance(row, dict) else None
                if row_uid is None:
                    return row
                row_uid_str = str(row_uid)
                if row_uid_str != str(target_link_uuid):
                    return row

                new_uid = uuid.uuid4()
                changed = await db.rekey_uid(uuid.UUID(row_uid_str), new_uid)
                if changed:
                    logger.info(f"ðŸ” {table_label}: Row-UID von Link-UID entkoppelt ({row_uid_str} -> {new_uid})")
                    refreshed = await db.get_by_uid(new_uid)
                    return refreshed or row
            except Exception as exc:
                logger.warning(f"âš ï¸ {table_label}: Rekey auf Row-UID fehlgeschlagen: {exc}")
            return row

        # --- msy_systemsteuerung (User) ---
        row = await self.systemsteuerung.db.get_by_link_uid(user_uuid)
        row = await _ensure_row_identity_via_link_uid(self.systemsteuerung.db, row, user_uuid, "msy_systemsteuerung") if row else row
        if row and row.get("daten"):
            self.systemsteuerung.set_data(row["daten"])
            self.systemsteuerung.set_guid(str(row.get("uid")))
        else:
            logger.info(f"ðŸ“ msy_systemsteuerung fÃ¼r User {user_guid_str} nicht gefunden - erstelle mit Defaults")
            new_row_uid = str(uuid.uuid4())
            self.systemsteuerung.set_guid(new_row_uid)
            self.systemsteuerung.set_data({})
            self.systemsteuerung.set_value(user_guid_str, "THEME_MODE", "light", self.stichtag)
            await create_record_central(
                table_name="msy_systemsteuerung",
                uid=uuid.UUID(new_row_uid),
                daten=self.systemsteuerung.get_all_values(),
                name="",
                historisch=0,
                link_uid=user_uuid,
                system_pool=self._system_pool,
                mandant_pool=self._mandant_pool,
            )
            logger.info(f"âœ… msy_systemsteuerung fÃ¼r User {user_guid_str} erstellt")

        # STICHTAG: load or initialize
        stored = None
        try:
            stored, _ = self.systemsteuerung.get_value(user_guid_str, "STICHTAG", ab_zeit=self.stichtag)
        except Exception:
            stored = None

        if stored is not None:
            try:
                _apply_stichtag_to_all_instances(float(stored))
            except Exception:
                stored = None

        if stored is None:
            new_st = float(self.stichtag) if self.stichtag not in (None, 0, 9999365.00000) else float(now_pdvm())
            _apply_stichtag_to_all_instances(new_st)
            self.systemsteuerung.set_value(user_guid_str, "STICHTAG", new_st, self.stichtag)
            try:
                await self.systemsteuerung.save_all_values()
                logger.info(f"âœ… STICHTAG initialisiert und gespeichert: {new_st}")
            except Exception as e:
                logger.error(f"âŒ Fehler beim Persistieren von STICHTAG: {e}")

        # --- msy_anwendungsdaten (Mandant) ---
        row = await self.anwendungsdaten.db.get_by_link_uid(mandant_uuid)
        row = await _ensure_row_identity_via_link_uid(self.anwendungsdaten.db, row, mandant_uuid, "msy_anwendungsdaten") if row else row
        if row and row.get("daten"):
            self.anwendungsdaten.set_data(row["daten"])
            self.anwendungsdaten.set_guid(str(row.get("uid")))
        else:
            logger.info(f"ðŸ“ msy_anwendungsdaten fÃ¼r Mandant {mandant_guid_str} nicht gefunden - erstelle mit Defaults")
            new_row_uid = str(uuid.uuid4())
            self.anwendungsdaten.set_guid(new_row_uid)
            self.anwendungsdaten.set_data({})
            self.anwendungsdaten.set_value("CONFIG", "THEME_GUID", "", self.stichtag)
            await create_record_central(
                table_name="msy_anwendungsdaten",
                uid=uuid.UUID(new_row_uid),
                daten=self.anwendungsdaten.get_all_values(),
                name="",
                historisch=0,
                link_uid=mandant_uuid,
                system_pool=self._system_pool,
                mandant_pool=self._mandant_pool,
            )
            logger.info(f"âœ… msy_anwendungsdaten fÃ¼r Mandant {mandant_guid_str} erstellt")

        # --- Layout (Theme): canonical msy_layout, legacy self-heal from sys_layout ---
        theme_guid = None
        try:
            cfg = (self.mandant.data or {}).get("CONFIG") if isinstance(self.mandant.data, dict) else None
            if isinstance(cfg, dict):
                theme_guid = cfg.get("THEME_GUID")
        except Exception:
            theme_guid = None

        theme_guid_str = str(theme_guid).strip() if theme_guid is not None else ""
        if theme_guid_str:
            try:
                theme_uuid = uuid.UUID(theme_guid_str)
            except Exception:
                theme_uuid = None

            if theme_uuid is not None:
                # Immer auf canonical msy_layout arbeiten.
                self.layout = PdvmCentralDatabase(
                    "msy_layout",
                    guid=None,
                    no_save=True,
                    stichtag=float(self.stichtag),
                    system_pool=self._system_pool,
                    mandant_pool=self._mandant_pool,
                )

                row = await self.layout.db.get_row(theme_uuid)

                # Migration-Heilung: Falls msy_layout leer ist, einmalig aus Legacy sys_layout uebernehmen.
                if not row:
                    try:
                        legacy_layout_db = PdvmCentralDatabase(
                            "sys_layout",
                            guid=None,
                            no_save=True,
                            stichtag=float(self.stichtag),
                            system_pool=self._system_pool,
                            mandant_pool=self._mandant_pool,
                        )
                        legacy_row = await legacy_layout_db.db.get_row(theme_uuid)

                        if legacy_row:
                            # Legacy-Daten sofort fuer diese Session verwenden (auch wenn Persistierung spaeter fehlschlaegt).
                            row = legacy_row
                            try:
                                await create_record_central(
                                    table_name="msy_layout",
                                    uid=theme_uuid,
                                    daten=legacy_row.get("daten") or {},
                                    name=legacy_row.get("name") or "",
                                    historisch=int(legacy_row.get("historisch") or 0),
                                    system_pool=self._system_pool,
                                    mandant_pool=self._mandant_pool,
                                )
                                logger.info(f"âœ… Layout-Migration: Theme {theme_guid_str} von sys_layout nach msy_layout uebernommen")
                                # Nach erfolgreicher Persistierung canonical row erneut laden.
                                row = await self.layout.db.get_row(theme_uuid) or row
                            except Exception as migration_exc:
                                logger.warning(f"âš ï¸ Layout-Migration nach msy_layout fehlgeschlagen: {migration_exc}")
                        else:
                            logger.warning(f"âš ï¸ Theme {theme_guid_str} weder in msy_layout noch in sys_layout gefunden")
                    except Exception as legacy_exc:
                        logger.warning(f"âš ï¸ Legacy-Layout-Lookup in sys_layout fehlgeschlagen: {legacy_exc}")

                if row and row.get("daten"):
                    self.layout.set_data(row["daten"])
                else:
                    self.layout.set_data({})
                self.layout.set_guid(theme_guid_str)
                logger.info(f"âœ… Layout geladen aus msy_layout: {theme_guid_str}")

                # Mandanten-Overlay: eigene msy_layout-Zeile (link_uid = Mandant), Kennzeichen ROOT.LAYER=OVERLAY.
                # Zeilen ohne Kennzeichen (Paket-Kopien) werden bewusst ignoriert.
                self.layout_overlay = {}
                try:
                    overlay_row = await self.layout.db.get_by_link_uid(mandant_uuid)
                    overlay_data = (overlay_row or {}).get("daten")
                    if isinstance(overlay_data, str):
                        overlay_data = json.loads(overlay_data)
                    if isinstance(overlay_data, dict) and (overlay_data.get("ROOT") or {}).get("LAYER") == "OVERLAY":
                        self.layout_overlay = overlay_data
                except Exception as overlay_exc:
                    logger.warning(f"âš ï¸ Layout-Overlay konnte nicht geladen werden: {overlay_exc}")
        else:
            logger.warning("âš ï¸ Keine THEME_GUID im Mandant-CONFIG gefunden")

        await self._load_extra_layout_packages()

        # --- sys_control_dict Template-Cache (555) ---
        await self.preload_control_template_cache()

    # === Theme-Pakete (mehrere je Mandant) ===

    async def _fetch_package_row(self, theme_uuid: uuid.UUID) -> Optional[Dict[str, Any]]:
        """Paketzeile aus msy_layout; fehlt sie, wird sie einmalig aus sys_layout uebernommen (wie beim Login)."""
        pools = {"system_pool": self._system_pool, "mandant_pool": self._mandant_pool}
        row = await PdvmDatabase("msy_layout", **pools).get_row(theme_uuid)
        if row:
            return row
        legacy_row = await PdvmDatabase("sys_layout", **pools).get_row(theme_uuid)
        if not legacy_row:
            return None
        try:
            await create_record_central(
                table_name="msy_layout",
                uid=theme_uuid,
                daten=legacy_row.get("daten") or {},
                name=legacy_row.get("name") or "",
                historisch=int(legacy_row.get("historisch") or 0),
                **pools,
            )
        except Exception as exc:
            logger.warning(f"Theme-Paket {theme_uuid}: Uebernahme nach msy_layout fehlgeschlagen: {exc}")
        return legacy_row

    @staticmethod
    def _package_from_row(row: Dict[str, Any], guid: str) -> Dict[str, Any]:
        data = row.get("daten")
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except Exception:
                data = {}
        data = data if isinstance(data, dict) else {}
        info = data.get("info") if isinstance(data.get("info"), dict) else {}
        name = str(row.get("name") or info.get("name") or guid).strip()
        return {"name": name, "data": data}

    async def fetch_theme_package(self, guid: Any) -> Optional[Dict[str, Any]]:
        """Laedt ein Theme-Paket ({"name", "data"}) per GUID; ``None`` wenn es nicht existiert."""
        try:
            theme_uuid = uuid.UUID(str(guid).strip())
        except Exception:
            return None
        row = await self._fetch_package_row(theme_uuid)
        return self._package_from_row(row, str(theme_uuid)) if row else None

    def _allowed_package_guids(self) -> list:
        """THEME_ALLOWED (ohne das Standard-Paket), normalisierte GUID-Strings ohne Duplikate."""
        raw = self._raw_value(self.mandant, "CONFIG", "THEME_ALLOWED")
        default = str(self._raw_value(self.mandant, "CONFIG", "THEME_GUID") or "").strip().lower()
        guids: list = []
        for item in raw if isinstance(raw, list) else []:
            guid = str(item or "").strip().lower()
            if guid and guid != default and guid not in guids:
                guids.append(guid)
        return guids

    async def _load_extra_layout_packages(self) -> None:
        """Laedt die Standard- und alle freigegebenen Pakete in ``layout_packages`` (Session-Cache)."""
        packages: Dict[str, Dict[str, Any]] = {}
        extra_guids = self._allowed_package_guids()
        if self.layout is not None:
            guid = str(self.layout.guid)
            packages[guid] = {"name": self._default_package_name(), "data": self.layout.data}
            if extra_guids:
                try:
                    named = await self.fetch_theme_package(guid)
                    if named is not None:
                        packages[guid]["name"] = named["name"]
                except Exception as exc:
                    logger.warning(f"Name des Standard-Themepakets {guid} nicht lesbar: {exc}")
        for guid in extra_guids:
            try:
                package = await self.fetch_theme_package(guid)
            except Exception as exc:
                logger.warning(f"Theme-Paket {guid} konnte nicht geladen werden: {exc}")
                package = None
            if package is None:
                logger.warning(f"Freigegebenes Theme-Paket {guid} nicht gefunden")
                continue
            packages[guid] = package
        self.layout_packages = packages

    async def reload_layout_packages(self) -> None:
        """Nach Aenderung von THEME_GUID/THEME_ALLOWED: Standard-Paket und freigegebene Pakete neu laden."""
        guid = str(self._raw_value(self.mandant, "CONFIG", "THEME_GUID") or "").strip()
        if guid and (self.layout is None or str(self.layout.guid).lower() != guid.lower()):
            package = await self.fetch_theme_package(guid)
            if package is not None:
                self.layout = PdvmCentralDatabase(
                    "msy_layout",
                    guid=None,
                    no_save=True,
                    stichtag=float(self.stichtag),
                    system_pool=self._system_pool,
                    mandant_pool=self._mandant_pool,
                )
                self.layout.set_data(package["data"])
                self.layout.set_guid(guid)
        await self._load_extra_layout_packages()

    def _default_package_name(self) -> str:
        data = self.layout.data if self.layout is not None and isinstance(self.layout.data, dict) else {}
        info = data.get("info") if isinstance(data.get("info"), dict) else {}
        return str(info.get("name") or self.layout.guid)

    def _package_entries(self) -> Dict[str, Dict[str, Any]]:
        """Alle waehlbaren Pakete (Standard zuerst): guid -> {"name", "data"}."""
        entries: Dict[str, Dict[str, Any]] = {}
        if self.layout is not None:
            guid = str(self.layout.guid)
            cached = (getattr(self, "layout_packages", None) or {}).get(guid) or {}
            entries[guid] = {"name": cached.get("name") or self._default_package_name(), "data": self.layout.data}
        for guid, entry in (getattr(self, "layout_packages", None) or {}).items():
            entries.setdefault(guid, entry)
        return entries

    def _default_package_guid(self) -> Optional[str]:
        return str(self.layout.guid) if self.layout is not None else None

    def get_user_theme_package_guid(self) -> Optional[str]:
        """Aktives Paket: Benutzerwahl (THEME_CHOICE), sofern freigegeben, sonst das Standard-Paket des Mandanten."""
        choice = str(self._raw_value(self.systemsteuerung, str(self.user_guid), "THEME_CHOICE") or "").strip()
        entries = self._package_entries()
        if choice in entries:
            return choice
        return self._default_package_guid()

    def _package_data(self, guid: Optional[str]) -> Dict[str, Any]:
        entry = self._package_entries().get(guid or "")
        return entry["data"] if entry and isinstance(entry["data"], dict) else {}

    async def preload_control_template_cache(self) -> None:
        """LÃ¤dt nicht-persistenten Control-Template-Cache (GUID 555...) in die Session."""
        try:
            template_uid = uuid.UUID("55555555-5555-5555-5555-555555555555")
            db = PdvmDatabase(
                "sys_control_dict",
                system_pool=self._system_pool,
                mandant_pool=self._mandant_pool,
            )
            row = await db.get_by_uid(template_uid)
            data = row.get("daten") if isinstance(row, dict) else {}
            self._control_template_555_cache = copy.deepcopy(data) if isinstance(data, dict) else {}
            logger.info("âœ… GCS Control-Template-Cache geladen (555...)")
        except Exception as exc:
            self._control_template_555_cache = {}
            logger.warning(f"âš ï¸ GCS Control-Template-Cache konnte nicht geladen werden: {exc}")

    def get_control_template_555_cache(self) -> Dict[str, Any]:
        """Gibt eine sichere Kopie des nicht-persistenten 555-Template-Caches zurÃ¼ck."""
        return copy.deepcopy(self._control_template_555_cache) if isinstance(self._control_template_555_cache, dict) else {}
    
    # === Delegierte Methoden fÃ¼r KompatibilitÃ¤t ===
    
    def get_value(self, gruppe: str, feld: str, ab_zeit: Optional[float] = None):
        """
        Delegiert an systemsteuerung.get_value()
        FÃ¼r KompatibilitÃ¤t mit bestehender Layout-API
        """
        return self.systemsteuerung.get_value(gruppe, feld, ab_zeit or self.stichtag)
    
    def set_value(self, gruppe: str, feld: str, wert: Any, ab_zeit: Optional[float] = None):
        """
        Delegiert an systemsteuerung.set_value()
        FÃ¼r KompatibilitÃ¤t mit bestehender Layout-API
        """
        self.systemsteuerung.set_value(gruppe, feld, wert, ab_zeit or self.stichtag)
    
    def set_request_context(self, actor_ip: Optional[str] = None) -> None:
        """Setzt Request-Kontext (aktuell: Client-IP) fÃ¼r nachfolgende Saves."""
        self.actor_ip = actor_ip
        self.systemsteuerung.actor_ip = actor_ip
        self.anwendungsdaten.actor_ip = actor_ip

    async def save_all_values(
        self,
        actor_user_uid: Optional[str] = None,
        actor_ip: Optional[str] = None,
    ):
        """
        Delegiert an systemsteuerung.save_all_values()
        FÃ¼r KompatibilitÃ¤t mit GCS-API
        """
        effective_actor_user_uid = actor_user_uid or str(self.user_guid)
        effective_actor_ip = actor_ip if actor_ip is not None else self.actor_ip
        return await self.systemsteuerung.save_all_values(
            actor_user_uid=effective_actor_user_uid,
            actor_ip=effective_actor_ip,
        )
    
    # === Theme-Einstellungen ===
    
    def get_user_theme_group(self, mode: str, package: Optional[Dict[str, Any]] = None) -> str:
        """
        Ermittelt die Variante (Gruppe im Theme-Paket) fuer den Modus.

        Prioritaet: Benutzer (msy_systemsteuerung) -> Mandant (asy_mandanten.CONFIG) -> Modus-Name.
        Existiert eine Variante im aktiven Paket nicht (z. B. nach einem Paketwechsel), gilt die naechste.

        Args:
            mode: 'light' oder 'dark'
            package: Paketdaten; ohne Angabe das aktive Paket des Benutzers
        """
        candidates = [
            self._raw_value(self.systemsteuerung, str(self.user_guid), f"THEME_VARIANT_{mode.upper()}"),
            self._raw_value(self.mandant, "CONFIG", f"THEME_{mode.upper()}"),
        ]
        if package is None:
            package = self._package_data(self.get_user_theme_package_guid())
        for candidate in candidates:
            if candidate and (not package or isinstance(package.get(str(candidate)), dict)):
                return str(candidate)
        return mode

    @staticmethod
    def _raw_value(inst: Any, gruppe: str, feld: str) -> Any:
        """Liest einen Wert ohne Seiteneffekte (get_static_value legt fehlende Felder an)."""
        data = getattr(inst, "data", None)
        group = data.get(gruppe) if isinstance(data, dict) else None
        return group.get(feld) if isinstance(group, dict) else None

    def get_user_theme_mode(self) -> str:
        """Gespeicherter Hell/Dunkel-Modus des Benutzers (THEME_MODE), sonst Mandanten-Default, sonst 'light'."""
        stored = self._raw_value(self.systemsteuerung, str(self.user_guid), "THEME_MODE")
        if stored in ("light", "dark"):
            return stored
        default = self._raw_value(self.mandant, "CONFIG", "THEME_DEFAULT_MODE")
        return default if default in ("light", "dark") else "light"

    def resolve_active_theme(self, mode: Optional[str] = None) -> Dict[str, Any]:
        """Loest Paket, Mandanten-Overlay und Benutzer-Overlay zum aktiven Theme auf (siehe theme_service)."""
        mode = mode if mode in ("light", "dark") else self.get_user_theme_mode()
        user_overlay = self._raw_value(self.systemsteuerung, str(self.user_guid), "THEME_OVERRIDES")
        edit_patterns = self._raw_value(self.mandant, "CONFIG", "USER_THEME_EDIT")
        if not isinstance(edit_patterns, list):
            edit_patterns = []

        package_guid = self.get_user_theme_package_guid()
        package = self._package_data(package_guid)

        return theme_service.resolve_theme(
            package=package or (self.layout.data if self.layout is not None else None),
            package_guid=package_guid,
            mode=mode,
            variant=self.get_user_theme_group(mode, package),
            mandant_overlay=self.layout_overlay,
            user_overlay=user_overlay if isinstance(user_overlay, dict) else None,
            user_edit_patterns=edit_patterns,
        ) | self._resolve_layout_part()

    def _resolve_layout_part(self) -> Dict[str, Any]:
        """Wirksame Layout-Varianten (Strukturkatalog); Warnungen werden an ``warnings`` angehaengt."""
        cfg = self._mandant_theme_config()
        user_choice = self._raw_value(self.systemsteuerung, str(self.user_guid), "LAYOUT_CHOICE")
        layout, warnings = layout_schema.resolve_layout(
            default_map=cfg["layout_default"], allowed_map=cfg["layout_allowed"], user_choice=user_choice
        )
        return {"layout": layout, "layout_warnings": warnings}

    # --- Theme-Editor (P4) ---

    def _mandant_theme_config(self) -> Dict[str, Any]:
        cfg = self._raw_value(self.mandant, "CONFIG", "USER_THEME_EDIT")
        layout_default = self._raw_value(self.mandant, "CONFIG", "LAYOUT_DEFAULT")
        layout_allowed = self._raw_value(self.mandant, "CONFIG", "LAYOUT_ALLOWED")
        return {
            "theme_default": str(self._raw_value(self.mandant, "CONFIG", "THEME_GUID") or ""),
            "theme_allowed": self._allowed_package_guids(),
            "theme_light": self._raw_value(self.mandant, "CONFIG", "THEME_LIGHT") or "",
            "theme_dark": self._raw_value(self.mandant, "CONFIG", "THEME_DARK") or "",
            "default_mode": self._raw_value(self.mandant, "CONFIG", "THEME_DEFAULT_MODE") or "",
            "user_theme_edit": cfg if isinstance(cfg, list) else [],
            "layout_default": layout_default if isinstance(layout_default, dict) else {},
            "layout_allowed": layout_allowed if isinstance(layout_allowed, dict) else {},
        }

    def _layout_editor_part(self, scope: str) -> Dict[str, Any]:
        """Layout-Bereiche fuer den Editor; ``available`` = Varianten, die auf dieser Ebene waehlbar sind."""
        cfg = self._mandant_theme_config()
        catalog = layout_schema.get_layout_catalog()
        for area, data in catalog.items():
            all_options = [o["value"] for o in data["options"]]
            data["available"] = all_options if scope == "mandant" else layout_schema.available_options(
                area, cfg["layout_default"], cfg["layout_allowed"]
            )
            data["mandant_default"] = layout_schema.mandant_defaults(cfg["layout_default"])[area]
        return catalog

    def get_theme_editor_state(self, scope: str, package_guid: Optional[str] = None) -> Dict[str, Any]:
        """Zustand fuer den Theme-Editor: Basis je Modus, bestehendes Overlay der Ebene und Einstellungen.

        scope='mandant': Basis = Paket-Variante des Mandanten (Standard-Paket), Overlay = Mandanten-Overlay.
        scope='user': Basis = Paket-Variante des Benutzers inkl. Mandanten-Overlay, Overlay = Benutzer-Overlay.
            ``package_guid`` zeigt die Basis eines anderen freigegebenen Pakets (Vorschau vor dem Speichern).
        """
        if scope not in ("mandant", "user"):
            raise ValueError("scope muss 'mandant' oder 'user' sein")

        entries = self._package_entries()
        if scope == "mandant":
            used_guid = self._default_package_guid()
        else:
            used_guid = package_guid if package_guid in entries else self.get_user_theme_package_guid()
        package = self._package_data(used_guid) or None
        mandant_cfg = self._mandant_theme_config()
        user_key = str(self.user_guid)
        stored_user_overlay = self._raw_value(self.systemsteuerung, user_key, "THEME_OVERRIDES")
        stored_user_overlay = stored_user_overlay if isinstance(stored_user_overlay, dict) else {}

        modes: Dict[str, Any] = {}
        for mode in ("light", "dark"):
            if scope == "mandant":
                variant = mandant_cfg[f"theme_{mode}"] or mode
                variant_name, base, warnings = theme_service.compose_base(package, mode=mode, variant=variant)
                overlay = self.layout_overlay.get(mode) if isinstance(self.layout_overlay, dict) else None
            else:
                variant_name, base, warnings = theme_service.compose_base(
                    package, mode=mode, variant=self.get_user_theme_group(mode, package or {}), mandant_overlay=self.layout_overlay
                )
                overlay = stored_user_overlay.get(mode)
            modes[mode] = {
                "variant": variant_name,
                "base": base,
                "overlay": overlay if isinstance(overlay, dict) else {},
                "warnings": warnings,
            }

        if scope == "mandant":
            settings_node: Dict[str, Any] = dict(mandant_cfg)
        else:
            user_choice = self._raw_value(self.systemsteuerung, user_key, "LAYOUT_CHOICE")
            settings_node = {
                "theme_choice": str(self._raw_value(self.systemsteuerung, user_key, "THEME_CHOICE") or ""),
                "variant_light": self._raw_value(self.systemsteuerung, user_key, "THEME_VARIANT_LIGHT") or "",
                "variant_dark": self._raw_value(self.systemsteuerung, user_key, "THEME_VARIANT_DARK") or "",
                "mode": self.get_user_theme_mode(),
                "layout_choice": user_choice if isinstance(user_choice, dict) else {},
            }

        return {
            "scope": scope,
            "theme_package_id": used_guid,
            "packages": [
                {"guid": guid, "name": entry["name"], "is_default": guid == self._default_package_guid()}
                for guid, entry in entries.items()
            ],
            "variants": theme_service.list_variants(package),
            "modes": modes,
            "settings": settings_node,
            "layout": self._layout_editor_part(scope),
            "allowed_patterns": mandant_cfg["user_theme_edit"] if scope == "user" else None,
        }

    def _validate_variant(self, variant: Any, mode: str, package: Optional[Dict[str, Any]] = None) -> str:
        name = str(variant or "").strip()
        if not name:
            return ""
        if package is None:
            package = self._package_data(self.get_user_theme_package_guid()) or (self.layout.data if self.layout is not None else None)
        if name not in theme_service.list_variants(package).get(mode, []):
            raise theme_service.ThemeValidationError([f"Variante '{name}' existiert im Theme-Paket nicht fuer den Modus '{mode}'"])
        return name

    def _mandant_overlay_bases(self, modes: Any) -> list:
        """Basis je freigegebenem Paket (Mandanten-Variante, sonst Modus-Name) fuer die Kontrastpruefung des Overlays."""
        cfg = self._mandant_theme_config()
        result = []
        for guid, entry in self._package_entries().items():
            bases = {}
            for mode in modes:
                wanted = cfg[f"theme_{mode}"]
                variant = wanted if wanted and isinstance(entry["data"].get(wanted), dict) else mode
                bases[mode] = theme_service.compose_base(entry["data"], mode=mode, variant=variant)[1]
            result.append((guid, entry["name"], bases))
        return result

    async def list_available_theme_packages(self) -> list:
        """Alle Theme-Pakete aus sys_layout (ohne reservierte Basissaetze) zur Auswahl durch den Mandanten."""
        rows = await PdvmDatabase("sys_layout", system_pool=self._system_pool, mandant_pool=self._mandant_pool).get_all(
            where="historisch = 0", order_by="name ASC"
        )
        result = []
        for row in rows:
            guid = str(row.get("uid"))
            if guid in _RESERVED_BASE_UIDS:
                continue
            result.append({"guid": guid, "name": self._package_from_row(row, guid)["name"]})
        return result

    async def save_mandant_theme_overlay(self, overlay: Any) -> Dict[str, Any]:
        """Speichert das Mandanten-Overlay (msy_layout-Zeile mit ROOT.LAYER='OVERLAY', link_uid = Mandant)."""
        if self.layout is None:
            raise theme_service.ThemeValidationError(["Fuer den Mandanten ist kein Theme-Paket konfiguriert"])
        clean, errors = theme_service.validate_overlay_payload(overlay, layer="Mandant")
        if errors:
            raise theme_service.ThemeValidationError(errors)

        # Kontrast: Aenderungen duerfen in keinem freigegebenen Paket einen Pflicht-Kontrast verletzen
        # (das Overlay gilt fuer alle Pakete; Basis = Mandanten-Variante bzw. Modus-Name je Paket)
        contrast_text: list = []
        contrast_payload: list = []
        per_package = self._mandant_overlay_bases(clean)
        for guid, name, bases in per_package:
            texts, payload = theme_service.contrast_errors(bases, clean, layer="Mandant")
            prefix = f"[{name}] " if len(per_package) > 1 else ""
            contrast_text += [prefix + t for t in texts]
            contrast_payload += [{**p, "package": guid} for p in payload]
        if contrast_text:
            raise theme_service.ThemeValidationError(contrast_text, contrast_payload)

        daten = {
            "ROOT": {"TABLE": "msy_layout", "LAYER": "OVERLAY", "BASE_THEME_GUID": str(self.layout.guid)},
            "light": clean.get("light", {}),
            "dark": clean.get("dark", {}),
        }
        row = await self.layout.db.get_by_link_uid(self.mandant_guid)
        row_daten = (row or {}).get("daten")
        if isinstance(row_daten, str):
            row_daten = json.loads(row_daten)
        is_overlay_row = isinstance(row_daten, dict) and (row_daten.get("ROOT") or {}).get("LAYER") == "OVERLAY"

        if is_overlay_row:
            await update_record_central(
                table_name="msy_layout",
                uid=row["uid"],
                daten=daten,
                expected_snapshot_daten=row_daten,
                gcs=self,
            )
        else:
            mandant_name = (self.mandant.data.get("MANDANT") or {}).get("NAME") if isinstance(self.mandant.data, dict) else None
            await create_record_central(
                table_name="msy_layout",
                daten=daten,
                name=f"Overlay {mandant_name or self.mandant_guid}",
                link_uid=self.mandant_guid,
                gcs=self,
            )
        self.layout_overlay = daten
        return {"overlay": {"light": daten["light"], "dark": daten["dark"]}}

    async def save_mandant_theme_config(self, settings_in: Dict[str, Any]) -> Dict[str, Any]:
        """Speichert THEME_GUID/THEME_ALLOWED/THEME_LIGHT/THEME_DARK/THEME_DEFAULT_MODE/USER_THEME_EDIT in asy_mandanten.CONFIG."""
        errors: list = []
        updates: Dict[str, Any] = {}
        variant_package = self.layout.data if self.layout is not None else {}

        if "theme_default" in settings_in:
            guid = str(settings_in["theme_default"] or "").strip()
            package = await self.fetch_theme_package(guid) if guid else None
            if package is None:
                errors.append(f"Standard-Theme-Paket '{guid}' existiert nicht")
            else:
                updates["THEME_GUID"] = str(uuid.UUID(guid))
                variant_package = package["data"]
        if "theme_allowed" in settings_in:
            raw_allowed = settings_in["theme_allowed"]
            allowed: list = []
            if not isinstance(raw_allowed, list):
                errors.append("theme_allowed muss eine Liste von Theme-Paketen sein")
                raw_allowed = []
            for item in raw_allowed:
                if await self.fetch_theme_package(item) is None:
                    errors.append(f"Theme-Paket '{item}' existiert nicht")
                    continue
                guid = str(uuid.UUID(str(item).strip()))
                if guid not in allowed:
                    allowed.append(guid)
            updates["THEME_ALLOWED"] = allowed
        for mode in ("light", "dark"):
            key = f"theme_{mode}"
            if key in settings_in:
                try:
                    updates[f"THEME_{mode.upper()}"] = self._validate_variant(settings_in[key], mode, variant_package or {})
                except theme_service.ThemeValidationError as exc:
                    errors += exc.errors
        if "default_mode" in settings_in:
            default_mode = str(settings_in["default_mode"] or "").strip()
            if default_mode not in ("", "light", "dark"):
                errors.append("default_mode muss 'light', 'dark' oder leer sein")
            updates["THEME_DEFAULT_MODE"] = default_mode
        if "user_theme_edit" in settings_in:
            patterns, pattern_errors = theme_service.validate_user_edit_patterns(settings_in["user_theme_edit"])
            errors += pattern_errors
            updates["USER_THEME_EDIT"] = patterns
        if "layout_default" in settings_in:
            layout_default, layout_errors = layout_schema.validate_choice_map(settings_in["layout_default"], layer="Mandant")
            errors += layout_errors
            updates["LAYOUT_DEFAULT"] = layout_default
        if "layout_allowed" in settings_in:
            layout_allowed, allowed_errors = layout_schema.validate_allowed_map(settings_in["layout_allowed"])
            errors += allowed_errors
            updates["LAYOUT_ALLOWED"] = layout_allowed
        if errors:
            raise theme_service.ThemeValidationError(errors)

        # Frisch aus der Datenbank lesen: Die Session-Kopie (Login-Zeitpunkt) kann veraltet sein, z. B. durch eine
        # zweite Sitzung. Geschrieben werden nur die Theme-Schluessel, alles andere bleibt wie in der DB.
        row = await PdvmDatabase("asy_mandanten").get_by_uid(self.mandant_guid)
        current = (row or {}).get("daten")
        if isinstance(current, str):
            current = json.loads(current)
        if not isinstance(current, dict):
            raise theme_service.ThemeValidationError(["Mandantendaten konnten nicht gelesen werden"])

        before = copy.deepcopy(current)
        after = copy.deepcopy(current)
        cfg = after.get("CONFIG") if isinstance(after.get("CONFIG"), dict) else {}
        cfg.update(updates)
        after["CONFIG"] = cfg
        # asy_mandanten.gilt_bis ist eine Text-Spalte; ein mitgeschriebenes SELF_GILT_BIS wuerde als datetime
        # gebunden und scheitern. Ohne den Schluessel bleibt die Spalte unveraendert.
        if isinstance(after.get("ROOT"), dict):
            after["ROOT"].pop("SELF_GILT_BIS", None)

        await update_record_central(
            table_name="asy_mandanten",
            uid=self.mandant_guid,
            daten=after,
            expected_snapshot_daten=before,
            gcs=self,
        )
        if isinstance(self.mandant.data, dict):
            self.mandant.data["CONFIG"] = copy.deepcopy(cfg)
        if "THEME_GUID" in updates or "THEME_ALLOWED" in updates:
            await self.reload_layout_packages()
        return self._mandant_theme_config()

    async def save_user_theme_settings(
        self,
        overlay: Any,
        variant_light: Any = None,
        variant_dark: Any = None,
        layout_choice: Any = None,
        theme_choice: Any = None,
    ) -> Dict[str, Any]:
        """Speichert Benutzer-Overlay, Paket-/Variantenwahl und Layout-Wahl in msy_systemsteuerung (nur Freigegebenes)."""
        cfg = self._mandant_theme_config()
        patterns = cfg["user_theme_edit"]
        clean, errors = theme_service.validate_overlay_payload(
            overlay, layer="Benutzer", allowed_patterns=patterns, require_user_editable=True
        )

        # Paketwahl: nur freigegebene Pakete; leer = Standard-Paket des Mandanten
        chosen_package = self.get_user_theme_package_guid()
        clean_choice = None
        if theme_choice is not None:
            clean_choice = str(theme_choice or "").strip()
            if clean_choice and clean_choice not in self._package_entries():
                errors.append(f"Theme-Paket '{clean_choice}' ist für den Mandanten nicht freigegeben")
                clean_choice = None
            else:
                chosen_package = clean_choice or self._default_package_guid()
        package = self._package_data(chosen_package) or (self.layout.data if self.layout is not None else None)

        light = dark = None
        try:
            light = self._validate_variant(variant_light, "light", package) if variant_light is not None else None
            dark = self._validate_variant(variant_dark, "dark", package) if variant_dark is not None else None
        except theme_service.ThemeValidationError as exc:
            errors += exc.errors

        clean_layout = None
        if layout_choice is not None:
            clean_layout, layout_errors = layout_schema.validate_choice_map(layout_choice, layer="Benutzer")
            errors += layout_errors
            for area, option in clean_layout.items():
                if option not in layout_schema.available_options(area, cfg["layout_default"], cfg["layout_allowed"]):
                    errors.append(f"Benutzer: Variante '{option}' im Bereich '{area}' ist für den Mandanten nicht freigegeben")
        if errors:
            raise theme_service.ThemeValidationError(errors)

        # Kontrast: Basis = Paket-Variante des Benutzers (inkl. neu gewaehltem Paket/Variante) + Mandanten-Overlay
        def _variant_for(mode: str, override: Optional[str]) -> str:
            if override is None:
                return self.get_user_theme_group(mode, package or {})
            return override or cfg[f"theme_{mode}"] or mode

        bases = {
            mode: theme_service.compose_base(
                package, mode=mode, variant=_variant_for(mode, light if mode == "light" else dark),
                mandant_overlay=self.layout_overlay,
            )[1]
            for mode in clean
        }
        contrast_text, contrast_payload = theme_service.contrast_errors(bases, clean, layer="Benutzer")
        if contrast_text:
            raise theme_service.ThemeValidationError(contrast_text, contrast_payload)

        user_key = str(self.user_guid)
        self.systemsteuerung.set_value(user_key, "THEME_OVERRIDES", clean, self.stichtag)
        if clean_choice is not None:
            self.systemsteuerung.set_value(user_key, "THEME_CHOICE", clean_choice, self.stichtag)
        if light is not None:
            self.systemsteuerung.set_value(user_key, "THEME_VARIANT_LIGHT", light, self.stichtag)
        if dark is not None:
            self.systemsteuerung.set_value(user_key, "THEME_VARIANT_DARK", dark, self.stichtag)
        if clean_layout is not None:
            self.systemsteuerung.set_value(user_key, "LAYOUT_CHOICE", clean_layout, self.stichtag)
        await self.save_all_values()
        return {"overlay": clean}

    # === Stichtag ===
    
    def get_stichtag(self) -> float:
        """
        Liest Stichtag des Users aus user_guid Gruppe
        
        Returns:
            PDVM-Datum (z.B. 2025356.00000)
        """
        # Stichtag ist in der GCS fÃ¼hrend; wird bei Init aus sys_systemsteuerung geladen.
        return float(self.stichtag) if self.stichtag is not None else 9999365.00000
    
    def set_stichtag(self, new_stichtag: float):
        """
        Setzt Stichtag des Users in user_guid Gruppe
        
        Args:
            new_stichtag: PDVM-Datum
        """
        # Persistierbarer Stichtag (Gruppe=user_guid, Feld=STICHTAG)
        self.set_value(str(self.user_guid), "STICHTAG", float(new_stichtag), ab_zeit=self.stichtag)
        self.stichtag = float(new_stichtag)

        # Cache invalidieren (Basisdaten kÃ¶nnen bleiben, aber das stichtag-projizierte Ergebnis muss neu berechnet werden).
        # Aktuell cachen wir nur DB-Rohdaten; invalidate ist defensiv fÃ¼r zukÃ¼nftige abgeleitete Caches.
        try:
            self._view_base_rows_cache = self._view_base_rows_cache or {}
        except Exception:
            self._view_base_rows_cache = {}

        # Stichtag Ã¼ber alle Instanzen synchronisieren
        for inst in (self.benutzer, self.mandant, self.systemsteuerung, self.anwendungsdaten, self.layout):
            if inst is not None:
                inst.stichtag = float(new_stichtag)
    
    # === Menu-Einstellungen ===
    
    def get_menu_toggle(self, menu_guid: str) -> int:
        """
        Liest toggle_menu fÃ¼r spezifisches MenÃ¼ aus menu_guid Gruppe
        
        Args:
            menu_guid: UUID des MenÃ¼s
        
        Returns:
            0 = ausgeblendet, 1 = eingeblendet (default)
        """
        wert, _ = self.get_value(menu_guid, "toggle_menu", ab_zeit=self.stichtag)
        return wert if wert is not None else 1  # Default: eingeblendet
    
    def set_menu_toggle(self, menu_guid: str, toggle: int):
        """
        Setzt toggle_menu fÃ¼r spezifisches MenÃ¼ in menu_guid Gruppe
        
        Args:
            menu_guid: UUID des MenÃ¼s
            toggle: 0 = ausblenden, 1 = einblenden
        """
        self.set_value(menu_guid, "toggle_menu", toggle, ab_zeit=self.stichtag)
    
    def get_menu_visible(self, menu_guid: str) -> bool:
        """
        Liest menu_visible fÃ¼r spezifisches MenÃ¼ aus menu_guid Gruppe
        
        Returns:
            True = sichtbar (default), False = ausgeblendet
        """
        wert, _ = self.get_value(menu_guid, "menu_visible", ab_zeit=self.stichtag)
        return wert if wert is not None else True
    
    def set_menu_visible(self, menu_guid: str, visible: bool):
        """Setzt menu_visible fÃ¼r spezifisches MenÃ¼ in menu_guid Gruppe"""
        self.set_value(menu_guid, "menu_visible", visible, ab_zeit=self.stichtag)
    
    # === Expert Mode ===
    
    def get_expert_mode(self) -> bool:
        """
        Liest Expert-Mode aus Benutzerdaten (SETTINGS.EXPERT_MODE).

        PrimÃ¤re Quelle: asy_benutzer.daten -> Gruppe SETTINGS, Feld EXPERT_MODE
        Legacy-Fallback: sys_systemsteuerung (Gruppe user_guid, Feld EXPERT_MODE)
        
        Returns:
            True = Expert Mode aktiv, False = Standard (default)
        """
        # PrimÃ¤r: Benutzerdaten aus Login/GCS (SETTINGS.EXPERT_MODE)
        try:
            benutzer_data = self.benutzer.data if isinstance(self.benutzer.data, dict) else {}
            settings = benutzer_data.get("SETTINGS") if isinstance(benutzer_data.get("SETTINGS"), dict) else {}
            if "EXPERT_MODE" in settings:
                return self._truthy(settings.get("EXPERT_MODE"))
        except Exception:
            pass

        # Legacy-Fallback: historisch in sys_systemsteuerung unter user_guid gespeichert
        try:
            legacy_wert, _ = self.get_value(str(self.user_guid), "EXPERT_MODE", ab_zeit=self.stichtag)
            if legacy_wert is not None:
                return self._truthy(legacy_wert)
        except Exception:
            pass

        return False
    
    def set_expert_mode(self, expert_mode: bool):
        """Setzt expert_mode konsistent in SETTINGS.EXPERT_MODE und Legacy-Feld."""
        value = bool(expert_mode)

        # PrimÃ¤r: Benutzerdaten-Struktur (wird in GCS-Instanz gehalten)
        try:
            if not isinstance(self.benutzer.data, dict):
                self.benutzer.data = {}
            if not isinstance(self.benutzer.data.get("SETTINGS"), dict):
                self.benutzer.data["SETTINGS"] = {}
            self.benutzer.data["SETTINGS"]["EXPERT_MODE"] = value
        except Exception:
            pass

        # Legacy-KompatibilitÃ¤t: bestehende Leser auf sys_systemsteuerung weiter bedienen
        self.set_value(str(self.user_guid), "EXPERT_MODE", value, ab_zeit=self.stichtag)
    
    # === View-Einstellungen ===
    
    def get_view_controls(self, view_guid: str) -> Optional[Dict]:
        """
        Liest Controls-Konfiguration fÃ¼r View aus view_guid Gruppe
        
        Returns:
            Dict mit Control-Einstellungen oder None
        """
        wert, _ = self.get_value(view_guid, "controls", ab_zeit=self.stichtag)
        return wert
    
    def set_view_controls(self, view_guid: str, controls: Dict):
        """Setzt Controls-Konfiguration fÃ¼r View in view_guid Gruppe"""
        self.set_value(view_guid, "controls", controls, ab_zeit=self.stichtag)

    def get_view_table_state(self, view_guid: str) -> Optional[Dict]:
        """Liest Table-State (Sort/Filter) fÃ¼r View aus view_guid Gruppe."""
        wert, _ = self.get_value(view_guid, "table_state", ab_zeit=self.stichtag)
        return wert

    def set_view_table_state(self, view_guid: str, table_state: Dict):
        """Setzt Table-State (Sort/Filter) fÃ¼r View in view_guid Gruppe."""
        self.set_value(view_guid, "table_state", table_state, ab_zeit=self.stichtag)
    
    # === EDIT-Modus (temporÃ¤re Daten) ===
    
    def get_edit_value(self, feld: str) -> Any:
        """
        Liest temporÃ¤ren Wert aus EDIT-Gruppe
        
        Returns:
            Wert oder None
        """
        wert, _ = self.get_value("EDIT", feld, ab_zeit=self.stichtag)
        return wert
    
    def set_edit_value(self, feld: str, wert: Any):
        """Schreibt temporÃ¤ren Wert in EDIT-Gruppe"""
        self.set_value("EDIT", feld, wert, ab_zeit=self.stichtag)
    
    def clear_edit_data(self):
        """LÃ¶scht alle EDIT-Daten"""
        if "EDIT" in self.systemsteuerung.data:
            del self.systemsteuerung.data["EDIT"]


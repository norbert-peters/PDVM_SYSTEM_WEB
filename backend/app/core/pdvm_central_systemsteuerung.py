"""
PDVM Central Systemsteuerung
Global Configuration System für Benutzer- und Mandantendaten

Nach Desktop-Vorbild: pdvm_central_systemsteuerung.py
- Verwaltet sys_systemsteuerung (Benutzereinstellungen)
- Verwaltet sys_anwendungsdaten (Mandantendaten)
- Session-Cache für Performance
- Session-Storage: get_gcs() für direkten Zugriff
"""
import uuid
import logging
from typing import Optional, Dict, Any
from app.core.pdvm_central_datenbank import PdvmCentralDatabase
from app.core.pdvm_datenbank import PdvmDatabase

logger = logging.getLogger(__name__)


# ============================================
# SESSION STORAGE (In-Memory für MVP)
# ============================================
_gcs_sessions: Dict[str, 'PdvmCentralSystemsteuerung'] = {}


def get_gcs() -> Optional['PdvmCentralSystemsteuerung']:
    """
    Holt aktive GCS-Instanz aus Session
    
    ULTRA-VEREINFACHT: Import via `from pdvm_central_systemsteuerung import get_gcs as gcs`
    Verwendung: `expert_mode = gcs().expert_mode`
    
    Returns:
        PdvmCentralSystemsteuerung-Instanz oder None wenn keine Session aktiv
    """
    # TODO: Session-Token aus Context holen (FastAPI Dependency)
    # Für MVP: Erste verfügbare Session zurückgeben
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
        user_data: Komplette User-Daten aus sys_benutzer (aus Login)
        mandant_data: Komplette Mandant-Daten aus sys_mandanten (aus Login)
        system_db_url: Connection-String zur System-DB
        mandant_db_url: Connection-String zur Mandanten-DB
        stichtag: PDVM-Datum (optional, default = aktuell)
        
    Returns:
        PdvmCentralSystemsteuerung-Instanz
    """
    import asyncpg
    from app.core.pdvm_datetime import now_pdvm
    
    # Pools erstellen
    system_pool = await asyncpg.create_pool(system_db_url, min_size=2, max_size=10)
    mandant_pool = await asyncpg.create_pool(mandant_db_url, min_size=2, max_size=10)
    
    # Stichtag aus DB oder aktuell
    if stichtag is None:
        stichtag = now_pdvm()
    
    # Normalize GUID types early (caller often passes strings)
    try:
        user_guid = uuid.UUID(str(user_guid))
    except Exception:
        raise ValueError("Ungültige user_guid")
    try:
        mandant_guid = uuid.UUID(str(mandant_guid))
    except Exception:
        raise ValueError("Ungültige mandant_guid")

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
    
    # In Session-Store ablegen
    _gcs_sessions[session_token] = gcs
    
    logger.info(f"✅ GCS-Session erstellt: User={user_guid}, Mandant={mandant_guid}")
    return gcs


def get_gcs_session(session_token: str) -> Optional['PdvmCentralSystemsteuerung']:
    """
    Holt GCS-Session aus Store
    
    Args:
        session_token: JWT-Token
        
    Returns:
        PdvmCentralSystemsteuerung-Instanz oder None
    """
    return _gcs_sessions.get(session_token)


async def close_gcs_session(session_token: str):
    """
    Schließt GCS-Session (Logout)
    
    Args:
        session_token: JWT-Token
    """
    gcs = _gcs_sessions.pop(session_token, None)
    if gcs:
        # Pools schließen
        if gcs._system_pool:
            await gcs._system_pool.close()
        if gcs._mandant_pool:
            await gcs._mandant_pool.close()
        logger.info(f"✅ GCS-Session geschlossen: {session_token[:8]}...")


class PdvmCentralSystemsteuerung:
    """
    Global Configuration System
    Verwaltet Benutzer- und Mandantendaten in Session
    
    Desktop-Pattern: Separate PdvmCentralDatenbank-Instanzen für:
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
        Initialisiert GCS für User und Mandant
        
        Args:
            user_guid: UUID des Benutzers
            mandant_guid: UUID des Mandanten
            user_data: Komplette User-Daten aus sys_benutzer (aus Login)
            mandant_data: Komplette Mandant-Daten aus sys_mandanten (aus Login)
            stichtag: Aktueller Stichtag (default = aktuell)
            system_pool: Connection pool für pdvm_system Datenbank
            mandant_pool: Connection pool für mandanten Datenbank
        """
        self.user_guid = user_guid
        self.mandant_guid = mandant_guid
        self.stichtag = stichtag
        self._system_pool = system_pool
        self._mandant_pool = mandant_pool

        # Session-Cache: Base-Rows für Views (DB-Rohdaten), damit Stichtag-Wechsel nicht jedes Mal DB lesen muss.
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
        
        # ===== DESKTOP-PATTERN: Separate Instanzen =====
        
        # 1. Benutzer-Instanz (no_save=True, Daten aus Login)
        self.benutzer = PdvmCentralDatabase(
            "sys_benutzer",
            guid=None,  # Keine GUID → kein DB-Lesen
            no_save=True,  # Read-only
            stichtag=stichtag,
            system_pool=system_pool,
            mandant_pool=mandant_pool
        )
        self.benutzer.set_data(user_data)  # Daten aus Login setzen
        self.benutzer.set_guid(str(user_guid))  # GUID nachträglich setzen
        
        # 2. Mandant-Instanz (no_save=True, Daten aus Login)
        self.mandant = PdvmCentralDatabase(
            "sys_mandanten",
            guid=None,  # Keine GUID → kein DB-Lesen
            no_save=True,  # Read-only
            stichtag=stichtag,
            system_pool=system_pool,
            mandant_pool=mandant_pool
        )
        self.mandant.set_data(mandant_data)  # Daten aus Login setzen
        self.mandant.set_guid(str(mandant_guid))  # GUID nachträglich setzen
        
        # 3. Systemsteuerung-Instanz (Benutzereinstellungen, read/write)
        self.systemsteuerung = PdvmCentralDatabase(
            "sys_systemsteuerung",
            guid=None,  # Keine GUID → kein DB-Lesen
            no_save=False,  # Speicherbar
            stichtag=stichtag,
            system_pool=system_pool,
            mandant_pool=mandant_pool
        )
        
        # 4. Anwendungsdaten-Instanz (Mandanteneinstellungen, read/write)
        self.anwendungsdaten = PdvmCentralDatabase(
            "sys_anwendungsdaten",
            guid=None,  # Keine GUID → kein DB-Lesen
            no_save=False,  # Speicherbar
            stichtag=stichtag,
            system_pool=system_pool,
            mandant_pool=mandant_pool
        )
        
        # 5. Layout wird in initialize_from_db() geladen (linear)
        self.layout = None

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
        """Lineare Initialisierung: lädt systemsteuerung/anwendungsdaten/layout aus DB.

        WICHTIG: Keine create_task() / parallel init. Nach Rückkehr ist der GCS konsistent.
        """
        from app.core.pdvm_datetime import now_pdvm

        user_guid_str = str(self.user_guid)
        mandant_guid_str = str(self.mandant_guid)

        try:
            user_uuid = uuid.UUID(user_guid_str)
        except Exception:
            raise ValueError("Ungültige user_guid")

        try:
            mandant_uuid = uuid.UUID(mandant_guid_str)
        except Exception:
            raise ValueError("Ungültige mandant_guid")

        def _apply_stichtag_to_all_instances(new_stichtag: float) -> None:
            self.stichtag = float(new_stichtag)
            for inst in (self.benutzer, self.mandant, self.systemsteuerung, self.anwendungsdaten, self.layout):
                if inst is not None:
                    inst.stichtag = float(new_stichtag)

        # --- sys_systemsteuerung (User) ---
        row = await self.systemsteuerung.db.get_row(user_uuid)
        if row and row.get("daten"):
            self.systemsteuerung.set_data(row["daten"])
            self.systemsteuerung.set_guid(user_guid_str)
        else:
            logger.info(f"📝 sys_systemsteuerung für User {user_guid_str} nicht gefunden - erstelle mit Defaults")
            self.systemsteuerung.set_guid(user_guid_str)
            self.systemsteuerung.set_data({})
            self.systemsteuerung.set_value(user_guid_str, "THEME_MODE", "light", self.stichtag)
            await self.systemsteuerung.save_all_values()
            logger.info(f"✅ sys_systemsteuerung für User {user_guid_str} erstellt")

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
                logger.info(f"✅ STICHTAG initialisiert und gespeichert: {new_st}")
            except Exception as e:
                logger.error(f"❌ Fehler beim Persistieren von STICHTAG: {e}")

        # --- sys_anwendungsdaten (Mandant) ---
        row = await self.anwendungsdaten.db.get_row(mandant_uuid)
        if row and row.get("daten"):
            self.anwendungsdaten.set_data(row["daten"])
            self.anwendungsdaten.set_guid(mandant_guid_str)
        else:
            logger.info(f"📝 sys_anwendungsdaten für Mandant {mandant_guid_str} nicht gefunden - erstelle mit Defaults")
            self.anwendungsdaten.set_guid(mandant_guid_str)
            self.anwendungsdaten.set_data({})
            self.anwendungsdaten.set_value("CONFIG", "THEME_GUID", "", self.stichtag)
            await self.anwendungsdaten.save_all_values()
            logger.info(f"✅ sys_anwendungsdaten für Mandant {mandant_guid_str} erstellt")

        # --- sys_layout (Theme) ---
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
                self.layout = PdvmCentralDatabase(
                    "sys_layout",
                    guid=None,
                    no_save=True,
                    stichtag=float(self.stichtag),
                    system_pool=self._system_pool,
                    mandant_pool=self._mandant_pool,
                )
                row = await self.layout.db.get_row(theme_uuid)
                if row and row.get("daten"):
                    self.layout.set_data(row["daten"])
                else:
                    self.layout.set_data({})
                self.layout.set_guid(theme_guid_str)
                logger.info(f"✅ Layout geladen: {theme_guid_str}")
        else:
            logger.warning("⚠️ Keine THEME_GUID im Mandant-CONFIG gefunden")
    
    # === Delegierte Methoden für Kompatibilität ===
    
    def get_value(self, gruppe: str, feld: str, ab_zeit: Optional[float] = None):
        """
        Delegiert an systemsteuerung.get_value()
        Für Kompatibilität mit bestehender Layout-API
        """
        return self.systemsteuerung.get_value(gruppe, feld, ab_zeit or self.stichtag)
    
    def set_value(self, gruppe: str, feld: str, wert: Any, ab_zeit: Optional[float] = None):
        """
        Delegiert an systemsteuerung.set_value()
        Für Kompatibilität mit bestehender Layout-API
        """
        self.systemsteuerung.set_value(gruppe, feld, wert, ab_zeit or self.stichtag)
    
    async def save_all_values(self):
        """
        Delegiert an systemsteuerung.save_all_values()
        Für Kompatibilität mit GCS-API
        """
        return await self.systemsteuerung.save_all_values()
    
    # === Theme-Einstellungen ===
    
    def get_user_theme_group(self, mode: str) -> str:
        """
        Ermittelt die Layout-Gruppe basierend auf User-Präferenz
        
        Args:
            mode: 'light' oder 'dark'
            
        Returns:
            Name der Gruppe im sys_layout (z.B. "Orange_Dark")
        """
        # Mapping Key: THEME_LIGHT oder THEME_DARK
        config_key = f"THEME_{mode.upper()}"
        
        # Versuche Wert aus sys_benutzer.CONFIG zu lesen
        val = self.benutzer.get_static_value("CONFIG", config_key)
        
        # Fallback: Wenn leer, return mode selbst (für "light"/"dark" Standard)
        if not val:
            return mode
            
        return str(val)

    # === Stichtag ===
    
    def get_stichtag(self) -> float:
        """
        Liest Stichtag des Users aus user_guid Gruppe
        
        Returns:
            PDVM-Datum (z.B. 2025356.00000)
        """
        # Stichtag ist in der GCS führend; wird bei Init aus sys_systemsteuerung geladen.
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

        # Cache invalidieren (Basisdaten können bleiben, aber das stichtag-projizierte Ergebnis muss neu berechnet werden).
        # Aktuell cachen wir nur DB-Rohdaten; invalidate ist defensiv für zukünftige abgeleitete Caches.
        try:
            self._view_base_rows_cache = self._view_base_rows_cache or {}
        except Exception:
            self._view_base_rows_cache = {}

        # Stichtag über alle Instanzen synchronisieren
        for inst in (self.benutzer, self.mandant, self.systemsteuerung, self.anwendungsdaten, self.layout):
            if inst is not None:
                inst.stichtag = float(new_stichtag)
    
    # === Menu-Einstellungen ===
    
    def get_menu_toggle(self, menu_guid: str) -> int:
        """
        Liest toggle_menu für spezifisches Menü aus menu_guid Gruppe
        
        Args:
            menu_guid: UUID des Menüs
        
        Returns:
            0 = ausgeblendet, 1 = eingeblendet (default)
        """
        wert, _ = self.get_value(menu_guid, "toggle_menu", ab_zeit=self.stichtag)
        return wert if wert is not None else 1  # Default: eingeblendet
    
    def set_menu_toggle(self, menu_guid: str, toggle: int):
        """
        Setzt toggle_menu für spezifisches Menü in menu_guid Gruppe
        
        Args:
            menu_guid: UUID des Menüs
            toggle: 0 = ausblenden, 1 = einblenden
        """
        self.set_value(menu_guid, "toggle_menu", toggle, ab_zeit=self.stichtag)
    
    def get_menu_visible(self, menu_guid: str) -> bool:
        """
        Liest menu_visible für spezifisches Menü aus menu_guid Gruppe
        
        Returns:
            True = sichtbar (default), False = ausgeblendet
        """
        wert, _ = self.get_value(menu_guid, "menu_visible", ab_zeit=self.stichtag)
        return wert if wert is not None else True
    
    def set_menu_visible(self, menu_guid: str, visible: bool):
        """Setzt menu_visible für spezifisches Menü in menu_guid Gruppe"""
        self.set_value(menu_guid, "menu_visible", visible, ab_zeit=self.stichtag)
    
    # === Expert Mode ===
    
    def get_expert_mode(self) -> bool:
        """
        Liest expert_mode des Users aus user_guid Gruppe
        
        Returns:
            True = Expert Mode aktiv, False = Standard (default)
        """
        wert, _ = self.get_value(str(self.user_guid), "EXPERT_MODE", ab_zeit=self.stichtag)
        return wert if wert is not None else False
    
    def set_expert_mode(self, expert_mode: bool):
        """Setzt expert_mode des Users in user_guid Gruppe"""
        self.set_value(str(self.user_guid), "EXPERT_MODE", expert_mode, ab_zeit=self.stichtag)
    
    # === View-Einstellungen ===
    
    def get_view_controls(self, view_guid: str) -> Optional[Dict]:
        """
        Liest Controls-Konfiguration für View aus view_guid Gruppe
        
        Returns:
            Dict mit Control-Einstellungen oder None
        """
        wert, _ = self.get_value(view_guid, "controls", ab_zeit=self.stichtag)
        return wert
    
    def set_view_controls(self, view_guid: str, controls: Dict):
        """Setzt Controls-Konfiguration für View in view_guid Gruppe"""
        self.set_value(view_guid, "controls", controls, ab_zeit=self.stichtag)

    def get_view_table_state(self, view_guid: str) -> Optional[Dict]:
        """Liest Table-State (Sort/Filter) für View aus view_guid Gruppe."""
        wert, _ = self.get_value(view_guid, "table_state", ab_zeit=self.stichtag)
        return wert

    def set_view_table_state(self, view_guid: str, table_state: Dict):
        """Setzt Table-State (Sort/Filter) für View in view_guid Gruppe."""
        self.set_value(view_guid, "table_state", table_state, ab_zeit=self.stichtag)
    
    # === EDIT-Modus (temporäre Daten) ===
    
    def get_edit_value(self, feld: str) -> Any:
        """
        Liest temporären Wert aus EDIT-Gruppe
        
        Returns:
            Wert oder None
        """
        wert, _ = self.get_value("EDIT", feld, ab_zeit=self.stichtag)
        return wert
    
    def set_edit_value(self, feld: str, wert: Any):
        """Schreibt temporären Wert in EDIT-Gruppe"""
        self.set_value("EDIT", feld, wert, ab_zeit=self.stichtag)
    
    def clear_edit_data(self):
        """Löscht alle EDIT-Daten"""
        if "EDIT" in self.systemsteuerung.data:
            del self.systemsteuerung.data["EDIT"]

"""
PDVM Central Systemsteuerung
Global Configuration System für Benutzer- und Mandantendaten

Nach Desktop-Vorbild: pdvm_central_systemsteuerung.py
- Verwaltet sys_systemsteuerung (Benutzereinstellungen)
- Verwaltet sys_anwendungsdaten (Mandantendaten)
- Session-Cache für Performance
"""
import uuid
from typing import Optional, Dict, Any
from app.core.pdvm_central_datenbank import PdvmCentralDatabase
from app.core.pdvm_datenbank import PdvmDatabase


class PdvmCentralSystemsteuerung(PdvmCentralDatabase):
    """
    Global Configuration System
    Verwaltet Benutzer- und Mandantendaten in Session
    
    Vermeidet erneute DB-Zugriffe während Session durch Caching
    """
    
    def __init__(self, user_guid: uuid.UUID, mandant_guid: uuid.UUID, stichtag: float = 9999365.00000):
        """
        Initialisiert GCS für User und Mandant
        
        Args:
            user_guid: UUID des Benutzers
            mandant_guid: UUID des Mandanten
            stichtag: Aktueller Stichtag (default = aktuell)
        """
        super().__init__("sys_systemsteuerung", user_guid, stichtag)
        self.user_guid = user_guid
        self.mandant_guid = mandant_guid
        
        # Session-Cache
        self._user_data = None
        self._anwendungsdaten = None
        self._cache_loaded = False
    
    async def load_session_data(self):
        """
        Lädt alle relevanten Daten einmalig beim Session-Start
        Wird automatisch beim ersten Zugriff aufgerufen
        """
        if self._cache_loaded:
            return
        
        # Systemsteuerung (Benutzereinstellungen)
        self._user_data = await self.db.get_row(self.user_guid)
        
        # Mandantendaten aus sys_anwendungsdaten
        anwendungs_db = PdvmDatabase("sys_anwendungsdaten")
        self._anwendungsdaten = await anwendungs_db.get_row(self.mandant_guid)
        
        self._cache_loaded = True
    
    async def invalidate_cache(self):
        """Invalidiert Session-Cache (nach Änderungen)"""
        self._user_data = None
        self._anwendungsdaten = None
        self._cache_loaded = False
    
    # === Stichtag ===
    
    async def get_stichtag(self) -> float:
        """
        Liest Stichtag des Users (gecacht)
        
        Returns:
            PDVM-Datum (z.B. 2025356.00000)
        """
        if not self._cache_loaded:
            await self.load_session_data()
        
        stichtag = await self.get_static_value(str(self.user_guid), "stichtag")
        return stichtag if stichtag is not None else 9999365.00000
    
    async def set_stichtag(self, stichtag: float):
        """
        Setzt Stichtag des Users
        
        Args:
            stichtag: PDVM-Datum
        """
        await self.set_static_value(str(self.user_guid), "stichtag", stichtag)
        self.stichtag = stichtag
        await self.invalidate_cache()
    
    # === Menu-Einstellungen ===
    
    async def get_menu_toggle(self, menu_guid: str) -> int:
        """
        Liest toggle_menu für spezifisches Menü
        
        Args:
            menu_guid: UUID des Menüs
        
        Returns:
            0 = ausgeblendet, 1 = eingeblendet (default)
        """
        value = await self.get_static_value(menu_guid, "toggle_menu")
        return value if value is not None else 1  # Default: eingeblendet
    
    async def set_menu_toggle(self, menu_guid: str, toggle: int):
        """
        Setzt toggle_menu für spezifisches Menü
        
        Args:
            menu_guid: UUID des Menüs
            toggle: 0 = ausblenden, 1 = einblenden
        """
        await self.set_static_value(menu_guid, "toggle_menu", toggle)
    
    async def get_menu_visible(self, menu_guid: str) -> bool:
        """
        Liest menu_visible für spezifisches Menü
        
        Returns:
            True = sichtbar (default), False = ausgeblendet
        """
        value = await self.get_static_value(menu_guid, "menu_visible")
        return value if value is not None else True
    
    async def set_menu_visible(self, menu_guid: str, visible: bool):
        """Setzt menu_visible für spezifisches Menü"""
        await self.set_static_value(menu_guid, "menu_visible", visible)
    
    # === Expert Mode ===
    
    async def get_expert_mode(self) -> bool:
        """
        Liest expert_mode des Users
        
        Returns:
            True = Expert Mode aktiv, False = Standard (default)
        """
        value = await self.get_static_value(str(self.user_guid), "expert_mode")
        return value if value is not None else False
    
    async def set_expert_mode(self, expert_mode: bool):
        """Setzt expert_mode des Users"""
        await self.set_static_value(str(self.user_guid), "expert_mode", expert_mode)
        await self.invalidate_cache()
    
    # === Anwendungsdaten (Mandant) ===
    
    async def get_anwendungsdaten(self, gruppe: str, feld: str) -> Any:
        """
        Liest Mandantendaten aus sys_anwendungsdaten (gecacht)
        
        Args:
            gruppe: Gruppe in sys_anwendungsdaten
            feld: Feld in Gruppe
        
        Returns:
            Wert oder None
        """
        if not self._cache_loaded:
            await self.load_session_data()
        
        if not self._anwendungsdaten or not self._anwendungsdaten['daten']:
            return None
        
        daten = self._anwendungsdaten['daten']
        if gruppe not in daten:
            return None
        
        return daten[gruppe].get(feld)
    
    async def set_anwendungsdaten(self, gruppe: str, feld: str, wert: Any):
        """
        Schreibt Mandantendaten in sys_anwendungsdaten
        
        Args:
            gruppe: Gruppe in sys_anwendungsdaten
            feld: Feld in Gruppe
            wert: Zu setzender Wert
        """
        anwendungs_db = PdvmCentralDatabase("sys_anwendungsdaten", self.mandant_guid)
        await anwendungs_db.set_static_value(gruppe, feld, wert)
        await self.invalidate_cache()
    
    # === Allgemeine Wert-Zugriffe ===
    
    async def get_user_value(self, feld: str) -> Any:
        """
        Liest Wert aus user_guid-Gruppe
        
        Args:
            feld: Feldname (z.B. "version", "window_width")
        
        Returns:
            Wert oder None
        """
        return await self.get_static_value(str(self.user_guid), feld)
    
    async def set_user_value(self, feld: str, wert: Any):
        """
        Schreibt Wert in user_guid-Gruppe
        
        Args:
            feld: Feldname
            wert: Zu setzender Wert
        """
        await self.set_static_value(str(self.user_guid), feld, wert)
    
    # === View-Einstellungen ===
    
    async def get_view_controls(self, view_guid: str) -> Optional[Dict]:
        """
        Liest Controls-Konfiguration für View
        
        Returns:
            Dict mit Control-Einstellungen oder None
        """
        return await self.get_static_value(view_guid, "controls")
    
    async def set_view_controls(self, view_guid: str, controls: Dict):
        """Setzt Controls-Konfiguration für View"""
        await self.set_static_value(view_guid, "controls", controls)
    
    # === EDIT-Modus (temporäre Daten) ===
    
    async def get_edit_value(self, feld: str) -> Any:
        """
        Liest temporären Wert aus EDIT-Gruppe
        
        Returns:
            Wert oder None
        """
        return await self.get_static_value("EDIT", feld)
    
    async def set_edit_value(self, feld: str, wert: Any):
        """Schreibt temporären Wert in EDIT-Gruppe"""
        await self.set_static_value("EDIT", feld, wert)
    
    async def clear_edit_data(self):
        """Löscht alle EDIT-Daten"""
        row = await self.db.get_row(self.uid)
        if not row or not row['daten']:
            return
        
        daten = row['daten']
        if "EDIT" in daten:
            del daten["EDIT"]
            await self.db.update(self.uid, daten)

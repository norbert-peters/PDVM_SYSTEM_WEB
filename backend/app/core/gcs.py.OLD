#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WEB-GCS: Zentrale Systemsteuerung für Web-Anwendung

Vereinfachte Version der Desktop-GCS für Web:
- Kein PyQt, keine Signals
- Session-basiert (keine globale Instanz)
- Async-first mit asyncpg
- Fokus auf: User/Mandant-Daten, Stichtag, Properties, Menu-Zugriff
"""

import logging
from typing import Dict, Any, Optional
from datetime import datetime
import json
import asyncpg

logger = logging.getLogger(__name__)


class WebGCS:
    """
    Web-Zentrale Systemsteuerung
    
    Session-Instanz die nach Mandantenwahl erstellt wird.
    Verwaltet:
    - User-Daten (cached aus sys_benutzer)
    - Mandanten-Zugriff (cached aus sys_mandanten)
    - Berechtigungen (cached)
    - Systemsteuerung (sys_systemsteuerung in System-DB)
    - Anwendungsdaten (sys_anwendungsdaten in Mandanten-DB)
    - Stichtag (systemweit)
    - Properties (persistent in sys_systemsteuerung)
    - Connection Pools (system + mandant per session)
    """
    
    def __init__(
        self, 
        user_guid: str,
        user_data: dict,
        mandant_guid: str,
        mandant_data: dict,
        system_db_url: str,
        mandant_db_url: str,
        mandanten_access: list = None,
        berechtigungen: dict = None
    ):
        """
        Initialisiere GCS-Session
        
        Args:
            user_guid: UUID des Users aus sys_benutzer
            user_data: User-Daten (JSONB, cached beim Login)
            mandant_guid: UUID des Mandanten
            mandant_data: Mandanten-Daten (cached beim Login)
            system_db_url: Connection-String zur System-DB (mandant-specific!)
            mandant_db_url: Connection-String zur Mandanten-DB
            mandanten_access: Liste aller Mandanten mit Zugriff (cached)
            berechtigungen: Berechtigungen für aktuellen Mandanten (cached)
        """
        self.user_guid = user_guid
        self.user_data = user_data
        self.mandant_guid = mandant_guid
        self.mandant_data = mandant_data
        self.system_db_url = system_db_url
        self.mandant_db_url = mandant_db_url
        
        # Cached data (from login)
        self._mandanten_access = mandanten_access or []
        self._berechtigungen = berechtigungen or {}
        
        # Session-Daten (Cache)
        self._systemsteuerung: Dict[str, Any] = {}
        self._anwendungsdaten: Dict[str, Any] = {}
        
        # Stichtag (PDVM-Format als float)
        self._stichtag: Optional[float] = None
        
        # DB-Pools für Performance (per session!)
        self._system_pool: Optional[asyncpg.Pool] = None
        self._mandant_pool: Optional[asyncpg.Pool] = None
        
        logger.info(f"✅ WebGCS initialisiert: User={user_guid}, Mandant={mandant_guid}")
    
    async def initialize(self):
        """
        Async-Initialisierung: Erstellt Pools, lädt Daten
        
        MUSS nach __init__ aufgerufen werden!
        """
        # System-DB Pool erstellen (für Strukturdaten/Layouts)
        self._system_pool = await asyncpg.create_pool(
            self.system_db_url,
            min_size=2,
            max_size=10
        )
        
        # Mandanten-DB Pool erstellen (für Fachdaten)
        self._mandant_pool = await asyncpg.create_pool(
            self.mandant_db_url,
            min_size=2,
            max_size=10
        )
        
        # Systemsteuerung laden (aus System-DB!)
        await self._load_systemsteuerung()
        
        # Stichtag initialisieren
        await self._init_stichtag()
        
        logger.info(f"✅ WebGCS vollständig initialisiert mit beiden Pools")
    
    async def close(self):
        """Schließt beide DB-Pools"""
        if self._system_pool:
            await self._system_pool.close()
        if self._mandant_pool:
            await self._mandant_pool.close()
        logger.info("✅ WebGCS geschlossen")
    
    async def _load_systemsteuerung(self):
        """Lädt sys_systemsteuerung aus Mandanten-DB (nicht System-DB!)"""
        async with self._mandant_pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT daten FROM sys_systemsteuerung WHERE uid = $1 AND historisch = 0",
                self.user_guid
            )
            
            if row:
                data = row['daten']
                if isinstance(data, str):
                    self._systemsteuerung = json.loads(data)
                else:
                    self._systemsteuerung = data
                logger.info(f"✅ Systemsteuerung geladen: {len(self._systemsteuerung)} Properties")
            else:
                # Erstelle leeren Eintrag
                await conn.execute(
                    """INSERT INTO sys_systemsteuerung (uid, daten, name, historisch)
                       VALUES ($1, $2, $3, 0)""",
                    self.user_guid,
                    json.dumps({}),
                    f"User {self.user_guid}"
                )
                logger.info("✅ Systemsteuerung initialisiert (leer)")
    
    async def _init_stichtag(self):
        """Initialisiert Stichtag aus Systemsteuerung oder setzt aktuellen"""
        from .pdvm_datetime import now_pdvm
        
        stored_stichtag = self._systemsteuerung.get('stichtag')
        
        # Validierung: Sentinel-Werte ablehnen
        is_valid = False
        if stored_stichtag is not None:
            try:
                st_float = float(stored_stichtag)
                if st_float != 1001.0 and st_float != 9999365.0 and st_float > 0:
                    self._stichtag = st_float
                    is_valid = True
                    logger.info(f"✅ Stichtag aus DB geladen: {self._stichtag}")
            except (ValueError, TypeError):
                pass
        
        if not is_valid:
            # Aktuellen Zeitstempel setzen und speichern
            self._stichtag = now_pdvm()
            await self.set_property('stichtag', self._stichtag)
            logger.info(f"💾 Stichtag auf aktuellen Timestamp gesetzt: {self._stichtag}")
    
    @property
    def stichtag(self) -> float:
        """Stichtag als PDVM-Timestamp (float)"""
        return self._stichtag
    
    async def set_stichtag(self, value: float):
        """Setze neuen Stichtag und speichere persistent"""
        self._stichtag = float(value)
        await self.set_property('stichtag', self._stichtag)
        logger.info(f"💾 Stichtag aktualisiert: {self._stichtag}")
    
    @property
    def country(self) -> str:
        """Country aus User-Daten (SETTINGS.COUNTRY)"""
        try:
            settings = self.user_data.get('SETTINGS', {})
            return settings.get('COUNTRY', 'DEU')
        except:
            return 'DEU'
    
    @property
    def language(self) -> str:
        """Language aus User-Daten (SETTINGS.LANGUAGE)"""
        try:
            settings = self.user_data.get('SETTINGS', {})
            return settings.get('LANGUAGE', 'de-de')
        except:
            return 'de-de'
    
    @property
    def mode(self) -> str:
        """Mode aus User-Daten (SETTINGS.MODE) - 'user' oder 'admin'"""
        try:
            settings = self.user_data.get('SETTINGS', {})
            mode_value = settings.get('MODE', 'user')
            if mode_value not in ['user', 'admin']:
                return 'user'
            return mode_value
        except:
            return 'user'
    
    @property
    def expert_mode(self) -> bool:
        """Expert-Modus aus Systemsteuerung"""
        return self._systemsteuerung.get('expert_mode', False)
    
    async def set_expert_mode(self, value: bool):
        """Setze Expert-Modus persistent"""
        await self.set_property('expert_mode', bool(value))
        logger.info(f"💾 ExpertMode aktualisiert: {value}")
    
    # Cached data accessors (from login)
    
    @property
    def mandanten_access(self) -> list:
        """Liste aller Mandanten zu denen User Zugriff hat (cached from login)"""
        return self._mandanten_access
    
    @property
    def berechtigungen(self) -> dict:
        """Berechtigungen für aktuellen Mandanten (cached from login)"""
        return self._berechtigungen
    
    def has_permission(self, permission: str) -> bool:
        """
        Prüft ob User eine bestimmte Berechtigung hat
        
        Args:
            permission: Berechtigungs-Name (z.B. 'can_edit', 'is_admin')
            
        Returns:
            True wenn Berechtigung vorhanden
        """
        return self._berechtigungen.get(permission, False)
    
    # Pool accessors
    
    @property
    def system_pool(self) -> asyncpg.Pool:
        """Connection Pool zur System-DB (für Strukturdaten/Layouts)"""
        return self._system_pool
    
    @property
    def mandant_pool(self) -> asyncpg.Pool:
        """Connection Pool zur Mandanten-DB (für Fachdaten)"""
        return self._mandant_pool
    
    async def get_property(self, key: str, default: Any = None) -> Any:
        """
        Hole Property aus Systemsteuerung (Cache)
        
        Args:
            key: Property-Name
            default: Fallback-Wert
            
        Returns:
            Property-Wert oder default
        """
        return self._systemsteuerung.get(key, default)
    
    async def set_property(self, key: str, value: Any):
        """
        Setze Property in Systemsteuerung (Cache + DB)
        
        Args:
            key: Property-Name
            value: Wert (muss JSON-serialisierbar sein)
        """
        self._systemsteuerung[key] = value
        
        # Persistent speichern in Mandanten-DB (nicht System-DB!)
        async with self._mandant_pool.acquire() as conn:
            await conn.execute(
                """UPDATE sys_systemsteuerung 
                   SET daten = $1, modified_at = CURRENT_TIMESTAMP
                   WHERE uid = $2 AND historisch = 0""",
                json.dumps(self._systemsteuerung),
                self.user_guid
            )
    
    async def get_app_data(self, gruppe: str, key: str, default: Any = None) -> Any:
        """
        Hole Anwendungsdaten (z.B. Filter, Suchen)
        
        Struktur: sys_anwendungsdaten.daten = {gruppe: {key: value}}
        Beispiel: gruppe='view_guid', key='default_filter'
        
        Args:
            gruppe: Gruppen-Name (z.B. view_guid)
            key: Feld-Name
            default: Fallback-Wert
            
        Returns:
            Wert oder default
        """
        # Lazy-Load: Nur laden wenn nicht im Cache
        if not self._anwendungsdaten:
            async with self._mandant_pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT daten FROM sys_anwendungsdaten WHERE uid = $1 AND historisch = 0",
                    self.user_guid
                )
                
                if row:
                    data = row['daten']
                    if isinstance(data, str):
                        self._anwendungsdaten = json.loads(data)
                    else:
                        self._anwendungsdaten = data
                else:
                    # Erstelle leeren Eintrag
                    await conn.execute(
                        """INSERT INTO sys_anwendungsdaten (uid, daten, name, historisch)
                           VALUES ($1, $2, $3, 0)""",
                        self.user_guid,
                        json.dumps({}),
                        f"User {self.user_guid}"
                    )
        
        return self._anwendungsdaten.get(gruppe, {}).get(key, default)
    
    async def set_app_data(self, gruppe: str, key: str, value: Any):
        """
        Setze Anwendungsdaten persistent
        
        Args:
            gruppe: Gruppen-Name (z.B. view_guid)
            key: Feld-Name
            value: Wert (JSON-serialisierbar)
        """
        if gruppe not in self._anwendungsdaten:
            self._anwendungsdaten[gruppe] = {}
        
        self._anwendungsdaten[gruppe][key] = value
        
        # Persistent speichern
        async with self._mandant_pool.acquire() as conn:
            await conn.execute(
                """UPDATE sys_anwendungsdaten 
                   SET daten = $1, modified_at = CURRENT_TIMESTAMP
                   WHERE uid = $2 AND historisch = 0""",
                json.dumps(self._anwendungsdaten),
                self.user_guid
            )
    
    def get_menu_guid(self, app_name: str = 'START') -> Optional[str]:
        """
        Hole Menü-GUID für App aus User-Daten
        
        Args:
            app_name: App-Name (default: 'START' für Startmenü)
            
        Returns:
            Menu-GUID oder None
        """
        try:
            meineapps = self.user_data.get('MEINEAPPS', {})
            
            if app_name == 'START':
                # Startmenü aus MEINEAPPS.START.MENU
                start_data = meineapps.get('START', {})
                menu_guid = start_data.get('MENU')
                logger.debug(f"🎯 START.MENU GUID: {menu_guid}")
                return menu_guid
            else:
                # Andere Apps aus ANWENDUNGEN
                anwendungen = self.user_data.get('ANWENDUNGEN', {})
                app_data = anwendungen.get(app_name.upper(), {})
                menu_guid = app_data.get('MENU')
                logger.debug(f"🎯 {app_name}.MENU GUID: {menu_guid}")
                return menu_guid
        except Exception as e:
            logger.error(f"❌ Fehler beim Holen der Menu-GUID für {app_name}: {e}")
            return None
    
    async def get_menu_data(self, menu_guid: str, db_name: str = "pdvm_system") -> Optional[dict]:
        """
        Lädt Menü-Daten aus sys_menudaten
        
        Args:
            menu_guid: GUID des Menüs
            db_name: Datenbank-Name (default: pdvm_system)
            
        Returns:
            Menu-Daten (JSONB) oder None
        """
        # DB-Connection zur angegebenen Datenbank
        # TODO: Multi-DB-Support - aktuell nur Mandanten-DB
        async with self._mandant_pool.acquire() as conn:
            # Prüfe ob sys_menudaten in Mandanten-DB existiert
            table_exists = await conn.fetchval("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name = 'sys_menudaten'
                )
            """)
            
            if not table_exists:
                logger.warning(f"⚠️ sys_menudaten existiert nicht in Mandanten-DB")
                return None
            
            row = await conn.fetchrow(
                "SELECT uid, name, daten FROM sys_menudaten WHERE uid = $1 AND historisch = 0",
                menu_guid
            )
            
            if not row:
                logger.warning(f"⚠️ Menü {menu_guid} nicht gefunden")
                return None
            
            menu_data = row['daten']
            if isinstance(menu_data, str):
                menu_data = json.loads(menu_data)
            
            return {
                'uid': str(row['uid']),
                'name': row['name'],
                'menu_data': menu_data
            }
    
    def to_dict(self) -> dict:
        """
        Serialisiert GCS für Session-Storage
        
        Returns:
            Dictionary mit allen relevanten Daten
        """
        return {
            'user_guid': self.user_guid,
            'user_data': self.user_data,
            'mandant_guid': self.mandant_guid,
            'mandant_data': self.mandant_data,
            'mandant_db_url': self.mandant_db_url,
            'stichtag': self._stichtag,
            'systemsteuerung': self._systemsteuerung,
            'anwendungsdaten': self._anwendungsdaten
        }
    
    @classmethod
    async def from_dict(cls, data: dict) -> 'WebGCS':
        """
        Deserialisiert GCS aus Session-Storage
        
        Args:
            data: Dictionary von to_dict()
            
        Returns:
            WebGCS-Instanz
        """
        gcs = cls(
            user_guid=data['user_guid'],
            user_data=data['user_data'],
            mandant_guid=data['mandant_guid'],
            mandant_data=data['mandant_data'],
            mandant_db_url=data['mandant_db_url']
        )
        
        # Async-Init
        await gcs.initialize()
        
        # Cache wiederherstellen
        gcs._stichtag = data.get('stichtag')
        gcs._systemsteuerung = data.get('systemsteuerung', {})
        gcs._anwendungsdaten = data.get('anwendungsdaten', {})
        
        return gcs


# Session-Storage: In-Memory für MVP (später Redis/Memcached)
_gcs_sessions: Dict[str, WebGCS] = {}


async def create_gcs_session(
    user_guid: str,
    user_data: dict,
    mandant_guid: str,
    mandant_data: dict,
    system_db_url: str,
    mandant_db_url: str,
    session_token: str,
    mandanten_access: list = None,
    berechtigungen: dict = None
) -> WebGCS:
    """
    Erstellt neue GCS-Session
    
    Args:
        user_guid: User UUID
        user_data: User-Daten (cached from login)
        mandant_guid: Mandanten UUID
        mandant_data: Mandanten-Daten (cached from login)
        system_db_url: Connection-String zur System-DB (mandant-specific!)
        mandant_db_url: Connection-String zur Mandanten-DB
        session_token: JWT-Token als Session-Key
        mandanten_access: Liste aller Mandanten mit Zugriff (cached)
        berechtigungen: Berechtigungen für aktuellen Mandanten (cached)
        
    Returns:
        WebGCS-Instanz
    """
    gcs = WebGCS(
        user_guid, 
        user_data, 
        mandant_guid, 
        mandant_data, 
        system_db_url,
        mandant_db_url,
        mandanten_access,
        berechtigungen
    )
    await gcs.initialize()
    
    # In Session-Store ablegen
    _gcs_sessions[session_token] = gcs
    
    logger.info(f"✅ GCS-Session erstellt: {session_token[:8]}...")
    return gcs


def get_gcs_session(session_token: str) -> Optional[WebGCS]:
    """
    Holt GCS-Session aus Store
    
    Args:
        session_token: JWT-Token
        
    Returns:
        WebGCS-Instanz oder None
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
        await gcs.close()
        logger.info(f"✅ GCS-Session geschlossen: {session_token[:8]}...")

"""
Data Manager Layer
Business Logic für spezifische Datentypen

Nach Desktop-Vorbild: PdvmCentralDatenbank
Hält Instanzen im Memory, validiert, cached
"""
import logging
from typing import Dict, List, Optional, Any
from uuid import UUID, uuid4
from datetime import datetime
from .pdvm_database import PdvmDatabaseService

logger = logging.getLogger(__name__)


class MandantDataManager:
    """
    DataManager für Mandanten
    
    Features:
    - In-Memory Cache
    - Validierung
    - Geschäftslogik
    - Berechtigungsprüfung
    """
    
    def __init__(self):
        # Database Service für sys_mandanten Tabelle
        self.db_service = PdvmDatabaseService(database="auth", table="sys_mandanten")
        
        # In-Memory Cache
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._cache_loaded = False
    
    async def _load_cache(self, force: bool = False):
        """Lädt alle Mandanten in Cache"""
        if self._cache_loaded and not force:
            return
        
        mandanten = await self.db_service.list_all(historisch=0)
        self._cache = {str(m['uid']): m for m in mandanten}
        self._cache_loaded = True
        logger.info(f"📦 Mandanten-Cache geladen: {len(self._cache)} Mandanten")
    
    async def list_all(self, include_inactive: bool = False) -> List[Dict[str, Any]]:
        """
        Liste aller Mandanten
        
        Args:
            include_inactive: Auch historische Mandanten
            
        Returns:
            Liste von Mandanten
        """
        await self._load_cache()
        
        if include_inactive:
            # Direkt aus DB für historische
            return await self.db_service.list_all(historisch=None)
        
        return list(self._cache.values())
    
    async def get_by_id(self, mandant_id: str | UUID) -> Optional[Dict[str, Any]]:
        """
        Lädt Mandant per ID
        
        Args:
            mandant_id: UUID des Mandanten
            
        Returns:
            Mandant oder None
        """
        await self._load_cache()
        
        mandant_id = str(mandant_id)
        
        # Erst Cache prüfen
        if mandant_id in self._cache:
            return self._cache[mandant_id]
        
        # Sonst DB
        mandant = await self.db_service.get_by_uid(mandant_id)
        if mandant:
            self._cache[mandant_id] = mandant
        
        return mandant
    
    async def create(
        self,
        name: str,
        database: str,
        description: str = "",
        is_allowed: bool = True,
        config: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Erstellt neuen Mandanten
        
        Args:
            name: Mandanten-Name
            database: Datenbank-Name
            description: Beschreibung
            is_allowed: Berechtigung aktiv
            config: Zusätzliche Konfiguration
            
        Returns:
            Erstellter Mandant
        """
        # Validierung
        if not name or len(name) < 3:
            raise ValueError("Name muss mindestens 3 Zeichen haben")
        
        if not database:
            raise ValueError("Datenbank-Name erforderlich")
        
        # Daten-Struktur
        daten = {
            "MANDANT": {
                "DATABASE": database,
                "IS_ALLOWED": is_allowed,
                "DESCRIPTION": description,
                "CREATED": datetime.now().isoformat()
            },
            "CONFIG": config or {},
            "SECURITY": {
                "ALLOWED_USERS": [],  # UIDs von berechtigten Usern
                "ALLOWED_ROLES": []
            }
        }
        
        # In DB erstellen
        mandant = await self.db_service.create(
            daten=daten,
            name=name
        )
        
        # Cache aktualisieren
        self._cache[str(mandant['uid'])] = mandant
        
        logger.info(f"✅ Mandant erstellt: {name} (UID: {mandant['uid']})")
        return mandant
    
    async def update(
        self,
        mandant_id: str | UUID,
        name: Optional[str] = None,
        description: Optional[str] = None,
        is_allowed: Optional[bool] = None,
        config: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Aktualisiert Mandanten
        
        Args:
            mandant_id: UUID des Mandanten
            name: Neuer Name
            description: Neue Beschreibung
            is_allowed: Neue Berechtigung
            config: Neue Konfiguration
            
        Returns:
            Aktualisierter Mandant
        """
        # Lade aktuellen Stand
        mandant = await self.get_by_id(mandant_id)
        if not mandant:
            raise ValueError(f"Mandant nicht gefunden: {mandant_id}")
        
        # Update Daten
        daten = mandant['daten'].copy()
        
        if description is not None:
            daten['MANDANT']['DESCRIPTION'] = description
        
        if is_allowed is not None:
            daten['MANDANT']['IS_ALLOWED'] = is_allowed
        
        if config is not None:
            daten['CONFIG'].update(config)
        
        daten['MANDANT']['MODIFIED'] = datetime.now().isoformat()
        
        # In DB updaten
        updated = await self.db_service.update(
            uid=mandant_id,
            daten=daten,
            name=name if name is not None else mandant['name'],
            backup_old=True
        )
        
        # Cache aktualisieren
        self._cache[str(mandant_id)] = updated
        
        logger.info(f"✅ Mandant aktualisiert: {mandant_id}")
        return updated
    
    async def check_access(
        self,
        mandant_id: str | UUID,
        user_id: Optional[str | UUID] = None
    ) -> bool:
        """
        Prüft ob User Zugriff auf Mandant hat
        
        Args:
            mandant_id: UUID des Mandanten
            user_id: UUID des Users (optional, später für Rechte)
            
        Returns:
            True wenn berechtigt
        """
        mandant = await self.get_by_id(mandant_id)
        
        if not mandant:
            return False
        
        # Prüfe is_allowed Flag
        is_allowed = mandant['daten'].get('MANDANT', {}).get('IS_ALLOWED', False)
        
        # TODO: Später User-spezifische Rechte prüfen
        # if user_id:
        #     allowed_users = mandant['daten'].get('SECURITY', {}).get('ALLOWED_USERS', [])
        #     if str(user_id) not in allowed_users:
        #         return False
        
        return is_allowed
    
    async def get_database_name(self, mandant_id: str | UUID) -> Optional[str]:
        """
        Gibt Datenbank-Name für Mandant zurück
        
        Args:
            mandant_id: UUID des Mandanten
            
        Returns:
            Datenbank-Name oder None
        """
        mandant = await self.get_by_id(mandant_id)
        
        if not mandant:
            return None
        
        return mandant['daten'].get('MANDANT', {}).get('DATABASE')
    
    async def deactivate(self, mandant_id: str | UUID) -> Dict[str, Any]:
        """
        Deaktiviert Mandanten (soft delete)
        
        Args:
            mandant_id: UUID des Mandanten
            
        Returns:
            Aktualisierter Mandant
        """
        return await self.update(mandant_id, is_allowed=False)
    
    async def delete(self, mandant_id: str | UUID, hard: bool = False) -> bool:
        """
        Löscht Mandanten
        
        Args:
            mandant_id: UUID des Mandanten
            hard: True=wirklich löschen, False=historisch setzen
            
        Returns:
            True wenn erfolgreich
        """
        success = await self.db_service.delete(mandant_id, soft=not hard)
        
        # Aus Cache entfernen
        if str(mandant_id) in self._cache:
            del self._cache[str(mandant_id)]
        
        return success
    
    def clear_cache(self):
        """Leert Cache (für Tests/Reload)"""
        self._cache.clear()
        self._cache_loaded = False
        logger.info("🗑️  Mandanten-Cache geleert")


class PersonDataManager:
    """
    DataManager für Persondaten
    Beispiel für mandanten-spezifische Daten
    """
    
    def __init__(self, mandant_database: str):
        """
        Args:
            mandant_database: Name der Mandanten-Datenbank
        """
        self.db_service = PdvmDatabaseService(
            database=mandant_database,
            table="persondaten"
        )
        self._cache: Dict[str, Dict[str, Any]] = {}
    
    async def list_all(self) -> List[Dict[str, Any]]:
        """Liste aller Personen"""
        return await self.db_service.list_all(historisch=0)
    
    async def get_by_id(self, person_id: str | UUID) -> Optional[Dict[str, Any]]:
        """Lädt Person per ID"""
        # Erst Cache
        if str(person_id) in self._cache:
            return self._cache[str(person_id)]
        
        # Dann DB
        person = await self.db_service.get_by_uid(person_id)
        if person:
            self._cache[str(person_id)] = person
        
        return person
    
    async def create(
        self,
        personalnummer: str,
        familienname: str,
        vorname: str,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Erstellt neue Person
        
        Args:
            personalnummer: Personalnummer
            familienname: Nachname
            vorname: Vorname
            **kwargs: Weitere Felder
            
        Returns:
            Erstellte Person
        """
        # Validierung
        if not personalnummer or not familienname or not vorname:
            raise ValueError("Personalnummer, Familienname und Vorname erforderlich")
        
        # PDVM-Datenstruktur
        heute = datetime.now().strftime("%Y%j.0")  # YYYYDDD Format
        
        daten = {
            "ROOT": {},
            "PERSDATEN": {
                "PERSONALNUMMER": {heute: personalnummer},
                "FAMILIENNAME": {heute: familienname},
                "VORNAME": {heute: vorname},
                "ANREDE": {heute: kwargs.get('anrede', '')},
                "GEBURTSDATUM": {heute: kwargs.get('geburtsdatum', '')}
            },
            "ANSCHRIFT_PERSON": {
                "STRASSE": {heute: kwargs.get('strasse', '')},
                "PLZ": {heute: kwargs.get('plz', '')},
                "ORT": {heute: kwargs.get('ort', '')}
            }
        }
        
        name = f"{vorname} {familienname}"
        
        person = await self.db_service.create(daten=daten, name=name)
        
        # Cache
        self._cache[str(person['uid'])] = person
        
        logger.info(f"✅ Person erstellt: {name}")
        return person
    
    async def search_by_name(self, search_term: str) -> List[Dict[str, Any]]:
        """Sucht Personen nach Name"""
        return await self.db_service.search(
            search_term=search_term,
            search_fields=['name']
        )

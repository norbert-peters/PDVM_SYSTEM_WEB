"""
PDVM Central Database
Business-Logic-Layer für strukturierte Datenverwaltung

Nach Desktop-Vorbild: v2_pdvm_central_datenbank.py
- Nutzt PdvmDatabase für alle DB-Operationen
- Linear: get_value/set_value für Gruppe/Feld-basierte Zugriffe
- Automatische Zeitstempel-Verwaltung für historische Daten
- Fokus auf Business-Logik, nicht auf JSON-Parsing oder DB-Details
"""
import uuid
import logging
import copy
from typing import Dict, Optional, Any, List
from app.core.pdvm_datenbank import PdvmDatabase
from app.core.pdvm_datetime import PdvmDateTime

logger = logging.getLogger(__name__)


class PdvmCentralDatabase:
    """
    Business-Logic-Layer für strukturierte Datenverwaltung
    
    Verwaltet Daten in Gruppe/Feld-Struktur mit optionaler Zeithistorie.
    Nutzt PdvmDatabase für alle Persistierung - KEINE eigene DB-Logik.
    """
    
    def __init__(
        self,
        table_name: str,
        guid: Optional[str] = None,
        no_save: bool = False,
        stichtag: float = 9999365.00000,
        system_pool: Optional[Any] = None,
        mandant_pool: Optional[Any] = None,
        _skip_load: bool = False
    ):
        """
        Initialisiert die Business-Logic-Schicht
        
        WICHTIG: Nutze load() statt __init__ wenn Daten aus DB geladen werden sollen!
        
        Args:
            table_name: Name der Tabelle
            guid: GUID des Datensatzes (falls None, muss später gesetzt werden)
            no_save: Wenn True, verhindert save_all_values() die Persistierung
            stichtag: PDVM-Datum für Zeitpunkt-basierte Sicht
            system_pool: Connection pool für pdvm_system Datenbank
            mandant_pool: Connection pool für mandanten Datenbank
            _skip_load: INTERN - verhindert Auto-Load in Factory-Methode
        """
        self.table_name = table_name
        self.guid = str(guid) if guid else None
        self.no_save = no_save
        self.stichtag = stichtag
        self.db = PdvmDatabase(table_name, system_pool=system_pool, mandant_pool=mandant_pool)
        
        # Daten-Cache (wird bei Bedarf geladen)
        self.data: Dict[str, Any] = {}
        self._loaded_snapshot: Optional[Dict[str, Any]] = None
        self._data_loaded = False
        self.actor_user_uid: Optional[str] = None
        self.actor_ip: Optional[str] = None
        
        # Historisch-Status ermitteln
        self.historisch = False  # TODO: Aus Tabellen-Config holen
        
        logger.info(f"PdvmCentralDatabase initialisiert: {table_name}.{guid} (historisch: {self.historisch}, no_save: {no_save})")
    
    @classmethod
    async def load(
        cls,
        table_name: str,
        guid: str,
        no_save: bool = False,
        stichtag: float = 9999365.00000,
        system_pool: Optional[Any] = None,
        mandant_pool: Optional[Any] = None
    ) -> 'PdvmCentralDatabase':
        """
        Factory-Methode: Erstellt Instanz UND lädt Daten aus Datenbank.
        
        STANDARD-PATTERN für Datenzugriff:
        ```python
        menu = await PdvmCentralDatabase.load("sys_menudaten", menu_guid, system_pool=pool)
        grund = menu.get_value_by_group("GRUND")
        ```
        
        Args:
            table_name: Name der Tabelle
            guid: GUID des zu ladenden Datensatzes
            (weitere wie __init__)
            
        Returns:
            PdvmCentralDatabase: Instanz mit geladenen Daten
        """
        # Erstelle Instanz ohne Auto-Load
        instance = cls(
            table_name=table_name,
            guid=guid,
            no_save=no_save,
            stichtag=stichtag,
            system_pool=system_pool,
            mandant_pool=mandant_pool,
            _skip_load=True
        )
        
        # Lade Daten aus DB
        try:
            guid_uuid = uuid.UUID(guid)
            row = await instance.db.get_by_uid(guid_uuid)
            
            if row and "daten" in row:
                try:
                    instance.historisch = int(row.get("historisch") or 0) == 1
                except Exception:
                    instance.historisch = False
                instance.data = row["daten"]
                instance._loaded_snapshot = copy.deepcopy(instance.data)
                instance._data_loaded = True
                logger.info(f"✅ Daten geladen für {table_name}.{guid}: {len(instance.data)} Gruppen")
            else:
                logger.warning(f"⚠️ Keine Daten gefunden für {table_name}.{guid} - leere Instanz")
                instance.data = {}
                instance._loaded_snapshot = None
                instance._data_loaded = True
                
        except Exception as e:
            logger.error(f"❌ Fehler beim Laden von {table_name}.{guid}: {e}")
            instance.data = {}
            instance._data_loaded = False
            raise
        
        return instance
    
    def _get_current_timestamp(self) -> float:
        """
        Erstellt aktuellen Zeitstempel für historische Daten.
        
        Returns:
            float: Zeitstempel im PDVM-Format
        """
        dt_instance = PdvmDateTime()
        return float(dt_instance.now().pdvm_datetime_str.replace('.', ''))
    
    def set_guid(self, guid: str):
        """
        Setzt GUID ohne DB-Lesen (für Setup-Phase)
        
        Args:
            guid: Die zu setzende GUID (als String oder UUID)
        """
        self.guid = str(guid) if guid else None
        logger.debug(f"GUID gesetzt ohne DB-Lesen: {self.guid}")
    
    def set_data(self, daten: Dict[str, Any], guid: str = None):
        """
        Setzt Daten direkt in die Instanz ohne DB-Zugriff.
        
        PERFORMANCE-OPTIMIERUNG für Views:
        Wenn alle Daten bereits geladen sind (z.B. aus lesen_alle()), 
        können sie direkt in die Instanz gesetzt werden, um erneute 
        DB-Zugriffe zu vermeiden.
        
        Args:
            daten: Dictionary mit den Daten
            guid: Optional - GUID des Datensatzes
        """
        try:
            # GUID setzen falls übergeben
            if guid is not None and self.guid != guid:
                self.guid = guid
                logger.debug(f"GUID über set_data gesetzt: {guid}")
            
            # Daten direkt setzen
            if isinstance(daten, dict):
                self.data = daten.copy()
                self._loaded_snapshot = copy.deepcopy(self.data)
                gruppen_liste = list(self.data.keys())
                logger.info(f"✅ Daten gesetzt: {len(self.data)} Gruppen: {gruppen_liste}")
                
                # Debug-Info für jede Gruppe
                for gruppe_name in gruppen_liste:
                    gruppe_data = self.data[gruppe_name]
                    if isinstance(gruppe_data, dict):
                        logger.debug(f"   └─ Gruppe '{gruppe_name}': {len(gruppe_data)} Felder")
                    else:
                        logger.warning(f"   └─ Gruppe '{gruppe_name}': KEIN Dictionary! Type: {type(gruppe_data)}")
            else:
                logger.error(f"❌ Ungültiger Datentyp in set_data: {type(daten)}")
                self.data = {}
            
            # Markiere Daten als geladen
            self._data_loaded = True
            
        except Exception as e:
            logger.error(f"❌ Fehler in set_data: {e}")
            self.data = {}
            self._data_loaded = False
    
    def get_value(self, gruppe: str, feld: str, ab_zeit: Optional[float] = None) -> tuple[Any, Optional[float]]:
        """
        Liest einen Wert aus der Gruppe/Feld-Struktur.
        
        Args:
            gruppe: Name der Gruppe
            feld: Name des Feldes
            ab_zeit: Zeitpunkt für historische Daten (None = aktuell)
            
        Returns:
            Tuple[Any, Optional[float]]: (wert, abdatum) oder (wert, None) wenn nicht historisch
        """

        
        if gruppe not in self.data:
            return None, None
        
        gruppe_data = self.data[gruppe]
        if not isinstance(gruppe_data, dict):
            return None, None
        
        if feld not in gruppe_data:
            return None, None
        
        feld_data = gruppe_data[feld]
        
        # Für historische Daten: Zeitbasierte Auswahl
        if self.historisch and isinstance(feld_data, dict) and ab_zeit is not None:
            # Finde den passenden Zeitstempel
            best_time = None
            for timestamp in feld_data.keys():
                try:
                    ts_float = float(timestamp)
                    if ts_float <= ab_zeit:
                        if best_time is None or ts_float > best_time:
                            best_time = ts_float
                except (ValueError, TypeError):
                    continue
            
            if best_time is not None:
                for timestamp in feld_data.keys():
                    try:
                        if float(timestamp) == best_time:
                            return feld_data[timestamp], best_time
                    except (ValueError, TypeError):
                        continue
                return None, None
            else:
                return None, None
        
        # Nicht-historisch oder aktueller Wert
        if self.historisch and isinstance(feld_data, dict):
            # Neueste Zeit finden
            latest_time = None
            for timestamp in feld_data.keys():
                try:
                    ts_float = float(timestamp)
                    if latest_time is None or ts_float > latest_time:
                        latest_time = ts_float
                except (ValueError, TypeError):
                    continue
            
            if latest_time is not None:
                for timestamp in feld_data.keys():
                    try:
                        if float(timestamp) == latest_time:
                            return feld_data[timestamp], latest_time
                    except (ValueError, TypeError):
                        continue
        
        # Direkter Wert - für nicht-historische Daten
        return feld_data, None
    
    def get_static_value(self, gruppe: str, feld: str) -> Any:
        """
        Vereinfachte statische Wertabfrage nur für nicht-historische Daten.
        
        Args:
            gruppe: Name der Gruppe
            feld: Name des Feldes
            
        Returns:
            Any: Der direkte Wert
        """
        if self.historisch:
            raise ValueError("❌ get_static_value kann nicht auf historische Tabellen angewendet werden")
            

        
        if gruppe not in self.data:
            logger.warning(f"⚠️ Gruppe '{gruppe}' nicht gefunden - erstelle leer")
            self.data[gruppe] = {}
        
        if feld not in self.data[gruppe]:
            logger.info(f"📋 Feld '{feld}' in Gruppe '{gruppe}' nicht gefunden - erstelle leeres Dict")
            self.data[gruppe][feld] = {}
            return {}
        
        feld_data = self.data[gruppe][feld]
        
        # Legacy-Kompatibilität: Prüfe auf 'wert'-Dict-Struktur
        if isinstance(feld_data, dict) and 'wert' in feld_data:
            return feld_data['wert']
            
        return feld_data
    
    def get_value_by_group(self, gruppe: str) -> Dict[str, Any]:
        """
        Holt ALLE Felder einer Gruppe.
        
        Args:
            gruppe: Name der Gruppe
            
        Returns:
            Dict[str, Any]: Dictionary mit {feld: wert} für alle Felder
        """
        logger.debug(f"🔍 get_value_by_group('{gruppe}') aufgerufen")
        logger.debug(f"   Verfügbare Gruppen: {list(self.data.keys())}")
        
        if gruppe not in self.data:
            logger.warning(f"⚠️ Gruppe nicht gefunden: {gruppe}")
            logger.warning(f"   Verfügbare Gruppen: {list(self.data.keys())}")
            return {}
        
        gruppe_data = self.data[gruppe]
        
        if not isinstance(gruppe_data, dict):
            logger.warning(f"⚠️ Gruppe '{gruppe}' ist kein Dictionary: {type(gruppe_data)}")
            return {}
        
        logger.info(f"✅ Gruppe '{gruppe}' gefunden mit {len(gruppe_data)} Feldern")
        
        # Konvertiere Legacy 'wert'-Struktur wenn nötig
        result = {}
        for feld, feld_data in gruppe_data.items():
            if isinstance(feld_data, dict) and 'wert' in feld_data:
                result[feld] = feld_data['wert']
            else:
                result[feld] = feld_data
        
        return result
    
    def set_value(self, gruppe: str, feld: str, wert: Any, ab_zeit: Optional[float] = None):
        """
        Setzt einen Wert in der Gruppe/Feld-Struktur.
        
        Args:
            gruppe: Name der Gruppe
            feld: Name des Feldes  
            wert: Der zu setzende Wert
            ab_zeit: Zeitpunkt für historische Daten (None = jetzt)
        """

        
        # Gruppe sicherstellen
        if gruppe not in self.data:
            self.data[gruppe] = {}
        
        if not isinstance(self.data[gruppe], dict):
            self.data[gruppe] = {}
        
        # Zeitstempel für historische Daten
        if self.historisch:
            if ab_zeit is None:
                ab_zeit = self._get_current_timestamp()
            
            # Feld als Zeitstempel-Dictionary strukturieren
            if feld not in self.data[gruppe]:
                self.data[gruppe][feld] = {}
            elif not isinstance(self.data[gruppe][feld], dict):
                # Bestehenden Wert in historische Struktur konvertieren
                old_value = self.data[gruppe][feld]
                self.data[gruppe][feld] = {ab_zeit: old_value}
            
            self.data[gruppe][feld][ab_zeit] = wert
        else:
            # Direkter Wert
            self.data[gruppe][feld] = wert
        
        logger.debug(f"Wert gesetzt: {gruppe}.{feld} = {type(wert).__name__}")
    
    def get_all_values(self) -> Dict[str, Any]:
        """
        Gibt alle Daten zurück.
        
        Returns:
            Dict: Vollständige Datenstruktur
        """

        return self.data.copy()
    
    async def save_all_values(
        self,
        actor_user_uid: Optional[str] = None,
        actor_ip: Optional[str] = None,
    ) -> Optional[str]:
        """
        Speichert alle Daten in die Datenbank.
        
        SICHERHEITSSCHALTER: Wenn no_save=True wurde, wird nichts gespeichert.
        AUTO-GUID: Wenn keine GUID vorhanden ist, wird automatisch eine neue generiert.
        NAME-SYNC: ROOT.NAME/ROOT.SELF_NAME wird mit der 'name' Spalte synchronisiert.
        
        Returns:
            str: Die GUID des gespeicherten Datensatzes
        """
        if self.no_save:
            logger.debug(f"⚠️ save_all_values() übersprungen (no_save=True) für {self.table_name}.{self.guid}")
            return self.guid
        
        # AUTO-GUID: Generiere neue GUID falls keine vorhanden
        if not self.guid:
            self.guid = str(uuid.uuid4())
            logger.info(f"✅ Neue GUID generiert für {self.table_name}: {self.guid}")
        
        try:
            guid_uuid = uuid.UUID(self.guid)
            effective_actor_user_uid = actor_user_uid or self.actor_user_uid
            effective_actor_ip = actor_ip if actor_ip is not None else self.actor_ip
            
            # NAME-SYNC: ROOT.NAME / ROOT.SELF_NAME für die 'name' Spalte
            name_value = None
            if 'ROOT' in self.data and isinstance(self.data['ROOT'], dict):
                root = self.data['ROOT']
                name_value = root.get('NAME') or root.get('SELF_NAME')
                if not name_value or name_value == '-eingeben-':
                    name_value = None
            
            # Prüfe ob Datensatz existiert
            existing = await self.db.get_row(guid_uuid)
            
            if existing:
                # Update (only set name when present)
                if name_value:
                    await self.db.update(
                        guid_uuid,
                        self.data,
                        name=name_value,
                        expected_snapshot_daten=self._loaded_snapshot,
                        actor_user_uid=effective_actor_user_uid,
                        actor_ip=effective_actor_ip,
                    )
                else:
                    await self.db.update(
                        guid_uuid,
                        self.data,
                        expected_snapshot_daten=self._loaded_snapshot,
                        actor_user_uid=effective_actor_user_uid,
                        actor_ip=effective_actor_ip,
                    )
                logger.info(f"Daten aktualisiert für GUID {self.guid} mit name={name_value}")
            else:
                # Create (name optional for non-dialog system saves)
                await self.db.create(
                    guid_uuid,
                    self.data,
                    name=name_value or "",
                    historisch=1 if self.historisch else 0
                )
                logger.info(f"Neuer Datensatz erstellt mit GUID {self.guid} und name={name_value}")

            # Snapshot nach erfolgreichem Save aktualisieren.
            self._loaded_snapshot = copy.deepcopy(self.data)
            
            return self.guid
            
        except Exception as e:
            logger.error(f"Fehler beim Speichern von {self.guid}: {e}")
            raise
    
    def set_group(self, gruppe: str, gruppe_data: Dict[str, Any]):
        """
        Setzt oder ersetzt eine komplette Gruppe mit allen Feldern.
        
        Args:
            gruppe: Name der Gruppe
            gruppe_data: Dictionary mit allen Feldern der Gruppe
        """

        
        if not isinstance(gruppe_data, dict):
            raise ValueError(f"gruppe_data muss ein Dictionary sein, nicht {type(gruppe_data)}")
        
        self.data[gruppe] = gruppe_data.copy()
        logger.debug(f"Gruppe gesetzt: {gruppe} mit {len(gruppe_data)} Feldern")
    
    def delete_group(self, gruppe: str):
        """
        Löscht eine komplette Gruppe.
        
        Args:
            gruppe: Name der zu löschenden Gruppe
        """

        
        if gruppe in self.data:
            del self.data[gruppe]
            logger.debug(f"Gruppe gelöscht: {gruppe}")
    
    def delete_field(self, gruppe: str, feld: str):
        """
        Löscht ein Feld aus einer Gruppe (KOMPLETT - alle historischen Einträge).
        
        Args:
            gruppe: Name der Gruppe
            feld: Name des zu löschenden Feldes
        """

        
        if gruppe in self.data and isinstance(self.data[gruppe], dict):
            if feld in self.data[gruppe]:
                del self.data[gruppe][feld]
                logger.debug(f"Feld gelöscht: {gruppe}.{feld}")
    
    def get_groups(self) -> List[str]:
        """
        Gibt alle Gruppennamen zurück.
        
        Returns:
            List[str]: Liste der Gruppennamen
        """

        return list(self.data.keys())
    
    def get_fields(self, gruppe: str) -> List[str]:
        """
        Gibt alle Feldnamen einer Gruppe zurück.
        
        Args:
            gruppe: Name der Gruppe
            
        Returns:
            List[str]: Liste der Feldnamen
        """

        
        if gruppe not in self.data:
            return []
        
        gruppe_data = self.data[gruppe]
        if not isinstance(gruppe_data, dict):
            return []
        
        return list(gruppe_data.keys())
    
    # Legacy-Methoden für Kompatibilität mit altem Code
    
    async def get_all_data(self) -> Optional[Dict[str, Any]]:
        """Legacy: Lädt kompletten Datensatz"""
        if not self.guid:
            return None
        
        try:
            guid_uuid = uuid.UUID(self.guid)
            return await self.db.get_by_uid(guid_uuid)
        except Exception as e:
            logger.error(f"Fehler in get_all_data: {e}")
            return None

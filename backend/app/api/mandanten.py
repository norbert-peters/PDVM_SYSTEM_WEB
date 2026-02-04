"""
Mandanten API Endpoints
Nutzt MandantDataManager für Business Logic + GCS-Initialisierung
"""
from fastapi import APIRouter, HTTPException, Depends, Request
from typing import List
from ..models.schemas import MandantResponse, MandantSelectRequest, MandantSelectResponse
from ..api.auth import get_current_user
from ..core.data_managers import MandantDataManager
from ..core.database import get_database_url, DatabasePool
from ..core.config import settings
from ..core.connection_manager import ConnectionManager, ConnectionConfig
import logging
import asyncio
from datetime import datetime

router = APIRouter()
logger = logging.getLogger(__name__)


def _parse_idle_seconds(value) -> int | None:
    try:
        n = int(float(str(value).strip()))
        if n <= 0:
            return None
        return n
    except Exception:
        return None


# System-UIDs die nicht in der Auswahl angezeigt werden
SYSTEM_MANDANT_UIDS = [
    "66666666-6666-6666-6666-666666666666",  # Template
    "55555555-5555-5555-5555-555555555555",  # Properties Control
    "00000000-0000-0000-0000-000000000000",  # System-Infos
]

@router.get("", response_model=List[MandantResponse])
async def get_all_mandanten(current_user: dict = Depends(get_current_user)):
    """
    Gibt Liste aller Mandanten zurück (für Auswahl-Dialog)
    Filtert System-Datensätze (Template, Properties Control, System-Infos)
    Sortiert alphabetisch nach Name (aufsteigend)
    """
    manager = MandantDataManager()
    
    try:
        mandanten = await manager.list_all(include_inactive=False)
        
        # System-Datensätze filtern und in Response-Format konvertieren
        filtered_mandanten = [
            {
                "id": str(m["uid"]),
                "name": m["name"],
                "is_allowed": m["daten"].get("MANDANT", {}).get("IS_ALLOWED", False),
                "description": m["daten"].get("MANDANT", {}).get("DESCRIPTION", "")
            }
            for m in mandanten
            if str(m["uid"]) not in SYSTEM_MANDANT_UIDS
        ]
        
        # Alphabetisch nach Name sortieren (aufsteigend)
        return sorted(filtered_mandanten, key=lambda x: x["name"].lower())
    
    except Exception as e:
        logger.error(f"Fehler beim Laden der Mandanten: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/list", response_model=List[MandantResponse])
async def get_mandanten_list(current_user: dict = Depends(get_current_user)):
    """
    Gibt Liste aller Mandanten zurück (für Auswahl-Dialog)
    Nutzt MandantDataManager mit Cache
    Filtert System-Datensätze (Template, Properties Control, System-Infos)
    Sortiert alphabetisch nach Name (aufsteigend)
    
    Returns:
        Liste von Mandanten mit ID, Name, Berechtigung
    """
    manager = MandantDataManager()
    
    try:
        mandanten = await manager.list_all(include_inactive=False)
        
        # System-Datensätze filtern und in Response-Format konvertieren
        filtered_mandanten = [
            {
                "id": str(m["uid"]),
                "name": m["name"],
                "is_allowed": m["daten"].get("MANDANT", {}).get("IS_ALLOWED", False),
                "description": m["daten"].get("MANDANT", {}).get("DESCRIPTION", "")
            }
            for m in mandanten
            if str(m["uid"]) not in SYSTEM_MANDANT_UIDS
        ]
        
        # Alphabetisch nach Name sortieren (aufsteigend)
        return sorted(filtered_mandanten, key=lambda x: x["name"].lower())
    
    except Exception as e:
        logger.error(f"Fehler beim Laden der Mandanten: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/select", response_model=MandantSelectResponse)
async def select_mandant(
    request: MandantSelectRequest,
    current_user: dict = Depends(get_current_user),
    http_request: Request = None
):
    """
    Validiert Mandanten-Auswahl, erstellt GCS-Session
    
    Args:
        request: Mandanten-ID vom User
        
    Returns:
        Mandant-Details wenn berechtigt
        
    Raises:
        403: Wenn keine Berechtigung für Mandant
        404: Wenn Mandant nicht existiert
    """
    manager = MandantDataManager()
    mandant_id = request.mandant_id
    user_id = current_user.get("sub")  # User-ID aus JWT Token
    
    print(f"\n\n🚀 START: Mandant-Auswahl für Mandant '{mandant_id}' von User '{user_id}'", flush=True)
    logger.info(f"🚀 START: Mandant-Auswahl für Mandant '{mandant_id}' von User '{user_id}'")
    
    try:
        # Lade Mandant
        print(f"📖 Lade Mandant-Daten für ID '{mandant_id}'...", flush=True)
        logger.info(f"📖 Lade Mandant-Daten für ID '{mandant_id}'...")
        mandant = await manager.get_by_id(mandant_id)
        print(f"✅ Mandant geladen: {mandant.get('name') if mandant else 'None'}", flush=True)
        logger.info(f"✅ Mandant geladen: {mandant.get('name') if mandant else 'None'}")
        
        if not mandant:
            raise HTTPException(
                status_code=404,
                detail=f"Mandant '{mandant_id}' nicht gefunden"
            )
        
        # Prüfe Berechtigung
        logger.info(f"🔐 Prüfe Berechtigung für User '{user_id}' auf Mandant '{mandant_id}'...")
        has_access = await manager.check_access(mandant_id, user_id)
        logger.info(f"✅ Berechtigung: {has_access}")
        
        if not has_access:
            raise HTTPException(
                status_code=403,
                detail=f"Keine Berechtigung für Mandant '{mandant['name']}'"
            )
        
        # Hole Datenbank-Name
        print(f"🗄️ Hole Datenbank-Name für Mandant '{mandant_id}'...", flush=True)
        logger.info(f"🗄️ Hole Datenbank-Name für Mandant '{mandant_id}'...")
        database = await manager.get_database_name(mandant_id)
        print(f"🔧 DEBUG: Datenbank-Name: {database}", flush=True)
        logger.info(f"🔧 DEBUG: Datenbank-Name: {database}")
        
        # ========================================
        # CONNECTION-PARAMETER DIREKT AUS MANDANT-DATEN EXTRAHIEREN
        # Wir haben die Daten bereits oben geladen - keine neue Connection nötig!
        # ========================================
        print(f"\n🔧 Extrahiere Connection-Config aus Mandant-Daten...", flush=True)
        
        mandant_data = mandant.get('daten', {})
        mandant_config_dict = mandant_data.get('MANDANT', {})
        
        # Mandanten-DB Config
        mandant_config = ConnectionConfig(
            host=mandant_config_dict.get('HOST', 'localhost'),
            port=mandant_config_dict.get('PORT', 5432),
            user=mandant_config_dict.get('USER', 'postgres'),
            password=mandant_config_dict.get('PASSWORD', 'postgres'),
            database=mandant_config_dict.get('DATABASE', database)
        )
        mandant_db_url = mandant_config.to_url()
        
        # System-DB Config (aus SYSTEM_DB-Name + gleiche Connection-Daten)
        system_db_name = mandant_config_dict.get('SYSTEM_DB', 'pdvm_system')
        system_config = ConnectionConfig(
            host=mandant_config_dict.get('HOST', 'localhost'),
            port=mandant_config_dict.get('PORT', 5432),
            user=mandant_config_dict.get('USER', 'postgres'),
            password=mandant_config_dict.get('PASSWORD', 'postgres'),
            database=system_db_name
        )
        system_db_url = system_config.to_url()
        
        print(f"✅ Connection-Config extrahiert:", flush=True)
        print(f"  System-DB: {system_config.database} @ {system_config.host}:{system_config.port}", flush=True)
        print(f"  Mandant-DB: {mandant_config.database} @ {mandant_config.host}:{mandant_config.port}", flush=True)
        
        # ========================================
        # DATENBANK-EXISTENZ PRÜFEN UND ERSTELLEN
        # ========================================
        print(f"🔧 DEBUG: Starte Datenbank-Existenz-Prüfung...", flush=True)
        logger.info(f"🔧 DEBUG: Starte Datenbank-Existenz-Prüfung...")
        
        # Verwende direkte Connection statt Pool (Pool-Connections werden manchmal geschlossen)
        import asyncpg
        from ..core.config import settings
        
        try:
            print(f"🔍 Erstelle direkte Connection zu pdvm_system via ConnectionManager...", flush=True)
            # ✅ Verwende system_config vom ConnectionManager (bereits oben geladen)
            conn = await asyncpg.connect(**system_config.to_dict())
            try:
                print(f"✅ Connection erfolgreich", flush=True)
                print(f"🔍 Prüfe Datenbank '{database}' in pg_database...", flush=True)
                
                db_exists = await conn.fetchval(
                    "SELECT 1 FROM pg_database WHERE datname = $1",
                    database
                )
                print(f"✅ Query erfolgreich, db_exists={db_exists}", flush=True)
                
                if not db_exists:
                    logger.info(f"📦 Datenbank '{database}' existiert nicht - erstelle sie...")
                    
                    # CREATE DATABASE mit template0 (garantiert keine aktiven Verbindungen)
                    await conn.execute(f'CREATE DATABASE "{database}" WITH TEMPLATE template0')
                    logger.info(f"✅ Datenbank '{database}' erfolgreich erstellt")
                    
                    # WICHTIG: Nach CREATE DATABASE warten auf PostgreSQL-Initialisierung
                    await asyncio.sleep(1.0)
                    logger.info(f"⏳ Warte auf DB-Initialisierung...")
                    
                    # Erste Connection: Extensions installieren und Init-Tabelle anlegen
                    init_conn = await asyncpg.connect(mandant_db_url, timeout=10)
                    try:
                        # SCHRITT 1: Extensions installieren (uuid-ossp für gen_random_uuid)
                        await init_conn.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
                        logger.info(f"✅ Extension 'uuid-ossp' installiert")
                        
                        # SCHRITT 2: Init-Tabelle anlegen (jetzt mit UUID-Support)
                        await init_conn.execute("""
                            CREATE TABLE IF NOT EXISTS _db_init (
                                id SERIAL PRIMARY KEY,
                                created_at TIMESTAMP DEFAULT NOW(),
                                info TEXT DEFAULT 'Database initialization marker'
                            )
                        """)
                        await init_conn.execute(
                            "INSERT INTO _db_init (info) VALUES ($1)",
                            f"Database created at {datetime.utcnow().isoformat()}"
                        )
                        logger.info(f"✅ Init-Tabelle '_db_init' in '{database}' angelegt")
                    finally:
                        await init_conn.close()
                    
                    # DB_CREATED_AT setzen
                    from ..core.pdvm_datetime import now_pdvm_str
                    db_created_at = now_pdvm_str()
                    await manager.update_value(
                        mandant_id=mandant_id,
                        group="ROOT",
                        field="DB_CREATED_AT",
                        value=db_created_at
                    )
                else:
                    logger.info(f"✓ Datenbank '{database}' existiert bereits")
            finally:
                # Connection schließen
                await conn.close()
                print(f"✅ Connection geschlossen", flush=True)
        except Exception as db_error:
            logger.error(f"❌ Fehler bei Datenbank-Prüfung/Erstellung: {db_error}")
            raise HTTPException(
                status_code=500,
                detail=f"Fehler beim Erstellen der Datenbank: {str(db_error)}"
            )
        
        # ========================================
        # TABELLEN-PRÜFUNG UND AUTO-ERSTELLUNG
        # (Jetzt können wir sicher sein, dass die Datenbank existiert)
        # ========================================
        
        # mandant_db_url wurde bereits oben über ConnectionManager geladen!
        # Keine manuelle URL-Erstellung mehr nötig
        
        # ========================================
        # DATENBANK-WARTUNG VOR GCS-INITIALISIERUNG
        # Prüft und korrigiert:
        # - Fehlende Tabellen aus CONFIGS.FEATURES/SYS_TABLES (NEU ANLEGEN mit Standard-Schema)
        # - Existierende Tabellen: Fehlende Spalten (daten_backup, gilt_bis, etc.)
        # - Existierende Tabellen: Falsche Datentypen korrigieren (gilt_bis TEXT → TIMESTAMP)
        # - gilt_bis Werte für alte Datensätze korrigieren
        # ========================================
        try:
            print(f"\n🔧 Starte Datenbank-Wartung...", flush=True)
            logger.info(f"🔧 Starte Datenbank-Wartung für Mandant {mandant_id}")
            
            from ..core.mandant_db_maintenance import run_mandant_maintenance
            
            # Erstelle temporären Connection Pool für Wartung
            mandant_pool = await asyncpg.create_pool(mandant_db_url, min_size=1, max_size=2)
            
            try:
                # Führe Wartung aus - übergebe mandant['daten'] mit CONFIGS
                maintenance_stats = await run_mandant_maintenance(
                    mandant_pool, 
                    mandant_id,
                    mandant['daten']  # Login-Daten enthält CONFIGS.FEATURES/SYS_TABLES
                )
                
                logger.info(f"✅ Wartung abgeschlossen: {maintenance_stats}")
                print(f"✅ Wartung: {maintenance_stats['tables_created']} Tabellen erstellt, "
                      f"{maintenance_stats['records_updated']} Datensätze korrigiert", flush=True)
            finally:
                # Pool schließen
                await mandant_pool.close()
            
        except Exception as maintenance_error:
            # Wartung fehlgeschlagen - logge Warnung aber fahre fort
            logger.warning(f"⚠️ Datenbank-Wartung fehlgeschlagen: {maintenance_error}")
            print(f"⚠️ Wartung fehlgeschlagen: {maintenance_error}", flush=True)
        
        # ========================================
        # GCS-SESSION ERSTELLEN
        # (Jetzt können wir sicher sein, dass die Tabellen existieren)
        # ========================================
        
        # JWT-Token aus Header holen
        auth_header = http_request.headers.get("Authorization", "")
        token = auth_header.replace("Bearer ", "") if auth_header.startswith("Bearer ") else ""
        
        if not token:
            raise HTTPException(status_code=401, detail="Kein Token gefunden")
        
        # ✅ system_db_url wurde bereits oben über ConnectionManager geladen (aus system_config)
        # Keine manuelle URL-Konstruktion mehr nötig!
        
        # Extrahiere benötigte Variablen für GCS-Session
        system_database = system_config.database
        mandant_data = mandant.get('daten', {})
        
        # Maskierte URL für Logging
        masked_url = mandant_db_url.split('@')[0].split(':')[0] + ":***@" + mandant_db_url.split('@')[1] if '@' in mandant_db_url else mandant_db_url
        print(f"🔗 Connection-String: {masked_url}", flush=True)
        
        # User-Daten aus JWT Token (bereits vollständig mit MEINEAPPS, SETTINGS, etc.)
        user_data = current_user.get('user_data', {})
        
        # Mandanten-Daten aus DB laden
        mandant_data = mandant.get('daten', {})
        
        # TODO: Mandanten_access und Berechtigungen beim Login laden
        # Für jetzt: Platzhalter-Werte
        mandanten_access = []  # Wird später beim Login geladen
        berechtigungen = {}    # Wird später beim Login geladen
        
        # GCS-Session erstellen mit beiden Pools und Daten
        print(f"🚀 Erstelle GCS-Session für '{database}' (System: {system_database})...", flush=True)
        from app.core.pdvm_central_systemsteuerung import create_gcs_session
        
        gcs = await create_gcs_session(
            session_token=token,
            user_guid=user_id,
            mandant_guid=mandant_id,
            user_data=user_data,  # User-Daten aus Login
            mandant_data=mandant_data,  # Mandant-Daten aus DB
            system_db_url=system_db_url,
            mandant_db_url=mandant_db_url
        )
        
        logger.info(f"✅ GCS-Session erstellt für User {user_id}, Mandant {mandant['name']}")
        logger.info(f"   Stichtag: {gcs.stichtag}")
        
        # ========================================
        
        # Erfolgreiche Auswahl
        logger.info(f"✅ Mandant ausgewählt: {mandant['name']} von User {user_id}")
        
        return {
            "mandant_id": str(mandant["uid"]),
            "mandant_name": mandant["name"],
            "mandant_town": mandant_data.get("ROOT", {}).get("MANDANT_TOWN"),
            "mandant_street": mandant_data.get("ROOT", {}).get("MANDANT_STREET"),
            "idle_timeout": _parse_idle_seconds(mandant_data.get("ROOT", {}).get("IDLE_TIMEOUT")),
            "idle_warning": _parse_idle_seconds(mandant_data.get("ROOT", {}).get("IDLE_WARNING")),
            "database": database,
            "message": f"Mandant '{mandant['name']}' erfolgreich ausgewählt"
        }
    
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        logger.error(f"Fehler bei Mandanten-Auswahl: {e}")
        logger.error(f"Traceback:\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/template")
async def get_mandant_template(current_user: dict = Depends(get_current_user)):
    """
    Gibt Template und Properties Control für Mandanten-Neuanlage zurück
    
    Returns:
        template: Leere Mandanten-Struktur (UID 6666...)
        properties: Property-Definitionen (UID 5555...)
    """
    from ..core.pdvm_datenbank import PdvmDatabase
    import uuid
    
    try:
        # Für sys_mandanten verwenden wir PdvmDatabase direkt (keine Central-Klasse nötig)
        db = PdvmDatabase("sys_mandanten")
        
        # Template laden (UID 6666...)
        template_uid = uuid.UUID("66666666-6666-6666-6666-666666666666")
        template_record = await db.get_by_uid(template_uid)
        
        if not template_record:
            raise HTTPException(status_code=404, detail="Template nicht gefunden")
        
        # Properties Control laden (UID 5555...)
        properties_uid = uuid.UUID("55555555-5555-5555-5555-555555555555")
        properties_record = await db.get_by_uid(properties_uid)
        
        if not properties_record:
            raise HTTPException(status_code=404, detail="Properties Control nicht gefunden")
        
        # Properties umstrukturieren: von GUID-basiert zu name-basiert
        # Original: { "guid": { "name": "FIELD_NAME", "label": "...", ... }, ... }
        # Ziel: { "FIELD_NAME": { "label": "...", "type": "...", ... }, ... }
        properties_by_name = {}
        properties_controls = properties_record["daten"].get("PROPERTIES_CONTROLS", {})
        
        for guid, prop in properties_controls.items():
            field_name = prop.get("name")
            if field_name:
                properties_by_name[field_name] = {
                    "label": prop.get("label", field_name),
                    "type": prop.get("type", "text"),
                    "readonly": prop.get("readonly", False),
                    "required": prop.get("required", False),
                    "default_value": prop.get("default_value", "")
                }
        
        return {
            "template": template_record["daten"],
            "properties": properties_by_name,
            "template_uid": str(template_uid),
            "properties_uid": str(properties_uid)
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Fehler beim Laden des Templates: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/save")
async def save_mandant(
    mandant_data: dict,
    current_user: dict = Depends(get_current_user)
):
    """
    Speichert einen neuen Mandanten in sys_mandanten
    
    Workflow:
    1. Neue GUID generieren
    2. Timestamps setzen (CREATED_AT, MODIFIED_AT)
    3. Mit PdvmCentralDatabase.save_all_values() speichern
    
    Args:
        mandant_data: Template-Struktur mit Benutzereingaben
        
    Returns:
        Gespeicherter Mandant mit neuer GUID
    """
    from ..core.pdvm_central_datenbank import PdvmCentralDatabase
    from ..core.pdvm_datetime import PdvmDateTime
    import uuid
    
    try:
        # 1. Neue GUID generieren
        new_guid = str(uuid.uuid4())
        
        # 2. Timestamps setzen
        now_str = PdvmDateTime().now().pdvm_datetime_str
        
        # ROOT Gruppe mit GUID und Timestamps
        if "ROOT" not in mandant_data:
            mandant_data["ROOT"] = {}
            
        mandant_data["ROOT"]["SELF_GUID"] = new_guid
        mandant_data["ROOT"]["CREATED_AT"] = now_str
        mandant_data["ROOT"]["MODIFIED_AT"] = now_str
        
        # 3. PdvmCentralDatabase Instanz erstellen und Daten setzen
        central_db = PdvmCentralDatabase("sys_mandanten", new_guid)
        central_db.set_data(mandant_data, new_guid)
        
        # 4. Alle Werte speichern
        saved_guid = await central_db.save_all_values()
        
        logger.info(f"Mandant gespeichert: {saved_guid} - {mandant_data.get('ROOT', {}).get('NAME')}")
        
        return {
            "success": True,
            "mandant_id": saved_guid,
            "message": "Mandant erfolgreich gespeichert",
            "data": mandant_data
        }
    
    except Exception as e:
        logger.error(f"Fehler beim Speichern des Mandanten: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/pending-setup")
async def get_mandanten_pending_setup(current_user: dict = Depends(get_current_user)):
    """
    Listet alle Mandanten auf, deren Datenbank noch nicht eingerichtet ist
    
    Prüft für jeden Mandanten ob die in MANDANT.DATABASE eingetragene
    Datenbank existiert. Gibt Liste der Mandanten zurück, bei denen
    ROOT.DB_CREATED_AT nicht gesetzt ist oder Datenbank nicht existiert.
    
    Returns:
        Liste von Mandanten die aufgebaut werden müssen
    """
    from ..core.pdvm_datenbank import PdvmDatabase
    
    try:
        db = PdvmDatabase("sys_mandanten")
        all_mandanten = await db.get_all()
        
        pending = []
        
        for mandant in all_mandanten:
            # System-Datensätze überspringen
            if str(mandant["uid"]) in SYSTEM_MANDANT_UIDS:
                continue
            
            daten = mandant.get("daten", {})
            root = daten.get("ROOT", {})
            mandant_info = daten.get("MANDANT", {})
            
            # Einfache Prüfung: Ist DB_CREATED_AT gesetzt und nicht "-eingeben-"?
            # Wenn nicht → Datenbank muss aufgebaut werden
            db_created_at = root.get("DB_CREATED_AT")
            if not db_created_at or db_created_at == "-eingeben-":
                # Datenbank wurde noch nicht aufgebaut
                db_name = mandant_info.get("DATABASE", "-nicht konfiguriert-")
                
                pending.append({
                    "id": str(mandant["uid"]),
                    "name": mandant["name"],
                    "database": db_name,
                    "description": mandant_info.get("DESCRIPTION", ""),
                    "reason": "Datenbank noch nicht erstellt"
                })
                logger.info(f"Mandant '{mandant['name']}' benötigt DB-Setup (DB_CREATED_AT={db_created_at})")
        
        return pending
    
    except Exception as e:
        logger.error(f"Fehler beim Ermitteln der aufzubauenden Mandanten: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/setup/{mandant_id}")
async def setup_mandant_database(
    mandant_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Baut die Datenbank für einen Mandanten auf
    
    Workflow:
    1. Mandanten-Daten laden
    2. Datenbank erstellen (aus MANDANT.DATABASE)
    3. CONFIG.SYS_TABLES Tabellen anlegen
    4. CONFIG.FEATURES Tabellen anlegen
    5. ROOT.DB_CREATED_AT Zeitstempel setzen
    
    Args:
        mandant_id: UUID des Mandanten
        
    Returns:
        Success-Status und Details
    """
    from ..core.pdvm_datenbank import PdvmDatabase
    from ..core.pdvm_central_datenbank import PdvmCentralDatabase
    from ..core.pdvm_datetime import PdvmDateTime
    from ..core.database import DatabasePool
    import asyncpg
    import uuid
    
    try:
        # 1. Mandanten-Daten laden
        db = PdvmDatabase("sys_mandanten")
        mandant_uuid = uuid.UUID(mandant_id)
        central_db = PdvmCentralDatabase("sys_mandanten", mandant_id)
        
        # Daten laden
        mandant_record = await db.get_by_uid(mandant_uuid)
        if not mandant_record:
            raise HTTPException(status_code=404, detail="Mandant nicht gefunden")
        
        daten = mandant_record.get("daten", {})
        central_db.set_data(daten, mandant_id)
        
        # Konfiguration extrahieren
        mandant_info = daten.get("MANDANT", {})
        config = daten.get("CONFIG", {})
        root = daten.get("ROOT", {})
        
        db_name = mandant_info.get("DATABASE")
        if not db_name or db_name == "-eingeben-":
            raise HTTPException(status_code=400, detail="Datenbank-Name nicht konfiguriert")
        
        # 2. Nur Datenbank erstellen - KEINE Tabellen!
        # Tabellen werden beim ersten Login angelegt
        # Grund: Setup-Admin hat evtl. keine Berechtigung für neue DB
        
        try:
            # ✅ Verwende ConnectionManager für mandant-spezifische Connection-Daten
            system_config, mandant_config = await ConnectionManager.get_mandant_config(mandant_id)
            
            # Direkte Connection für CREATE DATABASE (außerhalb Pool)
            # Verbinde zu postgres (template) Datenbank für CREATE DATABASE
            # ✅ Nutze system_config für postgres-DB
            postgres_config = ConnectionConfig(
                host=system_config.host,
                port=system_config.port,
                user=system_config.user,
                password=system_config.password,
                database="postgres"  # Template-DB für CREATE DATABASE
            )
            conn = await asyncpg.connect(**postgres_config.to_dict())
            
            try:
                logger.info(f"Verwende direkte Connection für CREATE DATABASE")
                
                # Prüfe ob DB existiert
                exists = await conn.fetchval(
                    "SELECT 1 FROM pg_database WHERE datname = $1",
                    db_name
                )
                
                if not exists:
                    # CREATE DATABASE mit template0 (keine aktiven Verbindungen)
                    await conn.execute(f'CREATE DATABASE "{db_name}" WITH TEMPLATE template0')
                    logger.info(f"✅ Datenbank '{db_name}' erstellt")
                    
                    # Warten auf PostgreSQL-Initialisierung
                    await asyncio.sleep(1.0)
                    
                    # Extensions und Init-Tabelle sofort anlegen
                    try:
                        # ✅ Verwende mandant_config für neue DB-Connection
                        init_conn = await asyncpg.connect(**mandant_config.to_dict(), timeout=10)
                        try:
                            # SCHRITT 1: Extensions installieren
                            await init_conn.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
                            logger.info(f"✅ Extension 'uuid-ossp' installiert")
                            
                            # SCHRITT 2: Init-Tabelle anlegen
                            await init_conn.execute("""
                                CREATE TABLE IF NOT EXISTS _db_init (
                                    id SERIAL PRIMARY KEY,
                                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                                    description TEXT
                                )
                            """)
                            await init_conn.execute(
                                "INSERT INTO _db_init (description) VALUES ($1)",
                                f"Database initialized at {datetime.utcnow().isoformat()}"
                            )
                            logger.info(f"✅ Init-Tabelle in '{db_name}' erstellt")
                        finally:
                            await init_conn.close()
                    except Exception as init_error:
                        logger.warning(f"⚠️ Konnte Init-Tabelle nicht erstellen: {init_error}")
                else:
                    logger.info(f"ℹ️ Datenbank '{db_name}' existiert bereits")
            finally:
                await conn.close()
            
        except asyncpg.PostgresConnectionError as e:
            logger.error(f"Verbindungsfehler zu PostgreSQL: {e}")
            raise HTTPException(status_code=500, detail=f"Kann nicht mit PostgreSQL verbinden: {str(e)}")
        except asyncpg.PostgresError as e:
            logger.error(f"Fehler beim Erstellen der Datenbank: {e}")
            raise HTTPException(status_code=500, detail=f"Datenbankfehler: {str(e)}")
        except Exception as e:
            logger.error(f"Unerwarteter Fehler: {e}")
            raise HTTPException(status_code=500, detail=f"Fehler: {str(e)}")
        
        # 3. ROOT.DB_CREATED_AT setzen (Tabellen werden später beim Login erstellt)
        now_pdvm = PdvmDateTime().now().pdvm_datetime_str
        central_db.set_value("ROOT", "DB_CREATED_AT", now_pdvm)
        await central_db.save_all_values()
        
        logger.info(f"✅ Mandant '{mandant_record['name']}' Datenbank '{db_name}' erstellt")
        logger.info(f"ℹ️ Tabellen werden beim ersten Login automatisch angelegt")
        
        return {
            "success": True,
            "mandant_id": mandant_id,
            "database": db_name,
            "db_created_at": now_pdvm,
            "message": f"Datenbank '{db_name}' erfolgreich erstellt. Tabellen werden beim ersten Login angelegt."
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Fehler beim Aufbau der Mandanten-Datenbank: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/create")
async def create_mandant(
    mandant_data: dict,
    current_user: dict = Depends(get_current_user)
):
    """
    Erstellt einen neuen Mandanten inkl. Datenbank
    
    Workflow:
    1. Template laden und mit Daten füllen
    2. Validierung (DB-Name, Verbindung)
    3. Datenbank anlegen
    4. Schema ausführen (sys_tables aus CONFIG)
    5. Mandanten-Satz speichern
    6. Connection Pool anlegen
    
    Request Body:
    {
        "name": "Neue Firma GmbH",
        "database": "mandant_neue_firma",
        "description": "Test-Mandant",
        "host": "localhost",
        "port": 5432,
        "user": "postgres",
        "password": "password",
        ...
    }
    """
    from ..core.pdvm_datenbank import PdvmDatabase
    from ..core.pdvm_datetime import PdvmDateTime
    from ..core.database import DatabasePool
    import asyncpg
    import os
    import uuid
    
    try:
        # Für sys_mandanten verwenden wir PdvmDatabase direkt
        db = PdvmDatabase("sys_mandanten")
        
        # 1. Template laden
        template_uid = uuid.UUID("66666666-6666-6666-6666-666666666666")
        template_record = await db.get_by_uid(template_uid)
        
        if not template_record:
            raise HTTPException(status_code=404, detail="Template nicht gefunden")
        
        # Template-Daten aus dem Record extrahieren
        template = template_record.get("daten", {})
        
        # 2. Template mit Eingabedaten aktualisieren
        now_pdvm = PdvmDateTime().now().pdvm_datetime_str
        
        # Frontend sendet komplette Template-Struktur - mit Änderungen mergen
        if "ROOT" in mandant_data:
            for key, value in mandant_data["ROOT"].items():
                template["ROOT"][key] = value
        
        if "MANDANT" in mandant_data:
            for key, value in mandant_data["MANDANT"].items():
                template["MANDANT"][key] = value
        
        if "CONFIG" in mandant_data:
            for key, value in mandant_data["CONFIG"].items():
                template["CONFIG"][key] = value
        
        if "CONTACT" in mandant_data:
            for key, value in mandant_data["CONTACT"].items():
                template["CONTACT"][key] = value
        
        # Zeitstempel und Benutzer setzen
        template["ROOT"]["CREATED_AT"] = now_pdvm
        template["ROOT"]["MODIFIED_AT"] = now_pdvm
        template["ROOT"]["CREATED_BY"] = current_user.get("uid", "")
        
        # 3. Validierung
        database_name = template["MANDANT"]["DATABASE"]
        if not database_name or database_name == "-eingeben-":
            raise HTTPException(status_code=400, detail="Datenbank-Name erforderlich")
        
        # 4. DB-Verbindung testen
        try:
            test_conn = await asyncpg.connect(
                host=template["MANDANT"]["HOST"],
                port=template["MANDANT"]["PORT"],
                user=template["MANDANT"]["USER"],
                password=template["MANDANT"]["PASSWORD"],
                database="postgres"  # Connect to postgres DB to create new DB
            )
            
            # Prüfen ob DB bereits existiert
            existing = await test_conn.fetchval(
                "SELECT 1 FROM pg_database WHERE datname = $1",
                database_name
            )
            
            if existing:
                await test_conn.close()
                raise HTTPException(
                    status_code=400,
                    detail=f"Datenbank '{database_name}' existiert bereits"
                )
            
            # 5. Datenbank anlegen
            await test_conn.execute(f'CREATE DATABASE "{database_name}"')
            await test_conn.close()
            
            logger.info(f"✅ Datenbank '{database_name}' angelegt")
            
        except asyncpg.PostgresError as e:
            logger.error(f"DB-Fehler: {e}")
            raise HTTPException(status_code=500, detail=f"Datenbankfehler: {str(e)}")
        
        # 6. Schema ausführen
        try:
            mandant_conn = await asyncpg.connect(
                host=template["MANDANT"]["HOST"],
                port=template["MANDANT"]["PORT"],
                user=template["MANDANT"]["USER"],
                password=template["MANDANT"]["PASSWORD"],
                database=database_name
            )
            
            # Schema-Datei laden
            schema_path = os.path.join("database", "schema_mandant.sql")
            if os.path.exists(schema_path):
                with open(schema_path, "r", encoding="utf-8") as f:
                    schema_sql = f.read()
                    await mandant_conn.execute(schema_sql)
                    logger.info(f"✅ Schema ausgeführt für '{database_name}'")
            else:
                logger.warning(f"⚠️ Schema-Datei nicht gefunden: {schema_path}")
            
            await mandant_conn.close()
            
        except Exception as e:
            logger.error(f"Schema-Fehler: {e}")
            # DB wieder löschen bei Fehler
            cleanup_conn = await asyncpg.connect(
                host=template["MANDANT"]["HOST"],
                port=template["MANDANT"]["PORT"],
                user=template["MANDANT"]["USER"],
                password=template["MANDANT"]["PASSWORD"],
                database="postgres"
            )
            await cleanup_conn.execute(f'DROP DATABASE IF EXISTS "{database_name}"')
            await cleanup_conn.close()
            raise HTTPException(status_code=500, detail=f"Schema-Fehler: {str(e)}")
        
        # 7. Mandanten-Satz speichern
        mandant_name = template["ROOT"]["NAME"]
        new_mandant = await db.create(
            name=mandant_name,
            daten=template
        )
        
        logger.info(f"✅ Mandant '{mandant_name}' angelegt (UID: {new_mandant['uid']})")
        
        # NOTE: Pool creation removed - pools now managed in GCS per session
        
        return {
            "success": True,
            "mandant_id": str(new_mandant["uid"]),
            "mandant_name": mandant_name,
            "database": database_name,
            "message": f"Mandant '{mandant_name}' erfolgreich angelegt"
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Fehler beim Anlegen des Mandanten: {e}")
        raise HTTPException(status_code=500, detail=str(e))

"""
Mandanten API Endpoints
Nutzt MandantDataManager für Business Logic + GCS-Initialisierung
"""
from fastapi import APIRouter, HTTPException, Depends, Request
from typing import List
from ..models.schemas import MandantResponse, MandantSelectRequest, MandantSelectResponse
from ..api.auth import get_current_user
from ..core.security import require_superadmin_user
from ..core.mandant_setup_service import MandantValidationError, create_mandant
from ..core.mandant_access import allowed_mandant_ids, is_mandant_allowed, load_user_daten
from ..core.data_managers import MandantDataManager
from ..core.database import get_database_url, DatabasePool
from ..core.config import settings
from ..core.connection_manager import ConnectionManager, ConnectionConfig
from ..core import mandant_db_provisioning_service as provisioning
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


def _effective_language(user_data, mandant_data) -> str | None:
    """Oberflaechensprache der Sitzung: `USER.SETTINGS.LANGUAGE`, sonst `CONFIG.DEFAULT_LANGUAGE` des Mandanten (None, wenn beides fehlt).

    Das Frontend merkt sie sich fuer die Anmeldemaske des naechsten Besuchs.
    """
    from ..core.i18n_policy import normalize_language

    def _group(data, name) -> dict:
        value = data.get(name) if isinstance(data, dict) else None
        return value if isinstance(value, dict) else {}

    raw = _group(user_data, "SETTINGS").get("LANGUAGE") or _group(mandant_data, "CONFIG").get("DEFAULT_LANGUAGE")
    return normalize_language(raw) if str(raw or "").strip() else None


# System-UIDs die nicht in der Auswahl angezeigt werden
SYSTEM_MANDANT_UIDS = [
    "66666666-6666-6666-6666-666666666666",  # Template
    "55555555-5555-5555-5555-555555555555",  # Properties Control
    "00000000-0000-0000-0000-000000000000",  # System-Infos
]

async def _mandanten_of_user(current_user: dict) -> list:
    """Mandanten, die dem Benutzer zugelassen sind (`MANDANTEN.LIST`), ohne System-Datensätze, alphabetisch."""
    manager = MandantDataManager()
    try:
        allowed = set(allowed_mandant_ids(await load_user_daten(current_user.get("sub"))))
        mandanten = await manager.list_all(include_inactive=False)

        filtered_mandanten = [
            {
                "id": str(m["uid"]),
                "name": m["name"],
                "is_allowed": m["daten"].get("MANDANT", {}).get("IS_ALLOWED", False),
                "description": m["daten"].get("MANDANT", {}).get("DESCRIPTION", "")
            }
            for m in mandanten
            if str(m["uid"]) not in SYSTEM_MANDANT_UIDS and str(m["uid"]).lower() in allowed
        ]
        return sorted(filtered_mandanten, key=lambda x: x["name"].lower())
    except Exception as e:
        logger.error(f"Fehler beim Laden der Mandanten: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("", response_model=List[MandantResponse])
async def get_all_mandanten(current_user: dict = Depends(get_current_user)):
    """Zugelassene Mandanten des Benutzers (für Auswahl-Dialog), alphabetisch."""
    return await _mandanten_of_user(current_user)


@router.get("/list", response_model=List[MandantResponse])
async def get_mandanten_list(current_user: dict = Depends(get_current_user)):
    """Wie `GET /api/mandanten`: zugelassene Mandanten des Benutzers mit ID, Name, Berechtigung."""
    return await _mandanten_of_user(current_user)


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
        
        # Prüfe Berechtigung: Zulassung des Benutzers (MANDANTEN.LIST, frisch aus der DB) und Mandanten-Freigabe (IS_ALLOWED)
        logger.info(f"🔐 Prüfe Berechtigung für User '{user_id}' auf Mandant '{mandant_id}'...")
        user_allowed = is_mandant_allowed(await load_user_daten(user_id), mandant_id)
        has_access = user_allowed and await manager.check_access(mandant_id, user_id)
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

        # Adressen aus MANDANT.*, Zugangsdaten ueber CREDENTIAL bzw. AUTH-Zugangsdaten (ConnectionManager).
        from ..core.credential_service import ensure_fresh
        await ensure_fresh()
        try:
            system_config, mandant_config = ConnectionManager.resolve_mandant_connections(
                mandant_config_dict, fallback_database=database
            )
        except ValueError as cred_error:
            raise HTTPException(status_code=500, detail=str(cred_error))
        mandant_db_name = mandant_config.database
        mandant_db_url = mandant_config.to_url()
        system_db_url = system_config.to_url()
        # Existenzpruefung der Mandanten-DB: ueber die System-DB, wenn beide auf derselben Instanz liegen,
        # sonst ueber die Verwaltungsdatenbank 'postgres' der Mandanten-Instanz.
        if ConnectionManager.same_instance(system_config, mandant_config):
            admin_db_url = system_db_url
        else:
            admin_db_url = ConnectionConfig(
                mandant_config.host, mandant_config.port, mandant_config.user, mandant_config.password,
                "postgres", ssl=mandant_config.ssl,
            ).to_url()
        
        print(f"✅ Connection-Config extrahiert:", flush=True)
        print(f"  System-DB: {system_config.database} @ {system_config.host}:{system_config.port}", flush=True)
        print(f"  Mandant-DB: {mandant_config.database} @ {mandant_config.host}:{mandant_config.port}", flush=True)
        
        # ========================================
        # DATENBANK-EXISTENZ PRÜFEN UND ERSTELLEN
        # ========================================
        print(f"🔧 DEBUG: Starte Datenbank-Existenz-Prüfung...", flush=True)
        logger.info(f"🔧 DEBUG: Starte Datenbank-Existenz-Prüfung...")
        
        # Verwende direkte Connection statt Pool (Pool-Connections werden manchmal geschlossen)
        from ..core.config import settings
        
        try:
            print(f"🔍 Erstelle direkte Connection zu pdvm_system via ConnectionManager...", flush=True)
            # ✅ Verwende system_config vom ConnectionManager (bereits oben geladen)
            conn = await provisioning.connect_pooled(admin_db_url)
            try:
                print(f"✅ Connection erfolgreich", flush=True)
                print(f"🔍 Prüfe Datenbank '{mandant_db_name}' in pg_database...", flush=True)
                
                db_exists = await conn.lookup_database(mandant_db_name)
                print(f"✅ Query erfolgreich, db_exists={db_exists}", flush=True)
                
                if not db_exists:
                    if not settings.ALLOW_MANDANT_DB_AUTO_CREATE:
                        raise HTTPException(
                            status_code=500,
                            detail=(
                                f"Mandanten-Datenbank '{mandant_db_name}' existiert nicht. "
                                "Auto-Create ist deaktiviert. Bitte MANDANT.DATABASE in asy_mandanten pruefen."
                            )
                        )

                    logger.info(f"📦 Datenbank '{mandant_db_name}' existiert nicht - erstelle sie...")
                    
                    # CREATE DATABASE mit template0 (garantiert keine aktiven Verbindungen)
                    await conn.create_database(mandant_db_name, from_template0=True)
                    logger.info(f"✅ Datenbank '{mandant_db_name}' erfolgreich erstellt")
                    
                    # WICHTIG: Nach CREATE DATABASE warten auf PostgreSQL-Initialisierung
                    await asyncio.sleep(1.0)
                    logger.info(f"⏳ Warte auf DB-Initialisierung...")
                    
                    # Erste Connection: Extensions installieren und Init-Tabelle anlegen
                    init_conn = await provisioning.connect(mandant_db_url, timeout=10)
                    try:
                        # SCHRITT 1: Extensions installieren (uuid-ossp für gen_random_uuid)
                        await init_conn.install_uuid_ossp()
                        logger.info(f"✅ Extension 'uuid-ossp' installiert")
                        
                        # SCHRITT 2: Init-Tabelle anlegen (jetzt mit UUID-Support)
                        await init_conn.write_init_marker(provisioning.INIT_MARKER_AUTO_CREATE)
                        logger.info(f"✅ Init-Tabelle '_db_init' in '{mandant_db_name}' angelegt")
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
                    logger.info(f"✓ Datenbank '{mandant_db_name}' existiert bereits")
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
        # - Fehlende Tabellen aus CONFIG.FEATURES (NEU ANLEGEN mit Standard-Schema)
        # - Existierende Tabellen: Fehlende Spalten (daten_backup, gilt_bis, etc.)
        # - Existierende Tabellen: Falsche Datentypen korrigieren (gilt_bis TEXT → TIMESTAMP)
        # - gilt_bis Werte für alte Datensätze korrigieren
        # ========================================
        try:
            print(f"\n🔧 Starte Datenbank-Wartung...", flush=True)
            logger.info(f"🔧 Starte Datenbank-Wartung für Mandant {mandant_id}")
            
            from ..core.mandant_db_maintenance import run_mandant_maintenance
            
            # Erstelle temporären Connection Pool für Wartung
            mandant_pool = await provisioning.get_shared_pool(mandant_db_url)
            
            try:
                # Führe Wartung aus - übergebe mandant['daten'] mit CONFIG
                maintenance_stats = await run_mandant_maintenance(
                    mandant_pool, 
                    mandant_id,
                    mandant['daten']  # Login-Daten enthält CONFIG.FEATURES
                )
                
                logger.info(f"✅ Wartung abgeschlossen: {maintenance_stats}")
                print(f"✅ Wartung: {maintenance_stats['tables_created']} Tabellen erstellt, "
                      f"{maintenance_stats['records_updated']} Datensätze korrigiert", flush=True)
            finally:
                # Pool schließen
                pass  # gemeinsamer Pool (PoolRegistry) bleibt offen
            
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

        # Deprecated Cleanup: CONFIG.SYS_TABLES wird nicht mehr verwendet.
        try:
            cfg = mandant_data.get("CONFIG") if isinstance(mandant_data, dict) else None
            if isinstance(cfg, dict) and "SYS_TABLES" in cfg:
                cfg.pop("SYS_TABLES", None)
                if isinstance(mandant_data.get("MANDANT"), dict):
                    mandant_data["MANDANT"]["MODIFIED"] = datetime.now().isoformat()
                updated_mandant = await manager.db_service.update(
                    uid=mandant_id,
                    daten=mandant_data,
                    name=mandant.get("name"),
                    backup_old=True,
                )
                mandant = updated_mandant if isinstance(updated_mandant, dict) else mandant
                mandant_data = mandant.get("daten", mandant_data)
                logger.info(f"✅ Deprecated CONFIG.SYS_TABLES aus Mandant {mandant_id} entfernt")
        except Exception as cleanup_exc:
            logger.warning(f"⚠️ CONFIG.SYS_TABLES Cleanup fehlgeschlagen: {cleanup_exc}")
        
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

        # Systemvorlagen (Texte) einmalig in den Mandanten uebernehmen; ein Fehler darf die Anmeldung nicht blockieren.
        try:
            from app.core.text_template_service import ensure_mandant_templates

            copied = await ensure_mandant_templates(
                system_pool=gcs._system_pool, mandant_pool=gcs._mandant_pool, actor_user_uid=user_id
            )
            if copied:
                logger.info(f"✅ Textvorlagen in Mandant übernommen: {copied}")
        except Exception as template_exc:
            logger.warning(f"⚠️ Textvorlagen konnten nicht übernommen werden: {template_exc}")
        
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
            "language": _effective_language(user_data, mandant_data),
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
async def get_mandant_template(current_user: dict = Depends(require_superadmin_user)):
    """
    Gibt Template und Properties Control für Mandanten-Neuanlage zurück
    
    Returns:
        template: Neuer Mandantensatz in Datensatzform (ROOT + Gruppen) aus der 666-Vorlage, ohne Zugangsdaten
        frame_guid: Frame (sys_framedaten), das die Eingabemaske definiert (GET /api/frames/{uid}/runtime)
    """
    from ..core.pdvm_datenbank import PdvmDatabase
    from ..core.mandant_record_rules import MANDANT_FRAME_GUID, flatten_mandant_template
    import uuid
    
    try:
        # Für asy_mandanten verwenden wir PdvmDatabase direkt (keine Central-Klasse nötig)
        db = PdvmDatabase("asy_mandanten")
        
        # Template laden (UID 6666...)
        template_uid = uuid.UUID("66666666-6666-6666-6666-666666666666")
        template_record = await db.get_by_uid(template_uid)
        
        if not template_record:
            raise HTTPException(status_code=404, detail="Template nicht gefunden")
        
        # Feld-Properties (Typ, Label, ...) liefert das Frame ueber sys_control_dict, nicht dieser Endpunkt.
        return {
            "template": flatten_mandant_template(template_record["daten"]),
            "frame_guid": MANDANT_FRAME_GUID,
            "template_uid": str(template_uid),
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Fehler beim Laden des Templates: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/create")
async def create_mandant_endpoint(
    mandant_data: dict,
    setup_database: bool = True,
    current_user: dict = Depends(require_superadmin_user)
):
    """
    Legt einen neuen Mandanten an (nur Superadmin): prüfen, Satz speichern, dem Anleger in `MANDANTEN.LIST`
    zuweisen und die Datenbank einrichten (`setup_database=false` überspringt den letzten Schritt).

    Body: Datensatzform der Mandanten-Maske (wie von `GET /template`, Frame `Mandanten Edit`); Zugangsdaten nur als
    `CREDENTIAL`-Verweis. Antwort: Status je Teilschritt (`saved`, `access_granted`, `database.status`). Ein Fehler bei der
    Datenbank lässt den Satz bestehen (kein Rollback); die Aktion `mandant.setup` wiederholt diesen Schritt.
    Tabellen entstehen beim ersten Login des Mandanten.
    """
    try:
        result = await create_mandant(
            mandant_data=mandant_data,
            actor_uid=current_user.get("sub"),
            actor_ip=current_user.get("client_ip"),
            setup_database=setup_database,
        )
    except MandantValidationError as exc:
        raise HTTPException(status_code=422, detail={"errors": exc.errors})
    except Exception as e:
        logger.error(f"Fehler beim Anlegen des Mandanten: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    return {"success": True, **result}


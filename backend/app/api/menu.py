"""
Menu API - Lädt und verwaltet PDVM Menüs über GCS
Verwendet PdvmDatabase für sys_menudaten (in pdvm_system DB)
"""
from fastapi import APIRouter, Depends, HTTPException
from typing import Dict, Any
import logging
import uuid
from ..core.security import get_current_user
from ..core.pdvm_datenbank import PdvmDatabase
from ..api.gcs import get_gcs_instance

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/start")
async def get_start_menu(
    current_user: dict = Depends(get_current_user),
    gcs = Depends(get_gcs_instance)
) -> Dict[str, Any]:
    """
    Lädt das Startmenü des Benutzers aus GCS.MEINEAPPS.START.MENU
    
    Returns:
        Menü-Struktur mit VERTIKAL, GRUND, ZUSATZ, ROOT
    """
    try:
        # Startmenü-GUID aus GCS holen (MEINEAPPS.START.MENU)
        meineapps = gcs.get_user_value("MEINEAPPS")
        
        if not isinstance(meineapps, dict) or "START" not in meineapps:
            raise HTTPException(
                status_code=404,
                detail="Kein Startmenü definiert. Bitte Administrator kontaktieren."
            )
        
        start_config = meineapps["START"]
        menu_guid = start_config.get("MENU") if isinstance(start_config, dict) else None
        
        if not menu_guid:
            raise HTTPException(
                status_code=404,
                detail="Keine Startmenü-GUID gefunden"
            )
        
        logger.info(f"📋 Lade Startmenü: {menu_guid} für User {gcs.user_guid}")
        
        # Menü aus sys_menudaten laden (via PdvmDatabase mit system_pool)
        menu_db = PdvmDatabase("sys_menudaten", system_pool=gcs._system_pool)
        menu = await menu_db.get_by_uid(uuid.UUID(menu_guid))
        
        if not menu:
            raise HTTPException(
                status_code=404,
                detail=f"Startmenü {menu_guid} nicht gefunden"
            )
        
        return {
            "uid": str(menu["uid"]),
            "name": menu.get("name", "Startmenü"),
            "menu_data": menu.get("daten", {})
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Fehler beim Laden des Startmenüs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/app/{app_name}")
async def get_app_menu(
    app_name: str,
    current_user: dict = Depends(get_current_user),
    gcs = Depends(get_gcs_instance)
) -> Dict[str, Any]:
    """
    Lädt ein App-Menü aus GCS.MEINEAPPS.{APP_NAME}.MENU
    
    Args:
        app_name: Name der Applikation (z.B. "PERSONALWESEN", "ADMINISTRATION")
        
    Returns:
        Menü-Struktur oder Fehler bei fehlender Berechtigung
    """
    try:
        # App-Menü-GUID aus GCS holen (MEINEAPPS.{APP_NAME}.MENU)
        meineapps = gcs.get_user_value("MEINEAPPS")
        
        if not isinstance(meineapps, dict) or app_name not in meineapps:
            logger.warning(f"❌ Keine Berechtigung für {app_name}: User {gcs.user_guid}")
            return {
                "uid": None,
                "name": app_name,
                "menu_data": None,
                "error": "NO_PERMISSION",
                "message": f"Keine Berechtigung für {app_name}"
            }
        
        app_config = meineapps[app_name]
        menu_guid = app_config.get("MENU") if isinstance(app_config, dict) else None
        
        if not menu_guid:
            logger.warning(f"❌ Kein Menü für {app_name}: User {gcs.user_guid}")
            return {
                "uid": None,
                "name": app_name,
                "menu_data": None,
                "error": "NO_MENU",
                "message": f"Kein Menü für {app_name} definiert"
            }
        
        logger.info(f"📋 Lade App-Menü: {app_name} → {menu_guid}")
        
        # Menü aus sys_menudaten laden
        menu_db = PdvmDatabase("sys_menudaten", system_pool=gcs._system_pool)
        menu = await menu_db.get_by_uid(uuid.UUID(menu_guid))
        
        if not menu:
            raise HTTPException(
                status_code=404,
                detail=f"Menü {menu_guid} für {app_name} nicht gefunden"
            )
        
        return {
            "uid": str(menu["uid"]),
            "name": menu.get("name", app_name),
            "menu_data": menu.get("daten", {})
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Fehler beim Laden des App-Menüs {app_name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

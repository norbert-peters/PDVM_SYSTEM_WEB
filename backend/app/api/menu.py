"""
Menu API - Lädt und verwaltet PDVM Menüs über GCS
Verwendet PdvmCentralDatabase für sys_menudaten (in pdvm_system DB)
"""
from fastapi import APIRouter, Depends, HTTPException
from typing import Dict, Any
import logging
import uuid
from ..core.security import get_current_user
from ..core.pdvm_central_datenbank import PdvmCentralDatabase
from ..api.gcs import get_gcs_instance

router = APIRouter()
logger = logging.getLogger(__name__)


async def expand_templates(gruppe_items: Dict[str, Any], gruppe_name: str, system_pool) -> Dict[str, Any]:
    """
    Expandiert Template-Menüs (SPACER mit template_guid) in einer Gruppe.
    
    Args:
        gruppe_items: Dictionary mit Menu-Items einer Gruppe
        gruppe_name: Name der Gruppe (GRUND, ZUSATZ, VERTIKAL) für Template-Zugriff
        system_pool: Connection pool für sys_menudaten
        
    Returns:
        Expandierte Items mit eingefügten Templates
    """
    result = gruppe_items.copy()
    
    # Finde SPACER mit template_guid
    for item_guid, item in list(gruppe_items.items()):
        if item.get("type") == "SPACER" and item.get("template_guid"):
            template_guid = item["template_guid"]
            
            try:
                # Lade Template-Menü mit PdvmCentralDatabase.load()
                template_menu = await PdvmCentralDatabase.load("sys_menudaten", template_guid, system_pool=system_pool)
                
                # Hole Items derselben Gruppe
                template_items = template_menu.get_value_by_group(gruppe_name)
                
                # Füge Template-Items ein (ohne Duplikate)
                for tmpl_guid, tmpl_item in template_items.items():
                    if tmpl_guid not in result:
                        result[tmpl_guid] = tmpl_item
                
                logger.info(f"✅ Template {template_guid} in {gruppe_name} expandiert: {len(template_items)} Items")
                
            except Exception as e:
                logger.warning(f"⚠️ Template {template_guid} konnte nicht geladen werden: {e}")
    
    return result


@router.get("/start")
async def get_start_menu(
    current_user: dict = Depends(get_current_user),
    gcs = Depends(get_gcs_instance)
) -> Dict[str, Any]:
    """
    Lädt das Startmenü des Benutzers aus GCS.MEINEAPPS.START.MENU
    
    Einfache Pipeline:
    1. Menü-GUID aus GCS holen
    2. Menü in PdvmCentralDatabase laden
    3. Pro Gruppe: get_value_by_group() → Template expandieren → Fertig
    
    Returns:
        {
            "GRUND": {...},
            "ZUSATZ": {...},
            "VERTIKAL": {...}
        }
    """
    try:
        # 1. Startmenü-GUID aus GCS.BENUTZER.MEINEAPPS.START.MENU
        meineapps = gcs.benutzer.get_static_value("MEINEAPPS", "START")
        
        if not isinstance(meineapps, dict) or "MENU" not in meineapps:
            raise HTTPException(
                status_code=404,
                detail="Kein Startmenü definiert. Bitte Administrator kontaktieren."
            )
        
        menu_guid = meineapps.get("MENU")
        if not menu_guid:
            raise HTTPException(status_code=404, detail="Keine Startmenü-GUID gefunden")
        
        logger.info(f"📋 Lade Startmenü: {menu_guid} für User {gcs.user_guid}")
        
        # 2. Menü laden - Daten werden automatisch in Instanz geladen
        menu = await PdvmCentralDatabase.load("sys_menudaten", menu_guid, system_pool=gcs._system_pool)
        
        # 3. Gruppen einzeln holen und Template expandieren
        grund = menu.get_value_by_group("GRUND")
        vertikal = menu.get_value_by_group("VERTIKAL")
        
        # Template-Expansion (mit Gruppen-Namen für korrekte Template-Zuordnung)
        grund = await expand_templates(grund, "GRUND", gcs._system_pool) if grund else {}
        vertikal = await expand_templates(vertikal, "VERTIKAL", gcs._system_pool) if vertikal else {}
        
        return {
            "uid": menu_guid,
            "name": "Startmenü",
            "menu_data": {
                "GRUND": grund,
                "VERTIKAL": vertikal
            }
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
        # App-Menü-GUID aus BENUTZER-Instanz holen (MEINEAPPS.{APP_NAME}.MENU)
        # Desktop-Pattern: gcs.benutzer.get_static_value("MEINEAPPS", APP_NAME)
        app_config = gcs.benutzer.get_static_value("MEINEAPPS", app_name)
        
        if not app_config or not isinstance(app_config, dict):
            logger.warning(f"❌ Keine Berechtigung für {app_name}: User {gcs.user_guid}")
            return {
                "uid": None,
                "name": app_name,
                "menu_data": None,
                "error": "NO_PERMISSION",
                "message": f"Keine Berechtigung für {app_name}"
            }
        
        menu_guid = app_config.get("MENU")
        
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
        
        # Menü laden mit PdvmCentralDatabase.load()
        menu = await PdvmCentralDatabase.load("sys_menudaten", menu_guid, system_pool=gcs._system_pool)
        
        # Gruppen einzeln holen und Template expandieren
        grund = menu.get_value_by_group("GRUND")
        vertikal = menu.get_value_by_group("VERTIKAL")
        
        # Template-Expansion
        grund = await expand_templates(grund, "GRUND", gcs._system_pool) if grund else {}
        vertikal = await expand_templates(vertikal, "VERTIKAL", gcs._system_pool) if vertikal else {}
        
        # DEBUG: Zeige was zurückgegeben wird
        logger.info(f"📤 API Response für {app_name}:")
        logger.info(f"   GRUND: {len(grund)} Items")
        logger.info(f"   VERTIKAL: {len(vertikal)} Items")
        if vertikal:
            logger.info(f"   VERTIKAL Keys: {list(vertikal.keys())[:5]}...")  # Erste 5 Keys
        
        return {
            "uid": menu_guid,
            "name": app_name,
            "menu_data": {
                "GRUND": grund,
                "VERTIKAL": vertikal
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Fehler beim Laden des App-Menüs {app_name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

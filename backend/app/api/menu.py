"""
Menu API - Lädt und verwaltet PDVM Menüs über GCS
Verwendet PdvmCentralDatabase für sys_menudaten (in pdvm_system DB)
"""
from fastapi import APIRouter, Depends, HTTPException
from typing import Dict, Any, Optional
import logging
import uuid
import json
from pydantic import BaseModel, Field
from ..core.security import get_current_user
from ..core.pdvm_central_datenbank import PdvmCentralDatabase
from ..api.gcs import get_gcs_instance

router = APIRouter()
logger = logging.getLogger(__name__)

_SYS_FIELD_LAST_NAVIGATION = "LAST_NAVIGATION"


def _has_children(items: Dict[str, Any], uid: str) -> bool:
    uid_str = str(uid).strip()
    for _k, item in (items or {}).items():
        if not isinstance(item, dict):
            continue
        if str(item.get("parent_guid") or "").strip() == uid_str:
            return True
    return False


def _normalize_menu_group(items: Dict[str, Any]) -> Dict[str, Any]:
    """Enforce menu invariants on a fully expanded group (incl. templates).

    Rules:
    - If an item has children, it must be SUBMENU and must not have a command.
    - If a SUBMENU has no children, it becomes BUTTON.
    - Missing type defaults to BUTTON.
    - SEPARATOR/SPACER stay unchanged.
    """
    if not isinstance(items, dict):
        return items

    parent_uids = set()
    for uid_key in items.keys():
        uid_str = str(uid_key).strip()
        if uid_str and _has_children(items, uid_str):
            parent_uids.add(uid_str)

    out: Dict[str, Any] = {}
    for uid_key, item in items.items():
        if not isinstance(item, dict):
            out[uid_key] = item
            continue

        uid_str = str(uid_key).strip()
        t = str(item.get("type") or "").strip().upper()

        if t in {"SEPARATOR", "SPACER"}:
            out[uid_key] = item
            continue

        next_item = {**item}
        if uid_str in parent_uids:
            next_item["type"] = "SUBMENU"
            if next_item.get("command") is not None:
                next_item["command"] = None
        else:
            if t == "SUBMENU":
                next_item["type"] = "BUTTON"
            elif not t:
                next_item["type"] = "BUTTON"

        out[uid_key] = next_item

    return out


class MenuCommandModel(BaseModel):
    handler: str = Field(..., min_length=1)
    params: Dict[str, Any] = Field(default_factory=dict)


class MenuLastNavigationState(BaseModel):
    menu_type: str = Field(..., description="start|app")
    app_name: Optional[str] = None
    command: Optional[MenuCommandModel] = None
    updated_at: Optional[str] = None


def _parse_jsonish(raw: Any) -> Dict[str, Any]:
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        parsed = json.loads(str(raw))
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def _validate_last_nav_payload(data: Dict[str, Any]) -> Dict[str, Any]:
    menu_type = str((data or {}).get("menu_type") or "").strip().lower()
    if menu_type not in {"start", "app"}:
        raise HTTPException(status_code=400, detail="menu_type muss 'start' oder 'app' sein")

    app_name = data.get("app_name")
    app_name = str(app_name).strip() if app_name is not None else None
    if menu_type == "app" and not app_name:
        raise HTTPException(status_code=400, detail="app_name ist erforderlich wenn menu_type='app'")

    cmd = data.get("command")
    if cmd is not None and not isinstance(cmd, dict):
        raise HTTPException(status_code=400, detail="command muss ein Objekt sein")

    if isinstance(cmd, dict):
        handler = str(cmd.get("handler") or "").strip()
        if not handler:
            raise HTTPException(status_code=400, detail="command.handler fehlt")
        params = cmd.get("params")
        if params is None:
            params = {}
        if not isinstance(params, dict):
            raise HTTPException(status_code=400, detail="command.params muss ein Objekt sein")
        cmd = {"handler": handler, "params": params}

    out: Dict[str, Any] = {
        "menu_type": menu_type,
        "app_name": app_name,
        "command": cmd,
        "updated_at": str(data.get("updated_at") or "").strip() or None,
    }
    return out


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
        
        # 3. Gruppen einzeln holen
        grund = menu.get_value_by_group("GRUND")
        vertikal = menu.get_value_by_group("VERTIKAL")
        root = menu.get_value_by_group("ROOT")
        
        # Template-Expansion (mit Gruppen-Namen für korrekte Template-Zuordnung)
        grund = await expand_templates(grund, "GRUND", gcs._system_pool) if grund else {}
        vertikal = await expand_templates(vertikal, "VERTIKAL", gcs._system_pool) if vertikal else {}

        # Enforce invariants after expansion (parents become SUBMENU, commands stripped)
        grund = _normalize_menu_group(grund)
        vertikal = _normalize_menu_group(vertikal)
        
        return {
            "uid": menu_guid,
            "name": "Startmenü",
            "menu_data": {
                "ROOT": root,
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
        
        # Gruppen einzeln holen
        grund = menu.get_value_by_group("GRUND")
        vertikal = menu.get_value_by_group("VERTIKAL")
        root = menu.get_value_by_group("ROOT")
        
        # Template-Expansion
        grund = await expand_templates(grund, "GRUND", gcs._system_pool) if grund else {}
        vertikal = await expand_templates(vertikal, "VERTIKAL", gcs._system_pool) if vertikal else {}

        # Enforce invariants after expansion (parents become SUBMENU, commands stripped)
        grund = _normalize_menu_group(grund)
        vertikal = _normalize_menu_group(vertikal)
        
        # DEBUG: Zeige was zurückgegeben wird
        logger.info(f"📤 API Response für {app_name}:")
        logger.info(f"   ROOT: {root}")
        logger.info(f"   GRUND: {len(grund)} Items")
        logger.info(f"   VERTIKAL: {len(vertikal)} Items")
        if vertikal:
            logger.info(f"   VERTIKAL Keys: {list(vertikal.keys())[:5]}...")  # Erste 5 Keys
        
        return {
            "uid": menu_guid,
            "name": app_name,
            "menu_data": {
                "ROOT": root,
                "GRUND": grund,
                "VERTIKAL": vertikal
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Fehler beim Laden des App-Menüs {app_name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/last-navigation", response_model=MenuLastNavigationState)
async def get_last_navigation(
    current_user: dict = Depends(get_current_user),
    gcs = Depends(get_gcs_instance),
) -> MenuLastNavigationState:
    """Liest die letzte Menü-Navigation des Users aus sys_systemsteuerung.

    Persistenz-Key:
    - Gruppe: user_guid
    - Feld: LAST_NAVIGATION
    - Wert: JSON-Objekt
      {menu_type:'start'|'app', app_name?:'...', command?:{handler,params}, updated_at?:'...'}
    """

    try:
        key = str(uuid.UUID(str(gcs.user_guid)))
    except Exception:
        raise HTTPException(status_code=500, detail="Ungültige user_guid in GCS")

    try:
        raw, _ = gcs.systemsteuerung.get_value(key, _SYS_FIELD_LAST_NAVIGATION, ab_zeit=gcs.stichtag)
    except Exception:
        raw = None

    if raw is None:
        return MenuLastNavigationState(menu_type="start", app_name=None, command=None, updated_at=None)

    data = _parse_jsonish(raw)
    try:
        validated = _validate_last_nav_payload(data)
    except HTTPException:
        # Falls alte/kaputte Daten drin sind, lieber leer zurückgeben
        return MenuLastNavigationState(menu_type="start", app_name=None, command=None, updated_at=None)

    return MenuLastNavigationState(**validated)


@router.put("/last-navigation", response_model=MenuLastNavigationState)
async def put_last_navigation(
    payload: MenuLastNavigationState,
    current_user: dict = Depends(get_current_user),
    gcs = Depends(get_gcs_instance),
) -> MenuLastNavigationState:
    """Speichert die letzte Menü-Navigation des Users in sys_systemsteuerung."""

    try:
        key = str(uuid.UUID(str(gcs.user_guid)))
    except Exception:
        raise HTTPException(status_code=500, detail="Ungültige user_guid in GCS")

    raw = payload.model_dump()
    validated = _validate_last_nav_payload(raw)

    # updated_at automatisch setzen, wenn nicht mitgegeben
    if not validated.get("updated_at"):
        from datetime import datetime, timezone

        validated["updated_at"] = datetime.now(timezone.utc).isoformat()

    gcs.systemsteuerung.set_value(key, _SYS_FIELD_LAST_NAVIGATION, validated, gcs.stichtag)
    await gcs.systemsteuerung.save_all_values()
    return MenuLastNavigationState(**validated)

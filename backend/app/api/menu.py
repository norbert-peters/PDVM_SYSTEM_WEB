"""
Menu API - Lädt und verwaltet PDVM Menüs über GCS
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from typing import Dict, Any
import json
import asyncpg
from ..core.database import get_db_connection
from ..core.security import get_current_user
from ..core.gcs import get_gcs_session
from ..core.config import settings
from ..core.connection_manager import ConnectionManager

router = APIRouter()


@router.get("/{menu_guid}")
async def get_menu(
    menu_guid: str,
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Lädt ein Menü aus sys_menudaten.
    
    Args:
        menu_guid: GUID des Menüs (z.B. aus MEINEAPPS.START.MENU)
        
    Returns:
        Menü-Struktur mit VERTIKAL, GRUND, ZUSATZ, ROOT
        
    Beispiel Response:
        {
            "uid": "5ca6674e-...",
            "name": "Admin Startmenü",
            "menu_data": {
                "VERTIKAL": {...},
                "GRUND": {...},
                "ZUSATZ": {...},
                "ROOT": {...}
            }
        }
    """
    # ✅ Menü aus GLOBALER pdvm_system-Datenbank laden via ConnectionManager
    # TODO: Falls Mandant eigene System-DB hat, diese verwenden!
    # Aktuell: Default pdvm_system
    system_config = await ConnectionManager.get_system_config("pdvm_system")
    conn = await asyncpg.connect(**system_config.to_dict())
    
    try:
        # Menü laden
        menu = await conn.fetchrow(
            "SELECT uid, name, daten FROM sys_menudaten WHERE uid = $1 AND historisch = 0",
            menu_guid
        )
        
        if not menu:
            raise HTTPException(
                status_code=404,
                detail=f"Menü mit GUID {menu_guid} nicht gefunden"
            )
        
        # JSONB kann als String oder dict kommen
        menu_data = menu['daten']
        if isinstance(menu_data, str):
            menu_data = json.loads(menu_data)
        
        return {
            "uid": str(menu['uid']),
            "name": menu['name'],
            "menu_data": menu_data
        }
    finally:
        await conn.close()


@router.get("/user/start")
async def get_user_start_menu(
    request: Request,
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Lädt das Start-Menü des aktuellen Benutzers über GCS.
    
    Verwendet MEINEAPPS.START.MENU aus den User-Daten (via GCS).
    
    Returns:
        Menü-Struktur des Startmenüs
    """
    # Token aus Authorization Header extrahieren
    auth_header = request.headers.get("Authorization", "")
    token = auth_header.replace("Bearer ", "") if auth_header.startswith("Bearer ") else ""
    
    if not token:
        raise HTTPException(
            status_code=401,
            detail="Kein Token gefunden"
        )
    
    # GCS-Session holen (enthält vollständige User-Daten mit MEINEAPPS)
    gcs = get_gcs_session(token)
    
    if not gcs:
        raise HTTPException(
            status_code=401,
            detail="Keine GCS-Session gefunden - bitte Mandant auswählen"
        )
    
    # START.MENU GUID aus GCS User-Daten holen
    user_data = gcs.user_data  # Vollständige User-Daten sind in GCS gecached
    print(f"🔍 DEBUG: user_data keys: {list(user_data.keys()) if user_data else 'None'}", flush=True)
    print(f"🔍 DEBUG: MEINEAPPS content: {user_data.get('MEINEAPPS', 'NOT FOUND')}", flush=True)
    
    start_menu_guid = user_data.get('MEINEAPPS', {}).get('START', {}).get('MENU')
    print(f"🔍 DEBUG: Extracted START.MENU GUID: {start_menu_guid}", flush=True)
    
    if not start_menu_guid:
        raise HTTPException(
            status_code=404,
            detail="Kein Startmenü für Benutzer konfiguriert (MEINEAPPS.START.MENU fehlt)"
        )
    
    # Menü aus GLOBALER pdvm_system-Datenbank laden (nicht mandanten-spezifisch!)
    # sys_menudaten ist zentral in pdvm_system, nicht in pdvm_system_<mandant>
    conn = await asyncpg.connect(settings.DATABASE_URL_SYSTEM)
    
    try:
        # Menü laden
        menu = await conn.fetchrow(
            "SELECT uid, name, daten FROM sys_menudaten WHERE uid = $1 AND historisch = 0",
            start_menu_guid
        )
        
        if not menu:
            raise HTTPException(
                status_code=404,
                detail=f"Menü mit GUID {start_menu_guid} nicht gefunden"
            )
        
        # JSONB kann als String oder dict kommen
        menu_data = menu['daten']
        if isinstance(menu_data, str):
            menu_data = json.loads(menu_data)
        
        return {
            "uid": str(menu['uid']),
            "name": menu['name'],
            "menu_data": menu_data  # Frontend erwartet 'menu_data', nicht 'daten'
        }
    finally:
        await conn.close()


@router.get("/items/{menu_guid}/flat")
async def get_menu_items_flat(
    menu_guid: str,
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Lädt alle Menü-Items als flache Liste (für einfache Iteration).
    
    Returns:
        {
            "items": [
                {
                    "guid": "...",
                    "type": "BUTTON",
                    "label": "Personalwesen",
                    "gruppe": "VERTIKAL",
                    ...
                },
                ...
            ]
        }
    """
    menu = await get_menu(menu_guid, current_user)
    menu_data = menu['menu_data']
    
    items = []
    
    # Alle Gruppen durchgehen
    for gruppe in ['VERTIKAL', 'GRUND', 'ZUSATZ']:
        gruppe_items = menu_data.get(gruppe, {})
        
        for item_guid, item_data in gruppe_items.items():
            items.append({
                "guid": item_guid,
                "gruppe": gruppe,
                **item_data
            })
    
    # Nach sort_order sortieren
    items.sort(key=lambda x: (x.get('sort_order', 999), x.get('label', '')))
    
    return {
        "menu_uid": menu['uid'],
        "menu_name": menu['name'],
        "items": items,
        "root": menu_data.get('ROOT', {})
    }

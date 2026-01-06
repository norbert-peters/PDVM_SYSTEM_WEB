"""
Layout API
Endpoints für mandantenspezifische Layouts und Themes
"""
from fastapi import APIRouter, HTTPException, Depends
from typing import Optional, Dict, Any
from uuid import UUID
import logging
import json

from ..core.pdvm_database import PdvmDatabaseService
from ..core.security import get_current_user
from .gcs import get_gcs_instance

router = APIRouter(tags=["layout"])
logger = logging.getLogger(__name__)


@router.get("/{mandant_uid}")
async def get_mandant_layouts(
    mandant_uid: str,
    theme: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    """
    Lädt Layout-Konfiguration für einen Mandanten
    
    Args:
        mandant_uid: UUID des Mandanten
        theme: Optional - 'light' oder 'dark', wenn None werden beide zurückgegeben
        
    Returns:
        Layout-Konfiguration(en)
    """
    try:
        db = PdvmDatabaseService(database="pdvm_system", table="sys_layout")
        
        # Alle Layouts für den Mandanten
        all_layouts = await db.list_all(historisch=0)
        
        # Filtere nach mandant_uid
        mandant_layouts = [
            layout for layout in all_layouts 
            if layout.get('daten', {}).get('mandant_uid') == mandant_uid
        ]
        
        if not mandant_layouts:
            raise HTTPException(
                status_code=404,
                detail=f"Keine Layouts gefunden für Mandant {mandant_uid}"
            )
        
        # Wenn theme spezifiziert, nur dieses zurückgeben
        if theme:
            theme_layout = next(
                (l for l in mandant_layouts if l.get('daten', {}).get('theme') == theme),
                None
            )
            if not theme_layout:
                raise HTTPException(
                    status_code=404,
                    detail=f"Theme '{theme}' nicht gefunden für Mandant {mandant_uid}"
                )
            return theme_layout
        
        # Sonst alle Themes zurückgeben
        return {
            "mandant_uid": mandant_uid,
            "layouts": mandant_layouts
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Fehler beim Laden des Layouts: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/preferences/theme")
async def save_theme_preference(
    theme_mode: str,
    current_user: dict = Depends(get_current_user),
    gcs = Depends(get_gcs_instance)
):
    """
    Speichert Theme-Präferenz (light/dark) in sys_systemsteuerung
    
    Args:
        theme_mode: 'light' oder 'dark'
        
    Returns:
        Success-Nachricht
    """
    try:
        logger.info(f"📝 Speichere Theme-Präferenz: user={gcs.user_guid}, theme={theme_mode}")
        
        # Speichere über PdvmCentralSystemsteuerung (set_user_value)
        gcs.set_user_value("THEME_MODE", theme_mode)
        
        # Persistent speichern
        await gcs.save_all_values()
        
        logger.info(f"✅ Theme-Präferenz gespeichert: {theme_mode}")
        return {"success": True, "theme_mode": theme_mode}
        
    except Exception as e:
        logger.error(f"Fehler beim Speichern der Theme-Präferenz: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/preferences/theme")
async def get_theme_preference(
    current_user: dict = Depends(get_current_user),
    gcs = Depends(get_gcs_instance)
):
    """
    Lädt gespeicherte Theme-Präferenz aus sys_systemsteuerung
    
    Returns:
        Theme-Präferenz oder default 'light'
    """
    try:
        logger.info(f"📖 Lade Theme-Präferenz: user={gcs.user_guid}")
        
        # Lese über PdvmCentralSystemsteuerung (get_user_value)
        theme_mode = gcs.get_user_value("THEME_MODE")
        
        logger.info(f"💡 Gelesener Theme-Modus: {theme_mode}")
        
        # Default wenn noch nicht gesetzt
        if theme_mode is None:
            theme_mode = "light"
        
        return {"theme_mode": theme_mode}
        
    except Exception as e:
        logger.error(f"Fehler beim Laden der Theme-Präferenz: {e}")
        raise HTTPException(status_code=500, detail=str(e))
        logger.error(f"Fehler beim Laden der Theme-Präferenz: {e}")
        return {"theme_mode": "light"}  # Default bei Fehler


@router.get("/{mandant_uid}/{theme}")
async def get_mandant_theme(
    mandant_uid: str,
    theme: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Lädt spezifisches Theme für einen Mandanten
    NEUE STRUKTUR: Liest THEME_GUID aus Mandant-Config, lädt Theme und extrahiert Gruppe
    
    Args:
        mandant_uid: UUID des Mandanten
        theme: 'light' oder 'dark' (Gruppe)
        
    Returns:
        Layout-Konfiguration für das Theme
    """
    try:
        # 1. Lade Mandant aus auth DB um THEME_GUID zu bekommen
        from ..core.database import DatabasePool
        
        pool = DatabasePool._pool_auth
        async with pool.acquire() as conn:
            mandant_row = await conn.fetchrow("""
                SELECT uid, daten
                FROM sys_mandanten
                WHERE uid = $1
            """, mandant_uid)
        
        if not mandant_row:
            raise HTTPException(
                status_code=404,
                detail=f"Mandant {mandant_uid} nicht gefunden"
            )
        
        mandant_data = mandant_row['daten']
        if isinstance(mandant_data, str):
            mandant_data = json.loads(mandant_data)
        
        # 2. Hole THEME_GUID aus config
        theme_guid = mandant_data.get('config', {}).get('THEME_GUID')
        
        if not theme_guid:
            raise HTTPException(
                status_code=404,
                detail=f"THEME_GUID nicht in Mandant-Config gefunden"
            )
        
        # 3. Lade Theme-Datensatz aus sys_layout
        db = PdvmDatabaseService(database="pdvm_system", table="sys_layout")
        theme_record = await db.get_by_uid(theme_guid)
        
        if not theme_record:
            raise HTTPException(
                status_code=404,
                detail=f"Theme {theme_guid} nicht gefunden"
            )
        
        # 4. Extrahiere Gruppe (light/dark) aus daten-JSON
        theme_data = theme_record.get('daten', {})
        if isinstance(theme_data, str):
            theme_data = json.loads(theme_data)
            
        gruppe_data = theme_data.get(theme)
        
        if not gruppe_data:
            raise HTTPException(
                status_code=404,
                detail=f"Gruppe '{theme}' nicht im Theme gefunden"
            )
        
        # 5. Erstelle Response mit mandant_uid und mandant_name
        response = {
            "mandant_uid": mandant_uid,
            "mandant_name": mandant_data.get('name', 'Unknown'),
            "theme": theme,
            "colors": gruppe_data.get('colors', {}),
            "typography": gruppe_data.get('typography', {}),
            "customizations": gruppe_data.get('customizations', {}),
            "assets": gruppe_data.get('assets', {})
        }
        
        logger.info(f"✅ Theme geladen: {mandant_data.get('name')} → {theme}")
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Fehler beim Laden des Themes: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{mandant_uid}/{theme}")
async def update_mandant_theme(
    mandant_uid: str,
    theme: str,
    layout_data: Dict[str, Any],
    current_user: dict = Depends(get_current_user)
):
    """
    Aktualisiert Theme-Konfiguration für einen Mandanten
    
    Args:
        mandant_uid: UUID des Mandanten
        theme: 'light' oder 'dark'
        layout_data: Neue Layout-Konfiguration
        
    Returns:
        Aktualisiertes Layout
    """
    try:
        db = PdvmDatabaseService(database="pdvm_system", table="sys_layout")
        
        # Finde existierendes Layout
        all_layouts = await db.list_all(historisch=0)
        existing_layout = next(
            (l for l in all_layouts 
             if l.get('daten', {}).get('mandant_uid') == mandant_uid 
             and l.get('daten', {}).get('theme') == theme),
            None
        )
        
        if not existing_layout:
            raise HTTPException(
                status_code=404,
                detail=f"Layout nicht gefunden: {mandant_uid}/{theme}"
            )
        
        # Update daten
        updated_data = existing_layout.get('daten', {})
        updated_data.update(layout_data)
        
        # Speichere Update
        updated_layout = await db.update(
            uid=existing_layout['uid'],
            daten=updated_data
        )
        
        logger.info(f"✅ Layout aktualisiert: {mandant_uid}/{theme}")
        return updated_layout
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Fehler beim Update des Layouts: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/current/theme")
async def get_current_mandant_theme(
    theme: str = "light",
    current_user: dict = Depends(get_current_user)
):
    """
    Lädt Theme für den aktuell angemeldeten Mandanten
    
    Args:
        theme: 'light' oder 'dark' (default: light)
        
    Returns:
        Layout-Konfiguration
    """
    mandant_uid = current_user.get("mandant_uid")
    
    if not mandant_uid:
        raise HTTPException(
            status_code=400,
            detail="Kein Mandant ausgewählt"
        )
    
    return await get_mandant_theme(mandant_uid, theme, current_user)

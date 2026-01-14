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


def get_default_colors(theme: str) -> Dict[str, Any]:
    """Gibt Standard-Farben für light/dark Theme zurück"""
    if theme == 'dark':
        return {
            "primary": {"500": "#3b82f6", "600": "#2563eb"},
            "secondary": {"500": "#8b5cf6", "600": "#7c3aed"},
            "neutral": {"500": "#6b7280", "600": "#4b5563"},
            "success": "#10b981",
            "warning": "#f59e0b",
            "error": "#ef4444",
            "info": "#3b82f6",
            "background": {
                "primary": "#1e1e1e",
                "secondary": "#2d2d2d",
                "tertiary": "#3d3d3d"
            },
            "text": {
                "primary": "#ffffff",
                "secondary": "#b0b0b0",
                "disabled": "#6b7280",
                "inverse": "#000000"
            },
            "border": {
                "light": "#404040",
                "medium": "#525252",
                "dark": "#737373"
            }
        }
    else:  # light theme
        return {
            "primary": {"500": "#3b82f6", "600": "#2563eb"},
            "secondary": {"500": "#8b5cf6", "600": "#7c3aed"},
            "neutral": {"500": "#6b7280", "600": "#4b5563"},
            "success": "#10b981",
            "warning": "#f59e0b",
            "error": "#ef4444",
            "info": "#3b82f6",
            "background": {
                "primary": "#ffffff",
                "secondary": "#f3f4f6",
                "tertiary": "#e5e7eb"
            },
            "text": {
                "primary": "#111827",
                "secondary": "#4b5563",
                "disabled": "#9ca3af",
                "inverse": "#ffffff"
            },
            "border": {
                "light": "#e5e7eb",
                "medium": "#d1d5db",
                "dark": "#9ca3af"
            }
        }


def get_default_typography() -> Dict[str, Any]:
    """Gibt Standard-Typografie zurück"""
    return {
        "fontFamily": {
            "primary": "Inter, system-ui, sans-serif",
            "secondary": "Georgia, serif",
            "mono": "JetBrains Mono, monospace"
        },
        "fontSize": {"scale": 1.0},
        "fontWeight": {"normal": 400, "medium": 500, "bold": 700},
        "lineHeight": {"tight": 1.25, "normal": 1.5, "relaxed": 1.75}
    }


@router.get("/active")
async def get_active_theme(
    mode: Optional[str] = None,
    gcs = Depends(get_gcs_instance),
    current_user: dict = Depends(get_current_user)
):
    """
    Lädt das aktive Theme-Block-Set für den User.
    Kombiniert Mandanten-Vorgabe (Theme Package) und User-Präferenz (Variant).
    
    Args:
        mode: 'light' oder 'dark'. Wenn None, wird User-Präferenz aus GCS geladen.
    """
    logger.info(f"🎨 Lade aktives Theme für User {gcs.user_guid} (Mode override: {mode})")
    
    try:
        # 1. Modus bestimmen
        if not mode:
            # Versuche gespeicherten Modus, sonst Default 'light'
            mode = gcs.systemsteuerung.get_static_value(str(gcs.user_guid), "THEME_MODE") or "light"
        
        # 2. Ziel-Gruppe ermitteln (z.B. "Orange_Dark") via neuer Logic in GCS
        target_group = gcs.get_user_theme_group(mode)
        logger.info(f"Target Group: {target_group} (für Mode {mode})")
        
        # 3. Daten aus gcs.layout holen
        # Das Layout-Package wurde bereits beim GCS-Start basierend auf Mandant CONFIG geladen
        if not gcs.layout:
            logger.error("❌ gcs.layout ist None!")
            raise HTTPException(status_code=500, detail="Systemfehler: Layout-Container nicht initialisiert")
            
        # Hole alle Blöcke der Zielgruppe
        layout_blocks = gcs.layout.get_value_by_group(target_group)
        
        if not layout_blocks:
            logger.warning(f"⚠️ Keine Blöcke gefunden für Gruppe '{target_group}' im Layout {gcs.layout.guid}")
            # Fallback oder leeres Set zurückgeben?
            # Wir geben Warnung zurück, Frontend muss Fallback nutzen
        
        return {
            "theme_package_id": gcs.layout.guid,
            "theme_variant": target_group,
            "mode": mode,
            "blocks": layout_blocks
        }
        
    except Exception as e:
        logger.error(f"Fehler bei get_active_theme: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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
        
        # Speichere über systemsteuerung-Instanz (direkter Aufruf)
        gcs.systemsteuerung.set_value(str(gcs.user_guid), "THEME_MODE", theme_mode, gcs.stichtag)
        
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
        
        # Lese über systemsteuerung-Instanz (get_static_value für nicht-historische Daten)
        theme_mode = gcs.systemsteuerung.get_static_value(str(gcs.user_guid), "THEME_MODE")
        
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
    current_user: dict = Depends(get_current_user),
    gcs = Depends(get_gcs_instance)
):
    """
    Lädt spezifisches Theme für einen Mandanten
    NEUE STRUKTUR: Nutzt GCS-Theme-Instanz
    
    Args:
        mandant_uid: UUID des Mandanten
        theme: 'light' oder 'dark' (Gruppe)
        
    Returns:
        Layout-Konfiguration für das Theme
    """
    try:
        # Prüfe ob GCS-Layout-Instanz verfügbar
        if not gcs.layout:
            # Kein Theme konfiguriert -> Gib Standard-Theme zurück
            logger.warning(f"⚠️ Kein Theme für Mandant {mandant_uid} konfiguriert - verwende Standard")
            return {
                "mandant_uid": str(mandant_uid),
                "theme": theme,
                "colors": get_default_colors(theme),
                "typography": get_default_typography(),
                "customizations": {},
                "assets": {}
            }
        
        # Hole Theme-Gruppe direkt aus gcs.layout
        theme_group = gcs.layout.get_value_by_group(theme)
        
        if not theme_group:
            raise HTTPException(
                status_code=404,
                detail=f"Theme-Gruppe '{theme}' nicht gefunden"
            )
        
        # Erstelle Response
        response = {
            "mandant_uid": str(mandant_uid),
            "theme": theme,
            "colors": theme_group.get('colors', {}),
            "typography": theme_group.get('typography', {}),
            "customizations": theme_group.get('customizations', {}),
            "assets": theme_group.get('assets', {})
        }
        
        logger.info(f"✅ Theme geladen: {theme}")
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

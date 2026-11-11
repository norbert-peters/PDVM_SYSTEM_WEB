"""
Layout API
Aufgeloestes Theme (Paket + Mandanten-Overlay + Benutzer-Overlay), Token-Katalog und Hell/Dunkel-Praeferenz.

Die Logik liegt in ``app.core.theme_service`` bzw. ``PdvmCentralSystemsteuerung.resolve_active_theme``;
der Router enthaelt weder SQL noch direkten Zugriff auf JSON-Strukturen (ARCHITECTURE_RULES 1.1).
"""
from typing import Any, Dict, Optional
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..core import theme_service
from ..core.security import get_current_user, has_overlay_rights, require_overlay_user
from .gcs import get_gcs_instance

router = APIRouter(tags=["layout"])
logger = logging.getLogger(__name__)

_MODES = ("light", "dark")


def _check_mode(mode: Optional[str]) -> None:
    if mode is not None and mode not in _MODES:
        raise HTTPException(status_code=400, detail="mode muss 'light' oder 'dark' sein")


def _translate_write_error(exc: Exception) -> HTTPException:
    """Pruefungsfehler -> 422 (alle Meldungen), Schreibkonflikt -> 409, Rest -> 500."""
    if isinstance(exc, theme_service.ThemeValidationError):
        detail: Dict[str, Any] = {"errors": exc.errors}
        if exc.contrast:
            detail["contrast"] = exc.contrast
        return HTTPException(status_code=422, detail=detail)
    if isinstance(exc, ValueError) and "zwischenzeitlich" in str(exc):
        return HTTPException(
            status_code=409,
            detail="Die Daten wurden gleichzeitig geändert. Bitte erneut speichern.",
        )
    logger.error(f"Fehler beim Speichern der Theme-Einstellungen: {exc}")
    return HTTPException(status_code=500, detail=str(exc))


@router.get("/resolved")
async def get_resolved_theme(
    mode: Optional[str] = None,
    gcs=Depends(get_gcs_instance),
    current_user: dict = Depends(get_current_user),
):
    """
    Liefert das aktive Theme des Benutzers, bereits aus allen Schichten aufgeloest.

    Args:
        mode: 'light' oder 'dark'. Ohne Angabe gilt die gespeicherte Benutzer-Praeferenz
              (sonst Mandanten-Default, sonst 'light').
    """
    _check_mode(mode)
    try:
        theme = gcs.resolve_active_theme(mode)
    except Exception as e:
        logger.error(f"Fehler beim Aufloesen des Themes: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    for warning in theme.get("warnings", []) + theme.get("layout_warnings", []):
        logger.warning(f"Theme {theme.get('theme_variant')}: {warning}")
    return theme


@router.get("/catalog")
async def get_token_catalog(current_user: dict = Depends(get_current_user)):
    """Liefert das vorgegebene Token-Schema (Gruppen, Typen, Benutzer-Anpassbarkeit)."""
    return theme_service.get_catalog()


@router.post("/preferences/theme")
async def save_theme_preference(
    theme_mode: str,
    current_user: dict = Depends(get_current_user),
    gcs=Depends(get_gcs_instance),
):
    """Speichert den Hell/Dunkel-Modus des Benutzers in msy_systemsteuerung."""
    _check_mode(theme_mode)
    try:
        gcs.systemsteuerung.set_value(str(gcs.user_guid), "THEME_MODE", theme_mode, gcs.stichtag)
        await gcs.save_all_values()
        return {"success": True, "theme_mode": theme_mode}
    except Exception as e:
        logger.error(f"Fehler beim Speichern der Theme-Praeferenz: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/preferences/theme")
async def get_theme_preference(
    current_user: dict = Depends(get_current_user),
    gcs=Depends(get_gcs_instance),
):
    """Liefert den effektiven Hell/Dunkel-Modus des Benutzers."""
    return {"theme_mode": gcs.get_user_theme_mode()}


# --- Theme-Editor (P4) ---


class OverlayBody(BaseModel):
    overlay: Dict[str, Any] = {}


class MandantSettingsBody(BaseModel):
    theme_default: Optional[str] = None
    theme_allowed: Optional[list] = None
    theme_light: Optional[str] = None
    theme_dark: Optional[str] = None
    default_mode: Optional[str] = None
    user_theme_edit: Optional[list] = None
    layout_default: Optional[Dict[str, Any]] = None
    layout_allowed: Optional[Dict[str, Any]] = None


class UserSettingsBody(BaseModel):
    overlay: Dict[str, Any] = {}
    theme_choice: Optional[str] = None
    variant_light: Optional[str] = None
    variant_dark: Optional[str] = None
    layout_choice: Optional[Dict[str, Any]] = None


@router.get("/editor/{scope}")
async def get_theme_editor_state(
    scope: str,
    package: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
    gcs=Depends(get_gcs_instance),
):
    """
    Zustand fuer den Theme-Editor.

    scope='user' ("Mein Design"): jeder Benutzer; scope='mandant': nur Rolle 'overlay'.
    ``can_edit_overlay`` zeigt, ob der Benutzer die Mandanten-Ebene aendern darf.
    ``package`` (nur scope='user'): Basis eines anderen freigegebenen Theme-Pakets als Vorschau.
    """
    if scope not in ("mandant", "user"):
        raise HTTPException(status_code=404, detail="scope muss 'mandant' oder 'user' sein")
    can_edit_overlay = has_overlay_rights(current_user)
    if scope == "mandant" and not can_edit_overlay:
        raise HTTPException(status_code=403, detail="Rolle 'overlay' erforderlich")
    try:
        state = gcs.get_theme_editor_state(scope, package)
    except Exception as e:
        logger.error(f"Fehler beim Laden des Theme-Editors: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    state["can_edit_overlay"] = can_edit_overlay
    return state


@router.get("/packages")
async def list_theme_packages(
    current_user: dict = Depends(require_overlay_user),
    gcs=Depends(get_gcs_instance),
):
    """Alle verfuegbaren Theme-Pakete (sys_layout) zur Freigabe fuer den Mandanten (nur Rolle 'overlay')."""
    try:
        return {"packages": await gcs.list_available_theme_packages()}
    except Exception as e:
        logger.error(f"Fehler beim Laden der Theme-Pakete: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/overlay/mandant")
async def save_mandant_overlay(
    body: OverlayBody,
    current_user: dict = Depends(require_overlay_user),
    gcs=Depends(get_gcs_instance),
):
    """Speichert das Mandanten-Overlay (nur Rolle 'overlay')."""
    try:
        return await gcs.save_mandant_theme_overlay(body.overlay)
    except Exception as e:
        raise _translate_write_error(e)


@router.put("/settings/mandant")
async def save_mandant_settings(
    body: MandantSettingsBody,
    current_user: dict = Depends(require_overlay_user),
    gcs=Depends(get_gcs_instance),
):
    """Speichert Standard-Varianten, Standard-Modus und Benutzer-Freigaben des Mandanten (nur Rolle 'overlay')."""
    try:
        return await gcs.save_mandant_theme_config(body.model_dump(exclude_unset=True))
    except Exception as e:
        raise _translate_write_error(e)


@router.put("/settings/user")
async def save_user_settings(
    body: UserSettingsBody,
    current_user: dict = Depends(get_current_user),
    gcs=Depends(get_gcs_instance),
):
    """Speichert Benutzer-Overlay und Variantenwahl; Tokens nur nach Freigabe des Mandanten."""
    try:
        return await gcs.save_user_theme_settings(
            body.overlay, body.variant_light, body.variant_dark, body.layout_choice, body.theme_choice
        )
    except Exception as e:
        raise _translate_write_error(e)

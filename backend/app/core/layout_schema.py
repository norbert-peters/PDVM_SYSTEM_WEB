"""Strukturkatalog fuer die Oberflaeche (Layout-Varianten, P5).

Der Katalog beschreibt, welche Strukturvarianten es je Bereich gibt. Eine Variante ist ausschliesslich ein
Kennzeichen (``data-layout-<bereich>="<id>"`` auf ``<html>``); das Aussehen liefert das CSS im Code
(``frontend/src/styles/layouts/variants.css``). Es gibt bewusst kein freies CSS in der Datenbank.

Aufloesung (spaetere Ebene gewinnt, solange sie freigegeben ist):
1. Schema-Standard ("standard")
2. Mandanten-Vorgabe ``asy_mandanten.CONFIG.LAYOUT_DEFAULT`` = ``{bereich: id}``
3. Benutzerwahl ``msy_systemsteuerung.<user>.LAYOUT_CHOICE`` = ``{bereich: id}``; erlaubt sind nur Varianten aus
   ``asy_mandanten.CONFIG.LAYOUT_ALLOWED`` = ``{bereich: [id, ...]}`` (Opt-in wie ``USER_THEME_EDIT``) und die
   Mandanten-Vorgabe selbst.

Siehe docs/specs/THEMING_SYSTEM.md (Abschnitt 8).
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

DEFAULT_OPTION = "standard"

LAYOUT_SCHEMA: Dict[str, Dict[str, Any]] = {
    "header": {
        "label": "Kopfzeile",
        "options": {
            "standard": {"label": "Standard", "description": "Hohe Kopfzeile mit Logo, Mandantenadresse und Benutzerrolle."},
            "kompakt": {"label": "Kompakt", "description": "Niedrige Kopfzeile ohne Adresszeile und Rolle."},
        },
    },
    "shell": {
        "label": "Navigation",
        "options": {
            "standard": {"label": "Standard", "description": "Seitenleiste 240 px, Menüleiste 48 px."},
            "schmal": {"label": "Schmal", "description": "Schmale Seitenleiste (200 px) und niedrige Menüleiste (40 px)."},
            "breit": {"label": "Breit", "description": "Breite Seitenleiste (280 px) und höhere Menüleiste (52 px)."},
        },
    },
    "dichte": {
        "label": "Dichte",
        "options": {
            "standard": {"label": "Normal", "description": "Standardabstände."},
            "kompakt": {"label": "Kompakt", "description": "Engere Abstände in Layout, Formularen und Tabellen."},
            "luftig": {"label": "Luftig", "description": "Weitere Abstände in Layout, Formularen und Tabellen."},
        },
    },
    "form": {
        "label": "Formulare",
        "options": {
            "standard": {"label": "Karte", "description": "Jedes Feld in einer umrahmten Karte, Beschriftung oben."},
            "flach": {"label": "Flach", "description": "Felder ohne Kartenrahmen, Beschriftung oben."},
            "label-links": {"label": "Beschriftung links", "description": "Beschriftung links neben dem Feld."},
        },
    },
    "tabelle": {
        "label": "Tabellen",
        "options": {
            "standard": {"label": "Standard", "description": "Zeilen mit Trennlinie."},
            "zebra": {"label": "Zebra", "description": "Jede zweite Zeile leicht getönt."},
            "linien": {"label": "Gitternetz", "description": "Linien um jede Zelle."},
        },
    },
}


def schema_default(area: str) -> str:
    return DEFAULT_OPTION


def _is_valid(area: str, option: Any) -> bool:
    return area in LAYOUT_SCHEMA and isinstance(option, str) and option in LAYOUT_SCHEMA[area]["options"]


def validate_choice_map(value: Any, *, layer: str) -> Tuple[Dict[str, str], List[str]]:
    """Prueft ``{bereich: id}``; leere Werte bedeuten "nicht gesetzt" und werden entfernt."""
    if value is None:
        return {}, []
    if not isinstance(value, dict):
        return {}, [f"{layer}: Layout-Angabe muss ein Objekt {{bereich: variante}} sein"]
    clean: Dict[str, str] = {}
    errors: List[str] = []
    for area, option in value.items():
        if area not in LAYOUT_SCHEMA:
            errors.append(f"{layer}: unbekannter Layout-Bereich '{area}'")
        elif option in (None, ""):
            continue
        elif not _is_valid(area, option):
            errors.append(f"{layer}: Variante '{option}' gibt es im Bereich '{area}' nicht")
        else:
            clean[area] = option
    return clean, errors


def validate_allowed_map(value: Any) -> Tuple[Dict[str, List[str]], List[str]]:
    """Prueft ``{bereich: [id, ...]}`` (Freigabe des Mandanten); Duplikate werden entfernt."""
    if value is None:
        return {}, []
    if not isinstance(value, dict):
        return {}, ["Mandant: LAYOUT_ALLOWED muss ein Objekt {bereich: [varianten]} sein"]
    clean: Dict[str, List[str]] = {}
    errors: List[str] = []
    for area, options in value.items():
        if area not in LAYOUT_SCHEMA:
            errors.append(f"Mandant: unbekannter Layout-Bereich '{area}'")
            continue
        if not isinstance(options, list):
            errors.append(f"Mandant: Freigabe für '{area}' muss eine Liste sein")
            continue
        valid: List[str] = []
        for option in options:
            if not _is_valid(area, option):
                errors.append(f"Mandant: Variante '{option}' gibt es im Bereich '{area}' nicht")
            elif option not in valid:
                valid.append(option)
        if valid:
            clean[area] = valid
    return clean, errors


def _as_map(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def mandant_defaults(default_map: Any) -> Dict[str, str]:
    """Mandanten-Vorgabe je Bereich (ungueltige Eintraege fallen auf den Schema-Standard)."""
    source = _as_map(default_map)
    return {area: (source.get(area) if _is_valid(area, source.get(area)) else schema_default(area)) for area in LAYOUT_SCHEMA}


def available_options(area: str, default_map: Any, allowed_map: Any) -> List[str]:
    """Varianten, die ein Benutzer im Bereich waehlen darf: Mandanten-Vorgabe + Freigaben (Katalogreihenfolge)."""
    default = mandant_defaults(default_map)[area]
    allowed = _as_map(allowed_map).get(area)
    allowed = allowed if isinstance(allowed, list) else []
    return [opt for opt in LAYOUT_SCHEMA[area]["options"] if opt == default or opt in allowed]


def resolve_layout(
    *, default_map: Any = None, allowed_map: Any = None, user_choice: Any = None
) -> Tuple[Dict[str, str], List[str]]:
    """Loest die wirksame Variante je Bereich auf; nicht freigegebene Benutzerwahl wird verworfen (Warnung)."""
    layout = mandant_defaults(default_map)
    warnings: List[str] = []
    for area, option in _as_map(user_choice).items():
        if option in (None, ""):
            continue
        if not _is_valid(area, option):
            warnings.append(f"Layout '{area}': Variante '{option}' unbekannt")
        elif option not in available_options(area, default_map, allowed_map):
            warnings.append(f"Layout '{area}': Variante '{option}' ist für den Mandanten nicht freigegeben")
        else:
            layout[area] = option
    return layout, warnings


def get_layout_catalog() -> Dict[str, Any]:
    """Katalog fuer Editoren: Bereiche mit Beschriftung, Optionen (Reihenfolge = Katalogreihenfolge)."""
    return {
        area: {
            "label": data["label"],
            "default": schema_default(area),
            "options": [{"value": value, "label": spec["label"], "description": spec["description"]} for value, spec in data["options"].items()],
        }
        for area, data in LAYOUT_SCHEMA.items()
    }

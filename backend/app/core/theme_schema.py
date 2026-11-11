"""Token-Schema fuer das Theming-System V2 (vorgegebene Struktur der Theme-Daten).

Die Theme-Pakete (``sys_layout``/``msy_layout``) enthalten pro Variante (Gruppe, z. B. ``light``/``dark``)
die Gruppen ``color``, ``font`` und ``block_*``. Dieses Modul beschreibt, welche Tokens es gibt, welchen
Werttyp sie haben und welche davon ein Benutzer ueberhaupt anpassen duerfte (``user_editable``).
Die tatsaechliche Freigabe je Mandant steuert ``asy_mandanten.CONFIG.USER_THEME_EDIT``.

Siehe docs/specs/THEMING_SYSTEM.md (Abschnitt Layer/Resolver).
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

SCHEMA_VERSION = 1

TYPE_COLOR = "color"
TYPE_LENGTH = "length"
TYPE_BORDER = "border"
TYPE_SHADOW = "shadow"
TYPE_FONT = "font"
TYPE_NUMBER = "number"

# Gruppen, in denen Schluessel mit '_' und '-' gleichbedeutend sind (Frontend wandelt '_' -> '-').
HYPHEN_GROUPS = ("color", "font")

_PALETTE_STEPS = ("50", "100", "200", "300", "400", "500", "600", "700", "800", "900")


def _build_color_group() -> Dict[str, Dict[str, Any]]:
    tokens: Dict[str, Dict[str, Any]] = {}
    for family in ("primary", "secondary"):
        for step in _PALETTE_STEPS:
            tokens[f"{family}-{step}"] = {"type": TYPE_COLOR, "user_editable": True}
    for step in _PALETTE_STEPS:
        tokens[f"neutral-{step}"] = {"type": TYPE_COLOR, "user_editable": False}
    for name in ("success", "warning", "error", "info"):
        tokens[name] = {"type": TYPE_COLOR, "user_editable": False}
    for name in ("background-primary", "background-secondary", "background-tertiary"):
        tokens[name] = {"type": TYPE_COLOR, "user_editable": True}
    for name in ("border-light", "border-medium", "border-dark"):
        tokens[name] = {"type": TYPE_COLOR, "user_editable": True}
    # Textfarben sind kontrastkritisch und daher nie durch Benutzer aenderbar.
    for name in (
        "text-primary", "text-secondary", "text-disabled", "text-inverse",
        "text-on-primary", "text-on-secondary", "text-on-tertiary",
    ):
        tokens[name] = {"type": TYPE_COLOR, "user_editable": False}
    return tokens


def _block(**props: str) -> Dict[str, Dict[str, Any]]:
    return {name: {"type": ptype, "user_editable": False} for name, ptype in props.items()}


TOKEN_SCHEMA: Dict[str, Dict[str, Dict[str, Any]]] = {
    "color": _build_color_group(),
    "font": {
        "primary": {"type": TYPE_FONT, "user_editable": False},
        "secondary": {"type": TYPE_FONT, "user_editable": False},
        "mono": {"type": TYPE_FONT, "user_editable": False},
        "scale": {"type": TYPE_NUMBER, "user_editable": True, "min": 0.8, "max": 1.5, "options": ["0.9", "1", "1.1", "1.25", "1.5"]},
    },
    "block_header_std": _block(bg_color=TYPE_COLOR, text_color=TYPE_COLOR, border_bottom=TYPE_BORDER, shadow=TYPE_SHADOW),
    "block_header_mandant_std": _block(text_color=TYPE_COLOR, subtext_color=TYPE_COLOR),
    "block_header_user_std": _block(text_color=TYPE_COLOR, subtext_color=TYPE_COLOR),
    "block_sidebar_std": _block(bg_color=TYPE_COLOR, text_color=TYPE_COLOR, border_right=TYPE_BORDER),
    "block_surface_main": _block(bg_color=TYPE_COLOR, text_color=TYPE_COLOR),
    "block_input_std": _block(bg_color=TYPE_COLOR, text_color=TYPE_COLOR, border=TYPE_BORDER, radius=TYPE_LENGTH),
    "block_btn_primary": _block(bg_color=TYPE_COLOR, text_color=TYPE_COLOR, hover_bg=TYPE_COLOR, border=TYPE_BORDER, radius=TYPE_LENGTH),
    "block_stichtag_std": _block(
        bg_color=TYPE_COLOR, text_color=TYPE_COLOR, border=TYPE_BORDER, radius=TYPE_LENGTH,
        field_bg_color=TYPE_COLOR, field_text_color=TYPE_COLOR,
    ),
    # --- P2: Blocks fuer Menue, Dialog, Formular, Views, Tabs, Karten ---
    "block_menu_horizontal": _block(bg_color=TYPE_COLOR, border_bottom=TYPE_BORDER, shadow=TYPE_SHADOW),
    "block_menu_vertical": _block(bg_color=TYPE_COLOR, border_right=TYPE_BORDER),
    "block_menu_button": _block(text_color=TYPE_COLOR, hover_bg=TYPE_COLOR, active_bg=TYPE_COLOR),
    "block_menu_dropdown": _block(bg_color=TYPE_COLOR, border=TYPE_BORDER, shadow=TYPE_SHADOW),
    "block_dialog_modal": _block(
        bg_color=TYPE_COLOR, text_color=TYPE_COLOR, border=TYPE_BORDER, radius=TYPE_LENGTH, shadow=TYPE_SHADOW,
        overlay_color=TYPE_COLOR, divider_color=TYPE_COLOR,
    ),
    "block_card_std": _block(bg_color=TYPE_COLOR, text_color=TYPE_COLOR, border=TYPE_BORDER, radius=TYPE_LENGTH, shadow=TYPE_SHADOW),
    "block_pic_std": _block(
        bg_color=TYPE_COLOR, text_color=TYPE_COLOR, border=TYPE_BORDER, radius=TYPE_LENGTH,
        label_color=TYPE_COLOR, readonly_bg=TYPE_COLOR, focus_color=TYPE_COLOR,
    ),
    "block_pic_popover": _block(
        bg_color=TYPE_COLOR, text_color=TYPE_COLOR, border=TYPE_BORDER, radius=TYPE_LENGTH, shadow=TYPE_SHADOW,
        field_bg_color=TYPE_COLOR, field_text_color=TYPE_COLOR,
    ),
    "block_view_toolbar": _block(bg_color=TYPE_COLOR, text_color=TYPE_COLOR, border=TYPE_BORDER, radius=TYPE_LENGTH),
    "block_view_panel": _block(bg_color=TYPE_COLOR, text_color=TYPE_COLOR, border=TYPE_BORDER, radius=TYPE_LENGTH),
    "block_view_table": _block(bg_color=TYPE_COLOR, border=TYPE_BORDER, radius=TYPE_LENGTH),
    "block_view_table_header": _block(bg_color=TYPE_COLOR, text_color=TYPE_COLOR, border_bottom=TYPE_BORDER),
    "block_view_table_row_selected": _block(bg_color=TYPE_COLOR),
    "block_view_group_row": _block(bg_color=TYPE_COLOR, text_color=TYPE_COLOR),
    "block_view_total_row": _block(bg_color=TYPE_COLOR, text_color=TYPE_COLOR),
    "block_view_btn_std": _block(bg_color=TYPE_COLOR, text_color=TYPE_COLOR, border=TYPE_BORDER, radius=TYPE_LENGTH, hover_bg=TYPE_COLOR),
    "block_view_input_std": _block(bg_color=TYPE_COLOR, text_color=TYPE_COLOR, border=TYPE_BORDER, radius=TYPE_LENGTH),
    "block_tabs_std": _block(
        bar_padding=TYPE_LENGTH, bar_bg_color=TYPE_COLOR, bar_border_bottom=TYPE_BORDER, bar_sticky_height=TYPE_LENGTH,
        tab_padding=TYPE_LENGTH, tab_radius=TYPE_LENGTH, tab_bg_color=TYPE_COLOR, tab_text_color=TYPE_COLOR,
        tab_hover_bg_color=TYPE_COLOR, tab_active_bg_color=TYPE_COLOR, tab_active_text_color=TYPE_COLOR,
        tab_active_border_color=TYPE_COLOR, panel_bg_color=TYPE_COLOR, panel_border=TYPE_BORDER,
        panel_padding=TYPE_LENGTH, panel_radius=TYPE_LENGTH, panel_top_radius=TYPE_LENGTH,
        meta_text_color=TYPE_COLOR,
    ),
}

# Pflichtpaare fuer die Kontrastpruefung: (Vordergrund, Hintergrund, Mindestverhaeltnis nach WCAG AA).
# Referenzen haben die Form "<gruppe>.<token>".
CONTRAST_PAIRS: List[Tuple[str, str, float]] = [
    ("color.text-primary", "color.background-primary", 4.5),
    ("color.text-primary", "color.background-secondary", 4.5),
    ("color.text-secondary", "color.background-primary", 4.5),
    ("color.text-secondary", "color.background-secondary", 4.5),
    ("color.text-inverse", "color.primary-500", 4.5),
    ("color.text-on-primary", "color.background-primary", 4.5),
    ("color.text-on-secondary", "color.background-secondary", 4.5),
    ("color.text-on-tertiary", "color.background-tertiary", 4.5),
    ("block_surface_main.text_color", "block_surface_main.bg_color", 4.5),
    ("block_header_std.text_color", "block_header_std.bg_color", 4.5),
    ("block_sidebar_std.text_color", "block_sidebar_std.bg_color", 4.5),
    ("block_input_std.text_color", "block_input_std.bg_color", 4.5),
    ("block_btn_primary.text_color", "block_btn_primary.bg_color", 4.5),
    ("block_stichtag_std.text_color", "block_stichtag_std.bg_color", 4.5),
    ("block_card_std.text_color", "block_card_std.bg_color", 4.5),
    ("block_dialog_modal.text_color", "block_dialog_modal.bg_color", 4.5),
    ("block_pic_std.text_color", "block_pic_std.bg_color", 4.5),
    ("block_stichtag_std.field_text_color", "block_stichtag_std.field_bg_color", 4.5),
    ("block_pic_popover.text_color", "block_pic_popover.bg_color", 4.5),
    ("block_pic_popover.field_text_color", "block_pic_popover.field_bg_color", 4.5),
]

# Wirksamer Wert, wenn ein Block-Token im Theme fehlt: dieselbe Kette wie im CSS (var(--block-..., var(--color-...))).
# Damit gelten auch Farben aus dem Fallback als geprueft, und eine Aenderung an der Fallback-Farbe zaehlt als
# Aenderung des Paares.
CONTRAST_FALLBACKS: Dict[str, str] = {
    "block_surface_main.text_color": "color.text-primary",
    "block_surface_main.bg_color": "color.background-primary",
    "block_header_std.text_color": "color.text-primary",
    "block_header_std.bg_color": "color.background-primary",
    "block_sidebar_std.text_color": "color.text-primary",
    "block_sidebar_std.bg_color": "color.background-secondary",
    "block_input_std.text_color": "color.text-primary",
    "block_input_std.bg_color": "color.background-primary",
    "block_btn_primary.text_color": "color.text-inverse",
    "block_btn_primary.bg_color": "color.primary-500",
    "block_stichtag_std.text_color": "color.text-inverse",
    "block_stichtag_std.bg_color": "color.primary-500",
    "block_card_std.text_color": "color.text-primary",
    "block_card_std.bg_color": "color.background-primary",
    "block_dialog_modal.text_color": "color.text-primary",
    "block_dialog_modal.bg_color": "color.background-primary",
    "block_pic_std.text_color": "color.text-primary",
    "block_pic_std.bg_color": "color.background-primary",
    "block_stichtag_std.field_text_color": "block_pic_std.text_color",
    "block_stichtag_std.field_bg_color": "block_pic_std.bg_color",
    "block_pic_popover.text_color": "color.text-primary",
    "block_pic_popover.bg_color": "color.background-primary",
    "block_pic_popover.field_text_color": "color.text-primary",
    "block_pic_popover.field_bg_color": "color.background-secondary",
}


def ref_chain(ref: str) -> List[str]:
    """``ref`` und seine Fallback-Kette (z. B. block_btn_primary.bg_color -> color.primary-500)."""
    chain = [ref]
    while chain[-1] in CONTRAST_FALLBACKS and len(chain) < 4:
        chain.append(CONTRAST_FALLBACKS[chain[-1]])
    return chain


def describe_ref(ref: str) -> str:
    """Lesbare Beschriftung eines Tokenverweises (``<gruppe>.<token>``)."""
    group, _, name = ref.partition(".")
    return f"{GROUP_LABELS.get(group, group)}: {token_label(group, name)}"


def normalize_token_name(group: str, name: str) -> str:
    """Vereinheitlicht Tokennamen (``text-on_primary`` und ``text-on-primary`` sind identisch)."""
    return name.replace("_", "-") if group in HYPHEN_GROUPS else name


def get_token_spec(group: str, name: str) -> Dict[str, Any] | None:
    return TOKEN_SCHEMA.get(group, {}).get(normalize_token_name(group, name))


# ---------------------------------------------------------------------------
# UI-Metadaten (Beschriftung, Control-Typ) - Grundlage fuer die Editor-Controls (P3/P4)
# ---------------------------------------------------------------------------

# Schema-Typ -> Typ des PdvmInputControl
CONTROL_TYPE_BY_TOKEN_TYPE: Dict[str, str] = {
    TYPE_COLOR: "color",
    TYPE_LENGTH: "css_length",
    TYPE_BORDER: "css_border",
    TYPE_SHADOW: "string",
    TYPE_FONT: "font_family",
    TYPE_NUMBER: "dropdown",
}

GROUP_LABELS: Dict[str, str] = {
    "color": "Farbpalette",
    "font": "Schrift",
    "block_header_std": "Kopfzeile",
    "block_header_mandant_std": "Kopfzeile - Mandant",
    "block_header_user_std": "Kopfzeile - Benutzer",
    "block_sidebar_std": "Seitenleiste",
    "block_surface_main": "Arbeitsfläche",
    "block_input_std": "Eingabefelder",
    "block_btn_primary": "Primärbutton",
    "block_stichtag_std": "Stichtagsleiste",
    "block_menu_horizontal": "Menü horizontal",
    "block_menu_vertical": "Menü vertikal",
    "block_menu_button": "Menüeintrag",
    "block_menu_dropdown": "Menü-Dropdown",
    "block_dialog_modal": "Dialog (Modal)",
    "block_card_std": "Karten",
    "block_pic_std": "Formularfelder",
    "block_pic_popover": "Datum/Zeit-Auswahl (Popover)",
    "block_view_toolbar": "View - Werkzeugleiste",
    "block_view_panel": "View - Panels",
    "block_view_table": "View - Tabelle",
    "block_view_table_header": "View - Tabellenkopf",
    "block_view_table_row_selected": "View - gewählte Zeile",
    "block_view_group_row": "View - Gruppenzeile",
    "block_view_total_row": "View - Summenzeile",
    "block_view_btn_std": "View - Buttons",
    "block_view_input_std": "View - Eingaben",
    "block_tabs_std": "Tabs",
}

PROP_LABELS: Dict[str, str] = {
    "bg_color": "Hintergrund",
    "text_color": "Textfarbe",
    "subtext_color": "Zusatztext",
    "border": "Rahmen",
    "border_bottom": "Rahmen unten",
    "border_right": "Rahmen rechts",
    "radius": "Eckenradius",
    "shadow": "Schatten",
    "hover_bg": "Hintergrund bei Hover",
    "active_bg": "Hintergrund aktiv",
    "overlay_color": "Abdunklung",
    "divider_color": "Trennlinie",
    "label_color": "Beschriftung",
    "readonly_bg": "Hintergrund schreibgeschützt",
    "focus_color": "Fokusfarbe",
    "field_bg_color": "Feld: Hintergrund",
    "field_text_color": "Feld: Textfarbe",
    "bar_padding": "Leiste: Innenabstand",
    "bar_bg_color": "Leiste: Hintergrund",
    "bar_border_bottom": "Leiste: Rahmen unten",
    "bar_sticky_height": "Leiste: Höhe",
    "tab_padding": "Tab: Innenabstand",
    "tab_radius": "Tab: Eckenradius",
    "tab_bg_color": "Tab: Hintergrund",
    "tab_text_color": "Tab: Textfarbe",
    "tab_hover_bg_color": "Tab: Hover-Hintergrund",
    "tab_active_bg_color": "Aktiver Tab: Hintergrund",
    "tab_active_text_color": "Aktiver Tab: Textfarbe",
    "tab_active_border_color": "Aktiver Tab: Rahmenfarbe",
    "panel_bg_color": "Panel: Hintergrund",
    "panel_border": "Panel: Rahmen",
    "panel_padding": "Panel: Innenabstand",
    "panel_radius": "Panel: Eckenradius",
    "panel_top_radius": "Panel: Radius oben",
    "meta_text_color": "Metatext",
}

_FAMILY_LABELS = {"primary": "Primär", "secondary": "Sekundär", "neutral": "Neutral"}
_COLOR_LABELS: Dict[str, str] = {
    "success": "Erfolg", "warning": "Warnung", "error": "Fehler", "info": "Information",
    "background-primary": "Hintergrund primär", "background-secondary": "Hintergrund sekundär",
    "background-tertiary": "Hintergrund tertiär",
    "border-light": "Rahmen hell", "border-medium": "Rahmen mittel", "border-dark": "Rahmen dunkel",
    "text-primary": "Text primär", "text-secondary": "Text sekundär", "text-disabled": "Text deaktiviert",
    "text-inverse": "Text invertiert (auf Füllflächen)",
    "text-on-primary": "Text auf Fläche primär", "text-on-secondary": "Text auf Fläche sekundär",
    "text-on-tertiary": "Text auf Fläche tertiär",
}
_FONT_LABELS = {"primary": "Schrift primär", "secondary": "Schrift sekundär", "mono": "Schrift Festbreite", "scale": "Skalierung"}


def token_label(group: str, name: str) -> str:
    """Deutsche Beschriftung eines Tokens (Basis fuer die Editor-Controls)."""
    if group == "color":
        family, _, step = name.partition("-")
        if family in _FAMILY_LABELS and step.isdigit():
            return f"{_FAMILY_LABELS[family]} {step}"
        return _COLOR_LABELS.get(name, name)
    if group == "font":
        return _FONT_LABELS.get(name, name)
    return PROP_LABELS.get(name, name)


def contrast_partners(group: str, name: str) -> List[Dict[str, Any]]:
    """Gegenfarben mit Mindestverhaeltnis aus den Kontrast-Pflichtpaaren (in beide Richtungen)."""
    ref = f"{group}.{normalize_token_name(group, name)}"
    partners: List[Dict[str, Any]] = []
    for fg, bg, minimum in CONTRAST_PAIRS:
        if fg == ref:
            partners.append({"ref": bg, "min": minimum})
        elif bg == ref:
            partners.append({"ref": fg, "min": minimum})
    return partners

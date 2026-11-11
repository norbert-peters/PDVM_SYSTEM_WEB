"""Theme-Service: Schichtung (Paket -> Mandant -> Benutzer), Validierung und Kontrastpruefung.

Rein funktionale Logik ohne Datenbankzugriff. Die Orchestrierung (Laden der Schichten aus der GCS-Session)
liegt in ``PdvmCentralSystemsteuerung.resolve_active_theme``.

Schichten (spaetere ueberschreibt fruehere):
1. Theme-Paket-Variante (``msy_layout``/``sys_layout``, Gruppe z. B. ``light``/``dark``)
2. Mandanten-Overlay (nur Abweichungen, Gruppen ``light``/``dark``)
3. Benutzer-Overlay (``msy_systemsteuerung.<user>.THEME_OVERRIDES``), nur fuer vom Mandanten freigegebene Tokens
"""
from __future__ import annotations

import copy
import re
from fnmatch import fnmatchcase
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .theme_color import contrast_ratio, lightness_distance, parse_css_color, suggest_compliant_color  # noqa: F401
from .theme_schema import (
    CONTRAST_PAIRS,
    CONTROL_TYPE_BY_TOKEN_TYPE,
    GROUP_LABELS,
    SCHEMA_VERSION,
    TOKEN_SCHEMA,
    TYPE_BORDER,
    TYPE_COLOR,
    TYPE_FONT,
    TYPE_LENGTH,
    TYPE_NUMBER,
    TYPE_SHADOW,
    contrast_partners,
    describe_ref,
    get_token_spec,
    normalize_token_name,
    ref_chain,
    token_label,
)

_HEX = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")
_RGB = re.compile(
    r"^rgba?\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*(?:,\s*(0|1|0?\.\d+|1\.0+)\s*)?\)$"
)
_HSL = re.compile(r"^hsla?\(\s*\d{1,3}(?:\.\d+)?\s*,\s*\d{1,3}%\s*,\s*\d{1,3}%\s*(?:,\s*(?:0|1|0?\.\d+)\s*)?\)$")
_VAR = re.compile(r"^var\(--[a-z0-9-]+\)$")
_COLOR_KEYWORDS = {"transparent", "inherit", "currentcolor"}
_LENGTH_ATOM = r"(?:0|\d+(?:\.\d+)?(?:px|rem|em|%))"
# 1-4 Laengen (padding/radius-Kurzformen wie "8px 12px")
_LENGTH = re.compile(rf"^{_LENGTH_ATOM}(?:\s+{_LENGTH_ATOM}){{0,3}}$")
_BORDER = re.compile(r"^(\d+(?:\.\d+)?px)\s+(solid|dashed|dotted|double)\s+(.+)$")
_SHADOW_CHARS = re.compile(r"^[0-9a-zA-Z#().,%\s-]+$")
_FONT_CHARS = re.compile(r"^[A-Za-z0-9 _,'\"\-]+$")
# Zeichen/Muster, die in keinem Tokenwert vorkommen duerfen (CSS-Injection).
_FORBIDDEN = re.compile(r"[;{}<>\\]|url\s*\(|expression\s*\(|@import|/\*", re.IGNORECASE)


class ThemeValidationError(ValueError):
    """Pruefung eines zu speichernden Themes/Overlays fehlgeschlagen (``errors`` = alle Meldungen).

    ``contrast`` enthaelt bei Kontrastverstoessen die strukturierten Eintraege inkl. Vorschlaegen.
    """

    def __init__(self, errors: List[str], contrast: Optional[List[Dict[str, Any]]] = None):
        super().__init__("; ".join(errors))
        self.errors = errors
        self.contrast = contrast or []


def _is_color(value: str) -> bool:
    text = value.strip()
    return bool(
        _HEX.match(text) or (_RGB.match(text) and parse_css_color(text)) or _HSL.match(text)
        or _VAR.match(text) or text.lower() in _COLOR_KEYWORDS
    )


def validate_token_value(token_type: str, value: Any, spec: Optional[Dict[str, Any]] = None) -> bool:
    """Prueft einen Tokenwert gegen den Typ aus dem Schema (restriktiv, keine freien CSS-Ausdruecke)."""
    if token_type == TYPE_NUMBER:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return False
        spec = spec or {}
        return spec.get("min", float("-inf")) <= number <= spec.get("max", float("inf"))
    if not isinstance(value, str):
        return False
    text = value.strip()
    if not text or len(text) > 200 or _FORBIDDEN.search(text):
        return False
    if token_type == TYPE_COLOR:
        return _is_color(text)
    if token_type == TYPE_LENGTH:
        return bool(_LENGTH.match(text))
    if token_type == TYPE_BORDER:
        if text.lower() == "none":
            return True
        m = _BORDER.match(text)
        return bool(m and _is_color(m.group(3)))
    if token_type == TYPE_SHADOW:
        return text.lower() == "none" or (bool(_SHADOW_CHARS.match(text)) and text.count("(") == text.count(")"))
    if token_type == TYPE_FONT:
        return bool(_FONT_CHARS.match(text))
    return False


def is_token_allowed(group: str, name: str, patterns: Optional[Sequence[str]]) -> bool:
    """``None`` = alles erlaubt; sonst muss ``<gruppe>.<token>`` zu einem Muster passen (``color.primary-*``)."""
    if patterns is None:
        return True
    ref = f"{group}.{normalize_token_name(group, name)}"
    return any(fnmatchcase(ref, str(p).strip()) for p in patterns)


def sanitize_overlay(
    overlay: Any,
    *,
    layer: str,
    allowed_patterns: Optional[Sequence[str]] = None,
    require_user_editable: bool = False,
) -> Tuple[Dict[str, Dict[str, Any]], List[str]]:
    """Filtert ein Overlay (``{gruppe: {token: wert}}``) auf gueltige, erlaubte Tokens.

    Ungueltige Eintraege werden verworfen und als Warnung gemeldet; die Aufloesung bricht nie ab.
    """
    clean: Dict[str, Dict[str, Any]] = {}
    warnings: List[str] = []
    if not isinstance(overlay, dict):
        return clean, warnings
    for group, tokens in overlay.items():
        if not isinstance(tokens, dict):
            continue
        for name, value in tokens.items():
            ref = f"{group}.{name}"
            spec = get_token_spec(group, name)
            if spec is None:
                warnings.append(f"{layer}: unbekanntes Token '{ref}' ignoriert")
                continue
            if require_user_editable and not spec.get("user_editable"):
                warnings.append(f"{layer}: Token '{ref}' ist nicht benutzeranpassbar")
                continue
            if not is_token_allowed(group, name, allowed_patterns):
                warnings.append(f"{layer}: Token '{ref}' ist nicht freigegeben")
                continue
            if not validate_token_value(spec["type"], value, spec):
                warnings.append(f"{layer}: ungueltiger Wert fuer '{ref}'")
                continue
            clean.setdefault(group, {})[normalize_token_name(group, name)] = value
    return clean, warnings


def _normalized_group(group: str, tokens: Dict[str, Any]) -> Dict[str, Any]:
    return {normalize_token_name(group, k): v for k, v in tokens.items()}


_BARE_HEX = re.compile(r"^(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")


def normalize_package_values(variant: Dict[str, Any]) -> Tuple[Dict[str, Dict[str, Any]], List[Dict[str, Any]]]:
    """Ergaenzt bei Hex-Farben ohne ``#`` (z. B. ``000000``) das Rautenzeichen; Rohdaten-Reparatur fuer Pakete.

    Gibt die korrigierte Variante und die Aenderungen (``ref``, ``old``, ``new``) zurueck.
    """
    fixed: Dict[str, Dict[str, Any]] = {}
    changes: List[Dict[str, Any]] = []
    for group, tokens in (variant or {}).items():
        if not isinstance(tokens, dict):
            continue
        fixed[group] = dict(tokens)
        for name, value in tokens.items():
            spec = get_token_spec(group, name)
            if spec and spec["type"] == TYPE_COLOR and isinstance(value, str) and _BARE_HEX.match(value.strip()):
                new = "#" + value.strip()
                fixed[group][name] = new
                changes.append({"ref": f"{group}.{normalize_token_name(group, name)}", "old": value, "new": new})
    return fixed, changes


def sanitize_package_variant(variant: Any) -> Tuple[Dict[str, Any], List[str]]:
    """Entfernt ungueltige Werte bekannter Tokens aus einer Paket-Variante (Warnung je Wert).

    Ein ungueltiger Wert wuerde als CSS-Variable gesetzt und die Darstellung eines Blocks brechen; ohne ihn greift
    der CSS-Fallback. Unbekannte Tokens bleiben unveraendert.
    """
    if not isinstance(variant, dict):
        return {}, []
    clean: Dict[str, Any] = {}
    warnings: List[str] = []
    for group, tokens in variant.items():
        if not isinstance(tokens, dict):
            clean[group] = tokens
            continue
        kept: Dict[str, Any] = {}
        for name, value in tokens.items():
            spec = get_token_spec(group, name)
            if spec is not None and not validate_token_value(spec["type"], value, spec):
                warnings.append(f"Paket: ungueltiger Wert fuer '{group}.{normalize_token_name(group, name)}' ignoriert")
                continue
            kept[name] = value
        clean[group] = kept
    return clean, warnings


def merge_layers(base: Dict[str, Any], *overlays: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Mischt Overlays token-genau ueber die Basis-Variante (Basis bleibt unveraendert)."""
    merged: Dict[str, Dict[str, Any]] = {}
    for group, tokens in (base or {}).items():
        if isinstance(tokens, dict):
            merged[group] = _normalized_group(group, copy.deepcopy(tokens))
    for overlay in overlays:
        for group, tokens in overlay.items():
            merged.setdefault(group, {}).update(_normalized_group(group, tokens))
    return merged


def _lookup(blocks: Dict[str, Dict[str, Any]], ref: str) -> Any:
    group, _, token = ref.partition(".")
    tokens = blocks.get(group, {})
    wanted = normalize_token_name(group, token)
    if wanted in tokens:
        return tokens[wanted]
    # Rohdaten aus der DB koennen Unterstriche enthalten (text-on_tertiary): Schluessel normalisiert vergleichen
    for key, value in tokens.items():
        if normalize_token_name(group, key) == wanted:
            return value
    return None


def effective_value(blocks: Dict[str, Dict[str, Any]], ref: str) -> Tuple[Any, str]:
    """Wirksamer Wert eines Tokens inkl. CSS-Fallback-Kette und das Token, aus dem er stammt."""
    for candidate in ref_chain(ref):
        value = _lookup(blocks, candidate)
        if isinstance(value, str) and value.strip():
            return value, candidate
    return None, ref


def check_contrast(blocks: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Wertet die Pflichtpaare aus; nur Paare mit beiden aufloesbaren Farben werden gemeldet."""
    results: List[Dict[str, Any]] = []
    for fg_ref, bg_ref, minimum in CONTRAST_PAIRS:
        ratio = contrast_ratio(effective_value(blocks, fg_ref)[0], effective_value(blocks, bg_ref)[0])
        if ratio is None:
            continue
        results.append({"fg": fg_ref, "bg": bg_ref, "ratio": ratio, "min": minimum, "ok": ratio >= minimum})
    return results


def _overlay_refs(overlay_clean: Dict[str, Dict[str, Any]]) -> set:
    return {f"{group}.{normalize_token_name(group, name)}" for group, tokens in overlay_clean.items() for name in tokens}


def contrast_violations(
    base_blocks: Dict[str, Dict[str, Any]],
    overlay_clean: Dict[str, Dict[str, Any]],
    *,
    suggest: bool = True,
) -> List[Dict[str, Any]]:
    """Kontrastpaare, deren wirksamer Wert durch das Overlay veraendert wird und die danach unter dem Mindestmass liegen.

    Vom Paket geerbte Verstoesse (Overlay beruehrt das Paar nicht) werden hier nicht gemeldet; sie bleiben
    Hinweise (``check_contrast``). Zu jedem Verstoss liefert ``suggestions`` je geaendertem Token die naechstgelegene
    Farbe mit ausreichendem Kontrast (``theme_color.suggest_compliant_color``).
    """
    merged = merge_layers(base_blocks, overlay_clean)
    touched = _overlay_refs(overlay_clean)
    violations: List[Dict[str, Any]] = []
    for fg_ref, bg_ref, minimum in CONTRAST_PAIRS:
        fg_value, fg_src = effective_value(merged, fg_ref)
        bg_value, bg_src = effective_value(merged, bg_ref)
        fg_changed, bg_changed = fg_src in touched, bg_src in touched
        if not (fg_changed or bg_changed):
            continue
        ratio = contrast_ratio(fg_value, bg_value)
        if ratio is None or ratio >= minimum:
            continue
        entry: Dict[str, Any] = {
            "fg": fg_ref, "bg": bg_ref, "ratio": ratio, "min": minimum,
            "fg_value": fg_value, "bg_value": bg_value, "fg_source": fg_src, "bg_source": bg_src,
            "suggestions": [],
        }
        if suggest:
            for changed, source, value, other in ((fg_changed, fg_src, fg_value, bg_value), (bg_changed, bg_src, bg_value, fg_value)):
                if not changed:
                    continue
                suggestion = suggest_compliant_color(value, other, minimum)
                if suggestion:
                    entry["suggestions"].append({"ref": source, "value": suggestion[0], "ratio": suggestion[1]})
        violations.append(entry)
    return violations


def enforce_contrast(
    base_blocks: Dict[str, Dict[str, Any]],
    overlay_clean: Dict[str, Dict[str, Any]],
) -> Tuple[Dict[str, Dict[str, Any]], List[str]]:
    """Entfernt Overlay-Tokens, die einen Pflicht-Kontrast verletzen (Laufzeitschutz fuer den Resolver).

    Ein Benutzer-Overlay kann durch spaetere Aenderungen (Mandanten-Overlay, Variantenwechsel) ungueltig werden;
    damit immer alles lesbar bleibt, werden die verursachenden Tokens ignoriert und als Warnung gemeldet.
    """
    accepted = {group: dict(tokens) for group, tokens in overlay_clean.items()}
    warnings: List[str] = []
    for _ in range(10):
        violations = contrast_violations(base_blocks, accepted, suggest=False)
        if not violations:
            break
        overlay_refs = _overlay_refs(accepted)
        drop = set()
        for v in violations:
            # pro Verstoss nur eine Seite verwerfen: bevorzugt den Text, sonst den Hintergrund
            if v["fg_source"] in overlay_refs:
                drop.add(v["fg_source"])
            elif v["bg_source"] in overlay_refs:
                drop.add(v["bg_source"])
        if not drop:
            break
        for ref in sorted(drop):
            group, _, name = ref.partition(".")
            if name in accepted.get(group, {}):
                del accepted[group][name]
                warnings.append(f"Benutzer: '{describe_ref(ref)}' ignoriert (Kontrast unter dem Mindestmass)")
        accepted = {g: t for g, t in accepted.items() if t}
    return accepted, warnings


def contrast_errors(
    bases: Dict[str, Dict[str, Dict[str, Any]]],
    overlays: Dict[str, Dict[str, Dict[str, Any]]],
    *,
    layer: str,
) -> Tuple[List[str], List[Dict[str, Any]]]:
    """Fehlermeldungen und strukturierte Eintraege (je Modus) fuer ein zu speicherndes Overlay."""
    errors: List[str] = []
    payload: List[Dict[str, Any]] = []
    mode_label = {"light": "Hell", "dark": "Dunkel"}
    for mode, overlay in overlays.items():
        for v in contrast_violations(bases.get(mode, {}), overlay):
            text = (
                f"{layer} ({mode_label.get(mode, mode)}): Kontrast {describe_ref(v['fg'])} auf {describe_ref(v['bg'])} "
                f"ist {v['ratio']}:1 (mind. {v['min']}:1)"
            )
            if v["suggestions"]:
                text += " - Vorschlag: " + ", ".join(f"{describe_ref(s['ref'])} = {s['value']}" for s in v["suggestions"])
            errors.append(text)
            payload.append({**v, "mode": mode})
    return errors, payload


BG_PENALTY = 4.0  # Gewicht fuer Hintergrund-Anpassungen in repair_contrast


def repair_contrast(
    blocks: Dict[str, Dict[str, Any]], *, max_passes: int = 8, comfort: float = 0.0
) -> Tuple[Dict[str, Dict[str, Any]], List[Dict[str, Any]]]:
    """Korrigiert eine Theme-Variante (``{gruppe: {token: wert}}``) auf Pflicht-Kontraste.

    Je verletztem Paar wird die Farbe (Vordergrund oder Hintergrund) angepasst, deren Aenderung
    am kleinsten ausfaellt; nur ausdrueckliche Werte der Variante werden veraendert.
    ``comfort`` ist ein hoeheres Zielverhaeltnis (z. B. 7.0) fuer bereits verletzte Paare, damit repariertes
    Grau nicht nur knapp das Minimum erreicht; scheitert es, gilt das Minimum.
    Gibt die korrigierte Variante und die Liste der Aenderungen zurueck.
    """
    fixed = {group: dict(tokens) for group, tokens in blocks.items() if isinstance(tokens, dict)}
    changes: List[Dict[str, Any]] = []
    for _ in range(max_passes):
        progress = False
        for fg_ref, bg_ref, minimum in CONTRAST_PAIRS:
            fg_value, fg_src = effective_value(fixed, fg_ref)
            bg_value, bg_src = effective_value(fixed, bg_ref)
            ratio = contrast_ratio(fg_value, bg_value)
            if ratio is None or ratio >= minimum:
                continue
            options = []
            # Die Textseite (Vordergrund) wird bevorzugt angepasst; Flaechenfarben tragen die Markenidentitaet und
            # werden nur geaendert, wenn das deutlich weniger Veraenderung bedeutet (Faktor BG_PENALTY).
            for source, value, other, penalty in ((fg_src, fg_value, bg_value, 1.0), (bg_src, bg_value, fg_value, BG_PENALTY)):
                suggestion = None
                if comfort > minimum:
                    suggestion = suggest_compliant_color(value, other, comfort)
                suggestion = suggestion or suggest_compliant_color(value, other, minimum)
                if suggestion:
                    options.append((lightness_distance(value, suggestion[0]) * penalty, source, value, suggestion[0]))
            if not options:
                continue
            _, source, old, new = min(options)
            group, _, name = source.partition(".")
            key = next((k for k in fixed.get(group, {}) if normalize_token_name(group, k) == name), name)
            fixed.setdefault(group, {})[key] = new
            changes.append({"ref": source, "old": old, "new": new, "pair": f"{fg_ref} / {bg_ref}", "ratio_before": ratio})
            progress = True
        if not progress:
            break
    return fixed, changes


def pick_variant(package: Dict[str, Any], mode: str, requested: Optional[str]) -> Tuple[Optional[str], List[str]]:
    """Waehlt die Variante; faellt auf den Modus-Namen zurueck, wenn die gewuenschte nicht existiert."""
    warnings: List[str] = []
    for candidate in (requested, mode):
        if candidate and isinstance(package.get(candidate), dict):
            if requested and candidate != requested:
                warnings.append(f"Variante '{requested}' nicht im Paket - verwende '{candidate}'")
            return candidate, warnings
    warnings.append(f"Keine Variante fuer Modus '{mode}' im Paket gefunden")
    return None, warnings


def resolve_theme(
    *,
    package: Optional[Dict[str, Any]],
    package_guid: Optional[str],
    mode: str,
    variant: Optional[str],
    mandant_overlay: Optional[Dict[str, Any]] = None,
    user_overlay: Optional[Dict[str, Any]] = None,
    user_edit_patterns: Optional[Iterable[str]] = None,
) -> Dict[str, Any]:
    """Loest die drei Schichten zu den finalen Bloecken auf.

    ``user_edit_patterns`` stammt aus ``asy_mandanten.CONFIG.USER_THEME_EDIT``; ohne Eintrag darf der
    Benutzer keine Tokens ueberschreiben.
    """
    mode = "dark" if mode == "dark" else "light"
    package = package if isinstance(package, dict) else {}
    chosen, warnings = pick_variant(package, mode, variant)
    base, base_warnings = sanitize_package_variant(package.get(chosen, {}) if chosen else {})
    warnings += base_warnings

    mandant_clean, w = sanitize_overlay(
        (mandant_overlay or {}).get(mode), layer="Mandant"
    )
    warnings += w
    user_clean, w = sanitize_overlay(
        (user_overlay or {}).get(mode),
        layer="Benutzer",
        allowed_patterns=list(user_edit_patterns or []),
        require_user_editable=True,
    )
    warnings += w

    # Benutzer-Overlay darf keinen Pflicht-Kontrast verletzen (Laufzeitschutz, siehe enforce_contrast)
    user_clean, w = enforce_contrast(merge_layers(base, mandant_clean), user_clean)
    warnings += w

    blocks = merge_layers(base, mandant_clean, user_clean)
    contrast = check_contrast(blocks)
    return {
        "theme_package_id": package_guid,
        "theme_variant": chosen or mode,
        "mode": mode,
        "schema_version": SCHEMA_VERSION,
        "blocks": blocks,
        "layers": {"mandant": bool(mandant_clean), "user": bool(user_clean)},
        "contrast_issues": [c for c in contrast if not c["ok"]],
        "warnings": warnings,
    }


def get_catalog() -> Dict[str, Any]:
    """Das vorgegebene Token-Schema inkl. generierter Control-Definitionen (fuer Editoren).

    Jedes Token liefert Typ, Beschriftung, ``control_type`` (Typ des PdvmInputControl), Wertegrenzen,
    Optionen und die Kontrast-Gegenfarben. Die Controls werden aus dem Schema erzeugt und nicht in
    ``sys_control_dict`` gepflegt (die Variantengruppe des Themes ist zur Laufzeit variabel).
    """
    groups: Dict[str, Any] = {}
    for group, tokens in TOKEN_SCHEMA.items():
        described: Dict[str, Any] = {}
        for name, spec in tokens.items():
            entry = copy.deepcopy(spec)
            entry["label"] = token_label(group, name)
            entry["control_type"] = CONTROL_TYPE_BY_TOKEN_TYPE[spec["type"]]
            partners = contrast_partners(group, name)
            if partners:
                entry["contrast_against"] = partners
            described[name] = entry
        groups[group] = {"label": GROUP_LABELS.get(group, group), "tokens": described}
    return {
        "schema_version": SCHEMA_VERSION,
        "groups": groups,
        "user_edit_presets": user_edit_presets(),
        "contrast_pairs": [
            {"fg": fg, "bg": bg, "min": minimum, "fg_chain": ref_chain(fg), "bg_chain": ref_chain(bg)}
            for fg, bg, minimum in CONTRAST_PAIRS
        ],
    }


# ---------------------------------------------------------------------------
# Editor-Unterstuetzung (P4): Freigabe-Presets, strikte Pruefung, Basis je Ebene
# ---------------------------------------------------------------------------

_PRESET_FAMILY_LABELS = {
    "primary": "Primärfarbe (Skala)",
    "secondary": "Sekundärfarbe (Skala)",
    "background": "Hintergründe",
    "border": "Rahmenfarben",
}


def user_edit_presets() -> List[Dict[str, str]]:
    """Muster, die der Mandant fuer Benutzer freigeben kann (``USER_THEME_EDIT``); nur benutzeranpassbare Tokens."""
    presets: List[Dict[str, str]] = []
    for group, tokens in TOKEN_SCHEMA.items():
        editable = [name for name, spec in tokens.items() if spec.get("user_editable")]
        if group == "color":
            families: Dict[str, List[str]] = {}
            for name in editable:
                families.setdefault(name.split("-")[0], []).append(name)
            for family in families:
                label = _PRESET_FAMILY_LABELS.get(family, family)
                presets.append({"value": f"color.{family}-*", "label": f"{GROUP_LABELS['color']}: {label}"})
        else:
            for name in editable:
                presets.append({"value": f"{group}.{name}", "label": f"{GROUP_LABELS.get(group, group)}: {token_label(group, name)}"})
    return presets


def validate_user_edit_patterns(patterns: Any) -> Tuple[List[str], List[str]]:
    """Prueft ``USER_THEME_EDIT``: nur Muster, die mindestens ein benutzeranpassbares Token treffen."""
    if patterns is None:
        return [], []
    if not isinstance(patterns, list):
        return [], ["USER_THEME_EDIT muss eine Liste sein"]
    editable_refs = [
        f"{group}.{name}"
        for group, tokens in TOKEN_SCHEMA.items()
        for name, spec in tokens.items() if spec.get("user_editable")
    ]
    clean: List[str] = []
    errors: List[str] = []
    for raw in patterns:
        pattern = str(raw or "").strip()
        if not pattern or pattern in clean:
            continue
        if not any(fnmatchcase(ref, pattern) for ref in editable_refs):
            errors.append(f"Freigabe '{pattern}' trifft kein benutzeranpassbares Token")
            continue
        clean.append(pattern)
    return clean, errors


def validate_overlay_payload(
    overlay: Any,
    *,
    layer: str,
    allowed_patterns: Optional[Sequence[str]] = None,
    require_user_editable: bool = False,
) -> Tuple[Dict[str, Dict[str, Dict[str, Any]]], List[str]]:
    """Strikte Pruefung eines zu speichernden Overlays (``{light|dark: {gruppe: {token: wert}}}``).

    Im Gegensatz zum Resolver (verwirft Fehler still) liefert die Pruefung beim Speichern alle Fehler zurueck.
    """
    if overlay is None:
        return {}, []
    if not isinstance(overlay, dict):
        return {}, ["Overlay muss ein Objekt sein"]
    clean: Dict[str, Dict[str, Dict[str, Any]]] = {}
    errors: List[str] = []
    for mode, groups in overlay.items():
        if mode not in ("light", "dark"):
            errors.append(f"unbekannter Modus '{mode}' (erlaubt: light, dark)")
            continue
        mode_clean, mode_errors = sanitize_overlay(
            groups, layer=layer, allowed_patterns=allowed_patterns, require_user_editable=require_user_editable
        )
        errors += mode_errors
        if mode_clean:
            clean[mode] = mode_clean
    return clean, errors


def compose_base(
    package: Optional[Dict[str, Any]],
    *,
    mode: str,
    variant: Optional[str],
    mandant_overlay: Optional[Dict[str, Any]] = None,
) -> Tuple[Optional[str], Dict[str, Dict[str, Any]], List[str]]:
    """Basis fuer einen Editor: Paket-Variante, optional mit Mandanten-Overlay (fuer die Benutzer-Ebene)."""
    package = package if isinstance(package, dict) else {}
    chosen, warnings = pick_variant(package, mode, variant)
    base, base_warnings = sanitize_package_variant(package.get(chosen, {}) if chosen else {})
    overlay_clean, overlay_warnings = sanitize_overlay((mandant_overlay or {}).get(mode), layer="Mandant")
    return chosen, merge_layers(base, overlay_clean), warnings + base_warnings + overlay_warnings


def list_variants(package: Optional[Dict[str, Any]]) -> Dict[str, List[str]]:
    """Variantengruppen des Pakets, nach Modus gruppiert (Name enthaelt 'dark'/'light'; sonst beide)."""
    result: Dict[str, List[str]] = {"light": [], "dark": []}
    for name, value in (package or {}).items():
        if not isinstance(value, dict) or name in ("ROOT", "info", "TEMPLATES", "TABLE_INFO"):
            continue
        lowered = name.lower()
        if "dark" in lowered:
            result["dark"].append(name)
        elif "light" in lowered:
            result["light"].append(name)
        else:
            result["light"].append(name)
            result["dark"].append(name)
    return result

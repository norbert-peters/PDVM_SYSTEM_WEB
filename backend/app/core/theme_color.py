"""Farbrechnung fuer das Theming-System: Parsen, WCAG-Kontrast und Vorschlag der naechstgelegenen Farbe.

Der Vorschlag (``suggest_compliant_color``) aendert die Farbe nur in der Helligkeit (OKLab-L) und behaelt
Farbton und -- soweit im sRGB-Gamut moeglich -- die Saettigung. Gesucht wird in beide Richtungen die kleinste
Helligkeitsaenderung, die den geforderten Kontrast erreicht; so bleibt der Eindruck der Farbe erhalten
(z. B. wird ein Orange zu einem dunkleren Orange, nicht zu Grau).

Die TypeScript-Fassung steht in ``frontend/src/utils/themeColor.ts`` und muss dieselben Ergebnisse liefern
(Vergleichswerte in ``backend/test_theme_color.py``).
"""
from __future__ import annotations

import math
import re
from typing import Any, Optional, Tuple

_HEX = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")
_RGB = re.compile(
    r"^rgba?\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*(?:,\s*(0|1|0?\.\d+|1\.0+)\s*)?\)$"
)

STEP = 0.0025  # Schrittweite der Helligkeitssuche (OKLab-L)


def parse_css_color(value: Any) -> Optional[Tuple[int, int, int, float]]:
    """Liest #hex und rgb()/rgba(); andere Formate (hsl, var, Schluesselwoerter) liefern None."""
    if not isinstance(value, str):
        return None
    text = value.strip()
    if _HEX.match(text):
        h = text[1:]
        if len(h) in (3, 4):
            h = "".join(c * 2 for c in h)
        r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
        a = int(h[6:8], 16) / 255 if len(h) == 8 else 1.0
        return r, g, b, a
    m = _RGB.match(text)
    if m:
        r, g, b = (int(m.group(i)) for i in (1, 2, 3))
        if max(r, g, b) > 255:
            return None
        return r, g, b, float(m.group(4)) if m.group(4) is not None else 1.0
    return None


def _luminance(r: int, g: int, b: int) -> float:
    def channel(c: int) -> float:
        s = c / 255
        return s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4

    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def _ratio(rgb_a: Tuple[int, int, int], rgb_b: Tuple[int, int, int]) -> float:
    hi, lo = sorted((_luminance(*rgb_a), _luminance(*rgb_b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def contrast_ratio(fg: Any, bg: Any) -> Optional[float]:
    """WCAG-Kontrastverhaeltnis; None bei nicht auswertbaren oder transparenten Farben."""
    a, b = parse_css_color(fg), parse_css_color(bg)
    if a is None or b is None or a[3] < 1.0 or b[3] < 1.0:
        return None
    return round(_ratio(a[:3], b[:3]), 2)


# --- OKLab ----------------------------------------------------------------

def _to_linear(c: int) -> float:
    s = c / 255
    return s / 12.92 if s <= 0.04045 else ((s + 0.055) / 1.055) ** 2.4


def _from_linear(x: float) -> float:
    x = min(1.0, max(0.0, x))
    return 12.92 * x if x <= 0.0031308 else 1.055 * (x ** (1 / 2.4)) - 0.055


def _rgb_to_oklab(r: int, g: int, b: int) -> Tuple[float, float, float]:
    lr, lg, lb = _to_linear(r), _to_linear(g), _to_linear(b)
    l = 0.4122214708 * lr + 0.5363325363 * lg + 0.0514459929 * lb
    m = 0.2119034982 * lr + 0.6806995451 * lg + 0.1073969566 * lb
    s = 0.0883024619 * lr + 0.2817188376 * lg + 0.6299787005 * lb
    l_, m_, s_ = l ** (1 / 3), m ** (1 / 3), s ** (1 / 3)
    return (
        0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_,
        1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_,
        0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_,
    )


def _oklab_to_linear(L: float, a: float, b: float) -> Tuple[float, float, float]:
    l_ = L + 0.3963377774 * a + 0.2158037573 * b
    m_ = L - 0.1055613458 * a - 0.0638541728 * b
    s_ = L - 0.0894841775 * a - 1.2914855480 * b
    l, m, s = l_ ** 3, m_ ** 3, s_ ** 3
    return (
        4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
        -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
        -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s,
    )


def _in_gamut(rgb: Tuple[float, float, float]) -> bool:
    return all(-1e-6 <= c <= 1 + 1e-6 for c in rgb)


def _lch_to_rgb(L: float, C: float, h: float) -> Tuple[int, int, int]:
    """OKLCH -> sRGB (8 Bit); ausserhalb des Gamuts wird die Saettigung per Bisektion reduziert."""
    a, b = math.cos(h), math.sin(h)
    lin = _oklab_to_linear(L, C * a, C * b)
    if not _in_gamut(lin):
        lo, hi = 0.0, C
        for _ in range(24):
            mid = (lo + hi) / 2
            if _in_gamut(_oklab_to_linear(L, mid * a, mid * b)):
                lo = mid
            else:
                hi = mid
        lin = _oklab_to_linear(L, lo * a, lo * b)
    return tuple(round(_from_linear(c) * 255) for c in lin)  # type: ignore[return-value]


def _hex(rgb: Tuple[int, int, int]) -> str:
    return "#{:02x}{:02x}{:02x}".format(*rgb)


def suggest_compliant_color(color: Any, against: Any, minimum: float) -> Optional[Tuple[str, float]]:
    """Naechstgelegene Farbe (gleicher Farbton, geaenderte Helligkeit) mit Kontrast >= ``minimum`` zu ``against``.

    Gibt ``(hex, ratio)`` zurueck. Ist die Farbe bereits ausreichend, kommt sie unveraendert zurueck;
    nicht auswertbare Farben (Transparenz, var(), hsl) liefern ``None``.
    """
    fg, bg = parse_css_color(color), parse_css_color(against)
    if fg is None or bg is None or fg[3] < 1.0 or bg[3] < 1.0:
        return None
    fg_rgb, bg_rgb = fg[:3], bg[:3]
    current = _ratio(fg_rgb, bg_rgb)
    if current >= minimum:
        return _hex(fg_rgb), round(current, 2)

    L0, a0, b0 = _rgb_to_oklab(*fg_rgb)
    C, h = math.hypot(a0, b0), math.atan2(b0, a0)

    best: Optional[Tuple[float, Tuple[int, int, int]]] = None
    for direction in (1, -1):
        steps = int(1 / STEP) + 1
        for i in range(1, steps):
            L = L0 + direction * i * STEP
            if L < 0 or L > 1:
                break
            rgb = _lch_to_rgb(L, C, h)
            if _ratio(rgb, bg_rgb) >= minimum:
                if best is None or abs(L - L0) < best[0]:
                    best = (abs(L - L0), rgb)
                break

    if best is None:  # nur Schwarz/Weiss kann helfen (z. B. mittlerer Hintergrund)
        black, white = (0, 0, 0), (255, 255, 255)
        rgb = max((black, white), key=lambda c: _ratio(c, bg_rgb))
        if _ratio(rgb, bg_rgb) < minimum:
            return None
        best = (0.0, rgb)
    return _hex(best[1]), round(_ratio(best[1], bg_rgb), 2)


def lightness_distance(a: Any, b: Any) -> float:
    """Unterschied der OKLab-Helligkeit zweier Farben (Mass fuer "wie stark wird die Farbe veraendert")."""
    ca, cb = parse_css_color(a), parse_css_color(b)
    if ca is None or cb is None:
        return float("inf")
    return abs(_rgb_to_oklab(*ca[:3])[0] - _rgb_to_oklab(*cb[:3])[0])

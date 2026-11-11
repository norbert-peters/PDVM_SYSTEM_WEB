"""Tests fuer Farbrechnung und Kontrast-Durchsetzung (P6)."""
import pytest

from app.core import theme_service as ts
from app.core.theme_color import contrast_ratio, lightness_distance, suggest_compliant_color
from app.core.theme_schema import CONTRAST_PAIRS

# Referenzwerte; frontend/src/utils/themeColor.ts liefert fuer dieselben Eingaben identische Ergebnisse
# (Paritaet am 10.11.2026 mit esbuild-Bundle + node geprueft).
VECTORS = [
    (("#ffffff", "#ff9800", 4.5), ("#444444", 4.52)),
    (("#e65100", "#ffffff", 4.5), ("#d04900", 4.53)),
    (("#ff9800", "#ffffff", 4.5), ("#ad6500", 4.53)),
    (("#2196f3", "#ffffff", 4.5), ("#007acd", 4.5)),
    (("#ffcc80", "#fff8f0", 4.5), ("#986a15", 4.52)),
    (("#757575", "#f5f5f5", 4.5), ("#707070", 4.54)),
    (("#ffb74d", "#121212", 4.5), ("#ffb74d", 10.82)),  # bereits ausreichend: unveraendert
    (("#777777", "#808080", 4.5), ("#171717", 4.54)),
    (("#1b5e20", "#2e7d32", 4.5), ("#c5ffc4", 4.51)),
    (("#66bb6a", "#ffffff", 3), ("#51a656", 3.03)),
    (("#ff0000", "#00ff00", 7), ("#900000", 7.0)),
    (("#123456", "#123457", 4.5), ("#799ec6", 4.54)),
]


@pytest.mark.parametrize("args,expected", VECTORS)
def test_suggestion_matches_reference_values(args, expected):
    assert suggest_compliant_color(*args) == expected


def test_suggestion_properties():
    for (color, against, minimum), _ in VECTORS:
        color_out, ratio = suggest_compliant_color(color, against, minimum)
        assert ratio >= minimum - 0.005 and contrast_ratio(color_out, against) >= minimum - 0.005
    # nicht auswertbare Farben liefern keinen Vorschlag
    assert suggest_compliant_color("var(--x)", "#ffffff", 4.5) is None
    assert suggest_compliant_color("rgba(0,0,0,0.5)", "#ffffff", 4.5) is None
    # die Aenderung bleibt klein: Orange wird zu dunklerem Orange (gleicher Farbton), nicht zu Grau
    orange, _ = suggest_compliant_color("#e65100", "#ffffff", 4.5)
    assert orange.startswith("#d") and lightness_distance("#e65100", orange) < 0.05


PACKAGE_LIGHT = {
    "color": {
        "primary-500": "#ff9800", "text-primary": "#111111", "text-secondary": "#444444", "text-inverse": "#ffffff",
        "background-primary": "#ffffff", "background-secondary": "#f5f5f5",
    },
    "block_btn_primary": {"bg_color": "#0b5394", "text_color": "#ffffff"},
}


def test_violations_only_for_pairs_the_overlay_changes():
    # geerbter Verstoss (Weiss auf Orange, text-inverse/primary-500) bleibt unberuehrt, solange nichts daran geaendert wird
    assert ts.contrast_violations(PACKAGE_LIGHT, {"color": {"text-secondary": "#555555"}}) == []

    bad = ts.contrast_violations(PACKAGE_LIGHT, {"block_btn_primary": {"bg_color": "#ffcc80"}})
    assert [(v["fg"], v["bg"]) for v in bad] == [("block_btn_primary.text_color", "block_btn_primary.bg_color")]
    suggestion = bad[0]["suggestions"][0]
    assert suggestion["ref"] == "block_btn_primary.bg_color"
    assert ts.contrast_ratio("#ffffff", suggestion["value"]) >= 4.5


def test_fallback_chain_counts_for_blocks_without_explicit_value():
    # block_btn_primary hat keinen eigenen Hintergrund: wirksam ist color.primary-500 (CSS-Fallback)
    base = {"color": {"primary-500": "#0b5394", "text-inverse": "#ffffff"}}
    assert ts.contrast_violations(base, {"color": {"primary-500": "#ffcc80"}})
    value, source = ts.effective_value(base, "block_btn_primary.bg_color")
    assert (value, source) == ("#0b5394", "color.primary-500")


def test_enforce_contrast_drops_only_the_offending_tokens():
    overlay = {"color": {"text-primary": "#fefefe", "background-secondary": "#eeeeee"}}
    accepted, warnings = ts.enforce_contrast(PACKAGE_LIGHT, overlay)
    assert accepted == {"color": {"background-secondary": "#eeeeee"}}
    assert len(warnings) == 1 and "Text primär" in warnings[0]


def test_resolver_ignores_user_tokens_that_break_contrast():
    package = {"light": PACKAGE_LIGHT}
    result = ts.resolve_theme(
        package=package, package_guid="g", mode="light", variant=None,
        user_overlay={"light": {"color": {"background-primary": "#222222", "primary-500": "#0a4a85"}}},
        user_edit_patterns=["color.*"],
    )
    # Hintergrund #222222 macht text-primary (#111111) unlesbar -> ignoriert; primary-500 bleibt
    assert result["blocks"]["color"]["background-primary"] == "#ffffff"
    assert result["blocks"]["color"]["primary-500"] == "#0a4a85"
    assert any("Hintergrund primär" in w for w in result["warnings"])


def test_contrast_errors_message_and_payload():
    errors, payload = ts.contrast_errors({"light": PACKAGE_LIGHT}, {"light": {"block_btn_primary": {"bg_color": "#ffcc80"}}}, layer="Mandant")
    assert len(errors) == 1 and "Mandant (Hell)" in errors[0] and "Vorschlag" in errors[0] and "#" in errors[0]
    assert payload[0]["mode"] == "light" and payload[0]["suggestions"]


def test_repair_contrast_fixes_variant_with_minimal_change():
    fixed, changes = ts.repair_contrast(PACKAGE_LIGHT)
    assert not [c for c in ts.check_contrast(fixed) if not c["ok"]]
    assert PACKAGE_LIGHT["color"]["primary-500"] == "#ff9800"  # Eingabe bleibt unveraendert
    # Weiss auf Orange: bevorzugt wird die Textseite angepasst, die Markenfarbe bleibt
    assert fixed["color"]["primary-500"] == "#ff9800" and fixed["color"]["text-inverse"] != "#ffffff"
    assert changes and all("ref" in c and "new" in c for c in changes)


def test_catalog_exposes_contrast_pairs_with_chains():
    catalog = ts.get_catalog()
    pairs = {(p["fg"], p["bg"]): p for p in catalog["contrast_pairs"]}
    btn = pairs[("block_btn_primary.text_color", "block_btn_primary.bg_color")]
    assert btn["fg_chain"] == ["block_btn_primary.text_color", "color.text-inverse"]
    assert btn["bg_chain"] == ["block_btn_primary.bg_color", "color.primary-500"]
    assert btn["min"] == 4.5


def test_raw_db_keys_with_underscore_are_checked_and_repaired():
    # Rohdaten aus der DB nutzen teils 'text-on_tertiary'; die Pruefung darf diese Paare nicht uebergehen
    raw = {"color": {"text-on_tertiary": "#333333", "background-tertiary": "#2a2a2a"}}
    bad = [c for c in ts.check_contrast(raw) if not c["ok"]]
    assert [(c["fg"], c["bg"]) for c in bad] == [("color.text-on-tertiary", "color.background-tertiary")]
    fixed, changes = ts.repair_contrast(raw)
    assert set(fixed["color"]) == {"text-on_tertiary", "background-tertiary"}  # bestehender Schluessel wird ueberschrieben
    assert not [c for c in ts.check_contrast(fixed) if not c["ok"]] and changes


def test_repair_comfort_target_gives_more_than_the_minimum():
    raw = {"color": {"text-on-secondary": "#000000", "background-secondary": "#1e1e1e"}}
    minimal, _ = ts.repair_contrast(raw)
    comfy, _ = ts.repair_contrast(raw, comfort=7.0)
    assert contrast_ratio(minimal["color"]["text-on-secondary"], "#1e1e1e") >= 4.5
    assert contrast_ratio(comfy["color"]["text-on-secondary"], "#1e1e1e") >= 7.0


def test_bare_hex_values_are_normalized_and_invalid_package_values_dropped():
    variant = {"block_stichtag_std": {"text_color": "000000", "bg_color": "#ffa726"}, "color": {"text-primary": "#111111"}}
    fixed, changes = ts.normalize_package_values(variant)
    assert fixed["block_stichtag_std"]["text_color"] == "#000000"
    assert changes == [{"ref": "block_stichtag_std.text_color", "old": "000000", "new": "#000000"}]
    assert variant["block_stichtag_std"]["text_color"] == "000000"  # Eingabe bleibt unveraendert

    clean, warnings = ts.sanitize_package_variant(variant)
    assert "text_color" not in clean["block_stichtag_std"] and clean["block_stichtag_std"]["bg_color"] == "#ffa726"
    assert len(warnings) == 1 and "block_stichtag_std.text_color" in warnings[0]


def test_resolver_ignores_invalid_package_values():
    result = ts.resolve_theme(
        package={"dark": {"block_stichtag_std": {"text_color": "000000", "bg_color": "#ffa726"}}},
        package_guid="g", mode="dark", variant=None, user_overlay=None, user_edit_patterns=[],
    )
    assert "text_color" not in result["blocks"]["block_stichtag_std"]
    assert any("block_stichtag_std.text_color" in w for w in result["warnings"])


def test_stichtag_field_and_popover_blocks_are_in_schema_with_contrast_pairs():
    pairs = {(fg, bg) for fg, bg, _ in CONTRAST_PAIRS}
    for group in ("block_stichtag_std", "block_pic_popover"):
        assert "field_bg_color" in ts.TOKEN_SCHEMA[group] and "field_text_color" in ts.TOKEN_SCHEMA[group]
        assert (f"{group}.field_text_color", f"{group}.field_bg_color") in pairs
    assert ("block_pic_popover.text_color", "block_pic_popover.bg_color") in pairs
    # Fallback der Stichtag-Felder folgt dem CSS: Feld -> Formularfeld (block_pic_std) -> Farbpalette
    assert ts.ref_chain("block_stichtag_std.field_bg_color") == [
        "block_stichtag_std.field_bg_color", "block_pic_std.bg_color", "color.background-primary",
    ]


def _css_status_formulas():
    """Liest die Formeln der abgeleiteten Status-Tokens aus variables.css: {(modus, status): (bg_prozent, text_prozent, text_mit)}."""
    import re
    from pathlib import Path

    css = (Path(__file__).resolve().parents[1] / "frontend" / "src" / "styles" / "base" / "variables.css").read_text(encoding="utf-8")
    base = css[css.index("Abgeleitete Tokens"):]
    dark_start = base.index(':root[data-theme="dark"],')
    result = {}
    for mode, chunk in (("light", base[:dark_start]), ("dark", base[dark_start:])):
        for status in ("success", "warning", "error", "info"):
            bg = re.search(rf"--color-{status}-bg:\s*color-mix\(in srgb, var\(--color-{status}\) (\d+)%, var\(--color-background-primary\)\)", base[:dark_start])
            text = re.search(rf"--color-{status}-text:\s*color-mix\(in srgb, var\(--color-{status}\) (\d+)%, (black|white)\)", chunk)
            if mode == "dark" and not text:
                text = re.search(rf"--color-{status}-text:\s*color-mix\(in srgb, var\(--color-{status}\) (\d+)%, (black|white)\)", base[:dark_start])
            assert bg and text, (mode, status)
            result[(mode, status)] = (int(bg.group(1)), int(text.group(1)), text.group(2))
    return result


def status_contrasts(tokens, mode):
    """Kontrast von --color-<status>-text auf --color-<status>-bg (deckend ueber background-primary), wie im CSS berechnet."""
    from app.core.theme_color import parse_css_color

    def mix(a, percent, b):
        return tuple(round(x * percent / 100 + y * (100 - percent) / 100) for x, y in zip(a, b))

    formulas = _css_status_formulas()
    page = parse_css_color(tokens["background-primary"])[:3]
    out = {}
    for status in ("success", "warning", "error", "info"):
        color = parse_css_color(tokens[status])[:3]
        bg_pct, text_pct, text_with = formulas[(mode, status)]
        bg = mix(color, bg_pct, page)
        text = mix(color, text_pct, (0, 0, 0) if text_with == "black" else (255, 255, 255))
        out[status] = contrast_ratio("#%02x%02x%02x" % text, "#%02x%02x%02x" % bg)
    return out


def _css_default_tokens():
    import re
    from pathlib import Path

    css = (Path(__file__).resolve().parents[1] / "frontend" / "src" / "styles" / "base" / "variables.css").read_text(encoding="utf-8")

    def colors(selector):
        body = re.search(selector + r"\s*\{(.*?)\n\}", css, re.S).group(1)
        return dict(re.findall(r"--color-([a-z0-9-]+):\s*(#[0-9a-fA-F]{3,8})", body))

    light = colors(r":root,\s*:root\[data-theme=\"light\"\]")
    return light, {**light, **colors(r":root\[data-theme=\"dark\"\]")}


def test_css_default_themes_pass_required_contrast():
    # Hell/Dunkel-Defaults in variables.css gelten ohne geladenes Theme (z. B. Login) und bei fehlendem Paket
    light, dark = _css_default_tokens()
    for name, tokens in (("light", light), ("dark", dark)):
        results = ts.check_contrast({"color": tokens})
        assert len(results) == len(CONTRAST_PAIRS)
        assert not [c for c in results if not c["ok"]], name


def test_status_message_colors_are_readable_in_default_themes():
    # Fehler-/Erfolgs-/Warn-/Info-Meldungen: deckender Hintergrund, Text >= 4.5:1 (Hell und Dunkel)
    light, dark = _css_default_tokens()
    for mode, tokens in (("light", light), ("dark", dark)):
        for status, ratio in status_contrasts(tokens, mode).items():
            assert ratio >= 4.5, (mode, status, ratio)

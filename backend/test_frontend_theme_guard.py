"""Guard fuer das Theming-System V2 (ARCHITECTURE_RULES 4.2): keine harten Farben im Frontend.

Farben duerfen nur in ``frontend/src/styles/base/variables.css`` (Default-Schicht) stehen. Alle anderen
CSS-/TS-Dateien beziehen sie ueber ``var(--block-*, var(--color-*))``. Zusaetzlich sind Legacy-Variablen
und das ``.dark``-Selektorschema verboten (der Modus steht in ``:root[data-theme]``).

Ausfuehren: ..\\.venv\\Scripts\\python.exe -m pytest test_frontend_theme_guard.py
"""
import re
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "frontend" / "src"
DEFAULTS_FILE = SRC / "styles" / "base" / "variables.css"

COLOR_LITERAL = re.compile(r"(?<![&\w-])#[0-9a-fA-F]{3,8}\b|\brgba?\(|\bhsla?\(")
# Benannte Farben als Stringwert in Inline-Styles ('crimson', 'white' ...)
NAMED_COLOR = re.compile(
    r"['\"](?:white|black|red|crimson|darkred|green|blue|gray|grey|orange|yellow|purple|navy|silver)['\"]",
    re.IGNORECASE,
)
LEGACY_VAR = re.compile(r"var\(\s*--(?:surface-|border-color\b|primary-color\b|text-(?:primary|secondary)\b|color-error-dark\b)")
DARK_CLASS = re.compile(r"(?<![\w-])\.dark\b")

_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_LINE_COMMENT = re.compile(r"(?<![:\"'])//[^\n]*")


def _strip_comments(text: str, line_comments: bool) -> str:
    # Zeilenzahl bleibt erhalten, damit die Fundstellen stimmen
    text = _BLOCK_COMMENT.sub(lambda m: "\n" * m.group(0).count("\n"), text)
    return _LINE_COMMENT.sub("", text) if line_comments else text


def _files(*suffixes: str):
    return sorted(p for p in SRC.rglob("*") if p.suffix in suffixes and p.is_file())


def _scan(paths, pattern, *, skip=(), line_comments=False):
    findings = []
    for path in paths:
        if path in skip:
            continue
        raw = path.read_text(encoding="utf-8", errors="ignore")
        raw_lines = raw.splitlines()
        text = _strip_comments(raw, line_comments)
        for number, line in enumerate(text.splitlines(), start=1):
            # Einzelne, begruendete Ausnahmen (z. B. natives Farbfeld braucht einen Hex-Startwert)
            if pattern.search(line) and "guard-allow-color" not in raw_lines[number - 1]:
                findings.append(f"{path.relative_to(SRC).as_posix()}:{number}: {line.strip()[:110]}")
    return findings


def _fail_message(title, findings):
    shown = "\n  ".join(findings[:60])
    more = f"\n  ... und {len(findings) - 60} weitere" if len(findings) > 60 else ""
    return f"{title} ({len(findings)}):\n  {shown}{more}"


def test_css_has_no_hardcoded_colors_outside_defaults():
    findings = _scan(_files(".css"), COLOR_LITERAL, skip=(DEFAULTS_FILE,))
    assert not findings, _fail_message("Harte Farben in CSS (nur variables.css erlaubt)", findings)


def test_components_have_no_inline_color_literals():
    findings = _scan(_files(".ts", ".tsx"), COLOR_LITERAL, line_comments=True)
    findings += _scan(_files(".tsx"), NAMED_COLOR, line_comments=True)
    assert not findings, _fail_message("Harte Farben in TS/TSX (Klassen und Tokens verwenden)", findings)


def test_no_legacy_theme_variables():
    findings = _scan(_files(".css", ".ts", ".tsx"), LEGACY_VAR, line_comments=True)
    assert not findings, _fail_message("Legacy-Variablen (--surface-*, --border-color, --primary-color, --text-*)", findings)


def test_dark_mode_uses_data_theme_not_dark_class():
    findings = _scan(_files(".css"), DARK_CLASS)
    assert not findings, _fail_message("'.dark'-Selektor statt ':root[data-theme=\"dark\"]'", findings)


# Markenfarben-Stufen als Textfarbe (z. B. Orange #ff9800 auf Weiss 2,2:1) sind nicht kontrastgeprueft;
# fuer Text auf der Seitenflaeche gilt --color-text-on-primary (Pflichtpaar auf background-primary).
BRAND_AS_TEXT = re.compile(r"(?<![-\w])color:\s*['\"]?var\(--color-(?:primary|secondary)-(?:[1-5]00|[1-5]0)\b")
# Die hellen Stufen 50-200 bleiben im Dunkelmodus hell; als Flaeche blenden sie dort und nehmen hellem Text den Kontrast.
LIGHT_SCALE_SURFACE = re.compile(r"background(?:-color)?:\s*['\"]?[^;]*var\(--color-(?:primary|secondary)-(?:50|100|200)\)")


def test_brand_colors_are_not_used_as_text_color():
    findings = _scan(_files(".css", ".tsx"), BRAND_AS_TEXT, line_comments=True)
    assert not findings, _fail_message("Markenfarbe als Textfarbe (--color-text-on-primary verwenden)", findings)


def test_light_color_scale_is_not_used_as_surface():
    findings = _scan(_files(".css", ".tsx"), LIGHT_SCALE_SURFACE, line_comments=True)
    assert not findings, _fail_message(
        "Helle Farbstufen (50-200) als Flaeche (color-mix mit Hintergrund bzw. --state-* verwenden)", findings
    )


def test_layout_variants_in_css_match_catalog():
    """Jede Katalog-Option braucht CSS (ausser 'standard'), und jedes CSS-Attribut braucht einen Katalogeintrag."""
    from app.core.layout_schema import LAYOUT_SCHEMA

    css = (SRC / "styles" / "layouts" / "variants.css").read_text(encoding="utf-8")
    used = set(re.findall(r'data-layout-([a-z]+)="([a-z-]+)"', css))
    expected = {(area, opt) for area, data in LAYOUT_SCHEMA.items() for opt in data["options"] if opt != "standard"}
    assert used == expected, f"fehlt im CSS: {sorted(expected - used)}; ohne Katalogeintrag: {sorted(used - expected)}"


def test_block_variables_exist_in_token_schema():
    from app.core.theme_schema import TOKEN_SCHEMA

    known = {
        f"--{group.replace('_', '-')}-{token.replace('_', '-')}"
        for group, tokens in TOKEN_SCHEMA.items() if group.startswith("block_")
        for token in tokens
    }
    used = re.compile(r"var\(\s*(--block-[a-z0-9-]+)")
    findings = []
    for path in _files(".css", ".ts", ".tsx"):
        for number, line in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), start=1):
            findings += [
                f"{path.relative_to(SRC).as_posix()}:{number}: {name}"
                for name in used.findall(line) if name not in known
            ]
    assert not findings, _fail_message("--block-* Variablen ohne Eintrag in theme_schema.TOKEN_SCHEMA", findings)

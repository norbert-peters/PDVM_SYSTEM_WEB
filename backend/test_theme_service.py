"""Tests fuer app.core.theme_service / theme_schema (Schichten, Validierung, Kontrast)."""
from app.core import theme_service as ts

PACKAGE = {
    "ROOT": {"SELF_GUID": "x"},
    "info": {"name": "Test"},
    "light": {
        "color": {
            "primary-500": "#ff9800",
            "text-primary": "#000000",
            "text-on_primary": "#111111",
            "background-primary": "#ffffff",
            "background-secondary": "#f5f5f5",
            "text-secondary": "#555555",
        },
        "font": {"primary": "Inter, sans-serif", "scale": "1"},
        "block_btn_primary": {"bg_color": "#ff9800", "text_color": "#ffffff", "radius": "0.5rem"},
    },
    "dark": {"color": {"background-primary": "#121212", "text-primary": "#ffffff"}},
}


def _resolve(**kwargs):
    base = dict(package=PACKAGE, package_guid="g", mode="light", variant=None)
    base.update(kwargs)
    return ts.resolve_theme(**base)


def test_contrast_ratio_matches_wcag_reference_values():
    assert ts.contrast_ratio("#000000", "#ffffff") == 21.0
    assert ts.contrast_ratio("#ffffff", "#ff9800") == 2.16
    assert ts.contrast_ratio("var(--x)", "#ffffff") is None
    assert ts.contrast_ratio("rgba(0,0,0,0.5)", "#ffffff") is None


def test_package_only_normalizes_hyphen_groups():
    result = _resolve()
    assert result["theme_variant"] == "light"
    assert "text-on-primary" in result["blocks"]["color"]
    assert "text-on_primary" not in result["blocks"]["color"]
    assert result["blocks"]["block_btn_primary"]["bg_color"] == "#ff9800"
    assert result["layers"] == {"mandant": False, "user": False}


def test_mandant_overlay_overrides_package_token_by_token():
    overlay = {"light": {"block_btn_primary": {"bg_color": "#0055aa"}, "color": {"text_on_primary": "#fff"}}}
    result = _resolve(mandant_overlay=overlay)
    assert result["blocks"]["block_btn_primary"]["bg_color"] == "#0055aa"
    assert result["blocks"]["block_btn_primary"]["text_color"] == "#ffffff"
    assert result["layers"]["mandant"] is True
    assert PACKAGE["light"]["block_btn_primary"]["bg_color"] == "#ff9800"  # Basis bleibt unveraendert


def test_user_overlay_requires_mandant_release_and_user_editable_token():
    overlay = {"light": {"color": {"primary-500": "#123456", "text-primary": "#ff0000", "background-primary": "#eeeeee"}}}

    blocked = _resolve(user_overlay=overlay)
    assert blocked["blocks"]["color"]["primary-500"] == "#ff9800"
    assert blocked["layers"]["user"] is False

    released = _resolve(user_overlay=overlay, user_edit_patterns=["color.primary-*", "color.text-*"])
    assert released["blocks"]["color"]["primary-500"] == "#123456"
    # text-primary ist nie benutzeranpassbar, auch wenn der Mandant es freigibt
    assert released["blocks"]["color"]["text-primary"] == "#000000"
    # background-primary ist nicht freigegeben
    assert released["blocks"]["color"]["background-primary"] == "#ffffff"
    assert any("text-primary" in w for w in released["warnings"])


def test_invalid_and_malicious_values_are_dropped_without_failing():
    overlay = {
        "light": {
            "color": {"primary-500": "red; background:url(http://evil)", "primary-600": "#12"},
            "block_btn_primary": {"radius": "1px}", "bg_color": "#abcdef"},
            "unknown_block": {"x": "#fff"},
        }
    }
    result = _resolve(mandant_overlay=overlay)
    assert result["blocks"]["color"]["primary-500"] == "#ff9800"
    assert "primary-600" not in result["blocks"]["color"]
    assert result["blocks"]["block_btn_primary"]["radius"] == "0.5rem"
    assert result["blocks"]["block_btn_primary"]["bg_color"] == "#abcdef"
    assert "unknown_block" not in result["blocks"]
    assert len(result["warnings"]) == 4


def test_variant_fallback_and_missing_package():
    result = _resolve(variant="Nope_Light")
    assert result["theme_variant"] == "light"
    assert any("Nope_Light" in w for w in result["warnings"])

    empty = _resolve(package=None, package_guid=None)
    assert empty["blocks"] == {} and empty["theme_variant"] == "light"


def test_contrast_issues_report_failing_pairs_only():
    result = _resolve()
    failing = {(c["fg"], c["bg"]) for c in result["contrast_issues"]}
    assert ("block_btn_primary.text_color", "block_btn_primary.bg_color") in failing
    assert ("color.text-primary", "color.background-primary") not in failing


def test_value_validators_by_type():
    v = ts.validate_token_value
    assert v("color", "#fff") and v("color", "rgba(0, 0, 0, 0.5)") and v("color", "var(--color-primary-500)")
    assert not v("color", "rgb(300,0,0)") and not v("color", "#12345")
    assert v("length", "0.5rem") and v("length", "0") and not v("length", "calc(1px+2px)")
    assert v("length", "8px 12px") and v("length", "0 0 4px 4px") and not v("length", "1px 2px 3px 4px 5px")
    assert v("border", "1px solid #ffcc80") and v("border", "none") and not v("border", "1px wavy #fff")
    assert v("shadow", "0 1px 2px 0 rgba(0, 0, 0, 0.05)") and not v("shadow", "0 0 0 url(x)")
    assert v("font", "Inter, 'Segoe UI', sans-serif") and not v("font", "a;b")
    spec = {"min": 0.8, "max": 1.5}
    assert v("number", "1.2", spec) and not v("number", 3, spec) and not v("number", "abc", spec)


def test_catalog_contains_all_groups_and_user_flags():
    catalog = ts.get_catalog()
    color = catalog["groups"]["color"]
    assert color["label"] == "Farbpalette"
    assert color["tokens"]["primary-500"]["user_editable"] is True
    assert color["tokens"]["text-primary"]["user_editable"] is False
    assert "block_btn_primary" in catalog["groups"]


def test_catalog_generates_controls_for_every_token():
    from app.core.theme_schema import CONTROL_TYPE_BY_TOKEN_TYPE, GROUP_LABELS, TOKEN_SCHEMA

    catalog = ts.get_catalog()
    assert set(catalog["groups"]) == set(TOKEN_SCHEMA) == set(GROUP_LABELS)
    for group, data in catalog["groups"].items():
        for name, entry in data["tokens"].items():
            assert entry["control_type"] in CONTROL_TYPE_BY_TOKEN_TYPE.values(), (group, name)
            assert entry["label"] and entry["label"] != name or group == "color", (group, name)
            for partner in entry.get("contrast_against", []):
                ref_group, _, ref_token = partner["ref"].partition(".")
                assert ref_token in catalog["groups"][ref_group]["tokens"], partner

    tokens = catalog["groups"]["color"]["tokens"]
    assert tokens["primary-500"]["label"] == "Primär 500"
    assert tokens["primary-500"]["control_type"] == "color"
    assert {p["ref"] for p in tokens["text-primary"]["contrast_against"]} == {
        "color.background-primary", "color.background-secondary",
    }
    btn = catalog["groups"]["block_btn_primary"]["tokens"]
    assert btn["bg_color"]["contrast_against"] == [{"ref": "block_btn_primary.text_color", "min": 4.5}]
    assert btn["radius"]["control_type"] == "css_length" and btn["border"]["control_type"] == "css_border"
    scale = catalog["groups"]["font"]["tokens"]["scale"]
    assert scale["control_type"] == "dropdown" and "1.25" in scale["options"]


def _gcs(user_data=None, mandant_cfg=None, overlay=None):
    from types import SimpleNamespace
    from app.core.pdvm_central_systemsteuerung import PdvmCentralSystemsteuerung

    gcs = object.__new__(PdvmCentralSystemsteuerung)
    gcs.user_guid = "u1"
    gcs.systemsteuerung = SimpleNamespace(data={"u1": user_data or {}})
    gcs.mandant = SimpleNamespace(data={"CONFIG": mandant_cfg or {}})
    gcs.layout = SimpleNamespace(data=PACKAGE, guid="pkg-1")
    gcs.layout_overlay = overlay or {}
    return gcs


def test_gcs_variant_precedence_user_then_mandant_then_mode():
    pkg = dict(PACKAGE, Blue_Light={"color": {"primary-500": "#0000ff"}}, Green_Light={"color": {"primary-500": "#00ff00"}})
    gcs = _gcs(mandant_cfg={"THEME_LIGHT": "Green_Light"})
    gcs.layout.data = pkg
    assert gcs.resolve_active_theme("light")["theme_variant"] == "Green_Light"

    gcs.systemsteuerung.data["u1"]["THEME_VARIANT_LIGHT"] = "Blue_Light"
    assert gcs.resolve_active_theme("light")["blocks"]["color"]["primary-500"] == "#0000ff"

    assert _gcs().resolve_active_theme("light")["theme_variant"] == "light"


def test_gcs_mode_precedence_user_then_mandant_default_then_light():
    assert _gcs().get_user_theme_mode() == "light"
    assert _gcs(mandant_cfg={"THEME_DEFAULT_MODE": "dark"}).get_user_theme_mode() == "dark"
    assert _gcs(user_data={"THEME_MODE": "light"}, mandant_cfg={"THEME_DEFAULT_MODE": "dark"}).get_user_theme_mode() == "light"
    assert _gcs(mandant_cfg={"THEME_DEFAULT_MODE": "dark"}).resolve_active_theme()["mode"] == "dark"


def test_gcs_user_overrides_need_mandant_release():
    overrides = {"light": {"color": {"primary-500": "#abcdef"}}}
    gcs = _gcs(user_data={"THEME_OVERRIDES": overrides})
    assert gcs.resolve_active_theme("light")["blocks"]["color"]["primary-500"] == "#ff9800"

    gcs = _gcs(user_data={"THEME_OVERRIDES": overrides}, mandant_cfg={"USER_THEME_EDIT": ["color.primary-*"]})
    assert gcs.resolve_active_theme("light")["blocks"]["color"]["primary-500"] == "#abcdef"


def test_layout_router_resolved_catalog_and_mode_validation():
    from fastapi.testclient import TestClient
    from app.api.gcs import get_gcs_instance
    from app.core.security import get_current_user
    from app.main import app

    app.dependency_overrides[get_gcs_instance] = lambda: _gcs(mandant_cfg={"THEME_DEFAULT_MODE": "dark"})
    app.dependency_overrides[get_current_user] = lambda: {"sub": "u1"}
    try:
        client = TestClient(app)
        resolved = client.get("/api/layout/resolved")
        assert resolved.status_code == 200
        body = resolved.json()
        assert body["mode"] == "dark" and body["theme_package_id"] == "pkg-1"
        assert client.get("/api/layout/resolved", params={"mode": "light"}).json()["mode"] == "light"
        assert client.get("/api/layout/resolved", params={"mode": "neon"}).status_code == 400
        assert client.get("/api/layout/catalog").json()["groups"]["color"]["tokens"]["primary-500"]["type"] == "color"
        assert client.get("/api/layout/preferences/theme").json() == {"theme_mode": "dark"}
        assert client.get("/api/layout/active").status_code == 404
    finally:
        app.dependency_overrides.clear()

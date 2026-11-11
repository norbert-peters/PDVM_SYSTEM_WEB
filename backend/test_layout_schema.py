"""Tests fuer den Strukturkatalog (Layout-Varianten, P5)."""
import pytest

from app.core import layout_schema as ls
from app.core import theme_service as ts
from test_theme_editor import make_gcs, run


def test_catalog_has_labelled_options_and_standard_default():
    catalog = ls.get_layout_catalog()
    assert set(catalog) == {"header", "shell", "dichte", "form", "tabelle"}
    for area, data in catalog.items():
        values = [o["value"] for o in data["options"]]
        assert data["label"] and data["default"] == "standard" and values[0] == "standard", area
        assert all(o["label"] and o["description"] for o in data["options"]), area


def test_validate_choice_map_and_allowed_map():
    clean, errors = ls.validate_choice_map({"header": "kompakt", "shell": "", "form": "gibtsnicht", "x": "y"}, layer="Mandant")
    assert clean == {"header": "kompakt"} and len(errors) == 2
    assert ls.validate_choice_map(None, layer="Mandant") == ({}, [])
    assert ls.validate_choice_map("x", layer="Mandant")[1]

    clean, errors = ls.validate_allowed_map({"form": ["flach", "flach", "label-links"], "tabelle": [], "foo": ["a"], "dichte": ["nope"]})
    assert clean == {"form": ["flach", "label-links"]} and len(errors) == 2
    assert ls.validate_allowed_map({"form": "flach"})[1]


def test_resolve_layout_precedence_and_release():
    default = {"header": "kompakt", "shell": "nope"}
    allowed = {"form": ["flach"], "header": ["standard"]}

    layout, warnings = ls.resolve_layout(default_map=default, allowed_map=allowed)
    assert layout["header"] == "kompakt" and layout["shell"] == "standard" and not warnings

    layout, warnings = ls.resolve_layout(
        default_map=default, allowed_map=allowed,
        user_choice={"form": "flach", "header": "standard", "tabelle": "zebra", "dichte": "kompakt", "shell": "xx", "x": "y"},
    )
    assert layout["form"] == "flach" and layout["header"] == "standard"  # freigegeben
    assert layout["tabelle"] == "standard" and layout["dichte"] == "standard"  # nicht freigegeben
    assert len(warnings) == 4  # tabelle, dichte (nicht freigegeben), shell und Bereich 'x' (unbekannt)

    # Mandanten-Vorgabe ist immer waehlbar
    assert "kompakt" in ls.available_options("header", default, allowed)
    assert ls.available_options("tabelle", None, None) == ["standard"]


def test_gcs_resolved_theme_contains_layout():
    gcs = make_gcs(
        user_data={"LAYOUT_CHOICE": {"form": "flach", "tabelle": "zebra"}},
        mandant_cfg={"LAYOUT_DEFAULT": {"header": "kompakt"}, "LAYOUT_ALLOWED": {"form": ["flach"]}},
    )
    result = gcs.resolve_active_theme("light")
    assert result["layout"] == {"header": "kompakt", "shell": "standard", "dichte": "standard", "form": "flach", "tabelle": "standard"}
    assert any("tabelle" in w for w in result["layout_warnings"])
    assert make_gcs().resolve_active_theme("dark")["layout"]["header"] == "standard"


def test_editor_state_layout_availability_per_scope():
    gcs = make_gcs(
        user_data={"LAYOUT_CHOICE": {"form": "flach"}},
        mandant_cfg={"LAYOUT_DEFAULT": {"header": "kompakt"}, "LAYOUT_ALLOWED": {"form": ["flach"]}},
    )
    mandant = gcs.get_theme_editor_state("mandant")
    assert mandant["layout"]["form"]["available"] == ["standard", "flach", "label-links"]
    assert mandant["settings"]["layout_default"] == {"header": "kompakt"}
    assert mandant["settings"]["layout_allowed"] == {"form": ["flach"]}

    user = gcs.get_theme_editor_state("user")
    assert user["layout"]["form"]["available"] == ["standard", "flach"]
    assert user["layout"]["header"]["available"] == ["kompakt"]  # nur die Mandanten-Vorgabe, nichts freigegeben
    assert user["layout"]["header"]["mandant_default"] == "kompakt"
    assert user["layout"]["tabelle"]["available"] == ["standard"]
    assert user["settings"]["layout_choice"] == {"form": "flach"}


def test_save_mandant_layout_config_validates(monkeypatch):
    from app.core import pdvm_central_systemsteuerung as gcs_module
    from test_theme_editor import FakeMandantDb

    calls = []

    async def fake_update(**kwargs):
        calls.append(kwargs)

    monkeypatch.setattr(gcs_module, "update_record_central", fake_update)
    monkeypatch.setattr(gcs_module, "PdvmDatabase", FakeMandantDb)
    FakeMandantDb.current = {"ROOT": {}, "CONFIG": {"THEME_GUID": "pkg-1"}}

    gcs = make_gcs()
    result = run(gcs.save_mandant_theme_config(
        {"layout_default": {"header": "kompakt", "form": ""}, "layout_allowed": {"form": ["flach", "label-links"]}}
    ))
    cfg = calls[0]["daten"]["CONFIG"]
    assert cfg["LAYOUT_DEFAULT"] == {"header": "kompakt"} and cfg["LAYOUT_ALLOWED"] == {"form": ["flach", "label-links"]}
    assert result["layout_default"] == {"header": "kompakt"}

    with pytest.raises(ts.ThemeValidationError) as err:
        run(gcs.save_mandant_theme_config({"layout_default": {"header": "riesig"}, "layout_allowed": {"nix": ["a"]}}))
    assert len(err.value.errors) == 2
    assert len(calls) == 1


def test_save_user_layout_choice_requires_release():
    gcs = make_gcs(mandant_cfg={"LAYOUT_DEFAULT": {"header": "kompakt"}, "LAYOUT_ALLOWED": {"form": ["flach"], "header": ["standard"]}})
    run(gcs.save_user_theme_settings({}, layout_choice={"form": "flach", "header": "standard", "tabelle": ""}))
    assert gcs.systemsteuerung.data["u1"]["LAYOUT_CHOICE"] == {"form": "flach", "header": "standard"}

    with pytest.raises(ts.ThemeValidationError) as err:
        run(gcs.save_user_theme_settings({}, layout_choice={"form": "label-links", "tabelle": "zebra", "dichte": "gibtsnicht"}))
    assert len(err.value.errors) == 3
    # ohne layout_choice bleibt die gespeicherte Wahl unveraendert
    run(gcs.save_user_theme_settings({}))
    assert gcs.systemsteuerung.data["u1"]["LAYOUT_CHOICE"] == {"form": "flach", "header": "standard"}

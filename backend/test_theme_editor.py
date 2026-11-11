"""Tests fuer den Theme-Editor (P4): Rolle 'overlay', strikte Pruefung, Editor-Zustand und Schreibwege."""
import asyncio
import uuid
from types import SimpleNamespace

import pytest

from app.core import security, theme_service as ts
from app.core import pdvm_central_systemsteuerung as gcs_module
from app.core.pdvm_central_systemsteuerung import PdvmCentralSystemsteuerung

MANDANT = uuid.UUID("e51a8688-2cca-4a16-855d-52a69677fb50")

PACKAGE = {
    "ROOT": {},
    "info": {"name": "Test"},
    "light": {
        "color": {"primary-500": "#ff9800", "text-primary": "#000000", "background-primary": "#ffffff"},
        "block_btn_primary": {"bg_color": "#ff9800", "text_color": "#ffffff"},
    },
    "dark": {"color": {"primary-500": "#ffb74d", "background-primary": "#121212", "text-primary": "#ffffff"}},
    "Blue_Light": {"color": {"primary-500": "#0000ff"}},
}


class FakeSystemsteuerung(SimpleNamespace):
    def set_value(self, gruppe, feld, wert, ab_zeit=None):
        self.data.setdefault(gruppe, {})[feld] = wert


class FakeLayoutDb:
    def __init__(self, row=None):
        self.row = row

    async def get_by_link_uid(self, link_uid):
        assert link_uid == MANDANT
        return self.row


def make_gcs(*, user_data=None, mandant_cfg=None, overlay=None, row=None):
    gcs = object.__new__(PdvmCentralSystemsteuerung)
    gcs.user_guid = "u1"
    gcs.mandant_guid = MANDANT
    gcs.stichtag = 2026313.0
    gcs.systemsteuerung = FakeSystemsteuerung(data={"u1": dict(user_data or {})})
    gcs.mandant = SimpleNamespace(data={"MANDANT": {"NAME": "Filiale"}, "CONFIG": dict(mandant_cfg or {})})
    gcs.layout = SimpleNamespace(data=PACKAGE, guid="pkg-1", db=FakeLayoutDb(row))
    gcs.layout_overlay = overlay or {}
    gcs.saved = 0

    async def save_all_values(*args, **kwargs):
        gcs.saved += 1

    gcs.save_all_values = save_all_values
    return gcs


def run(coro):
    return asyncio.run(coro)


# --- Rolle 'overlay' ---

def test_overlay_role_is_read_from_permissions_roles_and_independent_of_admin():
    with_role = {"user_data": {"PERMISSIONS": {"ROLES": ["admin", "overlay"]}}}
    admin_only = {"user_data": {"PERMISSIONS": {"ROLES": ["admin"]}}}
    csv_role = {"user_data": {"SECURITY": {"ROLES": "user, Overlay"}}}
    assert security.has_overlay_rights(with_role) is True
    assert security.has_overlay_rights(csv_role) is True
    assert security.has_overlay_rights(admin_only) is False
    assert security.has_overlay_rights({}) is False


# --- Pruefung ---

def test_user_edit_presets_only_cover_user_editable_tokens():
    presets = {p["value"] for p in ts.user_edit_presets()}
    assert {"color.primary-*", "color.secondary-*", "color.background-*", "color.border-*", "font.scale"} <= presets
    assert not any(v.startswith("color.text") or v.startswith("block_") for v in presets)


def test_validate_user_edit_patterns():
    clean, errors = ts.validate_user_edit_patterns(["color.primary-*", " color.primary-* ", "font.scale", "color.text-*", "nope.*"])
    assert clean == ["color.primary-*", "font.scale"] and len(errors) == 2
    assert ts.validate_user_edit_patterns(None) == ([], [])
    assert ts.validate_user_edit_patterns("x")[1]


def test_validate_overlay_payload_reports_every_error():
    clean, errors = ts.validate_overlay_payload(
        {"light": {"color": {"primary-500": "#123456", "primary-600": "bad;"}}, "neon": {}}, layer="Mandant"
    )
    assert clean == {"light": {"color": {"primary-500": "#123456"}}}
    assert len(errors) == 2
    assert ts.validate_overlay_payload("x", layer="Mandant")[1]
    assert ts.validate_overlay_payload(None, layer="Mandant") == ({}, [])


def test_list_variants_and_compose_base():
    assert ts.list_variants(PACKAGE) == {"light": ["light", "Blue_Light"], "dark": ["dark"]}
    name, base, _ = ts.compose_base(PACKAGE, mode="light", variant="Blue_Light", mandant_overlay={"light": {"color": {"primary-600": "#111111"}}})
    assert name == "Blue_Light" and base["color"]["primary-500"] == "#0000ff" and base["color"]["primary-600"] == "#111111"


# --- Editor-Zustand ---

def test_editor_state_for_mandant_and_user_scope():
    overlay = {"light": {"color": {"primary-500": "#222222"}}}
    gcs = make_gcs(
        user_data={"THEME_OVERRIDES": {"light": {"color": {"background-primary": "#eeeeee"}}}},
        mandant_cfg={"USER_THEME_EDIT": ["color.background-*"]},
        overlay=overlay,
    )
    mandant = gcs.get_theme_editor_state("mandant")
    assert mandant["modes"]["light"]["base"]["color"]["primary-500"] == "#ff9800"
    assert mandant["modes"]["light"]["overlay"] == overlay["light"]
    assert mandant["allowed_patterns"] is None and mandant["theme_package_id"] == "pkg-1"

    user = gcs.get_theme_editor_state("user")
    assert user["modes"]["light"]["base"]["color"]["primary-500"] == "#222222"  # inkl. Mandanten-Overlay
    assert user["modes"]["light"]["overlay"] == {"color": {"background-primary": "#eeeeee"}}
    assert user["allowed_patterns"] == ["color.background-*"]
    with pytest.raises(ValueError):
        gcs.get_theme_editor_state("system")


# --- Schreibwege ---

def test_save_mandant_overlay_creates_then_updates(monkeypatch):
    calls = []

    async def fake_create(**kwargs):
        calls.append(("create", kwargs))
        return {}

    async def fake_update(**kwargs):
        calls.append(("update", kwargs))
        return {}

    monkeypatch.setattr(gcs_module, "create_record_central", fake_create)
    monkeypatch.setattr(gcs_module, "update_record_central", fake_update)

    gcs = make_gcs()
    run(gcs.save_mandant_theme_overlay({"light": {"color": {"primary-500": "#123456"}}}))
    kind, kwargs = calls[0]
    assert kind == "create" and kwargs["table_name"] == "msy_layout" and kwargs["link_uid"] == MANDANT
    assert kwargs["daten"]["ROOT"]["LAYER"] == "OVERLAY" and kwargs["daten"]["ROOT"]["BASE_THEME_GUID"] == "pkg-1"
    assert kwargs["daten"]["light"] == {"color": {"primary-500": "#123456"}} and kwargs["daten"]["dark"] == {}
    assert gcs.layout_overlay["light"]["color"]["primary-500"] == "#123456"

    existing = {"ROOT": {"LAYER": "OVERLAY"}, "light": {}, "dark": {}}
    gcs = make_gcs(row={"uid": uuid.uuid4(), "daten": existing})
    run(gcs.save_mandant_theme_overlay({"dark": {"color": {"primary-500": "#654321"}}}))
    kind, kwargs = calls[1]
    assert kind == "update" and kwargs["expected_snapshot_daten"] == existing

    # Paketkopien (ohne LAYER) duerfen nie ueberschrieben werden
    gcs = make_gcs(row={"uid": uuid.uuid4(), "daten": {"ROOT": {}, "light": {}}})
    run(gcs.save_mandant_theme_overlay({}))
    assert calls[2][0] == "create"


# --- Mehrere Theme-Pakete je Mandant ---

PKG2 = str(uuid.UUID("22222222-2222-4222-8222-222222222222"))
PACKAGE_BLUE = {
    "ROOT": {},
    "info": {"name": "Blau"},
    "light": {"color": {"primary-500": "#0000ff", "text-primary": "#ffffff", "background-primary": "#000040"}},
    "dark": {"color": {"primary-500": "#8080ff"}},
    "Ocean_Light": {"color": {"primary-500": "#0077aa"}},
}


def make_multi_gcs(**kwargs):
    gcs = make_gcs(**kwargs)
    gcs.layout_packages = {
        "pkg-1": {"name": "Orange", "data": PACKAGE},
        PKG2: {"name": "Blau", "data": PACKAGE_BLUE},
    }
    return gcs


def test_user_package_choice_resolves_selected_package_with_variant_fallback():
    gcs = make_multi_gcs(mandant_cfg={"THEME_LIGHT": "Blue_Light"})
    assert gcs.resolve_active_theme("light")["theme_package_id"] == "pkg-1"

    gcs.systemsteuerung.data["u1"]["THEME_CHOICE"] = PKG2
    theme = gcs.resolve_active_theme("light")
    # Blue_Light (Mandanten-Variante) gibt es im gewaehlten Paket nicht -> Modus-Name, ohne Warnung
    assert theme["theme_package_id"] == PKG2 and theme["theme_variant"] == "light" and not theme["warnings"]
    assert theme["blocks"]["color"]["primary-500"] == "#0000ff"

    gcs.systemsteuerung.data["u1"]["THEME_VARIANT_LIGHT"] = "Ocean_Light"
    assert gcs.resolve_active_theme("light")["blocks"]["color"]["primary-500"] == "#0077aa"

    gcs.systemsteuerung.data["u1"]["THEME_CHOICE"] = str(uuid.uuid4())  # nicht (mehr) freigegeben
    assert gcs.resolve_active_theme("light")["theme_package_id"] == "pkg-1"


def test_editor_state_lists_packages_and_previews_other_package():
    gcs = make_multi_gcs()
    user = gcs.get_theme_editor_state("user")
    assert [(p["guid"], p["name"], p["is_default"]) for p in user["packages"]] == [("pkg-1", "Orange", True), (PKG2, "Blau", False)]
    assert user["settings"]["theme_choice"] == "" and user["theme_package_id"] == "pkg-1"

    preview = gcs.get_theme_editor_state("user", PKG2)
    assert preview["theme_package_id"] == PKG2 and preview["variants"]["light"] == ["light", "Ocean_Light"]
    assert preview["modes"]["light"]["base"]["color"]["primary-500"] == "#0000ff"
    assert gcs.get_theme_editor_state("user", "unbekannt")["theme_package_id"] == "pkg-1"
    assert gcs.get_theme_editor_state("mandant", PKG2)["theme_package_id"] == "pkg-1"  # Mandant: immer Standard-Paket


def test_save_user_package_choice_only_from_released_packages():
    gcs = make_multi_gcs()
    run(gcs.save_user_theme_settings({}, "Ocean_Light", None, None, PKG2))
    stored = gcs.systemsteuerung.data["u1"]
    assert stored["THEME_CHOICE"] == PKG2 and stored["THEME_VARIANT_LIGHT"] == "Ocean_Light"

    with pytest.raises(ts.ThemeValidationError):
        run(gcs.save_user_theme_settings({}, None, None, None, str(uuid.uuid4())))
    with pytest.raises(ts.ThemeValidationError):  # Variante gehoert zum anderen Paket
        run(gcs.save_user_theme_settings({}, "Blue_Light", None, None, PKG2))

    run(gcs.save_user_theme_settings({}, "", None, None, ""))
    assert stored["THEME_CHOICE"] == "" and gcs.resolve_active_theme("light")["theme_package_id"] == "pkg-1"


def test_mandant_overlay_is_checked_against_every_released_package(monkeypatch):
    async def boom(**kwargs):
        raise AssertionError("darf nicht schreiben")

    monkeypatch.setattr(gcs_module, "create_record_central", boom)
    # Weisser Hintergrund passt zum Orange-Paket (schwarzer Text), nicht zum Blau-Paket (weisser Text)
    with pytest.raises(ts.ThemeValidationError) as err:
        run(make_multi_gcs().save_mandant_theme_overlay({"light": {"color": {"background-primary": "#ffffff"}}}))
    assert err.value.errors and all(e.startswith("[Blau] ") for e in err.value.errors)
    assert {c["package"] for c in err.value.contrast} == {PKG2}


def test_save_mandant_config_validates_released_packages(monkeypatch):
    calls = []

    async def fake_update(**kwargs):
        calls.append(kwargs)

    async def fake_fetch(guid):
        return {"name": "Blau", "data": PACKAGE_BLUE} if str(guid).lower() == PKG2 else None

    class FakeLayout(SimpleNamespace):
        def __init__(self, *args, **kwargs):
            super().__init__(data={}, guid=None, db=FakeLayoutDb())

        def set_data(self, data):
            self.data = data

        def set_guid(self, guid):
            self.guid = guid

    monkeypatch.setattr(gcs_module, "update_record_central", fake_update)
    monkeypatch.setattr(gcs_module, "PdvmDatabase", FakeMandantDb)
    monkeypatch.setattr(gcs_module, "PdvmCentralDatabase", FakeLayout)
    FakeMandantDb.current = {"ROOT": {}, "CONFIG": {"THEME_GUID": "pkg-1"}}
    gcs = make_gcs(mandant_cfg={"THEME_GUID": "pkg-1"})
    gcs._system_pool = gcs._mandant_pool = None
    gcs.fetch_theme_package = fake_fetch

    with pytest.raises(ts.ThemeValidationError) as err:
        run(gcs.save_mandant_theme_config({"theme_allowed": [PKG2, str(uuid.uuid4())]}))
    assert len(err.value.errors) == 1 and not calls

    result = run(gcs.save_mandant_theme_config({"theme_allowed": [PKG2.upper(), PKG2]}))
    assert result["theme_allowed"] == [PKG2] and calls[0]["daten"]["CONFIG"]["THEME_ALLOWED"] == [PKG2]
    assert [p["guid"] for p in gcs.get_theme_editor_state("user")["packages"]] == ["pkg-1", PKG2]

    # Standard-Paket wechseln: Varianten werden gegen das neue Paket geprueft
    run(gcs.save_mandant_theme_config({"theme_default": PKG2, "theme_light": "Ocean_Light"}))
    cfg = calls[1]["daten"]["CONFIG"]
    assert cfg["THEME_GUID"] == PKG2 and cfg["THEME_LIGHT"] == "Ocean_Light"
    assert gcs._default_package_guid() == PKG2
    with pytest.raises(ts.ThemeValidationError):
        run(gcs.save_mandant_theme_config({"theme_default": str(uuid.uuid4())}))


def test_save_mandant_overlay_rejects_invalid_values(monkeypatch):
    async def boom(**kwargs):
        raise AssertionError("darf nicht schreiben")

    monkeypatch.setattr(gcs_module, "create_record_central", boom)
    with pytest.raises(ts.ThemeValidationError) as err:
        run(make_gcs().save_mandant_theme_overlay({"light": {"color": {"primary-500": "url(x)"}}}))
    assert err.value.errors


class FakeMandantDb:
    """Ersetzt PdvmDatabase('asy_mandanten'): liefert den aktuellen DB-Stand (nicht die Session-Kopie)."""

    current = {}

    def __init__(self, table_name, *args, **kwargs):
        assert table_name == "asy_mandanten"

    async def get_by_uid(self, uid):
        assert uid == MANDANT
        return {"uid": uid, "daten": FakeMandantDb.current}


def test_save_mandant_config_validates_and_writes_cfg(monkeypatch):
    calls = []

    async def fake_update(**kwargs):
        calls.append(kwargs)

    monkeypatch.setattr(gcs_module, "update_record_central", fake_update)
    monkeypatch.setattr(gcs_module, "PdvmDatabase", FakeMandantDb)
    # DB-Stand weicht von der Session-Kopie ab (zweite Sitzung) und enthaelt ein SELF_GILT_BIS (Text-Spalte)
    FakeMandantDb.current = {
        "ROOT": {"SELF_GILT_BIS": "9999365.00000", "NAME": "M"},
        "CONTACT": {"TOWN": "Neu"},
        "CONFIG": {"THEME_GUID": "pkg-1", "FEATURES": ["x"]},
    }
    gcs = make_gcs(mandant_cfg={"THEME_GUID": "pkg-1"})
    result = run(gcs.save_mandant_theme_config(
        {"theme_light": "Blue_Light", "default_mode": "dark", "user_theme_edit": ["color.primary-*"]}
    ))
    assert result["theme_light"] == "Blue_Light" and result["default_mode"] == "dark"
    written = calls[0]["daten"]
    cfg = written["CONFIG"]
    assert cfg["THEME_LIGHT"] == "Blue_Light" and cfg["USER_THEME_EDIT"] == ["color.primary-*"]
    assert cfg["THEME_GUID"] == "pkg-1" and cfg["FEATURES"] == ["x"]  # fremde Schluessel bleiben erhalten
    assert written["CONTACT"] == {"TOWN": "Neu"}  # Aenderung der zweiten Sitzung geht nicht verloren
    assert "SELF_GILT_BIS" not in written["ROOT"] and written["ROOT"]["NAME"] == "M"
    assert calls[0]["expected_snapshot_daten"]["CONFIG"] == {"THEME_GUID": "pkg-1", "FEATURES": ["x"]}
    assert gcs.mandant.data["CONFIG"]["THEME_DEFAULT_MODE"] == "dark"

    with pytest.raises(ts.ThemeValidationError) as err:
        run(gcs.save_mandant_theme_config({"theme_dark": "Blue_Light", "default_mode": "neon", "user_theme_edit": ["color.text-*"]}))
    assert len(err.value.errors) == 3


def test_save_user_settings_requires_mandant_release():
    overlay = {"light": {"color": {"primary-500": "#abcdef", "text-primary": "#ff0000"}}}
    gcs = make_gcs(mandant_cfg={"USER_THEME_EDIT": ["color.primary-*"]})
    with pytest.raises(ts.ThemeValidationError):
        run(gcs.save_user_theme_settings(overlay))  # text-primary nie benutzeranpassbar
    assert gcs.saved == 0

    result = run(gcs.save_user_theme_settings({"light": {"color": {"primary-500": "#abcdef"}}}, "Blue_Light", None))
    assert result["overlay"] == {"light": {"color": {"primary-500": "#abcdef"}}}
    stored = gcs.systemsteuerung.data["u1"]
    assert stored["THEME_OVERRIDES"] == result["overlay"] and stored["THEME_VARIANT_LIGHT"] == "Blue_Light"
    assert "THEME_VARIANT_DARK" not in stored and gcs.saved == 1

    # ohne Freigabe des Mandanten ist keine Token-Aenderung moeglich, die Variantenwahl schon
    gcs = make_gcs()
    with pytest.raises(ts.ThemeValidationError):
        run(gcs.save_user_theme_settings({"light": {"color": {"primary-500": "#abcdef"}}}))
    run(gcs.save_user_theme_settings({}, "Blue_Light"))
    with pytest.raises(ts.ThemeValidationError):
        run(gcs.save_user_theme_settings({}, "Nope_Light"))


def test_save_user_settings_blocks_poor_contrast():
    gcs = make_gcs(mandant_cfg={"USER_THEME_EDIT": ["color.background-*"]})
    with pytest.raises(ts.ThemeValidationError) as exc:
        run(gcs.save_user_theme_settings({"light": {"color": {"background-primary": "#222222"}}}))
    assert exc.value.contrast and "Benutzer (Hell)" in exc.value.errors[0]
    assert gcs.saved == 0 and "THEME_OVERRIDES" not in gcs.systemsteuerung.data["u1"]
    run(gcs.save_user_theme_settings({"light": {"color": {"background-primary": "#f0f0f0"}}}))
    assert gcs.saved == 1


# --- Router ---

def _client(user_data, gcs):
    from fastapi.testclient import TestClient
    from app.api.gcs import get_gcs_instance
    from app.core.security import get_current_user
    from app.main import app

    app.dependency_overrides[get_gcs_instance] = lambda: gcs
    app.dependency_overrides[get_current_user] = lambda: {"sub": "u1", "user_data": user_data}
    return TestClient(app), app


def test_router_enforces_overlay_role_and_maps_errors(monkeypatch):
    async def fake_create(**kwargs):
        return {}

    monkeypatch.setattr(gcs_module, "create_record_central", fake_create)

    client, app = _client({"PERMISSIONS": {"ROLES": ["user"]}}, make_gcs())
    try:
        assert client.get("/api/layout/editor/mandant").status_code == 403
        assert client.put("/api/layout/overlay/mandant", json={"overlay": {}}).status_code == 403
        assert client.put("/api/layout/settings/mandant", json={"default_mode": "dark"}).status_code == 403
        body = client.get("/api/layout/editor/user").json()
        assert body["can_edit_overlay"] is False and body["scope"] == "user"
        assert client.get("/api/layout/editor/system").status_code == 404
        bad = client.put("/api/layout/settings/user", json={"overlay": {"light": {"color": {"primary-500": "#abcdef"}}}})
        assert bad.status_code == 422 and bad.json()["detail"]["errors"]
    finally:
        app.dependency_overrides.clear()

    client, app = _client({"PERMISSIONS": {"ROLES": ["overlay"]}}, make_gcs())
    try:
        assert client.get("/api/layout/editor/mandant").json()["can_edit_overlay"] is True
        ok = client.put("/api/layout/overlay/mandant", json={"overlay": {"light": {"color": {"primary-500": "#123456"}}}})
        assert ok.status_code == 200 and ok.json()["overlay"]["light"]["color"]["primary-500"] == "#123456"
        invalid = client.put("/api/layout/overlay/mandant", json={"overlay": {"light": {"color": {"primary-500": "red;"}}}})
        assert invalid.status_code == 422
        # schlechter Kontrast (weisser Text auf hellem Orange) wird nicht gespeichert; Antwort enthaelt Vorschlaege
        low = client.put("/api/layout/overlay/mandant", json={"overlay": {"light": {"block_btn_primary": {"bg_color": "#ffcc80"}}}})
        assert low.status_code == 422
        detail = low.json()["detail"]
        assert detail["errors"] and detail["contrast"]
        assert detail["contrast"][0]["mode"] == "light" and detail["contrast"][0]["suggestions"]
    finally:
        app.dependency_overrides.clear()

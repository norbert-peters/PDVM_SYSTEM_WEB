import asyncio

from app.core import view_state_service


def test_resolve_view_control_references_keeps_configs_from_control(monkeypatch):
    control_guid = "11111111-1111-1111-1111-111111111111"

    async def _fake_load_control_definition(*args, **kwargs):
        return {
            "daten": {
                "CONTROL": {
                    "GRUPPE": "PERSDATEN",
                    "FELD": "ANREDE",
                    "TYPE": "dropdown",
                    "LABEL": "Anrede",
                    "CONFIGS": {
                        "DROPDOWN": {
                            "TABLE": "sys_dropdowndaten",
                            "KEY": "22222222-2222-2222-2222-222222222222",
                            "FELD": "anrede",
                        }
                    },
                },
                "ROOT": {
                    "TABLE": "msy_persondaten",
                },
            }
        }

    monkeypatch.setattr(
        view_state_service.PdvmDatabase,
        "load_control_definition",
        _fake_load_control_definition,
    )

    origin = {
        control_guid: {
            "TABLE": "msy_persondaten",
        }
    }

    resolved = asyncio.run(
        view_state_service.resolve_view_control_references(
            origin,
            system_pool=None,
            mandant_pool=None,
        )
    )

    assert control_guid in resolved
    entry = resolved[control_guid]
    assert entry.get("type") == "dropdown"
    assert isinstance(entry.get("configs"), dict)
    assert "DROPDOWN" in entry["configs"]


def test_resolve_view_control_references_builds_configs_from_legacy_dropdown_fields(monkeypatch):
    control_guid = "33333333-3333-3333-3333-333333333333"

    async def _fake_load_control_definition(*args, **kwargs):
        return {
            "daten": {
                "CONTROL": {
                    "GRUPPE": "PERSDATEN",
                    "FELD": "ANREDE",
                    "TYPE": "dropdown",
                    "DROPDOWN": {
                        "table": "sys_dropdowndaten",
                        "key": "44444444-4444-4444-4444-444444444444",
                        "feld": "anrede",
                    },
                    "DROPDOWN_SOURCE": {
                        "type": "static",
                    },
                },
                "ROOT": {
                    "TABLE": "msy_persondaten",
                },
            }
        }

    monkeypatch.setattr(
        view_state_service.PdvmDatabase,
        "load_control_definition",
        _fake_load_control_definition,
    )

    origin = {
        control_guid: {
            "TABLE": "msy_persondaten",
        }
    }

    resolved = asyncio.run(
        view_state_service.resolve_view_control_references(
            origin,
            system_pool=None,
            mandant_pool=None,
        )
    )

    assert control_guid in resolved
    entry = resolved[control_guid]
    assert entry.get("type") == "dropdown"
    assert isinstance(entry.get("configs"), dict)
    assert isinstance(entry["configs"].get("dropdown"), dict)
    assert isinstance(entry["configs"].get("dropdown_source"), dict)


def test_resolve_view_control_references_overrides_empty_view_configs(monkeypatch):
    control_guid = "55555555-1111-1111-1111-111111111111"

    async def _fake_load_control_definition(*args, **kwargs):
        return {
            "daten": {
                "CONTROL": {
                    "GRUPPE": "USER",
                    "FELD": "ANREDE",
                    "TYPE": "dropdown",
                    "CONFIGS": {
                        "dropdown": {
                            "table": "sys_dropdowndaten",
                            "key": "2a60c785-0829-46db-a16b-9369596fab63",
                            "feld": "",
                            "gruppe": "",
                        }
                    },
                },
                "ROOT": {
                    "TABLE": "asy_benutzer",
                },
            }
        }

    monkeypatch.setattr(
        view_state_service.PdvmDatabase,
        "load_control_definition",
        _fake_load_control_definition,
    )

    origin = {
        control_guid: {
            "TABLE": "asy_benutzer",
            "configs": {},
        }
    }

    resolved = asyncio.run(
        view_state_service.resolve_view_control_references(
            origin,
            system_pool=None,
            mandant_pool=None,
        )
    )

    entry = resolved[control_guid]
    assert isinstance(entry.get("configs"), dict)
    assert isinstance(entry["configs"].get("dropdown"), dict)
    assert entry["configs"]["dropdown"].get("key") == "2a60c785-0829-46db-a16b-9369596fab63"


def test_resolve_view_control_references_backfills_partial_semantic_rows(monkeypatch):
    control_guid = "77777777-1111-1111-1111-111111111111"

    async def _fake_load_control_definition(*args, **kwargs):
        return {
            "daten": {
                "CONTROL": {
                    "GRUPPE": "USER",
                    "FELD": "ANREDE",
                    "TYPE": "dropdown",
                    "CONFIGS": {
                        "dropdown": {
                            "table": "sys_dropdowndaten",
                            "key": "2a60c785-0829-46db-a16b-9369596fab63",
                            "feld": "anrede",
                        }
                    },
                },
                "ROOT": {
                    "TABLE": "asy_benutzer",
                },
            }
        }

    monkeypatch.setattr(
        view_state_service.PdvmDatabase,
        "load_control_definition",
        _fake_load_control_definition,
    )

    # Altfall: View-Definition enthaelt bereits gruppe/feld, aber kein type/configs.
    origin = {
        control_guid: {
            "TABLE": "asy_benutzer",
            "gruppe": "USER",
            "feld": "ANREDE",
        }
    }

    resolved = asyncio.run(
        view_state_service.resolve_view_control_references(
            origin,
            system_pool=None,
            mandant_pool=None,
        )
    )

    entry = resolved[control_guid]
    assert entry.get("gruppe") == "USER"
    assert entry.get("feld") == "ANREDE"
    assert entry.get("type") == "dropdown"
    assert isinstance(entry.get("configs"), dict)
    assert isinstance(entry["configs"].get("dropdown"), dict)
    assert entry["configs"]["dropdown"].get("key") == "2a60c785-0829-46db-a16b-9369596fab63"


def test_resolve_view_control_references_overrides_stale_generic_type(monkeypatch):
    control_guid = "88888888-1111-1111-1111-111111111111"

    async def _fake_load_control_definition(*args, **kwargs):
        return {
            "daten": {
                "CONTROL": {
                    "GRUPPE": "USER",
                    "FELD": "ANREDE",
                    "TYPE": "dropdown",
                    "CONFIGS": {
                        "dropdown": {
                            "table": "sys_dropdowndaten",
                            "key": "2a60c785-0829-46db-a16b-9369596fab63",
                            "feld": "anrede",
                        }
                    },
                },
                "ROOT": {
                    "TABLE": "asy_benutzer",
                },
            }
        }

    monkeypatch.setattr(
        view_state_service.PdvmDatabase,
        "load_control_definition",
        _fake_load_control_definition,
    )

    # Altfall: View trägt bereits einen generischen Legacy-Typ.
    origin = {
        control_guid: {
            "TABLE": "asy_benutzer",
            "gruppe": "USER",
            "feld": "ANREDE",
            "type": "string",
            "configs": {"help": {}},
        }
    }

    resolved = asyncio.run(
        view_state_service.resolve_view_control_references(
            origin,
            system_pool=None,
            mandant_pool=None,
        )
    )

    entry = resolved[control_guid]
    assert entry.get("type") == "dropdown"
    assert isinstance(entry.get("configs"), dict)
    assert isinstance(entry["configs"].get("dropdown"), dict)
    assert entry["configs"]["dropdown"].get("key") == "2a60c785-0829-46db-a16b-9369596fab63"


def test_resolve_view_control_references_ignores_unknown_override_properties(monkeypatch):
    control_guid = "99999999-1111-1111-1111-111111111111"

    async def _fake_load_control_definition(*args, **kwargs):
        return {
            "daten": {
                "CONTROL": {
                    "GRUPPE": "USER",
                    "FELD": "ANREDE",
                    "TYPE": "dropdown",
                    "LABEL": "Anrede",
                },
                "ROOT": {
                    "TABLE": "asy_benutzer",
                },
            }
        }

    monkeypatch.setattr(
        view_state_service.PdvmDatabase,
        "load_control_definition",
        _fake_load_control_definition,
    )

    origin = {
        control_guid: {
            "TABLE": "asy_benutzer",
            "foo_custom": "bar",
        }
    }

    resolved = asyncio.run(
        view_state_service.resolve_view_control_references(
            origin,
            system_pool=None,
            mandant_pool=None,
        )
    )

    entry = resolved[control_guid]
    assert entry.get("gruppe") == "USER"
    assert entry.get("feld") == "ANREDE"
    assert entry.get("type") == "dropdown"
    assert "foo_custom" not in entry

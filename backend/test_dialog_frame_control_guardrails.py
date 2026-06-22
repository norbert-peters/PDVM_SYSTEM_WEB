import asyncio

from app.core import dialog_service


class _FakeGcs:
    _system_pool = None
    _mandant_pool = None


def test_resolve_frame_fields_uses_central_guardrail_merge(monkeypatch):
    control_guid = "aaaaaaaa-1111-1111-1111-111111111111"

    async def _fake_load_control_definition(*args, **kwargs):
        return {
            "daten": {
                "CONTROL": {
                    "GRUPPE": "USER",
                    "FELD": "ANREDE",
                    "TYPE": "dropdown",
                    "LABEL": "Anrede",
                    "CONFIGS": {
                        "dropdown": {
                            "table": "sys_dropdowndaten",
                            "key": "bbbbbbbb-2222-2222-2222-222222222222",
                            "feld": "anrede",
                        }
                    },
                },
                "ROOT": {"TABLE": "asy_benutzer"},
            }
        }

    monkeypatch.setattr(
        dialog_service.PdvmDatabase,
        "load_control_definition",
        _fake_load_control_definition,
    )

    daten = {
        "FIELDS": {
            control_guid: {
                "label": "Anrede (lokal)",
                "type": "string",
                "foo_custom": "bar",
            }
        }
    }

    resolved = asyncio.run(dialog_service._resolve_frame_fields(_FakeGcs(), daten))
    entry = resolved["FIELDS"][control_guid]

    assert entry.get("type") == "dropdown"
    assert entry.get("label") == "Anrede (lokal)"
    assert "foo_custom" not in entry


def test_resolve_frame_fields_keeps_tab_and_display_order_overrides(monkeypatch):
    control_guid = "dddddddd-1111-1111-1111-111111111111"

    async def _fake_load_control_definition(*args, **kwargs):
        return {
            "daten": {
                "CONTROL": {
                    "GRUPPE": "USER",
                    "FELD": "ANREDE",
                    "TYPE": "dropdown",
                    "LABEL": "Anrede",
                },
                "ROOT": {"TABLE": "asy_benutzer"},
            }
        }

    monkeypatch.setattr(
        dialog_service.PdvmDatabase,
        "load_control_definition",
        _fake_load_control_definition,
    )

    daten = {
        "FIELDS": {
            control_guid: {
                "TAB": 3,
                "DISPLAY_ORDER": 70,
                "foo_custom": "bar",
            }
        }
    }

    resolved = asyncio.run(dialog_service._resolve_frame_fields(_FakeGcs(), daten))
    entry = resolved["FIELDS"][control_guid]

    assert entry.get("tab") == 3
    assert entry.get("display_order") == 70
    assert "foo_custom" not in entry


def test_resolve_frame_fields_reads_templates_control_payload(monkeypatch):
    control_guid = "3addcaa2-e289-4cbc-9228-84ec87b01f42"

    async def _fake_load_control_definition(*args, **kwargs):
        return {
            "daten": {
                "ROOT": {
                    "SELF_GUID": control_guid,
                    "TABLE": "asy_benutzer",
                },
                "TEMPLATES": {
                    "CONTROL": {
                        "GRUPPE": "SETTINGS",
                        "FIELD": "MODE",
                        "TYPE": "string",
                        "LABEL": "Anwender Modus",
                        "TABLE": "asy_benutzer",
                    }
                },
            }
        }

    monkeypatch.setattr(
        dialog_service.PdvmDatabase,
        "load_control_definition",
        _fake_load_control_definition,
    )

    daten = {
        "FIELDS": {
            control_guid: {
                "TAB": 2,
                "DISPLAY_ORDER": 10,
            }
        }
    }

    resolved = asyncio.run(dialog_service._resolve_frame_fields(_FakeGcs(), daten))
    entry = resolved["FIELDS"][control_guid]

    assert entry.get("label") == "Anwender Modus"
    assert entry.get("type") == "string"
    assert entry.get("gruppe") == "SETTINGS"
    assert entry.get("feld") == "MODE"
    assert entry.get("tab") == 2
    assert entry.get("display_order") == 10


def test_normalize_frame_fields_for_storage_drops_unknown_override(monkeypatch):
    control_guid = "cccccccc-1111-1111-1111-111111111111"

    async def _fake_load_control_definition(*args, **kwargs):
        return {
            "daten": {
                "CONTROL": {
                    "GRUPPE": "USER",
                    "FELD": "ANREDE",
                    "TYPE": "dropdown",
                    "LABEL": "Anrede",
                },
                "ROOT": {"TABLE": "asy_benutzer"},
            }
        }

    monkeypatch.setattr(
        dialog_service.PdvmDatabase,
        "load_control_definition",
        _fake_load_control_definition,
    )

    daten = {
        "FIELDS": {
            control_guid: {
                "label": "Anrede (lokal)",
                "foo_custom": "bar",
            }
        }
    }

    normalized = asyncio.run(
        dialog_service._normalize_frame_fields_for_storage(_FakeGcs(), daten=daten)
    )
    stored_entry = normalized["FIELDS"][control_guid]

    assert stored_entry.get("label") == "Anrede (lokal)"
    assert "foo_custom" not in stored_entry


def test_normalize_frame_fields_for_storage_keeps_tab_and_display_order(monkeypatch):
    control_guid = "eeeeeeee-1111-1111-1111-111111111111"

    async def _fake_load_control_definition(*args, **kwargs):
        return {
            "daten": {
                "CONTROL": {
                    "GRUPPE": "USER",
                    "FELD": "ANREDE",
                    "TYPE": "dropdown",
                    "LABEL": "Anrede",
                },
                "ROOT": {"TABLE": "asy_benutzer"},
            }
        }

    monkeypatch.setattr(
        dialog_service.PdvmDatabase,
        "load_control_definition",
        _fake_load_control_definition,
    )

    daten = {
        "FIELDS": {
            control_guid: {
                "TAB": 2,
                "DISPLAY_ORDER": 40,
                "foo_custom": "bar",
            }
        }
    }

    normalized = asyncio.run(
        dialog_service._normalize_frame_fields_for_storage(_FakeGcs(), daten=daten)
    )
    stored_entry = normalized["FIELDS"][control_guid]

    assert stored_entry.get("tab") == 2
    assert stored_entry.get("display_order") == 40
    assert "foo_custom" not in stored_entry


def test_build_dialog_draft_sys_control_dict_normalizes_templates_to_control(monkeypatch):
    class _FakeGcsForDraft:
        _system_pool = None
        _mandant_pool = None

    template_uid = "66666666-6666-6666-6666-666666666666"

    async def _fake_load_template_row_and_daten(*args, **kwargs):
        return (
            {
                "uid": template_uid,
                "sec_id": None,
            },
            {
                "ROOT": {
                    "TABLE": "asy_benutzer",
                    "SELF_NAME": "template",
                },
                "TEMPLATES": {
                    "CONTROL": {
                        "GRUPPE": "SETTINGS",
                        "FIELD": "MODE",
                        "TYPE": "string",
                        "LABEL": "Anwender Modus",
                        "TABLE": "asy_benutzer",
                    }
                },
            },
        )

    async def _fake_load_control_base_template(*args, **kwargs):
        return {
            "ROOT": {
                "TABLE": "",
            },
            "CONTROL": {
                "TYPE": "string",
            },
        }

    monkeypatch.setattr(
        dialog_service,
        "_load_template_row_and_daten",
        _fake_load_template_row_and_daten,
    )
    monkeypatch.setattr(
        dialog_service,
        "_load_control_base_template",
        _fake_load_control_base_template,
    )

    built = asyncio.run(
        dialog_service.build_dialog_draft_from_template(
            _FakeGcsForDraft(),
            root_table="sys_control_dict",
            name="Neu",
            resolve_templates=False,
        )
    )

    daten = built.get("daten") or {}
    assert "ROOT" in daten
    assert "CONTROL" in daten
    assert "TEMPLATES" not in daten

    control = daten.get("CONTROL") or {}
    assert control.get("LABEL") == "Anwender Modus"
    assert control.get("FIELD") == "MODE"


def test_build_dialog_draft_normalizes_control_table_independent(monkeypatch):
    class _FakeGcsForDraft:
        _system_pool = None
        _mandant_pool = None

    async def _fake_load_template_row_and_daten(*args, **kwargs):
        return (
            {
                "uid": "66666666-6666-6666-6666-666666666666",
                "sec_id": None,
            },
            {
                "ROOT": {
                    "TABLE": "any_business_table",
                },
                "TEMPLATES": {
                    "CONTROL": {
                        "GRUPPE": "SETTINGS",
                        "FIELD": "MODE",
                        "TYPE": "string",
                        "LABEL": "Anwender Modus",
                    }
                },
            },
        )

    async def _fake_load_control_base_template(*args, **kwargs):
        return {
            "ROOT": {"TABLE": ""},
            "CONTROL": {"TYPE": "string"},
        }

    monkeypatch.setattr(
        dialog_service,
        "_load_template_row_and_daten",
        _fake_load_template_row_and_daten,
    )
    monkeypatch.setattr(
        dialog_service,
        "_load_control_base_template",
        _fake_load_control_base_template,
    )

    built = asyncio.run(
        dialog_service.build_dialog_draft_from_template(
            _FakeGcsForDraft(),
            root_table="dev_any_table",
            name="Neu",
            resolve_templates=False,
        )
    )

    daten = built.get("daten") or {}
    assert "ROOT" in daten
    assert "CONTROL" in daten
    assert "TEMPLATES" not in daten
    assert (daten.get("CONTROL") or {}).get("FIELD") == "MODE"


def test_build_dialog_draft_strips_template_groups_for_generic_table(monkeypatch):
    class _FakeGcsForDraft:
        _system_pool = None
        _mandant_pool = None

    async def _fake_load_template_row_and_daten(*args, **kwargs):
        return (
            {
                "uid": "66666666-6666-6666-6666-666666666666",
                "sec_id": None,
            },
            {
                "ROOT": {
                    "TABLE": "dev_any_table",
                },
                "CONFIG": {
                    "X": 1,
                },
                "TEMPLATES": {
                    "CONFIG": {
                        "X": 0,
                    }
                },
                "ELEMENTS": {
                    "GROUP_LISTS": {},
                },
            },
        )

    async def _fake_load_control_base_template(*args, **kwargs):
        return {
            "ROOT": {"TABLE": ""},
            "CONTROL": {"TYPE": "string"},
        }

    monkeypatch.setattr(
        dialog_service,
        "_load_template_row_and_daten",
        _fake_load_template_row_and_daten,
    )
    monkeypatch.setattr(
        dialog_service,
        "_load_control_base_template",
        _fake_load_control_base_template,
    )

    built = asyncio.run(
        dialog_service.build_dialog_draft_from_template(
            _FakeGcsForDraft(),
            root_table="dev_any_table",
            name="Neu",
            resolve_templates=False,
        )
    )

    daten = built.get("daten") or {}
    assert "CONFIG" in daten
    assert "TEMPLATES" not in daten
    assert "ELEMENTS" not in daten

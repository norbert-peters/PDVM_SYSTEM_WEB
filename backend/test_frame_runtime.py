import asyncio
import uuid

import pytest

from app.core import credential_store, email_service, frame_runtime_service as frames
from app.core.mandant_record_rules import flatten_mandant_template, validate_new_mandant
from app.core.pdvm_datenbank import PdvmDatabase


def _field(label, tab, order, feld="X"):
    return {"type": "string", "label": label, "gruppe": "ROOT", "feld": feld, "tab": tab, "display_order": order}


def test_runtime_payload_orders_fields_and_builds_tabs():
    daten = {
        "ROOT": {
            "EDIT_TYPE": "pdvm_edit",
            "TAB_ELEMENTS": {"a": {"TAB": 2, "HEAD": "Zwei"}},
        },
        "FIELDS": {
            str(uuid.uuid4()): _field("B", 2, 10),
            str(uuid.uuid4()): _field("A", 1, 20),
            str(uuid.uuid4()): _field("C", 1, 10),
            "ohne-control": {"tab": 1, "display_order": 30},
        },
    }
    payload = frames.build_runtime_payload("u", "Frame", daten)
    assert [f["label"] for f in payload["fields"]][:3] == ["C", "A", "ohne-control"]
    assert payload["tabs"] == [{"index": 1, "head": "Tab 1"}, {"index": 2, "head": "Zwei"}]
    broken = [f for f in payload["fields"] if f["resolution_warning"]]
    assert [f["key"] for f in broken] == ["ohne-control"]


def test_load_frame_runtime_is_cached_until_frame_or_control_is_written(monkeypatch):
    frames.invalidate_frame_runtime_cache()
    loads = []
    pool = object()

    async def fake_get_by_uid(self, uid, **kwargs):
        loads.append(uid)
        return {"uid": uid, "name": "F", "daten": {"ROOT": {}, "FIELDS": {}}}

    async def fake_resolve(scope, daten, visited=None):
        return daten

    monkeypatch.setattr(PdvmDatabase, "get_by_uid", fake_get_by_uid)
    monkeypatch.setattr(frames, "_resolve_frame_fields", fake_resolve)
    scope = frames.PoolScope(pool)
    frame_uid = uuid.uuid4()

    asyncio.run(frames.load_frame_runtime(scope, frame_uid))
    asyncio.run(frames.load_frame_runtime(scope, frame_uid))
    assert len(loads) == 1

    PdvmDatabase("sys_control_dict", system_pool=pool)._invalidate_caches_after_write()
    asyncio.run(frames.load_frame_runtime(scope, frame_uid))
    assert len(loads) == 2


def test_mandant_template_is_flattened_without_secrets():
    template = {
        "ROOT": {
            "NAME": None, "TABLE": "sys_mandanten", "SELF_NAME": "TEMPLATE_666", "IDLE_TIMEOUT": 1200,
            "SELF_GUID": "6666", "SELF_LINK_UID": "6666", "DB_CREATED_AT": "2025363.62838",
        },
        "TEMPLATES": {
            "MANDANT": {"DATABASE": "", "PASSWORD": "geheim"},
            "SEND_EMAIL": {"SMTP_PASS": "geheim", "SMTP_HOST": "h"},
            "TABLE_INFO": {"version": "2.0"},
        },
    }
    flat = flatten_mandant_template(template)
    assert flat["ROOT"] == {"NAME": None, "IDLE_TIMEOUT": 1200}
    assert flat["MANDANT"] == {"DATABASE": ""}
    assert flat["SEND_EMAIL"] == {"SMTP_HOST": "h"}
    assert "TABLE_INFO" not in flat


def test_new_mandant_validation_reports_missing_values_and_secrets():
    errors = validate_new_mandant({"ROOT": {"NAME": " "}, "MANDANT": {"DATABASE": "-eingeben-", "PASSWORD": "x"}})
    assert {(e["group"], e["field"]) for e in errors} == {
        ("ROOT", "NAME"),
        ("MANDANT", "DATABASE"),
        ("MANDANT", "PASSWORD"),
    }
    assert validate_new_mandant({"ROOT": {"NAME": "A"}, "MANDANT": {"DATABASE": "db", "PASSWORD": ""}}) == []


def test_smtp_password_comes_from_credential_store(monkeypatch):
    monkeypatch.setattr(
        email_service,
        "get_credential",
        lambda name: credential_store.Credential(user="mailer", password="aus-store") if name == "smtp" else None,
    )
    cfg = email_service.build_smtp_config({"CREDENTIAL": "smtp", "SMTP_PASS": "alt"})
    assert (cfg["smtp_user"], cfg["smtp_pass"]) == ("mailer", "aus-store")
    legacy = email_service.build_smtp_config({"SMTP_USER": "u", "SMTP_PASS": "alt"})
    assert (legacy["smtp_user"], legacy["smtp_pass"]) == ("u", "alt")
    with pytest.raises(ValueError):
        email_service.build_smtp_config({"CREDENTIAL": "fehlt"})

def test_dropdown_fields_get_options_from_sys_dropdowndaten_and_dropdown_writes_clear_the_cache(monkeypatch):
    frames.invalidate_frame_runtime_cache()
    dropdown_uid = str(uuid.uuid4())
    loads = []

    async def fake_get_by_uid(self, uid, **kwargs):
        loads.append((self.table_name, str(uid)))
        if self.table_name == "sys_dropdowndaten":
            return {"uid": uid, "name": "Sprachen", "daten": {
                "ROOT": {"FIELD_KEY": "sprache", "DEFAULT_LANGUAGE": "DE-DE"},
                "OPTIONS": {"DE-DE": {"DE-DE": "Deutsch", "EN-US": "German"}, "EN-US": {"DE-DE": "Englisch", "EN-US": "English"}},
            }}
        field = {"type": "dropdown", "label": "Sprache", "gruppe": "CONFIG", "feld": "DEFAULT_LANGUAGE", "tab": 1,
                 "display_order": 10, "configs": {"dropdown": {"key": dropdown_uid, "table": "sys_dropdowndaten"}}}
        no_source = {"type": "dropdown", "label": "Ohne", "gruppe": "CONFIG", "feld": "X", "tab": 1, "display_order": 20}
        return {"uid": uid, "name": "F", "daten": {"ROOT": {}, "FIELDS": {str(uuid.uuid4()): field, str(uuid.uuid4()): no_source}}}

    async def fake_resolve(scope, daten, visited=None):
        return daten

    monkeypatch.setattr(PdvmDatabase, "get_by_uid", fake_get_by_uid)
    monkeypatch.setattr(frames, "_resolve_frame_fields", fake_resolve)
    pool = object()
    scope = frames.PoolScope(pool)
    frame_uid = uuid.uuid4()

    de = asyncio.run(frames.load_frame_runtime(scope, frame_uid))
    with_source, without_source = de["fields"]
    assert with_source["options"] == [{"value": "DE-DE", "label": "Deutsch"}, {"value": "EN-US", "label": "Englisch"}]
    assert "CONFIGS.dropdown.key" in without_source["resolution_warning"]
    en = asyncio.run(frames.load_frame_runtime(scope, frame_uid, "en"))
    assert [o["label"] for o in en["fields"][0]["options"]] == ["German", "English"]

    count = len(loads)
    asyncio.run(frames.load_frame_runtime(scope, frame_uid))
    assert len(loads) == count  # aus dem Cache
    PdvmDatabase("sys_dropdowndaten", system_pool=pool)._invalidate_caches_after_write()
    asyncio.run(frames.load_frame_runtime(scope, frame_uid))
    assert len(loads) > count

def test_language_dropdown_can_show_each_option_in_its_own_language(monkeypatch):
    frames.invalidate_frame_runtime_cache()
    dropdown_uid = str(uuid.uuid4())

    async def fake_get_by_uid(self, uid, **kwargs):
        if self.table_name == "sys_dropdowndaten":
            return {"uid": uid, "name": "Sprachen", "daten": {
                "ROOT": {"FIELD_KEY": "sprache", "DEFAULT_LANGUAGE": "DE-DE"},
                "OPTIONS": {
                    "DE-DE": {"DE-DE": "Deutsch", "EN-US": "German"},
                    "EN-US": {"DE-DE": "Englisch", "EN-US": "English"},
                    "IT-IT": {"DE-DE": "Italienisch", "EN-US": "Italian"},  # ohne Eigenbezeichnung
                },
            }}
        cfg = {"key": dropdown_uid, "table": "sys_dropdowndaten", "label_language": "own"}
        field = {"type": "dropdown", "label": "Sprache", "gruppe": "CONFIG", "feld": "L", "tab": 1, "display_order": 10,
                 "configs": {"dropdown": cfg}}
        return {"uid": uid, "name": "F", "daten": {"ROOT": {}, "FIELDS": {str(uuid.uuid4()): field}}}

    async def fake_resolve(scope, daten, visited=None):
        return daten

    monkeypatch.setattr(PdvmDatabase, "get_by_uid", fake_get_by_uid)
    monkeypatch.setattr(frames, "_resolve_frame_fields", fake_resolve)
    scope = frames.PoolScope(object())
    for ui_language in ("DE-DE", "EN-US"):
        options = asyncio.run(frames.load_frame_runtime(scope, uuid.uuid4(), ui_language))["fields"][0]["options"]
        labels = [o["label"] for o in options]
        assert labels[:2] == ["Deutsch", "English"]  # unabhaengig von der Oberflaechensprache
        assert labels[2] == ("Italienisch" if ui_language == "DE-DE" else "Italian")  # Rueckfall auf die Oberflaechensprache

def test_action_and_info_controls_must_reference_registered_actions():
    def field(type_, configs):
        return {"type": type_, "configs": configs, "resolution_warning": None}

    payload = {"fields": [
        field("action", {"action": {"id": "user.lock"}}),
        field("action", {"action": {"id": "gibt.es.nicht"}}),
        field("action", {}),
        field("info", {"info": {"state": {"action": "texttemplate.adopt_source"}}}),
        field("info", {"info": {"state": {"action": "gibt.es.nicht"}}}),
        field("info", {"info": {"value_path": "SECURITY.ACCOUNT_LOCKED"}}),
    ]}
    frames._check_action_fields(payload)
    warnings = [f["resolution_warning"] for f in payload["fields"]]
    assert warnings[0] is None and warnings[3] is None and warnings[5] is None
    assert "gibt.es.nicht" in warnings[1] and "CONFIGS.action.id" in warnings[2] and "gibt.es.nicht" in warnings[4]

def test_password_input_is_only_allowed_in_public_form_frames():
    def payload(frame_type):
        return {"root": {"FRAME_TYPE": frame_type}, "fields": [
            {"type": "password_input", "configs": {}, "resolution_warning": None},
            {"type": "string", "configs": {}, "resolution_warning": None},
        ]}

    ok = payload("public_form")
    frames._check_password_input_fields(ok)
    assert [f["resolution_warning"] for f in ok["fields"]] == [None, None]

    for frame_type in (None, "norm", ""):
        bad = payload(frame_type)
        frames._check_password_input_fields(bad)
        assert "public_form" in bad["fields"][0]["resolution_warning"] and bad["fields"][1]["resolution_warning"] is None

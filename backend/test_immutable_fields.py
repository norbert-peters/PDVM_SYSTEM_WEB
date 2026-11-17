import asyncio
import uuid

import pytest

from app.core import frame_runtime_service as frames
from app.core import immutable_fields_service as immutable
from app.core.control_runtime_service import _normalize_runtime_control_from_row
from app.core.mandant_record_rules import IMMUTABLE_MANDANT_FIELDS
from app.core.pdvm_datenbank import PdvmDatabase

FIELDS = [("MANDANT", "DATABASE"), ("MANDANT", "PORT")]


def test_changing_a_set_immutable_field_is_a_violation():
    old = {"MANDANT": {"DATABASE": "db1", "PORT": 5432}}
    assert immutable.find_immutable_violations(old, {"MANDANT": {"DATABASE": "db2", "PORT": "5432"}}, FIELDS) == [
        {"group": "MANDANT", "field": "DATABASE"}
    ]
    # gleicher Wert (auch als Text) und fehlende Eingabe in anderen Feldern sind keine Aenderung
    assert immutable.find_immutable_violations(old, {"MANDANT": {"DATABASE": "db1", "PORT": "5432"}}, FIELDS) == []


def test_removing_an_immutable_value_is_a_violation_but_setting_an_empty_one_is_allowed():
    old = {"MANDANT": {"DATABASE": "db1", "PORT": ""}}
    assert immutable.find_immutable_violations(old, {"MANDANT": {"PORT": 5432}}, FIELDS) == [
        {"group": "MANDANT", "field": "DATABASE"}
    ]
    assert immutable.find_immutable_violations(old, {"MANDANT": {"DATABASE": "db1", "PORT": 5432}}, FIELDS) == []


def test_enforce_reads_current_row_and_raises(monkeypatch):
    async def fake_fields(table_name, *, system_pool):
        return FIELDS if table_name == "asy_mandanten" else []

    async def fake_get(self, uid, **kwargs):
        return {"daten": {"MANDANT": {"DATABASE": "db1"}}}

    monkeypatch.setattr(PdvmDatabase, "load_immutable_control_fields", staticmethod(fake_fields))
    monkeypatch.setattr(PdvmDatabase, "get_by_uid", fake_get)
    uid = uuid.uuid4()

    def run(table, daten):
        return asyncio.run(
            immutable.enforce_immutable_fields(
                table_name=table, uid=uid, new_daten=daten, system_pool=object(), mandant_pool=None
            )
        )

    run("asy_mandanten", {"MANDANT": {"DATABASE": "db1"}})
    run("andere_tabelle", {"MANDANT": {"DATABASE": "egal"}})
    with pytest.raises(immutable.ImmutableFieldError) as err:
        run("asy_mandanten", {"MANDANT": {"DATABASE": "db2"}})
    assert "MANDANT.DATABASE" in str(err.value)


def test_immutable_flows_from_control_into_runtime_field():
    row = {"daten": {"CONTROL": {"FIELD": "DATABASE", "TYPE": "string", "GRUPPE": "MANDANT", "IMMUTABLE": True}}}
    runtime = _normalize_runtime_control_from_row(row)
    assert runtime["immutable"] is True
    field = frames._build_field("k", {**runtime, "tab": 1})
    assert field["immutable"] is True and frames._build_field("k", {"feld": "X", "type": "string"})["immutable"] is False


def test_conditional_lock_stays_open_until_the_condition_field_has_a_value():
    fields = [("MANDANT", "HOST", "ROOT.DB_CREATED_AT")]
    changed = {"MANDANT": {"HOST": "korrekt"}}
    for open_state in ({"ROOT": {}}, {"ROOT": {"DB_CREATED_AT": ""}}, {"ROOT": {"DB_CREATED_AT": "-eingeben-"}}, {}):
        old = {**open_state, "MANDANT": {"HOST": "tippfehler"}}
        assert immutable.find_immutable_violations(old, changed, fields) == []
    locked = {"ROOT": {"DB_CREATED_AT": "2026320.5"}, "MANDANT": {"HOST": "tippfehler"}}
    assert immutable.find_immutable_violations(locked, changed, fields) == [{"group": "MANDANT", "field": "HOST"}]


def test_immutable_after_flows_from_control_into_runtime_field():
    row = {"daten": {"CONTROL": {"FIELD": "HOST", "TYPE": "string", "GRUPPE": "MANDANT", "IMMUTABLE": True,
                                 "IMMUTABLE_AFTER": "ROOT.DB_CREATED_AT"}}}
    runtime = _normalize_runtime_control_from_row(row)
    assert runtime["immutable_after"] == "ROOT.DB_CREATED_AT"
    assert frames._build_field("k", {**runtime, "tab": 1})["immutable_after"] == "ROOT.DB_CREATED_AT"
    assert frames._build_field("k", {"feld": "X", "type": "string"})["immutable_after"] is None


def test_mandant_immutable_fields_are_the_agreed_connection_fields():
    assert set(IMMUTABLE_MANDANT_FIELDS) == {
        ("MANDANT", f) for f in ("DATABASE", "HOST", "PORT", "SYSTEM_DB", "SYSTEM_HOST", "SYSTEM_PORT")
    }

import asyncio
import uuid

import pytest

from app.core import mandant_db_maintenance as maint
from app.core.pdvm_datenbank import PdvmDatabase


class _Row(dict):
    pass


class _FakeConn:
    def __init__(self, rows):
        self.rows = rows
        self.fetch_calls = 0

    async def fetch(self, query, *args):
        self.fetch_calls += 1
        wanted = {str(u) for u in args[0]}
        return [r for r in self.rows if str(r["uid"]) in wanted]


class _FakePool:
    def __init__(self, rows):
        self.conn = _FakeConn(rows)

    def acquire(self):
        pool = self

        class _Ctx:
            async def __aenter__(self_inner):
                return pool.conn

            async def __aexit__(self_inner, *exc):
                return False

        return _Ctx()


def _control_row(uid, field):
    return _Row(
        uid=uid,
        link_uid=uid,
        daten={"ROOT": {"SELF_GUID": str(uid)}, "CONTROL": {"FIELD": field}},
        name=field,
        historisch=0,
        sec_id=None,
        gilt_bis=None,
        created_at=None,
        modified_at=None,
    )


def test_load_control_definitions_uses_one_query_for_many_controls(monkeypatch):
    PdvmDatabase.invalidate_template_cache()
    uids = [uuid.uuid4() for _ in range(5)]
    pool = _FakePool([_control_row(u, f"F{i}") for i, u in enumerate(uids)])
    template_loads = []

    async def _fake_base(*, system_pool, mandant_pool):
        template_loads.append(1)
        return {"ROOT": {}, "CONTROL": {"TYPE": "string"}}

    monkeypatch.setattr(PdvmDatabase, "_load_control_base_template", staticmethod(_fake_base))

    result = asyncio.run(
        PdvmDatabase.load_control_definitions(uids + [uids[0]], system_pool=pool, mandant_pool=None)
    )

    assert pool.conn.fetch_calls == 1
    assert set(result) == set(uids)
    assert result[uids[2]]["daten"]["CONTROL"]["FIELD"] == "F2"
    assert result[uids[2]]["daten"]["CONTROL"]["TYPE"] == "string"  # Template ergaenzt


def test_load_control_definitions_empty_input_makes_no_query():
    pool = _FakePool([])
    assert asyncio.run(PdvmDatabase.load_control_definitions([], system_pool=pool, mandant_pool=None)) == {}
    assert pool.conn.fetch_calls == 0


def test_template_cache_serves_copies_and_is_invalidated_by_control_dict_write():
    PdvmDatabase.invalidate_template_cache()
    pool = _FakePool([])
    db = PdvmDatabase("sys_control_dict", system_pool=pool, mandant_pool=None)

    assert PdvmDatabase._template_cache_get(db, ("base",)) is None
    PdvmDatabase._template_cache_put(db, ("base",), {"CONTROL": {"TYPE": "string"}})
    first = PdvmDatabase._template_cache_get(db, ("base",))
    first["CONTROL"]["TYPE"] = "mutated"
    assert PdvmDatabase._template_cache_get(db, ("base",))["CONTROL"]["TYPE"] == "string"

    db._invalidate_caches_after_write()
    assert PdvmDatabase._template_cache_get(db, ("base",)) is None


def test_template_cache_not_invalidated_by_other_tables():
    PdvmDatabase.invalidate_template_cache()
    pool = _FakePool([])
    ctrl = PdvmDatabase("sys_control_dict", system_pool=pool, mandant_pool=None)
    other = PdvmDatabase("sys_framedaten", system_pool=pool, mandant_pool=None)
    PdvmDatabase._template_cache_put(ctrl, ("base",), {"a": 1})
    other._invalidate_caches_after_write()
    assert PdvmDatabase._template_cache_get(ctrl, ("base",)) == {"a": 1}


def test_maintenance_is_skipped_within_interval_and_rerun_when_config_changes(monkeypatch):
    maint.reset_maintenance_cache()
    runs = []

    async def _fake_run(self):
        runs.append(self.mandant_uid)
        return {"tables_created": ["x"], "tables_updated": [], "records_updated": 3, "errors": []}

    monkeypatch.setattr(maint.MandantDatabaseMaintenance, "run_maintenance", _fake_run)
    daten = {"CONFIG": {"FEATURES": ["a"]}}

    first = asyncio.run(maint.run_mandant_maintenance(object(), "m1", daten))
    second = asyncio.run(maint.run_mandant_maintenance(object(), "m1", daten))
    assert len(runs) == 1
    assert first["records_updated"] == 3
    assert second["skipped"] is True and second["records_updated"] == 0

    asyncio.run(maint.run_mandant_maintenance(object(), "m1", {"CONFIG": {"FEATURES": ["a", "b"]}}))
    assert len(runs) == 2  # geaenderte CONFIG loest neuen Lauf aus

    asyncio.run(maint.run_mandant_maintenance(object(), "m2", daten))
    assert len(runs) == 3  # anderer Mandant


def test_maintenance_with_errors_is_not_cached(monkeypatch):
    maint.reset_maintenance_cache()
    runs = []

    async def _fake_run(self):
        runs.append(1)
        return {"tables_created": [], "tables_updated": [], "records_updated": 0, "errors": ["boom"]}

    monkeypatch.setattr(maint.MandantDatabaseMaintenance, "run_maintenance", _fake_run)
    asyncio.run(maint.run_mandant_maintenance(object(), "m1", {}))
    asyncio.run(maint.run_mandant_maintenance(object(), "m1", {}))
    assert len(runs) == 2

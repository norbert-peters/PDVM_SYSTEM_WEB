import asyncio
import uuid

import pytest

from app.core import control_dict_service as cds


class _FakeConn:
    pass


class _FakePool:
    def acquire(self):
        pool = self

        class _Ctx:
            async def __aenter__(self_inner):
                return _FakeConn()

            async def __aexit__(self_inner, *exc):
                return False

        return _Ctx()


class _FakeGcs:
    _system_pool = _FakePool()
    _mandant_pool = None
    user_guid = str(uuid.uuid4())
    actor_ip = "127.0.0.1"


def _service(monkeypatch):
    svc = cds.ControlDictService(_FakeGcs())

    async def _noop():
        return None

    async def _get_control(uid):
        return {"uid": uid, "name": "n", "daten": {}, "historisch": 0}

    monkeypatch.setattr(svc, "_invalidate_control_cache", _noop)
    monkeypatch.setattr(svc, "get_control", _get_control)
    return svc


def test_create_control_writes_via_central_gateway(monkeypatch):
    asyncio.run(_create_control_case(monkeypatch))


async def _create_control_case(monkeypatch):
    svc = _service(monkeypatch)
    new_uid = uuid.uuid4()
    calls = []

    async def _build(conn, modul_type, table_name, field_data):
        return {"uid": new_uid, "name": "SYS_X", "daten": {"modul_type": modul_type}, "historisch": 0}

    async def _create(**kwargs):
        calls.append(kwargs)
        return {}

    monkeypatch.setattr(cds, "build_new_control", _build)
    monkeypatch.setattr(cds, "create_record_central", _create)

    result = await svc.create_control(modul_type="edit", table_name="sys_x", field_data={})
    assert result["uid"] == new_uid
    assert calls[0]["table_name"] == "sys_control_dict"
    assert calls[0]["uid"] == new_uid
    assert calls[0]["daten"] == {"modul_type": "edit"}


def test_switch_modul_writes_via_central_gateway(monkeypatch):
    asyncio.run(_switch_modul_case(monkeypatch))


async def _switch_modul_case(monkeypatch):
    svc = _service(monkeypatch)
    uid = uuid.uuid4()
    calls = []

    async def _get_by_uid(_uid):
        return {"uid": uid, "daten": {"modul_type": "edit"}}

    async def _build_switch(self, old_data, new_modul_type):
        return {"effective": {}, "stored": {"modul_type": new_modul_type}}

    async def _update(**kwargs):
        calls.append(kwargs)
        return {}

    monkeypatch.setattr(svc.db, "get_by_uid", _get_by_uid)
    monkeypatch.setattr(cds.ControlTemplateService, "build_modul_switch", _build_switch)
    monkeypatch.setattr(cds, "update_record_central", _update)

    await svc.switch_modul(uid=uid, new_modul_type="view")
    assert calls[0]["table_name"] == "sys_control_dict"
    assert calls[0]["daten"] == {"modul_type": "view"}


def test_switch_modul_unknown_control_raises(monkeypatch):
    asyncio.run(_unknown_control_case(monkeypatch))


async def _unknown_control_case(monkeypatch):
    svc = _service(monkeypatch)

    async def _get_by_uid(_uid):
        return None

    monkeypatch.setattr(svc.db, "get_by_uid", _get_by_uid)
    with pytest.raises(ValueError):
        await svc.switch_modul(uid=uuid.uuid4(), new_modul_type="view")

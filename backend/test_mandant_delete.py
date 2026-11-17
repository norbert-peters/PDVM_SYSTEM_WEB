import asyncio
import types
import uuid
from datetime import datetime, timedelta

import pytest

from app.core import frame_action_service as svc
from app.core import mandant_delete_service as mds
from app.core.connection_manager import ConnectionConfig
from app.core.mandant_tombstone import is_deleted_mandant_row, is_deleted_record

MANDANT = str(uuid.uuid4())
CREATED = datetime(2026, 11, 1, 10, 0, 0, 123456)


def _row(gilt_bis, created_at=CREATED):
    return {"gilt_bis": gilt_bis, "created_at": created_at}


def test_deleted_marker_is_gilt_bis_at_created_at_independent_of_any_stichtag():
    assert is_deleted_mandant_row(_row(CREATED))
    assert is_deleted_mandant_row(_row(CREATED + timedelta(seconds=1)))  # PDVM-Format rundet auf rund 1 Sekunde
    assert is_deleted_mandant_row(_row(CREATED - timedelta(days=1)))
    assert not is_deleted_mandant_row(_row(datetime(9999, 12, 31, 23, 59, 59)))
    assert not is_deleted_mandant_row(_row(None)) and not is_deleted_mandant_row(_row(CREATED + timedelta(days=30)))
    assert not is_deleted_mandant_row(_row(CREATED, created_at=None)) and not is_deleted_mandant_row(None)
    # nur die Mandantentabelle ist betroffen
    assert is_deleted_record("asy_mandanten", _row(CREATED)) and not is_deleted_record("asy_benutzer", _row(CREATED))


def _gcs(*roles):
    return types.SimpleNamespace(
        benutzer=types.SimpleNamespace(data={"PERMISSIONS": {"ROLES": list(roles)}}),
        mandant_guid=str(uuid.uuid4()), user_guid=str(uuid.uuid4()), actor_ip=None,
    )


def test_deleting_a_mandant_needs_superadmin_and_delmand(monkeypatch):
    calls = []

    async def fake_state(mandant_id, session_mandant_id):
        return {"can_delete": True, "reason": ""}

    async def fake_delete(uid, **kwargs):
        calls.append((uid, kwargs["confirm_name"]))
        return {"name": "X", "backup_file": "b.dump", "users_updated": 2}

    monkeypatch.setattr(svc.mandant_delete_service, "delete_state", fake_state)
    monkeypatch.setattr(svc.mandant_delete_service, "delete_mandant", fake_delete)

    def run(gcs, params=None):
        return asyncio.run(svc.run_action("mandant.delete", gcs=gcs, table="asy_mandanten", uid=MANDANT, params=params))

    for roles in (("superadmin",), ("delmand",), ("admin", "delmand")):
        with pytest.raises(svc.ActionDenied):
            run(_gcs(*roles), {"confirm_name": "X"})
    with pytest.raises(svc.ActionError):  # Bestaetigung ist Pflicht
        run(_gcs("superadmin", "delmand"))
    assert not calls

    res = run(_gcs("superadmin", "delmand"), {"confirm_name": "X"})
    assert calls == [(MANDANT, "X")] and res["data"]["relogin"] is True

    states = asyncio.run(svc.action_states(gcs=_gcs("superadmin"), table="asy_mandanten", uid=MANDANT, ids=["mandant.delete"]))
    assert states["mandant.delete"]["allowed"] is False
    states = asyncio.run(svc.action_states(gcs=_gcs("superadmin", "delmand"), table="asy_mandanten", uid=MANDANT, ids=["mandant.delete"]))
    assert states["mandant.delete"]["allowed"] and states["mandant.delete"]["state"]["can_delete"] is True


@pytest.fixture
def flow(monkeypatch, tmp_path):
    """Faelscht Datenbank und Werkzeuge; `steps` haelt die Reihenfolge der Schritte fest."""
    steps = []
    record = {"uid": uuid.UUID(MANDANT), "name": "Test", "historisch": 0, "created_at": CREATED, "daten": {"MANDANT": {"DATABASE": "test_db"}}}
    config = ConnectionConfig("localhost", 5432, "postgres", "pw", "test_db")
    state = {"exists": True, "dump_error": None, "shared": None, "config": config}

    async def load(mandant_id):
        return record

    async def get_config(mandant_id):
        return ConnectionConfig("localhost", 5432, "postgres", "pw", "pdvm_system"), state["config"]

    async def shared(mandant_id, db_name):
        return state["shared"]

    async def exists(cfg):
        return state["exists"]

    def dump(cfg, target):
        if state["dump_error"]:
            raise ValueError(state["dump_error"])
        steps.append("backup")
        target.write_bytes(b"dump")

    async def drop(cfg, mandant_id):
        steps.append("drop")
        return 1

    async def users(mandant_id, **kwargs):
        steps.append("users")
        return 2

    async def mark(rec, **kwargs):
        steps.append("mark")

    monkeypatch.setattr(mds, "_load", load)
    monkeypatch.setattr(mds.ConnectionManager, "get_mandant_config", staticmethod(get_config))
    monkeypatch.setattr(mds, "_shared_with_other_mandant", shared)
    monkeypatch.setattr(mds, "_database_exists", exists)
    monkeypatch.setattr(mds, "_dump_database", dump)
    monkeypatch.setattr(mds, "_drop_database", drop)
    monkeypatch.setattr(mds, "_remove_from_users", users)
    monkeypatch.setattr(mds, "_mark_deleted", mark)
    monkeypatch.setattr(mds, "_backup_dir", lambda: tmp_path)
    return types.SimpleNamespace(steps=steps, state=state, record=record)


def delete(**overrides):
    args = {"confirm_name": "Test", "session_mandant_id": str(uuid.uuid4())}
    args.update(overrides)
    return asyncio.run(mds.delete_mandant(MANDANT, **args))


def test_backup_comes_first_then_drop_then_users_then_marker(flow, tmp_path):
    out = delete()
    assert flow.steps == ["backup", "drop", "users", "mark"]
    assert out["database_dropped"] and out["users_updated"] == 2 and out["backup_file"].endswith(".dump")
    assert list(tmp_path.glob("*.dump")) and list(tmp_path.glob("*.mandant.json"))


def test_failed_backup_deletes_nothing(flow, tmp_path):
    flow.state["dump_error"] = "pg_dump: Verbindung abgelehnt"
    with pytest.raises(ValueError, match="nichts gelöscht"):
        delete()
    assert flow.steps == [] and not list(tmp_path.glob("*.dump"))


def test_missing_database_skips_backup_and_drop_so_an_interrupted_deletion_can_be_repeated(flow):
    flow.state["exists"] = False
    out = delete()
    assert flow.steps == ["users", "mark"] and out["backup_file"] is None and not out["database_dropped"]


@pytest.mark.parametrize(
    "change, message",
    [
        ({"confirm_name": "test"}, "Bestätigung"),
        ({"session_mandant_id": MANDANT.upper()}, "aktuellen Sitzung"),
    ],
)
def test_wrong_confirmation_or_own_session_mandant_is_refused_before_any_step(flow, change, message):
    with pytest.raises(ValueError, match=message):
        delete(**change)
    assert flow.steps == []


def test_system_and_shared_databases_are_never_dropped(flow):
    flow.state["config"] = ConnectionConfig("localhost", 5432, "postgres", "pw", "Auth")
    with pytest.raises(ValueError, match="Systemdatenbank"):
        delete()
    flow.state["config"] = ConnectionConfig("localhost", 5432, "postgres", "pw", "test_db")
    flow.state["shared"] = "Anderer Mandant"
    with pytest.raises(ValueError, match="Anderer Mandant"):
        delete()
    assert flow.steps == []


def test_removing_the_mandant_from_users_clears_list_and_default(monkeypatch):
    other = str(uuid.uuid4())
    users = [
        {"uid": uuid.uuid4(), "name": "a", "historisch": 0, "daten": {"MANDANTEN": {"LIST": [MANDANT.upper(), other], "DEFAULT": MANDANT}}},
        {"uid": uuid.uuid4(), "name": "b", "historisch": 0, "daten": {"MANDANTEN": {"LIST": [other], "DEFAULT": other}}},
        {"uid": uuid.uuid4(), "name": "c", "historisch": 0, "daten": {}},
    ]
    written = {}

    class FakeDb:
        def __init__(self, table):
            pass

        async def get_all(self):
            return users

    async def fake_update(**kwargs):
        written[kwargs["uid"]] = kwargs["daten"]

    import app.core.central_write_service as central

    monkeypatch.setattr(mds, "PdvmDatabase", FakeDb)
    monkeypatch.setattr(central, "update_record_central", fake_update)
    assert asyncio.run(mds._remove_from_users(MANDANT, actor_uid=None, actor_ip=None)) == 1
    assert written == {users[0]["uid"]: {"MANDANTEN": {"LIST": [other], "DEFAULT": ""}}}

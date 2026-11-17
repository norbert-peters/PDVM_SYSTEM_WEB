import asyncio
import types
import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import frame_actions as api
from app.core import frame_action_service as svc
from app.core import text_template_service as texts
from app.core.security import get_current_user

USER_UID = str(uuid.uuid4())
MANDANT = str(uuid.uuid4())


def _gcs(*roles, mandant=MANDANT):
    return types.SimpleNamespace(
        benutzer=types.SimpleNamespace(data={"PERMISSIONS": {"ROLES": list(roles)}}),
        mandant_guid=mandant, user_guid=str(uuid.uuid4()), actor_ip=None,
    )


@pytest.fixture
def calls(monkeypatch):
    seen = []

    async def lock(**kwargs):
        seen.append(("lock", kwargs))

    async def reset(**kwargs):
        seen.append(("reset", kwargs))
        return {"email": "a@b.c", "email_sent": True, "email_error": None, "expires_at": "x"}

    class FakeBenutzer:
        def __init__(self, uid):
            self.uid = uid

        async def get_user(self):
            return {"uid": self.uid, "daten": {"MANDANTEN": {"LIST": [MANDANT.upper()]}}}

    monkeypatch.setattr(svc, "update_account_lock", lock)
    monkeypatch.setattr(svc, "issue_password_reset", reset)
    monkeypatch.setattr(svc, "PdvmCentralBenutzer", FakeBenutzer)
    return seen


def run(action_id, gcs, table="asy_benutzer", uid=USER_UID, params=None):
    return asyncio.run(svc.run_action(action_id, gcs=gcs, table=table, uid=uid, params=params))


def test_session_admin_rights_follow_the_roles_of_the_session_user():
    from app.core.security import session_has_admin_rights

    assert session_has_admin_rights(_gcs("admin"))
    assert session_has_admin_rights(types.SimpleNamespace(benutzer=types.SimpleNamespace(data={"SECURITY": {"IS_ADMIN": True}})))
    assert not session_has_admin_rights(_gcs("vorlagen"))
    assert not session_has_admin_rights(_gcs())
    assert not session_has_admin_rights(types.SimpleNamespace())


def test_unknown_action_wrong_table_and_missing_role_are_rejected(calls):
    with pytest.raises(svc.ActionNotFound):
        run("user.gibt_es_nicht", _gcs("admin"))
    with pytest.raises(svc.ActionDenied):
        run("user.lock", _gcs("admin"), table="msy_textvorlagen")
    with pytest.raises(svc.ActionDenied):
        run("user.lock", _gcs("vorlagen"))
    assert not calls


def test_uid_and_parameters_are_validated_before_the_handler_runs(calls):
    with pytest.raises(svc.ActionError):
        run("user.lock", _gcs("admin"), uid="kein-uuid")
    with pytest.raises(svc.ActionError):
        run("user.lock", _gcs("admin"), params={"unbekannt": "x"})
    with pytest.raises(svc.ActionError):
        run("user.lock", _gcs("admin"), params={"reason": "x" * 501})
    assert not calls


def test_admin_runs_user_action_and_reason_is_passed(calls):
    res = run("user.lock", _gcs("admin"), params={"reason": " Test "})
    assert res["status"] == "ok" and res["refresh"] == ["record"] and res["message_key"] == "frame_action.user.lock.done"
    assert calls[0][0] == "lock" and calls[0][1]["locked"] is True and calls[0][1]["reason"] == "Test"
    assert run("user.password_reset", _gcs("admin"))["message_key"] == "frame_action.user.password_reset.sent"


def test_user_actions_only_reach_users_of_the_session_mandant(calls):
    with pytest.raises(svc.ActionDenied):
        run("user.lock", _gcs("admin", mandant=str(uuid.uuid4())))
    assert not calls
    run("user.lock", _gcs("superadmin", mandant=str(uuid.uuid4())))  # superadmin ist nicht an den Mandanten gebunden
    assert len(calls) == 1


def test_text_template_roles_follow_the_tables(calls):
    gcs_vorlagen, gcs_admin = _gcs("vorlagen"), _gcs("admin")
    states = asyncio.run(svc.action_states(gcs=gcs_admin, table=texts.SYSTEM_TABLE, uid=USER_UID, ids=["texttemplate.copy"]))
    assert states["texttemplate.copy"]["allowed"] is False  # Systemvorlagen pflegt nur 'vorlagen'
    states = asyncio.run(svc.action_states(gcs=gcs_vorlagen, table=texts.SYSTEM_TABLE, uid=USER_UID, ids=["texttemplate.copy"]))
    assert states["texttemplate.copy"]["allowed"] is True


def test_states_report_permission_and_provider_state(monkeypatch):
    async def source(*, table, uid, gcs):
        return {"outdated": True, "source_name": "Q"}

    monkeypatch.setattr(texts, "source_status", source)
    gcs = _gcs("admin")
    out = asyncio.run(svc.action_states(
        gcs=gcs, table=texts.MANDANT_TABLE, uid=USER_UID,
        ids=["texttemplate.adopt_source", "user.lock", "gibt.es.nicht", "texttemplate.adopt_source"],
    ))
    assert out["texttemplate.adopt_source"] == {
        "allowed": True, "reason": None, "state": {"outdated": True, "source_name": "Q"}, "executor": "server"}
    assert out["user.lock"]["allowed"] is False  # falsche Tabelle
    assert out["gibt.es.nicht"]["allowed"] is False
    assert svc.unknown_action_ids(["user.lock", "x"]) == ["x"]


def test_api_maps_errors_to_http_status(monkeypatch, calls):
    state = {"gcs": _gcs("vorlagen")}
    monkeypatch.setattr(api, "get_gcs_session", lambda token: state["gcs"])
    app = FastAPI()
    app.include_router(api.router)
    app.dependency_overrides[get_current_user] = lambda: {"uid": "x", "token": "t"}
    client = TestClient(app)
    body = {"table": "asy_benutzer", "uid": USER_UID}
    assert client.post("/user.lock/run", json=body).status_code == 403
    assert client.post("/nope/run", json=body).status_code == 404
    state["gcs"] = _gcs("admin")
    assert client.post("/user.lock/run", json={**body, "uid": "x"}).status_code == 400
    ok = client.post("/user.lock/run", json={**body, "params": {"reason": "r"}})
    assert ok.status_code == 200 and ok.json()["status"] == "ok"
    states = client.post("/state", json={**body, "ids": ["user.lock", "user.unlock"]})
    assert states.status_code == 200 and states.json()["states"]["user.lock"]["allowed"] is True

def test_mandant_setup_is_superadmin_only_and_only_while_the_database_is_missing(monkeypatch):
    calls = []
    state = {"exists": True, "needs_setup": True, "database": "mandant_x"}

    async def fake_state(uid):
        return dict(state)

    async def fake_setup(uid):
        calls.append(uid)
        return {"mandant_id": uid, "database": "mandant_x", "db_created_at": "1", "name": "X"}

    async def fake_grant(**kwargs):
        calls.append(("grant", kwargs["mandant_id"]))
        return True

    monkeypatch.setattr(svc, "mandant_setup_state", fake_state)
    monkeypatch.setattr(svc, "setup_mandant_database", fake_setup)
    monkeypatch.setattr(svc, "grant_mandant_access", fake_grant)
    uid = str(uuid.uuid4())

    with pytest.raises(svc.ActionDenied):
        run("mandant.setup", _gcs("admin"), table="asy_mandanten", uid=uid)
    assert not calls

    res = run("mandant.setup", _gcs("superadmin"), table="asy_mandanten", uid=uid)
    assert res["refresh"] == ["record", "state"] and calls == [uid, ("grant", uid)]
    # Nach dem Aufbau muss sich der Benutzer neu anmelden (Mandantenliste und Token stammen aus dem Login)
    assert res["data"]["relogin"] is True and res["data"]["access_granted"] is True

    state["needs_setup"] = False
    with pytest.raises(svc.ActionError):
        run("mandant.setup", _gcs("superadmin"), table="asy_mandanten", uid=uid)

    out = asyncio.run(svc.action_states(gcs=_gcs("superadmin"), table="asy_mandanten", uid=uid, ids=["mandant.setup"]))
    assert out["mandant.setup"]["allowed"] and out["mandant.setup"]["state"]["needs_setup"] is False
    out = asyncio.run(svc.action_states(gcs=_gcs("admin"), table="asy_mandanten", uid=uid, ids=["mandant.setup"]))
    assert out["mandant.setup"]["allowed"] is False


def test_host_actions_need_no_record_and_are_not_run_by_the_server():
    ids = ["workflow.validate", "workflow.dry_run", "workflow.apply", "user.lock"]
    develop = asyncio.run(svc.action_states(gcs=_gcs("develop"), table="dev_workflow_draft", ids=ids))
    assert develop["workflow.validate"] == {"allowed": True, "reason": None, "state": None, "executor": "host"}
    assert develop["workflow.dry_run"]["allowed"] is True
    assert develop["workflow.apply"]["allowed"] is False  # Live-Commit nur fuer Administratoren
    assert develop["user.lock"]["allowed"] is False  # falsche Tabelle/Rolle
    admin = asyncio.run(svc.action_states(gcs=_gcs("admin"), table="dev_workflow_draft", ids=["workflow.apply"]))
    assert admin["workflow.apply"]["allowed"] is True
    no_record = asyncio.run(svc.action_states(gcs=_gcs("admin"), table="asy_benutzer", ids=["user.lock"]))
    assert no_record["user.lock"] == {"allowed": False, "reason": "Kein Datensatz ausgewählt", "state": None, "executor": "server"}
    with pytest.raises(svc.ActionError):
        run("workflow.validate", _gcs("admin"), table="dev_workflow_draft", uid=str(uuid.uuid4()))

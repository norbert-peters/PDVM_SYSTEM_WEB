import types

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import mandanten, workflow_drafts
from app.core.security import get_current_user, has_superadmin_rights


def _user(*roles):
    return {"uid": "u", "token": "t", "user_data": {"PERMISSIONS": {"ROLES": list(roles)}}}


def _client(user, *routers):
    app = FastAPI()
    for router in routers:
        app.include_router(router, prefix="/api/x")
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app, raise_server_exceptions=False)


def test_superadmin_rights_come_from_the_roles_only():
    assert has_superadmin_rights(_user("superadmin"))
    assert not has_superadmin_rights(_user("admin", "develop", "overlay", "vorlagen"))
    assert not has_superadmin_rights({})


@pytest.mark.parametrize("method, path", [("get", "/api/x/template"), ("post", "/api/x/create")])
def test_creating_mandants_needs_the_superadmin_role(method, path):
    client = _client(_user("admin"), mandanten.router)
    response = getattr(client, method)(path, **({"json": {}} if method == "post" else {}))
    assert response.status_code == 403
    assert "superadmin" in response.json()["detail"]


def test_mandants_cannot_be_created_through_the_generic_dialog():
    from app.core.mandant_record_rules import dialog_create_blocked_reason

    assert "Neuer Mandant" in dialog_create_blocked_reason("asy_mandanten")
    assert "Neuer Mandant" in dialog_create_blocked_reason(" ASY_Mandanten ")
    assert dialog_create_blocked_reason("sys_menudaten") == ""
    assert dialog_create_blocked_reason(None) == ""


def test_new_mandant_is_added_to_the_users_mandant_list_once(monkeypatch):
    import asyncio

    from app.core import central_write_service, pdvm_central_benutzer
    from app.core.mandant_setup_service import grant_mandant_access

    user_uid = "11111111-1111-1111-1111-111111111111"
    mandant = "22222222-2222-2222-2222-222222222222"
    writes = []

    class FakeBenutzer:
        def __init__(self, uid):
            pass

        async def get_user(self):
            return {"daten": {"MANDANTEN": {"LIST": ["a"], "DEFAULT": "a"}}, "name": "x", "historisch": 0}

    async def fake_update(**kwargs):
        writes.append(kwargs)

    monkeypatch.setattr(pdvm_central_benutzer, "PdvmCentralBenutzer", FakeBenutzer)
    monkeypatch.setattr(central_write_service, "update_record_central", fake_update)

    assert asyncio.run(grant_mandant_access(user_uid=user_uid, mandant_id=mandant)) is True
    assert writes[0]["daten"]["MANDANTEN"] == {"LIST": ["a", mandant], "DEFAULT": "a"}

    class AlreadyThere(FakeBenutzer):
        async def get_user(self):
            return {"daten": {"MANDANTEN": {"LIST": [mandant]}}, "name": "x", "historisch": 0}

    monkeypatch.setattr(pdvm_central_benutzer, "PdvmCentralBenutzer", AlreadyThere)
    assert asyncio.run(grant_mandant_access(user_uid=user_uid, mandant_id=mandant)) is False
    assert len(writes) == 1


def test_allowed_mandants_follow_list_then_default():
    from app.core.mandant_access import allowed_mandant_ids, is_mandant_allowed

    a = "AAAAAAAA-0000-0000-0000-000000000001"
    b = "bbbbbbbb-0000-0000-0000-000000000002"
    assert allowed_mandant_ids({"MANDANTEN": {"LIST": [a, b], "DEFAULT": b}}) == [a.lower(), b]
    assert allowed_mandant_ids({"MANDANTEN": {"LIST": [], "DEFAULT": a}}) == [a.lower()]
    assert allowed_mandant_ids({"MANDANTEN": {"LIST": None}}) == []
    assert allowed_mandant_ids({}) == [] and allowed_mandant_ids(None) == []
    assert is_mandant_allowed({"MANDANTEN": {"LIST": [a]}}, a.lower())
    assert not is_mandant_allowed({"MANDANTEN": {"LIST": [a]}}, b)


def test_session_language_is_the_users_then_the_mandants_and_none_without_either():
    user = {"SETTINGS": {"LANGUAGE": "en"}}
    mandant = {"CONFIG": {"DEFAULT_LANGUAGE": "IT-IT"}}
    assert mandanten._effective_language(user, mandant) == "EN-US"
    assert mandanten._effective_language({}, mandant) == "IT-IT"
    assert mandanten._effective_language(None, {"CONFIG": {"DEFAULT_LANGUAGE": "  "}}) is None
    assert mandanten._effective_language(None, None) is None


def test_selecting_a_mandant_outside_the_users_list_is_forbidden_and_lists_are_filtered(monkeypatch):
    mine = "11111111-1111-1111-1111-111111111111"
    other = "22222222-2222-2222-2222-222222222222"
    rows = [{"uid": u, "name": n, "daten": {"MANDANT": {"IS_ALLOWED": True}}} for u, n in ((mine, "Mein"), (other, "Fremd"))]

    async def fake_daten(_uid):
        return {"MANDANTEN": {"LIST": [mine]}}

    async def fake_list(self, include_inactive=False):
        return rows

    async def fake_get(self, mandant_id):
        return next((r for r in rows if r["uid"] == str(mandant_id)), None)

    async def fake_access(self, mandant_id, user_id=None):
        return True

    monkeypatch.setattr(mandanten, "load_user_daten", fake_daten)
    monkeypatch.setattr(mandanten.MandantDataManager, "list_all", fake_list)
    monkeypatch.setattr(mandanten.MandantDataManager, "get_by_id", fake_get)
    monkeypatch.setattr(mandanten.MandantDataManager, "check_access", fake_access)

    client = _client({**_user("user"), "sub": "u"}, mandanten.router)
    for path in ("/api/x", "/api/x/list"):
        assert [m["id"] for m in client.get(path).json()] == [mine]

    denied = client.post("/api/x/select", json={"mandant_id": other})
    assert denied.status_code == 403
    assert "Fremd" in denied.json()["detail"]


def test_create_mandant_saves_first_and_keeps_the_record_when_the_database_fails(monkeypatch):
    import asyncio

    from app.core import mandant_setup_service as svc

    saved, calls = [], []

    class FakeCentral:
        def __init__(self, table, uid):
            self.uid = uid

        def set_data(self, data, uid):
            saved.append(data)

        async def save_all_values(self):
            return self.uid

    async def fake_grant(**kwargs):
        calls.append(("grant", kwargs["mandant_id"]))
        return True

    async def fake_setup(mandant_id):
        calls.append(("setup", mandant_id))
        raise ValueError("Kann nicht mit PostgreSQL verbinden")

    monkeypatch.setattr(svc, "PdvmCentralDatabase", FakeCentral)
    monkeypatch.setattr(svc, "grant_mandant_access", fake_grant)
    monkeypatch.setattr(svc, "setup_mandant_database", fake_setup)

    data = {"ROOT": {"NAME": " Neu GmbH "}, "MANDANT": {"DATABASE": "mandant_neu", "CREDENTIAL": "default"}}
    result = asyncio.run(svc.create_mandant(mandant_data=data, actor_uid="u"))
    assert result["saved"] is True and result["access_granted"] is True
    assert result["name"] == "Neu GmbH"
    assert result["database"]["status"] == "failed" and "PostgreSQL" in result["database"]["message"]
    assert [c[0] for c in calls] == ["grant", "setup"]
    assert saved[0]["ROOT"]["SELF_GUID"] == result["mandant_id"]

    calls.clear()
    skipped = asyncio.run(svc.create_mandant(mandant_data=data, actor_uid="u", setup_database=False))
    assert skipped["database"]["status"] == "skipped" and [c[0] for c in calls] == ["grant"]


def test_create_mandant_rejects_invalid_input_before_anything_is_saved(monkeypatch):
    import asyncio

    from app.core import mandant_setup_service as svc

    monkeypatch.setattr(svc, "PdvmCentralDatabase", lambda *a: pytest.fail("darf nicht speichern"))
    with pytest.raises(svc.MandantValidationError) as exc:
        asyncio.run(svc.create_mandant(mandant_data={"ROOT": {}}, actor_uid="u"))
    assert exc.value.errors


def test_retired_setup_endpoints_are_gone():
    client = _client(_user("superadmin"), mandanten.router)
    assert client.get("/api/x/pending-setup").status_code in (404, 405, 422)
    assert client.post("/api/x/setup/11111111-1111-1111-1111-111111111111").status_code in (404, 405)
    assert client.post("/api/x/save", json={}).status_code in (404, 405)


def test_live_commit_of_a_workflow_draft_is_admin_only_while_dry_run_stays_allowed():
    gcs = types.SimpleNamespace(_system_pool=object(), _mandant_pool=None, user_guid="u")
    app = FastAPI()
    app.include_router(workflow_drafts.router, prefix="/api/x")
    app.dependency_overrides[workflow_drafts.get_gcs_instance] = lambda: gcs
    app.dependency_overrides[get_current_user] = lambda: _user("develop")
    client = TestClient(app, raise_server_exceptions=False)
    guid = "22222222-2222-2222-2222-222222222222"

    live = client.post(f"/api/x/{guid}/commit-live", json={"dry_run": False})
    assert live.status_code == 403 and "Administratoren" in live.json()["detail"]
    dry = client.post(f"/api/x/{guid}/commit-live", json={"dry_run": True})
    assert dry.status_code != 403  # Dry-Run bleibt fuer Develop erlaubt (scheitert hier erst an der Datenbank)

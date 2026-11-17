import asyncio
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.api import auth
from app.core.rate_limit import RateLimiter
from app.core.security import create_access_token, get_current_user, is_password_change_path

REQUEST = SimpleNamespace(client=SimpleNamespace(host="203.0.113.9"))
FORM_WRONG = SimpleNamespace(username="User@Test.de", password="falsch")


def _manager(users, locked=(), failed=None):
    failed = failed if failed is not None else []

    class Fake:
        normalize_email = staticmethod(lambda e: str(e).strip().lower())
        hash_password = staticmethod(lambda p: "dummy-hash")

        @staticmethod
        def verify_password(password, hashed):
            return password == "richtig" and hashed == "hash"

        async def get_user_by_email(self, email):
            return users.get(email)

        async def is_account_locked(self, email):
            return email in locked

        async def increment_failed_login(self, email):
            failed.append(email)
            return len(failed)

    return Fake


@pytest.fixture(autouse=True)
def fresh_limiters(monkeypatch):
    monkeypatch.setattr(auth, "_login_failures", RateLimiter(limit=3, window_seconds=300))
    monkeypatch.setattr(auth, "_forgot_requests", RateLimiter(limit=2, window_seconds=900))


def _login(form):
    return asyncio.run(auth.login(REQUEST, form))


def test_unknown_user_and_wrong_password_get_the_same_answer_without_remaining_attempts(monkeypatch):
    failed = []
    monkeypatch.setattr(auth, "UserManager", _manager({"user@test.de": {"uid": "u", "name": "N", "passwort": "hash"}}, failed=failed))
    answers = []
    for username in ("user@test.de", "gibt.es.nicht@test.de"):
        with pytest.raises(HTTPException) as err:
            _login(SimpleNamespace(username=username, password="falsch"))
        answers.append((err.value.status_code, err.value.detail))
    assert answers[0] == answers[1] == (401, auth.GENERIC_LOGIN_ERROR)
    assert "Versuche" not in answers[0][1]
    assert failed == ["user@test.de"]  # nur bekannte Konten zaehlen hoch


def test_locked_account_is_only_revealed_to_someone_who_knows_the_password(monkeypatch):
    users = {"user@test.de": {"uid": "u", "name": "N", "passwort": "hash"}}
    monkeypatch.setattr(auth, "UserManager", _manager(users, locked={"user@test.de"}))
    with pytest.raises(HTTPException) as wrong:
        _login(FORM_WRONG)
    assert (wrong.value.status_code, wrong.value.detail) == (401, auth.GENERIC_LOGIN_ERROR)
    with pytest.raises(HTTPException) as right:
        _login(SimpleNamespace(username="user@test.de", password="richtig"))
    assert right.value.status_code == 403 and "gesperrt" in right.value.detail


def test_too_many_failed_logins_from_one_ip_are_rejected_before_any_lookup(monkeypatch):
    monkeypatch.setattr(auth, "UserManager", _manager({}))
    for _ in range(3):
        with pytest.raises(HTTPException) as err:
            _login(FORM_WRONG)
        assert err.value.status_code == 401
    with pytest.raises(HTTPException) as blocked:
        _login(FORM_WRONG)
    assert blocked.value.status_code == 429


def test_forgot_password_needs_user_and_stored_email_and_always_answers_the_same(monkeypatch):
    sent = []
    accounts = {
        "login@test.de": {"uid": "u-login", "benutzer": "login@test.de", "daten": {"USER": {"EMAIL": "Kontakt@Test.de"}}},
        "ohne@test.de": {"uid": "u-ohne", "benutzer": "ohne@test.de", "daten": {}},
    }

    class Fake:
        normalize_email = staticmethod(lambda e: str(e).strip().lower())
        validate_email = staticmethod(lambda e: "@" in e)

        async def get_user_by_email(self, email):
            return accounts.get(email)

    async def fake_issue(**kwargs):
        sent.append(kwargs["user_uid"])
        return {"email_sent": False, "email_error": "smtp down"}

    monkeypatch.setattr(auth, "UserManager", Fake)
    monkeypatch.setattr(auth, "issue_password_reset", fake_issue)
    monkeypatch.setattr(auth, "_forgot_requests", RateLimiter(limit=10, window_seconds=900))

    async def run(benutzer, email):
        reply = await auth.forgot_password(auth.ForgotPasswordRequest(benutzer=benutzer, email=email), REQUEST)
        await asyncio.sleep(0.05)  # Hintergrundversand abwarten
        return reply

    cases = [
        ("login@test.de", "kontakt@test.de"),  # Benutzer und hinterlegte Adresse passen (Gross-/Kleinschreibung egal)
        ("login@test.de", "andere@test.de"),  # Adresse passt nicht zum Konto
        ("login@test.de", "login@test.de"),  # Anmeldename ist nicht die hinterlegte Adresse
        ("unbekannt@test.de", "kontakt@test.de"),  # Benutzer unbekannt
        ("ohne@test.de", "kontakt@test.de"),  # Konto ohne hinterlegte Adresse
    ]
    replies = [asyncio.run(run(b, e)) for b, e in cases]
    assert all(r == {"email_sent": True, "message": auth.FORGOT_PASSWORD_REPLY} for r in replies)
    assert sent == ["u-login"]

    monkeypatch.setattr(auth, "_forgot_requests", RateLimiter(limit=1, window_seconds=900))
    asyncio.run(run("login@test.de", "kontakt@test.de"))
    with pytest.raises(HTTPException) as limited:
        asyncio.run(run("login@test.de", "kontakt@test.de"))
    assert limited.value.status_code == 429


def test_token_with_pending_password_change_may_only_change_the_password_or_log_out():
    assert is_password_change_path("/api/auth/password-change") and is_password_change_path("/api/auth/logout/")
    assert not is_password_change_path("/api/mandanten/select") and not is_password_change_path("/api/auth/keep-alive")

    app = FastAPI()
    for path in ("/api/auth/password-change", "/api/mandanten/select"):
        app.add_api_route(path, lambda current_user=get_current_user_dep: {"pwc": current_user["pwc"]}, methods=["GET"])
    client = TestClient(app, raise_server_exceptions=False)

    restricted = create_access_token({"sub": "u", "pwc": True})
    normal = create_access_token({"sub": "u"})
    headers = lambda t: {"Authorization": f"Bearer {t}"}

    assert client.get("/api/auth/password-change", headers=headers(restricted)).json() == {"pwc": True}
    denied = client.get("/api/mandanten/select", headers=headers(restricted))
    assert denied.status_code == 403 and "Passwortänderung" in denied.json()["detail"]
    assert client.get("/api/mandanten/select", headers=headers(normal)).json() == {"pwc": False}


from fastapi import Depends  # noqa: E402

get_current_user_dep = Depends(get_current_user)

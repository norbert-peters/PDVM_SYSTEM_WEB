import asyncio
import types
import uuid

from app.core import password_reset_service as prs
from app.core.pdvm_datenbank import PdvmDatabase


def test_send_email_config_is_read_fresh_not_from_stale_session(monkeypatch):
    mandant_uid = uuid.uuid4()
    stale = {"SEND_EMAIL": {"SMTP_PASS": "alt", "SMTP_HOST": "h"}}
    session = types.SimpleNamespace(
        mandant=types.SimpleNamespace(guid=str(mandant_uid), data=stale, get_value_by_group=lambda g: stale[g])
    )

    async def fake_get(self, uid, **kwargs):
        assert uid == mandant_uid and self.table_name == "asy_mandanten"
        return {"daten": {"SEND_EMAIL": {"SMTP_PASS": "neu", "SMTP_HOST": "h"}}}

    monkeypatch.setattr(PdvmDatabase, "get_by_uid", fake_get)
    assert asyncio.run(prs._get_send_email_config_async(session))["SMTP_PASS"] == "neu"


def test_send_email_config_falls_back_to_session_when_record_has_none(monkeypatch):
    stale = {"SEND_EMAIL": {"SMTP_PASS": "sess"}}
    session = types.SimpleNamespace(
        mandant=types.SimpleNamespace(guid=str(uuid.uuid4()), data=stale, get_value_by_group=lambda g: stale[g])
    )

    async def fake_get(self, uid, **kwargs):
        return None

    monkeypatch.setattr(PdvmDatabase, "get_by_uid", fake_get)
    assert asyncio.run(prs._get_send_email_config_async(session))["SMTP_PASS"] == "sess"


def _mandants(monkeypatch, rows):
    async def fake_get(self, uid, **kwargs):
        assert self.table_name == "asy_mandanten"
        daten = rows.get(str(uid))
        return {"daten": daten} if daten is not None else None

    monkeypatch.setattr(PdvmDatabase, "get_by_uid", fake_get)

    async def no_pool(*args, **kwargs):
        raise RuntimeError("keine Mandanten-DB im Test")

    from app.core.connection_manager import ConnectionManager

    monkeypatch.setattr(ConnectionManager, "get_mandant_config", staticmethod(no_pool))


def test_forgot_password_uses_the_mandant_of_the_user_not_the_first_one_with_a_config(monkeypatch):
    own, other, broken = (str(uuid.uuid4()) for _ in range(3))
    _mandants(monkeypatch, {
        broken: {"SEND_EMAIL": {"SMTP_HOST": "", "OTP_RATE_LIMIT": 10}},  # nicht-leere Gruppe, aber ohne Host (der Fehlerfall)
        own: {"SEND_EMAIL": {"SMTP_HOST": "smtp.own"}, "CONFIG": {"DEFAULT_LANGUAGE": "EN-GB"}},
        other: {"SEND_EMAIL": {"SMTP_HOST": "smtp.fremd"}},
    })
    user = {"daten": {"MANDANTEN": {"LIST": [broken, own], "DEFAULT": own}}}
    ctx = asyncio.run(prs._resolve_user_mandant(user))
    assert ctx["uid"] == own and ctx["send_email"]["SMTP_HOST"] == "smtp.own" and ctx["pool"] is None
    assert ctx["daten"]["CONFIG"]["DEFAULT_LANGUAGE"] == "EN-GB"

    # DEFAULT ohne nutzbare Konfiguration: naechster zugeordneter Mandant mit Host, nie ein fremder
    user = {"daten": {"MANDANTEN": {"LIST": [broken, own], "DEFAULT": broken}}}
    assert asyncio.run(prs._resolve_user_mandant(user))["uid"] == own
    user = {"daten": {"MANDANTEN": {"LIST": [broken], "DEFAULT": broken}}}
    ctx = asyncio.run(prs._resolve_user_mandant(user))
    assert ctx["uid"] == broken and not prs._smtp_usable(ctx["send_email"])
    assert asyncio.run(prs._resolve_user_mandant({"daten": {}}))["uid"] is None


def test_reset_without_session_fails_clearly_when_the_users_mandant_cannot_send_mail(monkeypatch):
    import pytest

    mandant = str(uuid.uuid4())
    _mandants(monkeypatch, {mandant: {"SEND_EMAIL": {"SMTP_HOST": ""}}})

    class FakeBenutzer:
        def __init__(self, uid):
            pass

        async def get_user(self):
            return {"daten": {"USER": {"EMAIL": "a@b.de"}, "MANDANTEN": {"LIST": [mandant], "DEFAULT": mandant}}}

    async def fresh():
        return None

    import app.core.credential_service as credentials

    monkeypatch.setattr(prs, "PdvmCentralBenutzer", FakeBenutzer)
    monkeypatch.setattr(credentials, "ensure_fresh", fresh)
    with pytest.raises(ValueError, match="kein E-Mail-Versand"):
        asyncio.run(prs.issue_password_reset(gcs=None, user_uid=str(uuid.uuid4())))

import asyncio

import pytest

from app.core import credential_service as svc
from app.core import credential_store as store
from app.core import secret_box
from app.core.config import settings


@pytest.fixture
def key(monkeypatch):
    monkeypatch.setattr(settings, "PDVM_SECRET_KEY", secret_box.generate_key())
    monkeypatch.setattr(settings, "PDVM_DB_CREDENTIALS", "")
    store.replace_stored_credentials({})
    yield
    store.replace_stored_credentials({})


def test_secret_box_roundtrip_and_wrong_key(key, monkeypatch):
    token = secret_box.encrypt("Geheim!")
    assert token.startswith("enc:v1:") and "Geheim!" not in token
    assert secret_box.decrypt(token) == "Geheim!"
    monkeypatch.setattr(settings, "PDVM_SECRET_KEY", secret_box.generate_key())
    with pytest.raises(secret_box.SecretKeyError):
        secret_box.decrypt(token)


def test_missing_key_is_a_clear_error(monkeypatch):
    monkeypatch.setattr(settings, "PDVM_SECRET_KEY", "")
    with pytest.raises(secret_box.SecretKeyError):
        secret_box.encrypt("x")


def test_env_credentials_win_over_stored_and_cannot_be_overwritten(key, monkeypatch):
    monkeypatch.setattr(settings, "PDVM_DB_CREDENTIALS", '{"default": {"user": "u", "password": "env-pw"}}')
    store.replace_stored_credentials({"default": store.Credential(user=None, password="db-pw")})
    assert store.get_credential("default").password == "env-pw"
    with pytest.raises(svc.CredentialError):
        asyncio.run(svc.set_credential("default", "neu"))


def test_set_credential_stores_only_ciphertext_and_fills_cache(key, monkeypatch):
    rows, written = [], {}

    async def load_rows():
        return rows

    async def create(**kw):
        written.update(kw)
        rows.append({"uid": kw["uid"], "name": kw["name"], "daten": kw["daten"]})
        return {}

    monkeypatch.setattr(svc, "_load_rows", load_rows)
    monkeypatch.setattr(svc, "create_record_central", create)

    info = asyncio.run(svc.set_credential("mail-1", "Geheim!", user="u"))

    assert "Geheim!" not in str(written["daten"]) and written["daten"]["CREDENTIAL"]["PASSWORD"].startswith("enc:v1:")
    assert "password" not in info and info["exists"] and info["source"] == "store"
    assert store.get_credential("mail-1").password == "Geheim!"


def test_invalid_names_are_rejected(key):
    for bad in ("", "../x", "a b", "-x", "x" * 65):
        with pytest.raises(svc.CredentialError):
            svc.validate_name(bad)

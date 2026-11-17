import pytest

from app.core import credential_store
from app.core.config import settings
from app.core.connection_manager import ConnectionManager


class FakeProvider:
    def __init__(self, entries):
        self.entries = entries

    def get(self, name):
        return self.entries.get(name)


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    monkeypatch.setattr(settings, "DATABASE_URL_AUTH", "postgresql://auth_user:auth%40pw@localhost:5432/auth")
    original = credential_store._provider
    yield
    credential_store.set_credential_provider(original)


def use_credentials(entries):
    credential_store.set_credential_provider(FakeProvider(entries))


def test_same_instance_falls_back_to_auth_credentials():
    use_credentials({})
    system, mandant = ConnectionManager.resolve_mandant_connections(
        {"HOST": "127.0.0.1", "PORT": 5432, "DATABASE": "m1", "SYSTEM_DB": "pdvm_system"}
    )
    assert (mandant.user, mandant.password, mandant.database) == ("auth_user", "auth@pw", "m1")
    assert (system.user, system.password, system.database) == ("auth_user", "auth@pw", "pdvm_system")


def test_named_credential_for_other_server_and_separate_system_db():
    use_credentials({
        "srv-b": credential_store.Credential(user="b_user", password="b-pw", ssl=True),
        "srv-s": credential_store.Credential(user="s_user", password="s-pw"),
    })
    system, mandant = ConnectionManager.resolve_mandant_connections({
        "HOST": "db-b", "PORT": 5433, "DATABASE": "m2", "CREDENTIAL": "srv-b",
        "SYSTEM_HOST": "db-s", "SYSTEM_PORT": 5432, "SYSTEM_DB": "sys", "SYSTEM_CREDENTIAL": "srv-s",
    })
    assert (mandant.host, mandant.user, mandant.password, mandant.ssl) == ("db-b", "b_user", "b-pw", True)
    assert (system.host, system.user, system.password, system.ssl) == ("db-s", "s_user", "s-pw", False)
    assert not ConnectionManager.same_instance(system, mandant)
    assert mandant.to_url().endswith("?sslmode=require")


def test_system_db_inherits_mandant_credential():
    use_credentials({"srv-b": credential_store.Credential(user="b_user", password="p@ss:w/rd")})
    system, mandant = ConnectionManager.resolve_mandant_connections(
        {"HOST": "db-b", "PORT": 5432, "DATABASE": "m", "CREDENTIAL": "srv-b"}
    )
    assert system.password == mandant.password == "p@ss:w/rd" and system.host == "db-b"
    assert "p%40ss%3Aw%2Frd" in mandant.to_url()


def test_unknown_named_credential_is_an_error():
    use_credentials({})
    with pytest.raises(ValueError, match="srv-x"):
        ConnectionManager.resolve_mandant_connections({"HOST": "db-x", "DATABASE": "m", "CREDENTIAL": "srv-x"})


def test_auth_password_is_never_sent_to_a_foreign_instance():
    use_credentials({})
    with pytest.raises(ValueError, match="db-x"):
        ConnectionManager.resolve_mandant_connections({"HOST": "db-x", "PORT": 5432, "DATABASE": "m"})


def test_default_credential_is_used_before_auth_fallback():
    use_credentials({"default": credential_store.Credential(user="def_user", password="def-pw")})
    _, mandant = ConnectionManager.resolve_mandant_connections({"DATABASE": "m"})
    assert (mandant.user, mandant.password) == ("def_user", "def-pw")


def test_legacy_password_still_works_during_transition():
    use_credentials({})
    _, mandant = ConnectionManager.resolve_mandant_connections(
        {"HOST": "db-x", "PORT": 5432, "USER": "u", "PASSWORD": "legacy-pw", "DATABASE": "m"}
    )
    assert (mandant.user, mandant.password) == ("u", "legacy-pw")


def test_repr_hides_password():
    use_credentials({})
    _, mandant = ConnectionManager.resolve_mandant_connections({"DATABASE": "m"})
    assert "auth@pw" not in repr(mandant)
    assert "***" in repr(credential_store.Credential(user="u", password="secret"))

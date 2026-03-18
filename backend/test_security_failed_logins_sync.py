import asyncio

from app.core.user_manager import UserManager
from app.core.database import DatabasePool


def test_increment_failed_login_writes_both_security_counters(monkeypatch):
    """Regression: FAILED_LOGINS and FAILED_LOGIN_ATTEMPTS must be updated together."""

    captured = {"query": "", "args": None}

    class FakeConn:
        async def fetchval(self, query, *args):
            return "1"

        async def execute(self, query, *args):
            captured["query"] = query
            captured["args"] = args
            return "OK"

    class FakeAcquire:
        async def __aenter__(self):
            return FakeConn()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class FakePool:
        def acquire(self):
            return FakeAcquire()

    DatabasePool._pool_auth = FakePool()

    async def _run():
        um = UserManager()
        result = await um.increment_failed_login("admin@super.de")
        assert result == 2
        q = captured["query"]
        assert "{SECURITY,FAILED_LOGIN_ATTEMPTS}" in q
        assert "{SECURITY,FAILED_LOGINS}" in q
        assert captured["args"][1] == 2

    asyncio.run(_run())

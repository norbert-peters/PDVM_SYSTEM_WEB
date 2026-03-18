import asyncio
import uuid

from app.api import auth


def test_auth_me_returns_fresh_user_data_from_db(monkeypatch):
    """/auth/me should return fresh user_data from DB (not stale token snapshot)."""

    user_id = str(uuid.uuid4())

    stale_current_user = {
        "sub": user_id,
        "email": "token@example.com",
        "name": "Token Name",
        "user_data": {
            "SECURITY": {
                "LAST_LOGIN": 2026001.1,
                "FAILED_LOGIN_ATTEMPTS": 3,
            }
        },
        "token": "dummy",
    }

    fresh_user = {
        "uid": user_id,
        "benutzer": "db@example.com",
        "name": "DB Name",
        "daten": {
            "SECURITY": {
                "LAST_LOGIN": 2026070.5,
                "FAILED_LOGIN_ATTEMPTS": 0,
            }
        },
    }

    class FakeUserManager:
        async def get_user_by_id(self, uid: str):
            return fresh_user

    monkeypatch.setattr(auth, "UserManager", FakeUserManager)

    async def _run():
        result = await auth.read_users_me(current_user=stale_current_user)

        assert result["email"] == "db@example.com"
        assert result["name"] == "DB Name"
        assert result["user_data"]["SECURITY"]["LAST_LOGIN"] == 2026070.5
        assert result["user_data"]["SECURITY"]["FAILED_LOGIN_ATTEMPTS"] == 0
        # token context stays available
        assert result["token"] == "dummy"

    asyncio.run(_run())

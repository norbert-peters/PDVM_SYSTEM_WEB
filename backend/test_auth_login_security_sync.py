import uuid
import asyncio
from types import SimpleNamespace

from app.api import auth


def test_login_uses_refreshed_user_data_after_security_update(monkeypatch):
    """Regression: JWT/user_data must reflect post-login SECURITY updates."""

    async def _run():
        captured_token_payload = {}

        stale_user = {
            "uid": str(uuid.uuid4()),
            "name": "Test User",
            "passwort": "hash",
            "daten": {
                "SECURITY": {
                    "FAILED_LOGIN_ATTEMPTS": 3,
                    "LAST_LOGIN": None,
                },
                "MANDANTEN": {
                    "LIST": ["11111111-1111-1111-1111-111111111111"],
                    "DEFAULT": "11111111-1111-1111-1111-111111111111",
                },
            },
        }

        refreshed_user = {
            **stale_user,
            "daten": {
                **stale_user["daten"],
                "SECURITY": {
                    "FAILED_LOGIN_ATTEMPTS": 0,
                    "LAST_LOGIN": 2026070.5,
                },
            },
        }

        class FakeUserManager:
            def __init__(self):
                self.get_user_calls = 0

            def normalize_email(self, email: str) -> str:
                return str(email).strip().lower()

            async def is_account_locked(self, email: str) -> bool:
                return False

            async def get_user_by_email(self, email: str):
                self.get_user_calls += 1
                return stale_user if self.get_user_calls == 1 else refreshed_user

            def verify_password(self, password: str, hashed_password: str) -> bool:
                return True

            async def update_last_login(self, email: str):
                return None

            async def check_password_change_required(self, email: str) -> bool:
                return False

            async def is_password_reset_expired(self, email: str) -> bool:
                return False

        class FakeMandantDataManager:
            async def list_all(self, include_inactive: bool = False):
                return [
                    {
                        "uid": "11111111-1111-1111-1111-111111111111",
                        "name": "Mandant A",
                        "daten": {"MANDANT": {"IS_ALLOWED": True, "DESCRIPTION": "A"}},
                    }
                ]

        def fake_create_access_token(*, data, expires_delta):
            captured_token_payload.clear()
            captured_token_payload.update(data)
            return "fake-token"

        monkeypatch.setattr(auth, "UserManager", FakeUserManager)
        monkeypatch.setattr(auth, "create_access_token", fake_create_access_token)

        import app.core.data_managers as data_managers

        monkeypatch.setattr(data_managers, "MandantDataManager", FakeMandantDataManager)

        form = SimpleNamespace(username="User@Test.de", password="Secret123!")

        result = await auth.login(form)

        assert result["access_token"] == "fake-token"
        assert result["user_data"]["SECURITY"]["FAILED_LOGIN_ATTEMPTS"] == 0
        assert result["user_data"]["SECURITY"]["LAST_LOGIN"] == 2026070.5

        assert captured_token_payload["user_data"]["SECURITY"]["FAILED_LOGIN_ATTEMPTS"] == 0
        assert captured_token_payload["user_data"]["SECURITY"]["LAST_LOGIN"] == 2026070.5

    asyncio.run(_run())

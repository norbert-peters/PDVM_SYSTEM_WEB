import uuid
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import auth
from app.api import mandanten


def test_login_to_mandanten_select_passes_refreshed_security_to_gcs(monkeypatch):
    """Flow test: /auth/login -> /mandanten/select must pass refreshed SECURITY via JWT user_data to GCS."""

    captured_gcs_kwargs = {}

    stale_user = {
        "uid": str(uuid.uuid4()),
        "name": "Test User",
        "passwort": "hash",
        "daten": {
            "SECURITY": {
                "FAILED_LOGIN_ATTEMPTS": 4,
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

        async def increment_failed_login(self, email: str) -> int:
            return 0

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
                    "daten": {
                        "MANDANT": {
                            "IS_ALLOWED": True,
                            "DESCRIPTION": "Testmandant",
                            "HOST": "localhost",
                            "PORT": 5432,
                            "USER": "postgres",
                            "PASSWORD": "postgres",
                            "DATABASE": "pdvm_mandant_a",
                            "SYSTEM_DB": "pdvm_system",
                        },
                        "ROOT": {"MANDANT_TOWN": "X", "MANDANT_STREET": "Y"},
                    },
                }
            ]

        async def get_by_id(self, mandant_id: str):
            if str(mandant_id) != "11111111-1111-1111-1111-111111111111":
                return None
            rows = await self.list_all(include_inactive=False)
            row = rows[0]
            return {
                "uid": row["uid"],
                "name": row["name"],
                "daten": row["daten"],
            }

        async def check_access(self, mandant_id: str, user_id: str) -> bool:
            return True

        async def get_database_name(self, mandant_id: str) -> str:
            return "pdvm_mandant_a"

        async def update_value(self, mandant_id: str, group: str, field: str, value):
            return None

    class FakeAsyncPgConn:
        async def fetchval(self, query, *args):
            # Simuliere: DB existiert bereits
            return 1

        async def execute(self, query, *args):
            return "OK"

        async def close(self):
            return None

    class FakeAsyncPgPool:
        async def close(self):
            return None

    async def fake_asyncpg_connect(*args, **kwargs):
        return FakeAsyncPgConn()

    async def fake_asyncpg_create_pool(*args, **kwargs):
        return FakeAsyncPgPool()

    async def fake_run_mandant_maintenance(pool, mandant_id, mandant_data):
        return {
            "tables_created": 0,
            "tables_updated": 0,
            "records_updated": 0,
        }

    async def fake_create_gcs_session(**kwargs):
        captured_gcs_kwargs.clear()
        captured_gcs_kwargs.update(kwargs)
        return SimpleNamespace(stichtag=9999365.0)

    # Patch User/mandant manager references in both modules
    monkeypatch.setattr(auth, "UserManager", FakeUserManager)
    monkeypatch.setattr(mandanten, "MandantDataManager", FakeMandantDataManager)

    import app.core.data_managers as data_managers

    monkeypatch.setattr(data_managers, "MandantDataManager", FakeMandantDataManager)

    # Patch asyncpg used inside mandanten.select
    import asyncpg

    monkeypatch.setattr(asyncpg, "connect", fake_asyncpg_connect)
    monkeypatch.setattr(asyncpg, "create_pool", fake_asyncpg_create_pool)

    # Patch maintenance + GCS creation points
    import app.core.mandant_db_maintenance as mandant_db_maintenance
    import app.core.pdvm_central_systemsteuerung as gcs_module

    monkeypatch.setattr(mandant_db_maintenance, "run_mandant_maintenance", fake_run_mandant_maintenance)
    monkeypatch.setattr(gcs_module, "create_gcs_session", fake_create_gcs_session)

    # Minimal app for this flow test (without global startup side effects)
    app = FastAPI()
    app.include_router(auth.router, prefix="/api/auth")
    app.include_router(mandanten.router, prefix="/api/mandanten")

    with TestClient(app) as client:
        login_resp = client.post(
            "/api/auth/login",
            data={"username": "user@test.de", "password": "Secret123!"},
        )
        assert login_resp.status_code == 200, login_resp.text

        token = login_resp.json().get("access_token")
        assert token

        select_resp = client.post(
            "/api/mandanten/select",
            json={"mandant_id": "11111111-1111-1111-1111-111111111111"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert select_resp.status_code == 200, select_resp.text

    # Kern-Assertion: GCS bekommt den refreshed SECURITY-Stand aus JWT/current_user.user_data
    assert captured_gcs_kwargs
    user_data = captured_gcs_kwargs["user_data"]
    assert user_data["SECURITY"]["FAILED_LOGIN_ATTEMPTS"] == 0
    assert user_data["SECURITY"]["LAST_LOGIN"] == 2026070.5

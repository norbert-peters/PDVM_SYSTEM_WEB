import asyncio
import uuid

from app.core import password_reset_service as prs


def test_issue_password_reset_stores_security_timestamps_as_pdvm(monkeypatch):
    """SECURITY timestamps for password reset must be stored in PDVM format, not ISO strings."""

    captured_update = {}

    class FakeBenutzer:
        def __init__(self, user_uuid):
            self.user_uuid = user_uuid

        async def get_user(self):
            return {
                "uid": str(self.user_uuid),
                "name": "Tester",
                "historisch": 0,
                "daten": {
                    "USER": {"EMAIL": "user@test.de"},
                    "SECURITY": {
                        "PASSWORD_RESET_SEND_COUNT": 0,
                    },
                },
            }

        async def change_password(self, new_hash: str):
            return None

    class FakeDb:
        def __init__(self, table_name):
            self.table_name = table_name

        async def update(self, uid, daten, name=None, historisch=None):
            captured_update["uid"] = uid
            captured_update["daten"] = daten
            captured_update["name"] = name
            captured_update["historisch"] = historisch

    async def fake_send_cfg(gcs):
        return {}

    monkeypatch.setattr(prs, "PdvmCentralBenutzer", FakeBenutzer)
    monkeypatch.setattr(prs, "PdvmDatabase", FakeDb)
    monkeypatch.setattr(prs, "_get_send_email_config_async", fake_send_cfg)

    # No-op mail send to avoid side effects
    monkeypatch.setattr(prs, "send_email", lambda *args, **kwargs: None)

    async def _run():
        result = await prs.issue_password_reset(gcs=None, user_uid=str(uuid.uuid4()))

        assert "expires_at" in result
        # API response keeps string contract but contains PDVM numeric text
        assert "." in str(result["expires_at"])
        assert "T" not in str(result["expires_at"])

        sec = captured_update["daten"]["SECURITY"]
        for key in [
            "PASSWORD_RESET_ISSUED_AT",
            "PASSWORD_RESET_EXPIRES_AT",
            "PASSWORD_RESET_SEND_WINDOW_START",
        ]:
            value = sec.get(key)
            assert isinstance(value, (int, float)), f"{key} must be numeric PDVM, got {type(value)}"
            assert float(value) >= 1001.0

    asyncio.run(_run())

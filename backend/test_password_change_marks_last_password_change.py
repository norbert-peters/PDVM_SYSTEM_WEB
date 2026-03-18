import asyncio
import uuid

from app.core import password_reset_service as prs


def test_mark_password_changed_sets_last_password_change_pdvm(monkeypatch):
    """Regression: LAST_PASSWORD_CHANGE must be written in SECURITY on password change."""

    captured_update = {}
    user_uuid = uuid.uuid4()

    class FakeBenutzer:
        def __init__(self, uid):
            self.uid = uid

        async def get_user(self):
            return {
                "uid": str(self.uid),
                "name": "Admin",
                "historisch": 0,
                "daten": {"SECURITY": {}},
            }

    class FakeDb:
        def __init__(self, table_name):
            self.table_name = table_name

        async def update(self, uid, daten, name=None, historisch=None):
            captured_update["uid"] = uid
            captured_update["daten"] = daten

    monkeypatch.setattr(prs, "PdvmCentralBenutzer", FakeBenutzer)
    monkeypatch.setattr(prs, "PdvmDatabase", FakeDb)

    async def _run():
        await prs.mark_password_changed(user_uid=str(user_uuid))
        sec = captured_update["daten"]["SECURITY"]
        value = sec.get("LAST_PASSWORD_CHANGE")
        assert isinstance(value, (int, float))
        assert float(value) >= 1001.0

    asyncio.run(_run())

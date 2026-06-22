import uuid

from app.core import pdvm_central_systemsteuerung as gcs_module


def test_gcs_uses_msy_systemsteuerung_and_delegates_save(monkeypatch):
    """Regression: GCS must route user settings via msy_systemsteuerung (not legacy sys_*)."""

    created_tables = []

    class FakeCentralDb:
        def __init__(self, table_name, guid=None, no_save=False, stichtag=None, system_pool=None, mandant_pool=None):
            self.table_name = table_name
            self.guid = guid
            self.no_save = no_save
            self.stichtag = stichtag
            self.system_pool = system_pool
            self.mandant_pool = mandant_pool
            self.data = {}
            self.saved = False
            self.last_set = None
            created_tables.append(table_name)

        def set_data(self, data):
            self.data = data

        def set_guid(self, guid):
            self.guid = guid

        def set_value(self, gruppe, feld, wert, ab_zeit=None):
            self.last_set = (gruppe, feld, wert, ab_zeit)

        async def save_all_values(self, *args, **kwargs):
            self.saved = True
            return str(uuid.uuid4())

    monkeypatch.setattr(gcs_module, "PdvmCentralDatabase", FakeCentralDb)

    user_guid = uuid.uuid4()
    mandant_guid = uuid.uuid4()

    gcs = gcs_module.PdvmCentralSystemsteuerung(
        user_guid=user_guid,
        mandant_guid=mandant_guid,
        user_data={"SETTINGS": {}},
        mandant_data={"ROOT": {}},
        stichtag=9999365.0,
        system_pool=None,
        mandant_pool=None,
    )

    assert "msy_systemsteuerung" in created_tables
    assert "msy_anwendungsdaten" in created_tables
    assert "sys_systemsteuerung" not in created_tables

    gcs.set_value("gruppe-a", "feld-a", "wert-a")
    assert gcs.systemsteuerung.last_set is not None
    assert gcs.systemsteuerung.last_set[0] == "gruppe-a"
    assert gcs.systemsteuerung.last_set[1] == "feld-a"
    assert gcs.systemsteuerung.last_set[2] == "wert-a"

    import asyncio

    asyncio.run(gcs.save_all_values())
    assert gcs.systemsteuerung.saved is True

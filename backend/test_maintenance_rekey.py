import asyncio

from app.core import mandant_db_maintenance as maint


class _Conn:
    def __init__(self):
        self.queries = []

    async def fetch(self, query, *args):
        self.queries.append(query)
        return []


def test_row_uid_rekey_never_touches_reserved_base_records(monkeypatch):
    """Ursache der Basissaetze mit falscher UID: Der Rekey tauschte auch 000/555/666 gegen Zufalls-UIDs."""
    maintenance = maint.MandantDatabaseMaintenance(object(), "m", {})
    conn = _Conn()

    async def _exists(self, c, t):
        return True

    async def _types(self, c, t):
        return {"uid": "uuid", "link_uid": "uuid"}

    monkeypatch.setattr(maint.MandantDatabaseMaintenance, "_table_exists", _exists)
    monkeypatch.setattr(maint.MandantDatabaseMaintenance, "_get_column_types", _types)

    asyncio.run(maintenance._rekey_row_uids_for_link_tables(conn, ["msy_systemsteuerung"]))

    sql = conn.queries[0]
    for reserved in (
        "00000000-0000-0000-0000-000000000000",
        "55555555-5555-5555-5555-555555555555",
        "66666666-6666-6666-6666-666666666666",
    ):
        assert reserved in sql

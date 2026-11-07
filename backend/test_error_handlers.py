import asyncpg
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.error_handlers import register_error_handlers


def _client() -> TestClient:
    app = FastAPI()
    register_error_handlers(app)

    @app.get("/missing")
    async def missing():
        raise asyncpg.exceptions.UndefinedTableError('Relation "sys_security" existiert nicht')

    @app.get("/other")
    async def other():
        raise asyncpg.exceptions.UndefinedColumnError("Spalte fehlt")

    return TestClient(app, raise_server_exceptions=False)


def test_undefined_table_maps_to_404():
    r = _client().get("/missing")
    assert r.status_code == 404
    assert "sys_security" in r.json()["detail"]


def test_other_db_errors_stay_500():
    assert _client().get("/other").status_code == 500

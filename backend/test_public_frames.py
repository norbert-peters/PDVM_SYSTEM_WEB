import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import public_frames
from app.core import frame_runtime_service as frames
from app.core import public_frame_service as service
from app.core.rate_limit import RateLimiter


def _payload(frame_type="public_form", types=("string", "password_input")):
    return {
        "uid": "u", "name": "n", "root": {"FRAME_TYPE": frame_type},
        "tabs": [{"index": 1, "head": ""}],
        "fields": [
            {"key": f"k{i}", "feld": f"F{i}", "type": t, "table": "auth_login", "control_uid": "x", "options": [{"value": "a"}],
             "resolution_warning": None}
            for i, t in enumerate(types)
        ],
    }


@pytest.fixture
def fake_loader(monkeypatch):
    seen = []

    async def scope(_gcs):
        return object()

    async def load(_scope, frame_uid, language=None):
        seen.append(frame_uid)
        return _payload()

    monkeypatch.setattr(frames, "resolve_pool_scope", scope)
    monkeypatch.setattr(frames, "load_frame_runtime", load)
    return seen


def test_only_the_three_allowlisted_frames_are_loaded_and_internal_references_are_removed(fake_loader):
    result = asyncio.run(service.load_login_frames("de"))
    assert set(result) == {"login", "forgot", "change"}
    assert set(fake_loader) == set(service.LOGIN_FRAME_UIDS.values())
    field = result["login"]["fields"][0]
    assert field["table"] is None and field["control_uid"] is None and field["options"] == []


@pytest.mark.parametrize(
    "payload",
    [
        _payload(frame_type="norm"),
        _payload(types=("string", "action")),
        _payload(types=("dropdown",)),
        {**_payload(), "fields": [{**_payload()["fields"][0], "resolution_warning": "kaputt"}]},
    ],
)
def test_frames_that_break_the_public_rules_are_rejected(monkeypatch, payload):
    async def scope(_gcs):
        return object()

    async def load(_scope, frame_uid, language=None):
        return payload

    monkeypatch.setattr(frames, "resolve_pool_scope", scope)
    monkeypatch.setattr(frames, "load_frame_runtime", load)
    with pytest.raises(service.PublicFrameError):
        asyncio.run(service.load_login_frames())


def test_endpoint_needs_no_token_hides_errors_and_limits_requests(monkeypatch, fake_loader):
    app = FastAPI()
    app.include_router(public_frames.router, prefix="/api/public")
    client = TestClient(app, raise_server_exceptions=False)
    public_frames._limiter.reset()

    ok = client.get("/api/public/login-frames")
    assert ok.status_code == 200 and set(ok.json()["frames"]) == {"login", "forgot", "change"}
    assert "max-age" in ok.headers["cache-control"]

    async def broken(_language=None):
        raise service.PublicFrameError("interne Details")

    monkeypatch.setattr(service, "load_login_frames", broken)
    failed = client.get("/api/public/login-frames")
    assert failed.status_code == 503 and "interne" not in failed.text

    monkeypatch.setattr(public_frames, "_limiter", RateLimiter(limit=1, window_seconds=60))
    client.get("/api/public/login-frames")
    assert client.get("/api/public/login-frames").status_code == 429


def test_rate_limiter_counts_per_key_inside_the_window():
    limiter = RateLimiter(limit=2, window_seconds=10)
    assert limiter.allow("a", now=0) and limiter.allow("a", now=1)
    assert not limiter.allow("a", now=2)
    assert limiter.allow("b", now=2)
    assert limiter.allow("a", now=12)  # Fenster abgelaufen

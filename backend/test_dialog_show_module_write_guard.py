import uuid
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import dialogs


DIALOG_GUID = "11111111-1111-1111-1111-111111111111"
RECORD_GUID = "22222222-2222-2222-2222-222222222222"
DRAFT_ID = "draft-show-guard"


def _build_app() -> FastAPI:
    app = FastAPI()
    app.include_router(dialogs.router, prefix="/api/dialogs")
    app.dependency_overrides[dialogs.get_gcs_instance] = lambda: SimpleNamespace(stichtag=9999365.0)
    return app


async def _fake_load_dialog_definition(gcs, dialog_uuid):
    return {"uid": str(dialog_uuid), "daten": {"ROOT": {}}}


def _runtime_show_module() -> dict:
    return {
        "root_table": "persondaten",
        "edit_type": "show_json",
        "dialog_type": "norm",
        "tab_modules": [
            {
                "index": 2,
                "module": "show",
                "guid": "bdcc1303-ec4d-4fd6-8fc1-395961f6324e",
                "table": "persondaten",
                "edit_type": "show_json",
            }
        ],
    }


def _patch_common_show_runtime(monkeypatch):
    monkeypatch.setattr(dialogs, "load_dialog_definition", _fake_load_dialog_definition)
    monkeypatch.setattr(dialogs, "extract_dialog_runtime_config", lambda _dialog_def: _runtime_show_module())


def test_put_record_rejects_write_for_show_module(monkeypatch):
    _patch_common_show_runtime(monkeypatch)

    async def _unexpected_update(*_args, **_kwargs):
        raise AssertionError("update should not be called for MODULE=show")

    monkeypatch.setattr(dialogs, "update_dialog_record_json", _unexpected_update)
    monkeypatch.setattr(dialogs, "update_dialog_record_central", _unexpected_update)

    app = _build_app()
    with TestClient(app) as client:
        response = client.put(
            f"/api/dialogs/{DIALOG_GUID}/record/{RECORD_GUID}",
            json={"daten": {"ROOT": {"SELF_NAME": "X"}}},
        )

    assert response.status_code == 400
    assert "MODULE=show" in str(response.json().get("detail", ""))


def test_post_record_create_rejects_write_for_show_module(monkeypatch):
    _patch_common_show_runtime(monkeypatch)

    async def _fake_build_draft(*_args, **_kwargs):
        return {
            "name": "Test Name",
            "daten": {"ROOT": {"SELF_NAME": "Test Name"}},
            "template_uid": "66666666-6666-6666-6666-666666666666",
            "sec_id": "",
        }

    async def _fake_create_from_template(*_args, **_kwargs):
        return {"uid": str(uuid.uuid4())}

    async def _unexpected_update(*_args, **_kwargs):
        raise AssertionError("update should not be called for MODULE=show")

    monkeypatch.setattr(dialogs, "build_dialog_draft_from_template", _fake_build_draft)
    monkeypatch.setattr(dialogs, "create_dialog_record_from_template", _fake_create_from_template)
    monkeypatch.setattr(dialogs, "validate_dialog_daten_generic", lambda _daten, edit_type=None: [])
    monkeypatch.setattr(dialogs, "update_dialog_record_json", _unexpected_update)
    monkeypatch.setattr(dialogs, "update_dialog_record_central", _unexpected_update)

    app = _build_app()
    with TestClient(app) as client:
        response = client.post(
            f"/api/dialogs/{DIALOG_GUID}/record",
            json={"name": "Test Name"},
        )

    assert response.status_code == 400
    assert "MODULE=show" in str(response.json().get("detail", ""))


def test_post_draft_commit_rejects_write_for_show_module(monkeypatch):
    _patch_common_show_runtime(monkeypatch)

    async def _fake_read_dialog_drafts(_gcs, *, group: str):
        return {
            DRAFT_ID: {
                "draft_id": DRAFT_ID,
                "name": "Test Draft",
                "daten": {"ROOT": {"SELF_NAME": "Test Draft"}},
                "root_table": "persondaten",
                "edit_type": "show_json",
                "template_uid": "66666666-6666-6666-6666-666666666666",
                "sec_id": "",
                "create_context": {},
            }
        }

    async def _fake_create_from_template(*_args, **_kwargs):
        return {"uid": str(uuid.uuid4())}

    async def _unexpected_update(*_args, **_kwargs):
        raise AssertionError("update should not be called for MODULE=show")

    monkeypatch.setattr(dialogs, "_read_dialog_drafts", _fake_read_dialog_drafts)
    monkeypatch.setattr(dialogs, "create_dialog_record_from_template", _fake_create_from_template)
    monkeypatch.setattr(dialogs, "validate_dialog_daten_generic", lambda _daten, edit_type=None: [])
    monkeypatch.setattr(dialogs, "update_dialog_record_json", _unexpected_update)
    monkeypatch.setattr(dialogs, "update_dialog_record_central", _unexpected_update)

    app = _build_app()
    with TestClient(app) as client:
        response = client.post(
            f"/api/dialogs/{DIALOG_GUID}/draft/{DRAFT_ID}/commit",
            json={},
        )

    assert response.status_code == 400
    assert "MODULE=show" in str(response.json().get("detail", ""))

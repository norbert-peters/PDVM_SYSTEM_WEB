import asyncio
from types import SimpleNamespace

import pytest

from app.core import dropdown_service


def _fake_gcs() -> SimpleNamespace:
    return SimpleNamespace(
        stichtag=9999365.0,
        _system_pool=None,
        _mandant_pool=None,
    )


def test_resolve_dropdown_rejects_unknown_source(monkeypatch):
    gcs = _fake_gcs()

    with pytest.raises(ValueError, match="DROPDOWN_SOURCE_INVALID"):
        asyncio.run(
            dropdown_service.resolve_dropdown_by_config(
                gcs,
                dropdown_config={"source": "unknown", "key": "x"},
                language="de-de",
            )
        )


def test_resolve_dropdown_requires_explicit_source_when_enabled(monkeypatch):
    gcs = _fake_gcs()
    monkeypatch.setattr(dropdown_service.settings, "DROPDOWN_REQUIRE_EXPLICIT_SOURCE", True)

    with pytest.raises(ValueError, match="source fehlt"):
        asyncio.run(
            dropdown_service.resolve_dropdown_by_config(
                gcs,
                dropdown_config={"key": "abc", "feld": "anrede"},
                language="de-de",
            )
        )


def test_prefix_dropdown_rejects_disallowed_prefix(monkeypatch):
    gcs = _fake_gcs()
    monkeypatch.setattr(dropdown_service.settings, "DROPDOWN_PREFIX_WHITELIST", "msy_,tst_")

    with pytest.raises(ValueError, match="DROPDOWN_PREFIX_NOT_ALLOWED"):
        asyncio.run(
            dropdown_service.resolve_dropdown_by_config(
                gcs,
                dropdown_config={"source": "prefix_multi_table", "prefix": "sys_"},
                language="de-de",
            )
        )


def test_prefix_dropdown_enforces_cap_and_uses_cache(monkeypatch):
    gcs = _fake_gcs()
    calls = {"list": 0, "fetch": 0}

    async def _fake_list_tables(_gcs, *, prefix: str, timeout_seconds: float):
        calls["list"] += 1
        return ["msy_persondaten"]

    async def _fake_fetch_rows(_gcs, *, table: str, limit: int, timeout_seconds: float):
        calls["fetch"] += 1
        return [
            {"uid": "00000000-0000-0000-0000-000000000001", "name": "A"},
            {"uid": "00000000-0000-0000-0000-000000000002", "name": "B"},
            {"uid": "00000000-0000-0000-0000-000000000003", "name": "C"},
        ]

    monkeypatch.setattr(dropdown_service.settings, "DROPDOWN_PREFIX_WHITELIST", "msy_")
    monkeypatch.setattr(dropdown_service.settings, "DROPDOWN_PREFIX_MAX_RESULTS", 2)
    monkeypatch.setattr(dropdown_service.settings, "DROPDOWN_PREFIX_CACHE_TTL_SECONDS", 999.0)
    monkeypatch.setattr(dropdown_service, "_list_tables_for_prefix", _fake_list_tables)
    monkeypatch.setattr(dropdown_service, "_fetch_table_lookup_rows", _fake_fetch_rows)

    result_1 = asyncio.run(
        dropdown_service.resolve_dropdown_by_config(
            gcs,
            dropdown_config={"source": "prefix_multi_table", "prefix": "msy_", "limit": 10},
            language="de-de",
        )
    )
    result_2 = asyncio.run(
        dropdown_service.resolve_dropdown_by_config(
            gcs,
            dropdown_config={"source": "prefix_multi_table", "prefix": "msy_", "limit": 10},
            language="de-de",
        )
    )

    assert len(result_1.get("options") or []) == 2
    assert len(result_2.get("options") or []) == 2
    assert calls["list"] == 1
    assert calls["fetch"] == 1


def test_prefix_dropdown_timeout_is_handled(monkeypatch):
    gcs = _fake_gcs()

    async def _timeout_list(_gcs, *, prefix: str, timeout_seconds: float):
        raise TimeoutError()

    monkeypatch.setattr(dropdown_service.settings, "DROPDOWN_PREFIX_WHITELIST", "msy_")
    monkeypatch.setattr(dropdown_service, "_list_tables_for_prefix", _timeout_list)

    with pytest.raises(ValueError, match="DROPDOWN_PREFIX_TIMEOUT"):
        asyncio.run(
            dropdown_service.resolve_dropdown_by_config(
                gcs,
                dropdown_config={"source": "prefix_multi_table", "prefix": "msy_"},
                language="de-de",
            )
        )


def test_static_dropdown_allows_uppercase_legacy_config_keys(monkeypatch):
    gcs = _fake_gcs()

    async def _fake_get_mapping(*args, **kwargs):
        return {
            "map": {"m": "Herr"},
            "options": [{"key": "m", "value": "Herr"}],
            "language": "DE-DE",
            "default_language": "DE-DE",
        }

    monkeypatch.setattr(dropdown_service, "get_dropdown_mapping_for_field", _fake_get_mapping)

    result = asyncio.run(
        dropdown_service.resolve_dropdown_by_config(
            gcs,
            dropdown_config={
                "SOURCE": "static",
                "TABLE": "sys_dropdowndaten",
                "KEY": "2a60c785-0829-46db-a16b-9369596fab63",
                "FELD": "anrede",
                "GROUP": "",
            },
            language="de-de",
        )
    )

    assert isinstance(result.get("map"), dict)
    assert result["map"].get("m") == "Herr"

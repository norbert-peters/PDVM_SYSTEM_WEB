import asyncio
import types
import uuid

import pytest

from app.core import text_template_service as texts
from app.core.pdvm_datenbank import PdvmDatabase


def _release(status="approved"):
    return {"STATUS": status, "VERSION": "v1.0.0", "APPROVED_BY": "x" if status == "approved" else "",
            "APPROVED_AT": "2026-11-14T10:00:00+00:00" if status == "approved" else ""}


def _daten(status_de="approved", status_en="approved", **root):
    return {
        "ROOT": {"TEMPLATE_KEY": "PASSWORD_RESET", "VARIABLES": ["otp", "expires_minutes"],
                 "REQUIRED_VARIABLES": ["otp"], **root},
        "DE-DE": {"SUBJECT": "Betreff", "BODY": "Passwort: {{otp}} ({{ expires_minutes }} min)",
                  "BODY_HTML": "<p>{{otp}}</p>", **_release(status_de)},
        "EN-US": {"SUBJECT": "Subject", "BODY": "Password: {{otp}}", **_release(status_en)},
    }


def _template(origin="system", **kw):
    return texts.TemplateRow(str(uuid.uuid4()), "T", _daten(**kw), origin)


def test_render_replaces_placeholders_and_rejects_unknown_ones():
    assert texts.render_text("a {{x}} b {{ y }}", {"x": 1, "y": "z"}) == "a 1 b z"
    assert texts.render_text("{{x}}", {"x": "<b>&"}, escape=True) == "&lt;b&gt;&amp;"
    with pytest.raises(texts.TextTemplateError):
        texts.render_text("{{fehlt}}", {})


def test_message_uses_first_approved_language_and_escapes_html():
    tpl = _template()
    msg = texts.render_message(tpl, "DE-DE", {"otp": "<A&B>", "expires_minutes": 5})
    assert msg["body"] == "Passwort: <A&B> (5 min)" and msg["body_html"] == "<p>&lt;A&amp;B&gt;</p>"
    assert texts.render_message(tpl, "EN-US", {"otp": "X"})["body_html"] is None
    with pytest.raises(texts.TextTemplateError):
        texts.render_message(tpl, "DE-DE", {"expires_minutes": 1})


def test_only_approved_languages_are_selected_and_mandant_falls_back_to_system():
    mandant, system = _template("mandant", status_de="review"), _template("system")
    # DE ist im Mandanten nicht freigegeben -> Systemvorlage; EN ist freigegeben -> Mandantenvorlage
    assert texts.select_group([mandant, system], texts.language_chain("DE-DE"))[0].origin == "system"
    assert texts.select_group([mandant, system], texts.language_chain("EN-US"))[0].origin == "mandant"
    # Sprache ohne Fassung (IT) faellt auf die Standardsprache zurueck
    assert texts.select_group([system], texts.language_chain("IT-IT"))[1] == "DE-DE"
    with pytest.raises(texts.NoApprovedLanguageError):
        texts.select_group([_template(status_de="review", status_en="new")], texts.language_chain("DE-DE"))


def test_validation_reports_undeclared_missing_and_release_problems():
    assert texts.validate_template(_daten()) == []
    bad = _daten()
    bad["DE-DE"]["BODY"] = "Kein Passwort, aber {{unbekannt}}"
    errors = " ".join(texts.validate_template(bad))
    assert "unbekannt" in errors and "otp" in errors
    unsigned = _daten()
    unsigned["DE-DE"]["APPROVED_BY"] = ""
    assert "Freigabe" in " ".join(texts.validate_template(unsigned))
    assert texts.validate_template({"ROOT": {}, "DE-DE": {"SUBJECT": "", "BODY": ""}})


def test_source_hash_ignores_identity_and_release_but_tracks_text():
    a, b = _daten(), _daten(status_de="review")
    b["ROOT"]["SELF_GUID"] = "andere-uid"
    assert texts.source_hash(a) == texts.source_hash(b)
    b["DE-DE"]["BODY"] += "!"
    assert texts.source_hash(a) != texts.source_hash(b)


def _gcs(*roles):
    return types.SimpleNamespace(benutzer=types.SimpleNamespace(data={"PERMISSIONS": {"ROLES": list(roles)}}), user_guid="u1")


def _guard(table, new, old=None, gcs=None, monkeypatch=None):
    async def fake_get(self, uid, **kw):
        return {"daten": old} if old is not None else None

    PdvmDatabase.get_by_uid, original = fake_get, PdvmDatabase.get_by_uid
    try:
        return asyncio.run(texts.guard_write(
            table=table, uid=uuid.uuid4(), new_daten=new, gcs=gcs, actor_user_uid=None, system_pool=None, mandant_pool=None))
    finally:
        PdvmDatabase.get_by_uid = original


def test_guard_requires_role_per_table():
    with pytest.raises(texts.TextTemplateError):
        _guard(texts.MANDANT_TABLE, _daten(), _daten(), _gcs("user"))
    with pytest.raises(texts.TextTemplateError):
        _guard(texts.SYSTEM_TABLE, _daten(), _daten(), _gcs("admin"))  # System nur mit Rolle 'vorlagen'
    assert _guard(texts.SYSTEM_TABLE, _daten(), _daten(), _gcs("vorlagen"))
    assert _guard(texts.MANDANT_TABLE, _daten(), _daten(), _gcs("admin"))


def test_text_change_resets_to_review_and_needs_explicit_approval():
    old, new = _daten(), _daten()
    new["DE-DE"]["BODY"] += " neu"
    out = _guard(texts.MANDANT_TABLE, new, old, _gcs("admin"))
    assert out["DE-DE"]["STATUS"] == "review" and out["DE-DE"]["APPROVED_BY"] == ""
    assert out["EN-US"]["STATUS"] == "approved"  # unveraenderte Sprache bleibt freigegeben
    # explizite Freigabe im naechsten Speichern: Benutzer, Zeit und neue Version werden gesetzt
    again = _daten(status_de="review")
    again["DE-DE"].update({k: out["DE-DE"][k] for k in ("SUBJECT", "BODY", "BODY_HTML")})
    again["DE-DE"]["STATUS"] = "approved"
    approved = _guard(texts.MANDANT_TABLE, again, out, _gcs("admin"))["DE-DE"]
    assert approved["STATUS"] == "approved" and approved["VERSION"] == "v1.0.1" and approved["APPROVED_BY"] == "u1"
    with pytest.raises(texts.TextTemplateError):  # ohne Freigaberecht gar nicht
        _guard(texts.MANDANT_TABLE, again, out, _gcs("user"))


def test_guard_protects_key_variables_and_source_and_normalizes_lists():
    old = _daten(SOURCE_UID="s1", SOURCE_HASH="h1")
    changed = _daten(SOURCE_UID="fremd", SOURCE_HASH="x")
    changed["ROOT"]["VARIABLES"] = "otp, expires_minutes"  # Text statt Liste: gleicher Inhalt
    out = _guard(texts.MANDANT_TABLE, changed, old, _gcs("admin"))
    assert out["ROOT"]["SOURCE_UID"] == "s1" and out["ROOT"]["VARIABLES"] == ["otp", "expires_minutes"]
    changed["ROOT"]["VARIABLES"] = "otp"
    with pytest.raises(texts.TextTemplateError):
        _guard(texts.MANDANT_TABLE, changed, old, _gcs("admin"))
    changed = _daten()
    changed["ROOT"]["TEMPLATE_KEY"] = "ANDERS"
    with pytest.raises(texts.TextTemplateError):
        _guard(texts.MANDANT_TABLE, changed, old, _gcs("admin"))


def test_internal_writes_without_session_are_validated_but_keep_release_state():
    assert _guard(texts.MANDANT_TABLE, _daten(), None, None)["DE-DE"]["STATUS"] == "approved"
    broken = _daten()
    broken["DE-DE"]["BODY"] = "ohne Pflichtvariable"
    with pytest.raises(texts.TextTemplateError):
        _guard(texts.MANDANT_TABLE, broken, None, None)


class _Pool:
    def __init__(self, rows):
        self.rows = rows

    def acquire(self):
        pool = self

        class _Ctx:
            async def __aenter__(self_inner):
                return self_inner

            async def __aexit__(self_inner, *exc):
                return False

            async def fetch(self_inner, sql, *args):
                return pool.rows

        return _Ctx()


def test_candidates_put_mandant_before_system_and_system_only_without_mandant_db():
    texts.invalidate_text_template_cache()
    row = {"uid": uuid.uuid4(), "name": "S", "daten": _daten()}
    system, mandant = _Pool([row]), _Pool([dict(row, uid=uuid.uuid4())])
    assert [c.origin for c in asyncio.run(texts.load_candidates("PASSWORD_RESET", system_pool=system, mandant_pool=mandant))] == [
        "mandant", "system"]
    assert [c.origin for c in asyncio.run(texts.load_candidates("PASSWORD_RESET", system_pool=system))] == ["system"]
    with pytest.raises(texts.TextTemplateError):
        asyncio.run(texts.load_candidates("GIBT_ES_NICHT", system_pool=_Pool([])))


def test_writes_to_template_tables_clear_the_cache():
    texts._cache[("k",)] = (1e18, object())
    PdvmDatabase("msy_textvorlagen", mandant_pool=object())._invalidate_caches_after_write()
    assert not texts._cache

def test_central_database_save_passes_the_session_to_the_gateway(monkeypatch):
    # Regression: ohne gcs galt der Dialog-Schreibzugriff als vertrauenswuerdig (Rollen/Statuslogik entfielen)
    from app.core import pdvm_central_datenbank as central_module

    seen = {}

    async def fake_update(**kwargs):
        seen.update(kwargs)

    class _Db:
        _system_pool = _mandant_pool = None

        async def get_row(self, uid):
            return {"uid": uid}

    monkeypatch.setattr(central_module, "update_record_central", fake_update)
    central = central_module.PdvmCentralDatabase("msy_textvorlagen", guid=str(uuid.uuid4()), _skip_load=True)
    central.db = _Db()
    session = object()
    asyncio.run(central.save_all_values(gcs=session))
    assert seen["gcs"] is session

def test_copy_groups_keeps_texts_and_resets_release_state():
    daten = {
        "ROOT": {"TEMPLATE_KEY": "K"},
        "DE-DE": {"SUBJECT": "S", "BODY": "B", "STATUS": "approved", "VERSION": "v1.0.2", "APPROVED_BY": "x", "APPROVED_AT": "y"},
        "OHNE_TEXT": {"FOO": 1},
    }
    groups = texts._copy_groups(daten)
    assert list(groups) == ["DE-DE"]
    assert groups["DE-DE"] == {"SUBJECT": "S", "BODY": "B", "STATUS": "review", "VERSION": "v1.0.2", "APPROVED_BY": "", "APPROVED_AT": ""}

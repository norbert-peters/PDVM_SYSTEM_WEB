import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "tools"))

import phase5_fix_misc as misc  # noqa: E402
import phase5_normalize_control_dict as cdict  # noqa: E402
import phase5_normalize_frames as frames  # noqa: E402

U666 = "66666666-6666-6666-6666-666666666666"
U555 = "55555555-5555-5555-5555-555555555555"
MOTHER = {"FIELD": "eingeben", "TYPE": "string", "LABEL": "eingeben", "TABLE": "sys_control_dict", "GRUPPE": "",
          "READ_ONLY": False, "CONFIGS": {}, "FELD": "eingeben"}


def row(uid, name, daten):
    return {"uid": uid, "name": name, "daten": daten}


def control(uid, name, field, table="sys_control_dict", gruppe="", **extra):
    ctrl = {"FIELD": field, "TYPE": "string", "LABEL": field, "TABLE": table, "GRUPPE": gruppe,
            "READ_ONLY": False, "CONFIGS": {}}
    ctrl.update(extra)
    return row(uid, name, {"ROOT": {"SELF_NAME": name}, "CONTROL": ctrl})


def mother_row():
    return row(U666, "SYS_666", {"ROOT": {}, "CONTROL": dict(MOTHER), "TEMPLATES": {"CONTROL": dict(MOTHER)}})


# --- sys_control_dict ---------------------------------------------------------------------------------------

def test_control_dict_removes_feld_and_fixes_names():
    rows = [
        mother_row(),
        control("a1", "SYS_TEXXT_KEY", "TEXT_KEY", table="sys_beschreibungen", FELD="TEXT_KEY"),
        control("a2", "SYS_OK", "OK", FELD="OK"),
    ]
    changes = {c.uid: c for c in cdict.plan(rows, used_uids=set())}
    assert changes["a1"].name == "SYS_TEXT_KEY"
    assert "FELD" not in changes["a1"].daten["CONTROL"]
    assert "FELD" not in changes["a2"].daten["CONTROL"]


def test_control_dict_mother_gets_new_properties_and_stays_synchronised():
    changes = {c.uid: c for c in cdict.plan([mother_row()], used_uids=set())}
    m = changes[U666].daten
    assert "FELD" not in m["CONTROL"]
    assert m["CONTROL"] == m["TEMPLATES"]["CONTROL"]
    assert "FIELDS_ELEMENTS" in m["CONTROL"] and "CONFIGS_ELEMENTS" in m["CONTROL"]


def test_control_dict_conflict_uses_feld_only_for_override_and_deletes_unused_tests():
    rows = [
        mother_row(),
        control("ef6a4b8a-0000-0000-0000-000000000000", "ASY_THEME_LIGHT", "LIGHT", table="asy_benutzer",
                FELD="THEME_LIGHT"),
        control("b1", "SYS_TEST", "eingeben", FELD="Test"),
    ]
    changes = {c.uid: c for c in cdict.plan(rows, used_uids=set())}
    assert changes["ef6a4b8a-0000-0000-0000-000000000000"].daten["CONTROL"]["FIELD"] == "THEME_LIGHT"
    assert changes["b1"].delete


def test_control_dict_duplicate_name_unused_is_deleted_used_is_kept():
    rows = [
        mother_row(),
        control("c1", "SYS_TAB", "TAB"),
        control("c2", "ASY_TAB", "TAB"),
        control("c3", "SYS_PRENT", "PARENT_GUID"),
        control("c4", "SYS_PARENT_GUID", "PARENT_GUID"),
    ]
    changes = {c.uid: c for c in cdict.plan(rows, used_uids={"c3"})}
    assert changes["c2"].delete
    assert "c3" not in changes or not changes["c3"].delete


# --- sys_framedaten -----------------------------------------------------------------------------------------

def frame(uid, name, fields):
    return row(uid, name, {"ROOT": {"SELF_NAME": name}, "FIELDS": fields})


def test_frames_layout_keys_become_upper_and_semantics_are_stripped():
    ctrl_uid = "11111111-1111-4111-8111-111111111111"
    controls = [mother_row(), control(ctrl_uid, "SYS_NAME", "NAME", gruppe="ROOT", LABEL="Name")]
    frm = frame("f1", "F", {ctrl_uid: {"tab": 2, "display_order": 30, "label": "Name", "type": "string"}})
    golden = {"f1": {"body": {"daten": {"FIELDS": {ctrl_uid: {"feld": "NAME", "type": "string", "label": "Name",
                                                                "gruppe": "ROOT", "table": "sys_control_dict"}}}}}}
    changes, new_controls, _ = frames.plan([frm], controls, golden)
    assert not new_controls
    assert changes[0].daten["FIELDS"][ctrl_uid] == {"TAB": 2, "DISPLAY_ORDER": 30}


def test_frames_inline_field_becomes_control_and_keeps_layout():
    key = "22222222-2222-4222-8222-222222222222"
    controls = [mother_row()]
    inline = {"feld": "WORKFLOW_NAME", "type": "string", "label": "Workflow Name", "gruppe": "FIELDS",
              "table": "SYS_DIALOGDATEN", "tab": 1, "display_order": 10, "read_only": False, "configs": {}}
    frm = frame("f1", "F", {key: inline})
    golden = {"f1": {"body": {"daten": {"FIELDS": {key: dict(inline)}}}}}
    changes, new_controls, _ = frames.plan([frm], controls, golden)
    assert len(new_controls) == 1
    new_uid, new = next(iter(new_controls.items()))
    assert new["name"] == "SYS_WORKFLOW_NAME"
    assert new["daten"]["CONTROL"]["FIELD"] == "WORKFLOW_NAME"
    assert new["daten"]["CONTROL"]["TABLE"] == "sys_dialogdaten"
    assert "FELD" not in new["daten"]["CONTROL"]
    assert changes[0].daten["FIELDS"] == {new_uid: {"TAB": 1, "DISPLAY_ORDER": 10}}


def test_frames_foreign_control_key_with_different_field_creates_own_control():
    foreign = "33333333-3333-4333-8333-333333333333"
    controls = [mother_row(), control(foreign, "SYS_GUID", "GUID", LABEL="Klicks fuer Edit")]
    inline = {"feld": "SELF_GUID", "type": "string", "label": "Self GUID", "gruppe": "ROOT",
              "table": "sys_dialogdaten", "tab": 1, "display_order": 10}
    frm = frame("f1", "F", {foreign: inline})
    golden = {"f1": {"body": {"daten": {"FIELDS": {foreign: dict(inline)}}}}}
    changes, new_controls, _ = frames.plan([frm], controls, golden)
    assert len(new_controls) == 1
    assert foreign not in changes[0].daten["FIELDS"]


def test_frames_dangling_layout_only_entries_are_removed_and_named_entries_kept():
    dangling = "44444444-4444-4444-8444-444444444444"
    frm = frame("f1", "F", {dangling: {"TAB": 4, "DISPLAY_ORDER": 10}, "CONTROL": {"element": {}}})
    changes, _, _ = frames.plan([frm], [mother_row()], {})
    assert dangling not in changes[0].daten["FIELDS"]
    assert "CONTROL" in changes[0].daten["FIELDS"]


def test_frames_lowercase_data_keys_are_documented_exceptions():
    key = "55555555-aaaa-4aaa-8aaa-555555555556"
    inline = {"feld": "tooltip", "type": "text", "label": "Tooltip", "gruppe": "MENU", "table": "SYS_MENUDATEN",
              "tab": 1, "display_order": 20}
    frm = frame("f1", "F", {key: inline})
    changes, new_controls, exceptions = frames.plan([frm], [mother_row()], {})
    assert not new_controls and exceptions
    assert not changes


# --- Menue-Tabellennamen ------------------------------------------------------------------------------------

def test_legacy_table_names_in_nested_data_are_renamed():
    data = {"a": {"command": {"params": {"table": "sys_security", "other": "sys_layout"}}}, "l": ["sys_benutzer", "x"]}
    new, n = misc.rename_tables(data)
    assert n == 2
    assert new["a"]["command"]["params"] == {"table": "msy_security", "other": "sys_layout"}
    assert new["l"] == ["asy_benutzer", "x"]

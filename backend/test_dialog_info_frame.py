"""Tests fuer das Standard-Info-Frame der Dialoge (Seed-Definition, Regeln 1.10/1.10b)."""
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "tools"))

from app.core.dialog_info import DIALOG_INFO_FRAME_GUID, DIALOG_INFO_GROUP, dialog_info_control_uid
from tools.seed_dialog_info_frame_v1 import INFO_TABS, build_specs

# erlaubte Control-Eigenschaften (Muttercontrol 666, Regel 1.10a)
MOTHER_CONTROL_KEYS = {
    "ABDATUM", "CONFIGS", "CONFIGS_ELEMENTS", "DEFAULT", "DISPLAY_ORDER", "DISPLAY_SHOW", "EXPERT_MODE", "EXPERT_ORDER",
    "FIELD", "FIELDS_ELEMENTS", "FILTER_TYPE", "GRUPPE", "HISTORICAL", "LABEL", "MODUL_TYPE", "NAME", "PARENT_GUID",
    "READ_ONLY", "SEARCHABLE", "SORTABLE", "SORT_BY_ORIGINAL", "SORT_DIRECTION", "SOURCE_PATH", "TAB", "TABLE", "TYPE",
    "UPPER_CASE",
}


def _specs():
    specs = build_specs()
    frame = next(s for s in specs if s.table == "sys_framedaten")
    controls = [s for s in specs if s.table == "sys_control_dict"]
    return frame, controls


def test_frame_uid_is_the_backend_constant_and_stable():
    frame, _ = _specs()
    assert frame.uid == DIALOG_INFO_FRAME_GUID
    assert frame.daten["ROOT"]["SELF_GUID"] == str(DIALOG_INFO_FRAME_GUID)
    # feste UID: eine Aenderung wuerde bestehende Installationen vom Frame trennen
    assert str(DIALOG_INFO_FRAME_GUID) == str(uuid.uuid5(uuid.UUID("5c1d3e0a-7f4b-4a8e-9b21-6d0c4f3a9e17"), "frame:dialog_info"))


def test_controls_follow_rule_1_10():
    _, controls = _specs()
    names = [c.name for c in controls]
    assert len(names) == len(set(names)) and len(controls) == sum(len(items) for _, _, items in INFO_TABS)
    for spec in controls:
        assert set(spec.daten) == {"ROOT", "CONTROL"}
        control = spec.daten["CONTROL"]
        assert set(control) <= MOTHER_CONTROL_KEYS
        assert control["FIELD"] == control["FIELD"].upper() and "FELD" not in control
        assert control["NAME"] == spec.name == spec.daten["ROOT"]["SELF_NAME"]
        assert spec.name.startswith("SYS_") and spec.name == spec.name.upper()
        assert control["GRUPPE"] == DIALOG_INFO_GROUP and control["READ_ONLY"] is True and control["TYPE"] == "string"
        assert spec.uid == dialog_info_control_uid(control["FIELD"]) and spec.daten["ROOT"]["SELF_GUID"] == str(spec.uid)


def test_frame_fields_reference_controls_and_carry_only_layout_keys():
    frame, controls = _specs()
    fields = frame.daten["FIELDS"]
    assert set(fields) == {str(c.uid) for c in controls}
    for value in fields.values():
        assert set(value) == {"TAB", "SOURCE_PATH", "DISPLAY_ORDER"}  # Regel 1.10b: keine Control-Kopien im Frame
    root = frame.daten["ROOT"]
    assert root["TABS"] == len(INFO_TABS) and root["FRAME_TYPE"] == "popup" and root["EDIT_TYPE"] == "pdvm_edit"
    tabs = {t["TAB"] for t in root["TAB_ELEMENTS"].values()}
    assert tabs == {v["TAB"] for v in fields.values()} == {t for t, _, _ in INFO_TABS}


def test_dialog_definition_exposes_info_frame_guid():
    import inspect
    from app.api import dialogs

    source = inspect.getsource(dialogs.get_dialog_definition)
    assert '"info_frame_guid": str(DIALOG_INFO_FRAME_GUID)' in source

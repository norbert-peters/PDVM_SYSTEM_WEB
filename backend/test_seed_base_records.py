import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "tools"))

from seed_base_records import U000, U555, U666, plan_table  # noqa: E402

OPEN = datetime(9999, 12, 31, 23, 59, 59)


def row(uid, name="x", daten=None, link_uid=None):
    return {"uid": uid, "name": name, "gilt_bis": OPEN, "daten": daten or {}, "link_uid": link_uid}


def full_base():
    return [
        row(U000, "Tabellen-Metadaten", {"ROOT": {}, "TABLE_INFO": {"version": "2.0"}}),
        row(U555, "Templates", {"ROOT": {}, "TEMPLATES": {}}),
        row(U666, "Template neuer Satz", {"ROOT": {}, "TEMPLATES": {"TABLE_INFO": {"version": "2.0"}}}),
    ]


def by_uid(works):
    return {w.uid: w for w in works}


def test_complete_table_needs_no_change():
    assert plan_table("tst_x", full_base(), True) == []


def test_missing_base_records_are_created():
    works = by_uid(plan_table("tst_x", [], True))
    assert set(works) == {U000, U555, U666}
    assert all(w.created for w in works.values())
    assert "TABLE_INFO" in works[U666].daten["TEMPLATES"]
    assert "TABLE_INFO" not in works[U666].daten


def test_wrong_uid_base_record_is_rekeyed():
    rows = [
        row("2a3263a0-b2f1-437c-8362-f8a1ffe159a1", "Tabellen-Metadaten",
            {"ROOT": {"SELF_GUID": "2a3263a0-b2f1-437c-8362-f8a1ffe159a1", "SELF_LINK_UID": U000},
             "TABLE_INFO": {"version": "2.0"}}),
        row(U555, daten={"ROOT": {}, "TEMPLATES": {}}),
        row(U666, daten={"ROOT": {}, "TEMPLATES": {"TABLE_INFO": {}}}),
    ]
    works = plan_table("msy_x", rows, True)
    assert len(works) == 1
    w = works[0]
    assert w.rekeyed and w.uid == U000 and not w.reserved_edit
    assert w.daten["ROOT"]["SELF_GUID"] == U000
    # TABLE_INFO bleibt im umgeschluesselten 000-Satz erhalten
    assert "TABLE_INFO" in w.daten


def test_666_gets_templates_and_table_info_and_is_reserved_edit():
    rows = full_base()
    rows[2] = row(U666, daten={"ROOT": {}, "FIELDS": {}})
    works = plan_table("tst_x", rows, True)
    assert len(works) == 1
    assert works[0].reserved_edit
    assert works[0].daten["TEMPLATES"]["TABLE_INFO"] == {"version": "2.0"}
    assert works[0].daten["FIELDS"] == {}


def test_top_level_table_info_in_666_is_moved():
    rows = full_base()
    rows[2] = row(U666, daten={"ROOT": {}, "TABLE_INFO": {"version": "9"}, "TEMPLATES": {}})
    w = plan_table("tst_x", rows, True)[0]
    assert "TABLE_INFO" not in w.daten
    assert w.daten["TEMPLATES"]["TABLE_INFO"] == {"version": "9"}


def test_table_info_removed_from_fachdatensatz_only():
    rows = full_base() + [row("11111111-1111-4111-8111-111111111111", "a",
                              {"ROOT": {"SELF_NAME": "a"}, "TABLE_INFO": {"version": "1"}})]
    works = plan_table("tst_x", rows, True)
    assert len(works) == 1
    assert "TABLE_INFO" not in works[0].daten
    assert not works[0].reserved_edit


def test_table_info_removed_from_555():
    rows = full_base()
    rows[1] = row(U555, "Templates", {"ROOT": {}, "TEMPLATES": {}, "TABLE_INFO": {}})
    works = plan_table("tst_x", rows, True)
    assert len(works) == 1 and works[0].uid == U555 and works[0].reserved_edit
    assert "TABLE_INFO" not in works[0].daten


def test_control_dict_mother_is_synchronised():
    rows = full_base()
    rows[2] = row(U666, daten={"ROOT": {}, "TEMPLATES": {"TABLE_INFO": {}, "CONTROL": {"FIELD": "X", "TYPE": "string"}}})
    w = plan_table("sys_control_dict", rows, True)[0]
    assert w.daten["CONTROL"] == w.daten["TEMPLATES"]["CONTROL"]

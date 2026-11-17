from app.api.menu import filter_menu_group_by_roles


def _menu():
    return {
        "root": {"label": "Verwaltung", "type": "SUBMENU"},
        "plain": {"label": "Für alle", "parent_guid": "root"},
        "new": {"label": "Neuer Mandant", "parent_guid": "root", "roles": ["superadmin"]},
        "only": {"label": "Zweig", "type": "SUBMENU", "roles": "admin, develop"},
        "only_child": {"label": "Kind", "parent_guid": "only"},
        "tail": {"label": "Allein", "type": "SUBMENU"},
        "tail_child": {"label": "Nur für Admin", "parent_guid": "tail", "roles": ["admin"]},
    }


def test_items_without_roles_stay_visible_for_everyone():
    items = {"a": {"label": "A"}, "b": {"label": "B", "roles": []}}
    assert filter_menu_group_by_roles(items, {"user"}) == items


def test_roles_hide_items_with_their_children_and_branches_that_become_empty():
    visible = filter_menu_group_by_roles(_menu(), {"user"})
    assert set(visible) == {"root", "plain"}

    visible = filter_menu_group_by_roles(_menu(), {"admin"})
    assert set(visible) == {"root", "plain", "only", "only_child", "tail", "tail_child"}


def test_superadmin_sees_everything_and_roles_are_case_insensitive():
    assert filter_menu_group_by_roles(_menu(), {"superadmin"}) == _menu()
    assert "only" in filter_menu_group_by_roles({"only": {"roles": ["ADMIN"]}}, {"admin"})

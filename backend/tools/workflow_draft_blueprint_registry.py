"""Registry fuer Workflow-Draft-Container Blueprint Artefakte.

Ziel:
- deterministische Dialog/View/Frame Blueprint-Daten fuer Draft-Container Workflow
- Wiederverwendung in Seeder/Health-Checks
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Dict, List


NAMESPACE = uuid.UUID("8b3216e8-a7b9-4a99-9188-0549f3a7b1e1")


def _uid(table_name: str, key: str) -> str:
    return str(uuid.uuid5(NAMESPACE, f"{table_name}:{key}"))


@dataclass(frozen=True)
class BlueprintSpec:
    category: str
    table_name: str
    key: str
    name: str
    daten: Dict[str, Any]

    @property
    def uid(self) -> uuid.UUID:
        return uuid.uuid5(NAMESPACE, f"{self.table_name}:{self.key}")


def _view_data(source_table: str) -> Dict[str, Any]:
    return {
        "ROOT": {
            "SELF_GUID": "",
            "SELF_NAME": "",
            "TABLE": source_table,
            "EDIT_TYPE": "view",
            "FILTER": {},
            "SORT": {"column": "modified_at", "reverse": True},
            "PROJECTION": ["name", "modified_at"],
        }
    }


def _field(
    frame_key: str,
    field: str,
    label: str,
    control_type: str,
    order: int,
    *,
    dropdown_options: List[Dict[str, str]] | None = None,
) -> tuple[str, Dict[str, Any]]:
    field_upper = str(field).upper()
    field_guid = str(uuid.uuid5(NAMESPACE, f"frame-field:{frame_key}:{field_upper}"))
    return (
        field_guid,
        {
            "tab": 1,
            "feld": field_upper,
            "name": f"wf_{frame_key}_{field.lower()}",
            "type": control_type,
            "label": label,
            "table": "SYS_CONTROL_DICT",
            "gruppe": "FIELDS",
            "abdatum": False,
            "configs": {
                "help": {"key": "", "feld": "", "table": "", "gruppe": ""},
                "dropdown": {
                    "key": "",
                    "feld": "",
                    "table": "",
                    "gruppe": "",
                    "options": list(dropdown_options or []),
                },
            },
            "tooltip": "",
            "read_only": False,
            "historical": False,
            "source_path": "fields",
            "display_order": order,
        },
    )


def _frame_data(tab_head: str, fields: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "ROOT": {
            "SELF_GUID": "",
            "SELF_NAME": "",
            "EDIT_TYPE": "pdvm_edit",
            "TAB_ELEMENTS": {"TAB_01": {"TAB": 1, "HEAD": tab_head, "GRUPPE": "FIELDS"}},
        },
        "FIELDS": fields,
    }


def _workflow_builder_dialog_data() -> Dict[str, Any]:
    return {
        "ROOT": {
            "SELF_GUID": "",
            "SELF_NAME": "",
            "TABLE": "dev_workflow_draft",
            "DIALOG_TYPE": "work",
            "OPEN_EDIT": "button",
            "SELECTION_MODE": "single",
            "CREATE_FRAME_GUID": _uid("sys_framedaten", "workflow_draft_create_frame_template"),
            "CREATE_REQUIRED": ["NAME"],
            "CREATE_DEFAULTS": {},
            "TAB_ELEMENTS": {
                "TAB_01": {
                    "TAB": 1,
                    "HEAD": "Overview",
                    "MODULE": "view",
                    "GUID": _uid("sys_viewdaten", "workflow_draft_overview_view_template"),
                    "EDIT_TYPE": "view",
                    "TABLE": "dev_workflow_draft",
                },
                "TAB_02": {
                    "TAB": 2,
                    "HEAD": "Setup",
                    "MODULE": "edit",
                    "GUID": _uid("sys_framedaten", "workflow_draft_setup_frame_template"),
                    "EDIT_TYPE": "pdvm_edit",
                    "TABLE": "dev_workflow_draft",
                },
                "TAB_03": {
                    "TAB": 3,
                    "HEAD": "Tabs",
                    "MODULE": "edit",
                    "GUID": _uid("sys_framedaten", "workflow_draft_tabs_frame_template"),
                    "EDIT_TYPE": "pdvm_edit",
                    "TABLE": "dev_workflow_draft_item",
                },
                "TAB_04": {
                    "TAB": 4,
                    "HEAD": "View",
                    "MODULE": "edit",
                    "GUID": _uid("sys_framedaten", "workflow_draft_view_frame_template"),
                    "EDIT_TYPE": "pdvm_edit",
                    "TABLE": "dev_workflow_draft_item",
                },
                "TAB_05": {
                    "TAB": 5,
                    "HEAD": "Content",
                    "MODULE": "edit",
                    "GUID": _uid("sys_framedaten", "workflow_draft_content_frame_template"),
                    "EDIT_TYPE": "pdvm_edit",
                    "TABLE": "dev_workflow_draft_item",
                },
                "TAB_06": {
                    "TAB": 6,
                    "HEAD": "Build",
                    "MODULE": "acti",
                    "GUID": _uid("sys_framedaten", "workflow_draft_build_frame_template"),
                    "EDIT_TYPE": "pdvm_edit",
                    "TABLE": "dev_workflow_draft",
                },
            },
        }
    }


def _dictionary_dialog_data() -> Dict[str, Any]:
    return {
        "ROOT": {
            "SELF_GUID": "",
            "SELF_NAME": "",
            "TABLE": "sys_control_dict",
            "DIALOG_TYPE": "norm",
            "OPEN_EDIT": "button",
            "SELECTION_MODE": "single",
            "TAB_ELEMENTS": {
                "TAB_01": {
                    "TAB": 1,
                    "HEAD": "Dictionary View",
                    "MODULE": "view",
                    "GUID": _uid("sys_viewdaten", "workflow_dictionary_view_template"),
                    "EDIT_TYPE": "view",
                    "TABLE": "sys_control_dict",
                },
                "TAB_02": {
                    "TAB": 2,
                    "HEAD": "Dictionary Edit",
                    "MODULE": "edit",
                    "GUID": _uid("sys_framedaten", "workflow_dictionary_frame_template"),
                    "EDIT_TYPE": "pdvm_edit",
                    "TABLE": "sys_control_dict",
                },
            },
        }
    }


def get_workflow_draft_blueprint_specs() -> List[BlueprintSpec]:
    create_fields = {}

    setup_fields = dict(
        [
            _field("draft_setup", "WORKFLOW_NAME", "Workflow Name", "string", 10),
            _field("draft_setup", "TARGET_TABLE", "Target Table", "string", 20),
            _field("draft_setup", "DESCRIPTION", "Description", "text", 30),
        ]
    )

    tabs_fields = dict(
        [
            _field("draft_tabs", "TAB_HEAD", "Tab Head", "string", 10),
            _field("draft_tabs", "TAB_MODULE", "Tab Module", "dropdown", 20),
            _field("draft_tabs", "TAB_GUID", "Tab GUID", "string", 30),
            _field("draft_tabs", "ADD_TAB_ACTION", "Add Tab", "action", 40),
            _field("draft_tabs", "REMOVE_TAB_ACTION", "Remove Tab", "action", 50),
        ]
    )

    content_fields = dict(
        [
            _field("draft_content", "TAB_REF", "Tab Ref", "string", 10),
            _field("draft_content", "VIEW_GUID", "View GUID", "string", 20),
            _field("draft_content", "FRAME_GUID", "Frame GUID", "string", 30),
            _field("draft_content", "EDIT_TYPE", "Edit Type", "string", 40),
            _field("draft_content", "SAVE_CONTENT_ACTION", "Save Content", "action", 50),
        ]
    )

    view_fields = dict(
        [
            _field("draft_view", "VIEW_NAME", "View Name", "string", 10),
            _field("draft_view", "VIEW_TABLE", "View Table", "string", 20),
            _field("draft_view", "VIEW_PROJECTION", "View Projection", "text", 30),
            _field("draft_view", "SAVE_VIEW_ACTION", "Save View", "action", 40),
        ]
    )

    build_fields = dict(
        [
            _field("draft_build", "VALIDATE_ACTION", "Validate", "action", 10),
            _field("draft_build", "BUILD_ACTION", "Build", "action", 20),
            _field("draft_build", "ABORT_ACTION", "Abort", "action", 30),
        ]
    )

    dictionary_fields = dict(
        [
            _field("dictionary", "DICTIONARY_SEARCH", "Dictionary Search", "string", 10),
            _field("dictionary", "CONTROL_FIELD", "Control Field", "string", 20),
            _field("dictionary", "CONTROL_TYPE", "Control Type", "string", 30),
            _field("dictionary", "CREATE_CONTROL_ACTION", "Create Control", "action", 40),
        ]
    )

    return [
        BlueprintSpec(
            "dialog",
            "sys_dialogdaten",
            "workflow_draft_builder_dialog_template",
            "WORKFLOW_DRAFT_BUILDER_DIALOG_TEMPLATE",
            _workflow_builder_dialog_data(),
        ),
        BlueprintSpec(
            "dialog",
            "sys_dialogdaten",
            "workflow_dictionary_dialog_template",
            "WORKFLOW_DICTIONARY_DIALOG_TEMPLATE",
            _dictionary_dialog_data(),
        ),
        BlueprintSpec(
            "view",
            "sys_viewdaten",
            "workflow_draft_overview_view_template",
            "WORKFLOW_DRAFT_OVERVIEW_VIEW_TEMPLATE",
            _view_data("dev_workflow_draft"),
        ),
        BlueprintSpec(
            "view",
            "sys_viewdaten",
            "workflow_draft_items_view_template",
            "WORKFLOW_DRAFT_ITEMS_VIEW_TEMPLATE",
            _view_data("dev_workflow_draft_item"),
        ),
        BlueprintSpec(
            "view",
            "sys_viewdaten",
            "workflow_dictionary_view_template",
            "WORKFLOW_DICTIONARY_VIEW_TEMPLATE",
            _view_data("sys_control_dict"),
        ),
        BlueprintSpec(
            "frame",
            "sys_framedaten",
            "workflow_draft_create_frame_template",
            "WORKFLOW_DRAFT_CREATE_FRAME_TEMPLATE",
            _frame_data("Create", create_fields),
        ),
        BlueprintSpec(
            "frame",
            "sys_framedaten",
            "workflow_draft_setup_frame_template",
            "WORKFLOW_DRAFT_SETUP_FRAME_TEMPLATE",
            _frame_data("Setup", setup_fields),
        ),
        BlueprintSpec(
            "frame",
            "sys_framedaten",
            "workflow_draft_tabs_frame_template",
            "WORKFLOW_DRAFT_TABS_FRAME_TEMPLATE",
            _frame_data("Tabs", tabs_fields),
        ),
        BlueprintSpec(
            "frame",
            "sys_framedaten",
            "workflow_draft_content_frame_template",
            "WORKFLOW_DRAFT_CONTENT_FRAME_TEMPLATE",
            _frame_data("Content", content_fields),
        ),
        BlueprintSpec(
            "frame",
            "sys_framedaten",
            "workflow_draft_view_frame_template",
            "WORKFLOW_DRAFT_VIEW_FRAME_TEMPLATE",
            _frame_data("View", view_fields),
        ),
        BlueprintSpec(
            "frame",
            "sys_framedaten",
            "workflow_draft_build_frame_template",
            "WORKFLOW_DRAFT_BUILD_FRAME_TEMPLATE",
            _frame_data("Build", build_fields),
        ),
        BlueprintSpec(
            "frame",
            "sys_framedaten",
            "workflow_dictionary_frame_template",
            "WORKFLOW_DICTIONARY_FRAME_TEMPLATE",
            _frame_data("Dictionary", dictionary_fields),
        ),
    ]


def with_resolved_self_fields(spec: BlueprintSpec) -> Dict[str, Any]:
    data = dict(spec.daten)
    root = data.get("ROOT") if isinstance(data.get("ROOT"), dict) else {}
    root = dict(root)
    root["SELF_GUID"] = str(spec.uid)
    root["SELF_NAME"] = spec.name
    data["ROOT"] = root
    return data

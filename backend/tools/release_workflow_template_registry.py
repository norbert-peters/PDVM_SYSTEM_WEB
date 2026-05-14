"""Registry fuer Release-Workflow-Templates (Phase A).

Ziel:
- zentrale, deterministische Definition fuer fehlende Workflow-Templates
- Wiederverwendung in Seed- und Health-Check-Tools
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Dict, List


NAMESPACE = uuid.UUID("c2f8b2f9-5b7b-4b76-9c58-b5c57c6f14d1")

WORKFLOW_CONTROL_DEFS = [
    ("RELEASE_TYPE", "Release Type", "dropdown"),
    ("TARGET_ENV", "Target Environment", "dropdown"),
    ("SOURCE_DB_ROLE", "Source DB Role", "dropdown"),
    ("TARGET_DB_ROLE", "Target DB Role", "dropdown"),
    ("POLICY_MODE", "Policy Mode", "dropdown"),
    ("PACKAGE_HASH", "Package Hash", "string"),
    ("SOURCE_COMMIT", "Source Commit", "string"),
    ("TABLE_PREFIX_FILTER", "Table Prefix Filter", "string"),
    ("DICTIONARY_SEARCH", "Dictionary Search", "string"),
    ("CREATE_PROPERTY_ACTION", "Create Property", "action"),
    ("DRY_RUN_ACTION", "Dry Run", "action"),
    ("APPLY_ACTION", "Apply", "action"),
]

WORKFLOW_CONTROL_META = {
    field: {"label": label, "type": control_type}
    for field, label, control_type in WORKFLOW_CONTROL_DEFS
}


def _template_uid(table_name: str, key: str) -> str:
    """Deterministische GUID fuer ein Template-Spec (gleich wie TemplateSpec.uid)."""
    return str(uuid.uuid5(NAMESPACE, f"{table_name}:{key}"))


def _frame_field_uid(frame_key: str, field_name: str) -> str:
    """Deterministische GUID fuer ein Frame-Feld."""
    return str(uuid.uuid5(NAMESPACE, f"frame-field:{frame_key}:{field_name}"))


@dataclass(frozen=True)
class TemplateSpec:
    category: str
    table_name: str
    key: str
    name: str
    daten: Dict[str, Any]

    @property
    def uid(self) -> uuid.UUID:
        return uuid.uuid5(NAMESPACE, f"{self.table_name}:{self.key}")


def _dialog_data(dialog_type: str) -> Dict[str, Any]:
    setup_frame_guid = _template_uid("sys_framedaten", "workflow_setup_frame_template")
    dialog_frame_guid = _template_uid("sys_framedaten", "workflow_dialog_config_frame_template")
    dictionary_frame_guid = _template_uid("sys_framedaten", "workflow_property_mapping_frame_template")
    apply_frame_guid = _template_uid("sys_framedaten", "workflow_apply_frame_template")
    view_guid = _template_uid("sys_viewdaten", "release_candidate_view_template")

    return {
        "ROOT": {
            "SELF_GUID": "",
            "SELF_NAME": "",
            "DIALOG_TYPE": dialog_type,
            "OPEN_EDIT": "double_click",
            "SELECTION_MODE": "single",
            "TAB_ELEMENTS": {
                "TAB_01": {
                    "TAB": 1,
                    "HEAD": "Setup",
                    "MODULE": "edit",
                    "GUID": setup_frame_guid,
                    "EDIT_TYPE": "pdvm_edit",
                    "TABLE": "sys_release_state",
                },
                "TAB_02": {
                    "TAB": 2,
                    "HEAD": "Dialog",
                    "MODULE": "edit",
                    "GUID": dialog_frame_guid,
                    "EDIT_TYPE": "pdvm_edit",
                    "TABLE": "sys_dialogdaten",
                },
                "TAB_03": {
                    "TAB": 3,
                    "HEAD": "View",
                    "MODULE": "view",
                    "GUID": view_guid,
                    "EDIT_TYPE": "view",
                    "TABLE": "dev_release",
                },
                "TAB_04": {
                    "TAB": 4,
                    "HEAD": "Dictionary",
                    "MODULE": "edit",
                    "GUID": dictionary_frame_guid,
                    "EDIT_TYPE": "pdvm_edit",
                    "TABLE": "sys_control_dict",
                },
                "TAB_05": {
                    "TAB": 5,
                    "HEAD": "Build",
                    "MODULE": "acti",
                    "GUID": apply_frame_guid,
                    "EDIT_TYPE": "pdvm_edit",
                    "TABLE": "sys_release_state",
                },
            },
        }
    }


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


def _frame_field(
    frame_key: str,
    tab: int,
    field: str,
    label: str,
    control_type: str,
    display_order: int,
) -> tuple[str, Dict[str, Any]]:
    field_upper = str(field).upper()
    field_guid = _frame_field_uid(frame_key, field_upper)
    field_name = f"wf_{field_lower(frame_key, field_upper)}"

    return (
        field_guid,
        {
            "tab": tab,
            "feld": field_upper,
            "name": field_name,
            "type": control_type,
            "label": label,
            "table": "SYS_CONTROL_DICT",
            "gruppe": "FIELDS",
            "abdatum": False,
            "configs": {
                "help": {"key": "", "feld": "", "table": "", "gruppe": ""},
                "dropdown": {"key": "", "feld": "", "table": "", "gruppe": ""},
            },
            "tooltip": "",
            "read_only": False,
            "historical": False,
            "source_path": "fields",
            "display_order": display_order,
        },
    )


def field_lower(frame_key: str, field_upper: str) -> str:
    """Erzeugt einen stabilen Namen fuer Frame-Felder."""
    suffix = str(frame_key).replace("workflow_", "")
    return f"{suffix}_{field_upper.lower()}"


def _frame_fields_from_control_keys(frame_key: str, control_keys: List[str], tab: int = 1) -> Dict[str, Any]:
    fields: Dict[str, Any] = {}
    for idx, key in enumerate(control_keys, start=1):
        meta = WORKFLOW_CONTROL_META.get(str(key).upper())
        if not meta:
            continue
        guid, field = _frame_field(
            frame_key=frame_key,
            tab=tab,
            field=str(key).upper(),
            label=str(meta["label"]),
            control_type=str(meta["type"]),
            display_order=idx * 10,
        )
        fields[guid] = field
    return fields


def _frame_data(tab_head: str, frame_key: str, fields: Dict[str, Any] | None = None) -> Dict[str, Any]:
    return {
        "ROOT": {
            "SELF_GUID": "",
            "SELF_NAME": "",
            "EDIT_TYPE": "pdvm_edit",
            "TAB_ELEMENTS": {
                "TAB_01": {"TAB": 1, "HEAD": tab_head, "GRUPPE": "ROOT"}
            },
        },
        "FIELDS": fields or {},
    }


def _control_data(field: str, label: str, control_type: str) -> Dict[str, Any]:
    field_upper = str(field).upper()
    name = f"SYS_{field_upper}"
    return {
        "ROOT": {
            "SELF_GUID": "",
            "SELF_NAME": name,
            "IS_TEMPLATE": True,
            "TEMPLATE_SCOPE": "RELEASE_WORKFLOW",
        },
        "CONTROL": {
            "FIELD": field_upper,
            "FELD": field_upper,
            "NAME": name,
            "name": name,
            "LABEL": label,
            "label": label,
            "TYPE": control_type,
            "type": control_type,
            "TABLE": "sys_control_dict",
            "table": "sys_control_dict",
            "GRUPPE": "ROOT",
            "gruppe": "ROOT",
            "MODUL_TYPE": "edit",
            "display_order": 0,
            "read_only": False,
            "historical": False,
            "searchable": True,
        },
    }


def get_release_workflow_template_specs() -> List[TemplateSpec]:
    setup_fields = _frame_fields_from_control_keys(
        "workflow_setup_frame_template",
        [
            "RELEASE_TYPE",
            "TARGET_ENV",
            "SOURCE_DB_ROLE",
            "TARGET_DB_ROLE",
            "POLICY_MODE",
            "PACKAGE_HASH",
            "SOURCE_COMMIT",
        ],
    )
    dialog_fields = {
        _frame_field_uid("workflow_dialog_config_frame_template", "WORKFLOW_NAME"): {
            "tab": 1,
            "feld": "WORKFLOW_NAME",
            "name": "wf_dialog_workflow_name",
            "type": "string",
            "label": "Workflow Name",
            "table": "SYS_CONTROL_DICT",
            "gruppe": "FIELDS",
            "abdatum": False,
            "configs": {"help": {"key": "", "feld": "", "table": "", "gruppe": ""}, "dropdown": {"key": "", "feld": "", "table": "", "gruppe": ""}},
            "tooltip": "",
            "read_only": False,
            "historical": False,
            "source_path": "fields",
            "display_order": 10,
        },
        _frame_field_uid("workflow_dialog_config_frame_template", "DIALOG_TYPE"): {
            "tab": 1,
            "feld": "DIALOG_TYPE",
            "name": "wf_dialog_dialog_type",
            "type": "dropdown",
            "label": "Dialog Type",
            "table": "SYS_CONTROL_DICT",
            "gruppe": "FIELDS",
            "abdatum": False,
            "configs": {"help": {"key": "", "feld": "", "table": "", "gruppe": ""}, "dropdown": {"key": "", "feld": "", "table": "", "gruppe": ""}},
            "tooltip": "",
            "read_only": False,
            "historical": False,
            "source_path": "fields",
            "display_order": 20,
        },
        _frame_field_uid("workflow_dialog_config_frame_template", "OPEN_EDIT"): {
            "tab": 1,
            "feld": "OPEN_EDIT",
            "name": "wf_dialog_open_edit",
            "type": "dropdown",
            "label": "Open Edit",
            "table": "SYS_CONTROL_DICT",
            "gruppe": "FIELDS",
            "abdatum": False,
            "configs": {"help": {"key": "", "feld": "", "table": "", "gruppe": ""}, "dropdown": {"key": "", "feld": "", "table": "", "gruppe": ""}},
            "tooltip": "",
            "read_only": False,
            "historical": False,
            "source_path": "fields",
            "display_order": 30,
        },
        _frame_field_uid("workflow_dialog_config_frame_template", "SELECTION_MODE"): {
            "tab": 1,
            "feld": "SELECTION_MODE",
            "name": "wf_dialog_selection_mode",
            "type": "dropdown",
            "label": "Selection Mode",
            "table": "SYS_CONTROL_DICT",
            "gruppe": "FIELDS",
            "abdatum": False,
            "configs": {"help": {"key": "", "feld": "", "table": "", "gruppe": ""}, "dropdown": {"key": "", "feld": "", "table": "", "gruppe": ""}},
            "tooltip": "",
            "read_only": False,
            "historical": False,
            "source_path": "fields",
            "display_order": 40,
        },
    }
    dictionary_fields = _frame_fields_from_control_keys(
        "workflow_property_mapping_frame_template",
        ["TABLE_PREFIX_FILTER", "DICTIONARY_SEARCH", "CREATE_PROPERTY_ACTION"],
    )
    apply_fields = _frame_fields_from_control_keys(
        "workflow_apply_frame_template",
        ["DRY_RUN_ACTION", "APPLY_ACTION"],
    )

    specs: List[TemplateSpec] = [
        TemplateSpec("dialog", "sys_dialogdaten", "workflow_dialog_base_template", "WORKFLOW_DIALOG_BASE_TEMPLATE", _dialog_data("work")),
        TemplateSpec("dialog", "sys_dialogdaten", "workflow_dialog_release_template", "WORKFLOW_DIALOG_RELEASE_TEMPLATE", _dialog_data("work")),
        TemplateSpec("dialog", "sys_dialogdaten", "workflow_dialog_patch_template", "WORKFLOW_DIALOG_PATCH_TEMPLATE", _dialog_data("work")),
        TemplateSpec("view", "sys_viewdaten", "release_candidate_view_template", "RELEASE_CANDIDATE_VIEW_TEMPLATE", _view_data("dev_release")),
        TemplateSpec("view", "sys_viewdaten", "release_items_view_template", "RELEASE_ITEMS_VIEW_TEMPLATE", _view_data("dev_release_item")),
        TemplateSpec("view", "sys_viewdaten", "target_state_view_template", "TARGET_STATE_VIEW_TEMPLATE", _view_data("sys_release_state")),
        TemplateSpec("view", "sys_viewdaten", "change_log_view_template", "CHANGE_LOG_VIEW_TEMPLATE", _view_data("sys_change_log")),
        TemplateSpec("frame", "sys_framedaten", "workflow_setup_frame_template", "WORKFLOW_SETUP_FRAME_TEMPLATE", _frame_data("Setup", "workflow_setup_frame_template", setup_fields)),
        TemplateSpec("frame", "sys_framedaten", "workflow_dialog_config_frame_template", "WORKFLOW_DIALOG_CONFIG_FRAME_TEMPLATE", _frame_data("Dialog", "workflow_dialog_config_frame_template", dialog_fields)),
        TemplateSpec("frame", "sys_framedaten", "workflow_property_mapping_frame_template", "WORKFLOW_PROPERTY_MAPPING_FRAME_TEMPLATE", _frame_data("Dictionary", "workflow_property_mapping_frame_template", dictionary_fields)),
        TemplateSpec("frame", "sys_framedaten", "workflow_apply_frame_template", "WORKFLOW_APPLY_FRAME_TEMPLATE", _frame_data("Build", "workflow_apply_frame_template", apply_fields)),
    ]

    for field, label, control_type in WORKFLOW_CONTROL_DEFS:
        key = f"workflow_control_{field.lower()}"
        name = f"SYS_{field}"
        specs.append(
            TemplateSpec("control", "sys_control_dict", key, name, _control_data(field, label, control_type))
        )

    return specs


def with_resolved_self_fields(spec: TemplateSpec) -> Dict[str, Any]:
    data = dict(spec.daten)
    root = data.get("ROOT") if isinstance(data.get("ROOT"), dict) else {}
    root = dict(root)
    root["SELF_GUID"] = str(spec.uid)
    root["SELF_NAME"] = spec.name
    data["ROOT"] = root
    return data

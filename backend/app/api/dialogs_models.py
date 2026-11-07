"""Pydantic-Modelle der Dialogs-API (reine Verschiebung aus app/api/dialogs.py).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class DialogUiStateResponse(BaseModel):
    group: str
    ui_state: Dict[str, Any] = Field(default_factory=dict)


class DialogUiStateUpdateRequest(BaseModel):
    ui_state: Dict[str, Any] = Field(default_factory=dict)


class FrameDefinitionResponse(BaseModel):
    uid: str
    name: str
    daten: Dict[str, Any]
    root: Dict[str, Any]


class DialogDefinitionResponse(BaseModel):
    uid: str
    name: str
    daten: Dict[str, Any]
    root: Dict[str, Any]
    root_table: str
    dialog_type: Optional[str] = None
    view_guid: Optional[str] = None
    edit_type: str
    selection_mode: str = "single"
    open_edit_mode: str = "button"
    frame_guid: Optional[str] = None
    frame: Optional[FrameDefinitionResponse] = None
    tab_modules: List[Dict[str, Any]] = Field(default_factory=list)
    meta: Dict[str, Any] = Field(default_factory=dict)


class DialogRowsRequest(BaseModel):
    limit: int = Field(default=200, ge=1, le=2000)
    offset: int = Field(default=0, ge=0)
    storage_scope: Optional[str] = Field(default=None)
    draft_guid: Optional[str] = Field(default=None)


class DialogRow(BaseModel):
    uid: str
    name: str


class DialogRowsResponse(BaseModel):
    dialog_guid: str
    table: str
    rows: List[DialogRow]
    meta: Dict[str, Any] = Field(default_factory=dict)


class DialogRecordResponse(BaseModel):
    uid: str
    name: str
    daten: Dict[str, Any]
    historisch: int = 0
    modified_at: Optional[str] = None


class DialogRecordUpdateRequest(BaseModel):
    daten: Dict[str, Any]
    storage_scope: Optional[str] = Field(default=None)
    draft_guid: Optional[str] = Field(default=None)


class DialogRecordCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    template_uid: Optional[str] = None
    is_template: Optional[bool] = None
    modul_type: Optional[str] = Field(None, description="Für edit_dict: edit, view, tabs")
    storage_scope: Optional[str] = Field(default=None)
    draft_guid: Optional[str] = Field(default=None)


class DialogValidationIssue(BaseModel):
    group: str
    index: Optional[int] = None
    field: Optional[str] = None
    code: str
    message: str


class DialogDraftStartRequest(BaseModel):
    # Rückwärtskompatibel: ältere Clients senden teils kein name beim Draft-Start.
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    template_uid: Optional[str] = None
    is_template: Optional[bool] = None
    modul_type: Optional[str] = Field(None, description="Für edit_dict: edit, view, tabs")
    create_context: Optional[Dict[str, Any]] = None


class DialogDraftUpdateRequest(BaseModel):
    daten: Dict[str, Any]


class DialogDraftCommitRequest(BaseModel):
    daten: Optional[Dict[str, Any]] = None
    create_context: Optional[Dict[str, Any]] = None


class DialogDraftResponse(BaseModel):
    draft_id: str
    name: str
    daten: Dict[str, Any]
    root_table: str
    edit_type: str
    validation_errors: List[DialogValidationIssue] = Field(default_factory=list)


class ModulSelectionRequiredResponse(BaseModel):
    """Response wenn Modul-Auswahl erforderlich ist"""
    error: str = "modul_selection_required"
    message: str
    available_moduls: List[str]
    modul_group_key: str = Field(default="CONTROL", description="Gruppe wo MODUL gefunden wurde")


class DialogLastCallResponse(BaseModel):
    key: str
    last_call: Optional[str] = None


class DialogLastCallUpdateRequest(BaseModel):
    record_uid: Optional[str] = None


class DialogCreateTableOption(BaseModel):
    value: str
    label: str
    scope: str


class DialogCreateTableOptionsResponse(BaseModel):
    role: str
    tables: List[DialogCreateTableOption] = Field(default_factory=list)


class ModulSelectionRequest(BaseModel):
    """Request für Modul-Auswahl bei edit_dict"""
    modul_type: str = Field(..., description="Gewählter MODUL_TYPE: edit, view, tabs")


class ModulSelectionResponse(BaseModel):
    """Response mit verfügbaren Modulen"""
    available_moduls: List[str] = Field(default_factory=list, description="Verfügbare MODUL-Typen")
    requires_modul_selection: bool = Field(default=False, description="True wenn Modul-Auswahl erforderlich ist")

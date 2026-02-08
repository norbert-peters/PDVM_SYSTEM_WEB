"""Import Data API

Streaming upload + backend parsing for edit_type import_data.
"""
from __future__ import annotations

import os
import tempfile
import json
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app.core.security import get_current_user
from app.core.pdvm_central_systemsteuerung import get_gcs_session
from app.core.import_data_service import (
    _column_entries,
    _merge_rows,
    _normalize_match_keys,
    apply_preview_rows,
    load_dataset,
    parse_file_to_preview,
)

router = APIRouter()


def _normalize_table_name(table_name: Optional[str]) -> str:
    t = str(table_name or "").strip()
    if not t:
        raise HTTPException(status_code=400, detail="table_name fehlt")
    if t not in {"sys_ext_table", "sys_ext_table_man"}:
        raise HTTPException(status_code=400, detail="Ungueltige table_name")
    return t


async def get_gcs_instance(current_user: dict = Depends(get_current_user)):
    token = current_user.get("token")
    if not token:
        raise HTTPException(status_code=401, detail="Kein Session-Token gefunden")

    gcs = get_gcs_session(token)
    if not gcs:
        raise HTTPException(status_code=404, detail="Keine GCS-Session gefunden. Bitte Mandant auswaehlen.")

    return gcs


class ImportApplyRequest(BaseModel):
    table_name: str = Field(..., description="sys_ext_table or sys_ext_table_man")
    dataset_uid: str
    rows: List[Dict[str, Any]] = Field(default_factory=list)


class ImportDatasetResponse(BaseModel):
    uid: str
    name: str
    daten: Dict[str, Any]


class ImportConfigUpdateRequest(BaseModel):
    table_name: str
    dataset_uid: str
    root_patch: Dict[str, Any] = Field(default_factory=dict)
    config_patch: Dict[str, Any] = Field(default_factory=dict)
    columns: List[str] = Field(default_factory=list)
    columns_map: Dict[str, Any] = Field(default_factory=dict)


class ImportClearRequest(BaseModel):
    table_name: str
    dataset_uid: str


def _normalize_columns_map(columns_map: Dict[str, Any]) -> Dict[str, Any]:
    normalized: Dict[str, Any] = {}
    used_keys: set[str] = set()
    template_uid = "55555555-5555-5555-5555-555555555555"

    for uid, raw_cfg in (columns_map or {}).items():
        if uid == template_uid:
            if isinstance(raw_cfg, dict):
                normalized[uid] = dict(raw_cfg)
            continue

        cfg = dict(raw_cfg) if isinstance(raw_cfg, dict) else {}
        key = str(cfg.get("key") or cfg.get("label") or "").strip()
        label = str(cfg.get("label") or key).strip()

        if not key:
            raise HTTPException(status_code=400, detail="Spalten-Key fehlt")

        key_norm = key.strip().lower()
        if key_norm in used_keys:
            raise HTTPException(status_code=400, detail=f"Duplicate Spalten-Key: {key}")
        used_keys.add(key_norm)

        cfg["key"] = key
        cfg["label"] = label
        if "aliases" in cfg and not isinstance(cfg["aliases"], list):
            cfg["aliases"] = [cfg["aliases"]]

        normalized[str(uid)] = cfg

    return normalized


@router.post("/preview")
async def preview_import(
    dataset_uid: str = Form(...),
    table_name: str = Form(...),
    sheet_name: Optional[str] = Form(default=None),
    has_headers: Optional[bool] = Form(default=True),
    custom_headers: Optional[str] = Form(default=None),
    header_overrides: Optional[str] = Form(default=None),
    file: UploadFile = File(...),
    gcs=Depends(get_gcs_instance),
):
    table = _normalize_table_name(table_name)
    if not file.filename:
        raise HTTPException(status_code=400, detail="Dateiname fehlt")

    dataset = await load_dataset(gcs, table_name=table, dataset_uid=dataset_uid)
    daten = dataset.get("daten") if isinstance(dataset.get("daten"), dict) else {}
    config = daten.get("CONFIG") if isinstance(daten.get("CONFIG"), dict) else {}
    columns_cfg = config.get("COLUMNS") if isinstance(config.get("COLUMNS"), dict) else {}

    custom_header_list: Optional[List[str]] = None
    if custom_headers:
        custom_header_list = [h.strip() for h in custom_headers.split(",") if h.strip()]

    overrides: Optional[Dict[str, str]] = None
    if header_overrides:
        try:
            parsed = json.loads(header_overrides)
            if isinstance(parsed, dict):
                overrides = {str(k): str(v) for k, v in parsed.items()}
        except Exception:
            overrides = None

    temp_path = None
    try:
        suffix = os.path.splitext(file.filename)[1]
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        temp_path = tmp.name
        try:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                tmp.write(chunk)
        finally:
            tmp.close()

        preview = parse_file_to_preview(
            path=temp_path,
            filename=file.filename,
            columns_cfg=columns_cfg,
            sheet_name=sheet_name,
            has_headers=bool(has_headers),
            custom_headers=custom_header_list,
            header_overrides=overrides,
        )
        root = daten.get("ROOT") if isinstance(daten.get("ROOT"), dict) else {}
        match_keys = [str(k) for k in root.get("MATCH_KEYS") or []]
        if not match_keys:
            match_keys = [str(k) for k in config.get("KEY_MERGE_PRIORITY") or []]
        match_keys = _normalize_match_keys(match_keys, columns_cfg)

        conflict_policy = str(root.get("CONFLICT_POLICY") or "base_wins").strip().lower()
        conflict_rules = root.get("CONFLICT_RULES") if isinstance(root.get("CONFLICT_RULES"), dict) else {}
        conflict_marker_field = root.get("CONFLICT_MARKER_FIELD")

        existing = daten.get("DATAS") if isinstance(daten.get("DATAS"), dict) else {}
        merged = _merge_rows(
            existing=existing,
            incoming=preview.get("rows") or [],
            match_keys=match_keys,
            conflict_policy=conflict_policy,
            conflict_rules=conflict_rules,
            conflict_marker_field=conflict_marker_field,
        )

        merged_rows: List[Dict[str, Any]] = []
        for uid, row in merged.items():
            data = dict(row)
            data["__uid"] = uid
            merged_rows.append(data)

        canonical_headers = list(preview.get("canonical_headers") or [])
        if not canonical_headers:
            canonical_headers = [canon for canon, _ in _column_entries(columns_cfg)]
        extra_keys = sorted({k for r in merged_rows for k in r.keys() if k != "__uid"} - set(canonical_headers))
        canonical_headers = canonical_headers + extra_keys

        preview["rows"] = merged_rows
        preview["canonical_headers"] = canonical_headers
        preview["preview_mode"] = "merged"
        return {
            "dataset_uid": dataset_uid,
            "table_name": table,
            **preview,
        }
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass


@router.post("/apply")
async def apply_import(request: ImportApplyRequest, gcs=Depends(get_gcs_instance)):
    table = _normalize_table_name(request.table_name)
    try:
        result = await apply_preview_rows(
            gcs,
            table_name=table,
            dataset_uid=request.dataset_uid,
            rows=request.rows,
        )
        return result
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/dataset/{dataset_uid}", response_model=ImportDatasetResponse)
async def get_import_dataset(dataset_uid: str, table_name: str, gcs=Depends(get_gcs_instance)):
    table = _normalize_table_name(table_name)
    try:
        return await load_dataset(gcs, table_name=table, dataset_uid=dataset_uid)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.put("/config", response_model=ImportDatasetResponse)
async def update_import_config(request: ImportConfigUpdateRequest, gcs=Depends(get_gcs_instance)):
    table = _normalize_table_name(request.table_name)
    dataset = await load_dataset(gcs, table_name=table, dataset_uid=request.dataset_uid)
    daten = dataset.get("daten") if isinstance(dataset.get("daten"), dict) else {}
    root = daten.get("ROOT") if isinstance(daten.get("ROOT"), dict) else {}
    config = daten.get("CONFIG") if isinstance(daten.get("CONFIG"), dict) else {}

    root = {**root, **(request.root_patch or {})}
    config = {**config, **(request.config_patch or {})}

    if request.columns_map:
        config["COLUMNS"] = _normalize_columns_map(request.columns_map)

    columns_cfg = config.get("COLUMNS") if isinstance(config.get("COLUMNS"), dict) else {}
    for col in request.columns or []:
        key = str(col).strip()
        if not key:
            continue
        columns_cfg.setdefault(
            key,
            {
                "type": "str",
                "required": False,
                "source": "base",
                "aliases": [],
            },
        )
    config["COLUMNS"] = columns_cfg

    daten = dict(daten)
    daten["ROOT"] = root
    daten["CONFIG"] = config

    from app.core.pdvm_datenbank import PdvmDatabase
    db = PdvmDatabase(table, system_pool=gcs._system_pool, mandant_pool=gcs._mandant_pool)
    await db.update(uuid.UUID(str(request.dataset_uid)), daten=daten, name=dataset.get("name"))

    return {"uid": dataset["uid"], "name": dataset["name"], "daten": daten}


@router.post("/clear", response_model=ImportDatasetResponse)
async def clear_import_data(request: ImportClearRequest, gcs=Depends(get_gcs_instance)):
    table = _normalize_table_name(request.table_name)
    dataset = await load_dataset(gcs, table_name=table, dataset_uid=request.dataset_uid)
    daten = dataset.get("daten") if isinstance(dataset.get("daten"), dict) else {}
    daten = dict(daten)
    daten["DATAS"] = {}

    from app.core.pdvm_datenbank import PdvmDatabase
    db = PdvmDatabase(table, system_pool=gcs._system_pool, mandant_pool=gcs._mandant_pool)
    await db.update(uuid.UUID(str(request.dataset_uid)), daten=daten, name=dataset.get("name"))

    return {"uid": dataset["uid"], "name": dataset["name"], "daten": daten}

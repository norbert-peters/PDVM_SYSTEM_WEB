from __future__ import annotations

import copy
import json
import re
import uuid
from typing import Any, Dict, Optional, Tuple

import asyncpg

from app.core.workflow_draft_service import WorkflowDraftService


_TABLE_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_UID_555 = uuid.UUID("55555555-5555-5555-5555-555555555555")
_UID_666 = uuid.UUID("66666666-6666-6666-6666-666666666666")


class WorkflowDraftAccess:
    """Einheitlicher Zugriff auf DRAFT_DB je Tabelle (linear, template-basiert)."""

    @staticmethod
    def _normalize_table_name(value: str) -> str:
        table = str(value or "").strip().lower()
        if not table:
            raise ValueError("table_name fehlt")
        if not _TABLE_NAME_RE.match(table):
            raise ValueError("table_name enthaelt ungueltige Zeichen")
        return table

    @staticmethod
    def _bucket_name(table_name: str) -> str:
        return WorkflowDraftAccess._normalize_table_name(table_name).upper()

    @staticmethod
    def _find_bucket_key_ci(payload: Dict[str, Any], bucket_key: str) -> Optional[str]:
        if not isinstance(payload, dict):
            return None
        wanted = str(bucket_key or "").strip().lower()
        if not wanted:
            return None
        for key in payload.keys():
            key_norm = str(key or "").strip().lower()
            if key_norm == wanted:
                return str(key)
        return None

    @staticmethod
    def _as_dict(value: Any) -> Dict[str, Any]:
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
                return parsed if isinstance(parsed, dict) else {}
            except Exception:
                return {}
        return {}

    @staticmethod
    def _merge_defined_fields(
        template_dict: Dict[str, Any],
        incoming: Dict[str, Any],
        path: Tuple[str, ...] = (),
    ) -> Dict[str, Any]:
        out = copy.deepcopy(template_dict) if isinstance(template_dict, dict) else {}
        if not isinstance(incoming, dict):
            return out

        for key, value in incoming.items():
            if key not in out:
                # ROOT.TAB_ELEMENTS ist eine dynamische Collection (TAB_01..TAB_NN)
                # und darf nicht durch das 555-Template auf leere Keys begrenzt werden.
                if path and str(path[-1]).strip().upper() == "TAB_ELEMENTS":
                    out[key] = copy.deepcopy(value)
                continue
            existing = out.get(key)
            if isinstance(existing, dict) and isinstance(value, dict):
                out[key] = WorkflowDraftAccess._merge_defined_fields(existing, value, path=path + (str(key),))
            else:
                out[key] = value
        return out

    @staticmethod
    def _fill_empty_groups_from_template(base: Dict[str, Any], fallback: Dict[str, Any]) -> Dict[str, Any]:
        out = copy.deepcopy(base) if isinstance(base, dict) else {}
        tpl = fallback if isinstance(fallback, dict) else {}

        # Leere Gruppe wird komplett aus dem Template uebernommen.
        if not out and tpl:
            return copy.deepcopy(tpl)

        for key, value in list(out.items()):
            tpl_value = tpl.get(key)
            if not isinstance(value, dict):
                continue
            if not value and isinstance(tpl_value, dict):
                out[key] = copy.deepcopy(tpl_value)
                continue
            if isinstance(tpl_value, dict):
                out[key] = WorkflowDraftAccess._fill_empty_groups_from_template(value, tpl_value)
        return out

    @staticmethod
    async def _load_table_template_data(
        conn: asyncpg.Connection,
        *,
        table_name: str,
        row_uid: uuid.UUID,
    ) -> Dict[str, Any]:
        row = await conn.fetchrow(
            f"SELECT daten FROM {table_name} WHERE uid = $1::uuid AND COALESCE(historisch, 0) = 0",
            row_uid,
        )
        if not row:
            raise ValueError(f"Template fehlt in {table_name}: {row_uid}")
        return WorkflowDraftAccess._as_dict(row.get("daten"))

    @staticmethod
    def _extract_work_payload(draft_data: Dict[str, Any]) -> Dict[str, Any]:
        items = draft_data.get("items") if isinstance(draft_data.get("items"), list) else []
        for item in items:
            item_type = str(item.get("item_type") or "").strip().lower()
            item_key = str(item.get("item_key") or "").strip().lower()
            if item_type == "work" and item_key == "container":
                payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
                normalized: Dict[str, Any] = {}
                for key, value in payload.items():
                    key_norm = str(key or "").strip()
                    if not key_norm:
                        continue
                    if key_norm.upper() == "WORKFLOW":
                        normalized["WORKFLOW"] = dict(value) if isinstance(value, dict) else {}
                    elif isinstance(value, dict):
                        normalized[key_norm.upper()] = dict(value)
                if "WORKFLOW" not in normalized:
                    normalized["WORKFLOW"] = {}
                return normalized
        return {"WORKFLOW": {}}

    @staticmethod
    async def build_record_from_templates(
        system_pool: asyncpg.Pool,
        *,
        table_name: str,
        record_uid: str,
        workflow_name: str,
        workflow_type: str,
        target_table: str,
        incoming_record: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        table_norm = WorkflowDraftAccess._normalize_table_name(table_name)
        incoming = incoming_record if isinstance(incoming_record, dict) else {}

        async with system_pool.acquire() as conn:
            data_555 = await WorkflowDraftAccess._load_table_template_data(
                conn,
                table_name=table_norm,
                row_uid=_UID_555,
            )
            data_666 = await WorkflowDraftAccess._load_table_template_data(
                conn,
                table_name=table_norm,
                row_uid=_UID_666,
            )

        templates_666 = data_666.get("TEMPLATES") if isinstance(data_666.get("TEMPLATES"), dict) else {}
        tpl666_key_map = {str(k).strip().lower(): k for k in templates_666.keys() if str(k).strip()}
        incoming_key_map = {str(k).strip().lower(): k for k in incoming.keys() if str(k).strip()}
        out: Dict[str, Any] = {}

        for group_name, group_value in data_555.items():
            if str(group_name).upper() == "ROOT":
                continue
            if not isinstance(group_value, dict):
                continue

            group_norm = str(group_name).strip().lower()
            tpl_key = tpl666_key_map.get(group_norm)
            fallback_group = templates_666.get(tpl_key) if isinstance(templates_666.get(tpl_key), dict) else {}
            merged_group = WorkflowDraftAccess._fill_empty_groups_from_template(group_value, fallback_group)

            incoming_key = incoming_key_map.get(group_norm)
            incoming_group = incoming.get(incoming_key)
            if isinstance(incoming_group, dict):
                merged_group = WorkflowDraftAccess._merge_defined_fields(merged_group, incoming_group)

            out[str(group_name)] = merged_group

        root_555 = data_555.get("ROOT") if isinstance(data_555.get("ROOT"), dict) else {}
        incoming_root = incoming.get("ROOT") if isinstance(incoming.get("ROOT"), dict) else {}

        root = WorkflowDraftAccess._merge_defined_fields(root_555, incoming_root)
        root = WorkflowDraftAccess._merge_defined_fields(
            root,
            {
                "SELF_GUID": str(record_uid),
                "SELF_NAME": str(workflow_name or "").strip() or "WORKFLOW_DRAFT",
                "WORKFLOW_TYPE": str(workflow_type or "").strip().lower() or "work",
                "TARGET_TABLE": str(target_table or "").strip() or "sys_dialogdaten",
            },
        )
        out["ROOT"] = root

        return out

    @staticmethod
    async def sanitize_work_container_payload(
        system_pool: asyncpg.Pool,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        src = payload if isinstance(payload, dict) else {}
        workflow = src.get("WORKFLOW") if isinstance(src.get("WORKFLOW"), dict) else {}

        workflow_name = str(workflow.get("WORKFLOW_NAME") or "").strip() or "WORKFLOW_DRAFT"
        workflow_type = str(workflow.get("WORKFLOW_TYPE") or "work").strip().lower() or "work"
        target_table = str(workflow.get("TARGET_TABLE") or "sys_dialogdaten").strip() or "sys_dialogdaten"

        out: Dict[str, Any] = {"WORKFLOW": dict(workflow)}

        for raw_bucket_name, raw_bucket_value in src.items():
            bucket_name = str(raw_bucket_name or "").strip()
            if not bucket_name or bucket_name.upper() == "WORKFLOW":
                continue
            if not isinstance(raw_bucket_value, dict):
                continue

            table_name = WorkflowDraftAccess._normalize_table_name(bucket_name)
            bucket_key = table_name.upper()

            bucket_out: Dict[str, Any] = {}
            for rec_uid_raw, rec_payload in raw_bucket_value.items():
                rec_uid = str(rec_uid_raw or "").strip()
                try:
                    rec_uid = str(uuid.UUID(rec_uid))
                except Exception:
                    rec_uid = str(uuid.uuid4())

                rec_data = rec_payload if isinstance(rec_payload, dict) else {}
                bucket_out[rec_uid] = await WorkflowDraftAccess.build_record_from_templates(
                    system_pool,
                    table_name=table_name,
                    record_uid=rec_uid,
                    workflow_name=workflow_name,
                    workflow_type=workflow_type,
                    target_table=target_table,
                    incoming_record=rec_data,
                )

            out[bucket_key] = bucket_out

        return out

    @staticmethod
    async def ensure_table_record_in_payload(
        system_pool: asyncpg.Pool,
        *,
        payload: Dict[str, Any],
        table_name: str,
        workflow_name: str,
        workflow_type: str,
        target_table: str,
        single_record: bool = False,
    ) -> Tuple[Dict[str, Any], str]:
        out = dict(payload) if isinstance(payload, dict) else {"WORKFLOW": {}}
        if not isinstance(out.get("WORKFLOW"), dict):
            out["WORKFLOW"] = {}

        bucket_key = WorkflowDraftAccess._bucket_name(table_name)
        existing_key = WorkflowDraftAccess._find_bucket_key_ci(out, bucket_key)
        bucket_raw = out.get(existing_key) if existing_key else out.get(bucket_key)
        bucket = bucket_raw if isinstance(bucket_raw, dict) else {}

        if bucket:
            existing_uid = str(next(iter(bucket.keys())))
            existing_record = bucket.get(existing_uid) if isinstance(bucket.get(existing_uid), dict) else {}
            bucket[existing_uid] = await WorkflowDraftAccess.build_record_from_templates(
                system_pool,
                table_name=table_name,
                record_uid=existing_uid,
                workflow_name=workflow_name,
                workflow_type=workflow_type,
                target_table=target_table,
                incoming_record=existing_record,
            )
            if single_record:
                bucket = {existing_uid: bucket[existing_uid]}
            if existing_key and existing_key != bucket_key:
                out.pop(existing_key, None)
            out[bucket_key] = bucket
            return out, existing_uid

        record_uid = str(uuid.uuid4())
        bucket[record_uid] = await WorkflowDraftAccess.build_record_from_templates(
            system_pool,
            table_name=table_name,
            record_uid=record_uid,
            workflow_name=workflow_name,
            workflow_type=workflow_type,
            target_table=target_table,
            incoming_record={},
        )
        if existing_key and existing_key != bucket_key:
            out.pop(existing_key, None)
        out[bucket_key] = bucket
        return out, record_uid

    @staticmethod
    async def list_table_records(
        system_pool: asyncpg.Pool,
        *,
        draft_guid: str,
        table_name: str,
        draft_table: str,
    ) -> Dict[str, Dict[str, Any]]:
        draft = await WorkflowDraftService.load_draft(
            system_pool,
            draft_guid=draft_guid,
            draft_table=draft_table,
        )
        work_payload = WorkflowDraftAccess._extract_work_payload(draft)
        bucket_key = WorkflowDraftAccess._bucket_name(table_name)
        bucket = work_payload.get(bucket_key) if isinstance(work_payload.get(bucket_key), dict) else {}
        return dict(bucket)

    @staticmethod
    async def save_table_record(
        system_pool: asyncpg.Pool,
        *,
        draft_guid: str,
        table_name: str,
        record_uid: Optional[str],
        payload: Dict[str, Any],
        updated_by_user_guid: str,
        draft_table: str,
        single_record: bool = False,
    ) -> Dict[str, Any]:
        draft = await WorkflowDraftService.load_draft(
            system_pool,
            draft_guid=draft_guid,
            draft_table=draft_table,
        )
        root = draft.get("root") if isinstance(draft.get("root"), dict) else {}
        work_payload = WorkflowDraftAccess._extract_work_payload(draft)
        workflow = work_payload.get("WORKFLOW") if isinstance(work_payload.get("WORKFLOW"), dict) else {}

        workflow_name = str(workflow.get("WORKFLOW_NAME") or root.get("TITLE") or "").strip() or "WORKFLOW_DRAFT"
        workflow_type = str(workflow.get("WORKFLOW_TYPE") or root.get("WORKFLOW_TYPE") or "work").strip().lower() or "work"
        target_table = str(workflow.get("TARGET_TABLE") or "sys_dialogdaten").strip() or "sys_dialogdaten"

        try:
            resolved_uid = str(uuid.UUID(str(record_uid))) if record_uid else str(uuid.uuid4())
        except Exception:
            resolved_uid = str(uuid.uuid4())

        bucket_key = WorkflowDraftAccess._bucket_name(table_name)
        existing_key = WorkflowDraftAccess._find_bucket_key_ci(work_payload, bucket_key)
        bucket_raw = work_payload.get(existing_key) if existing_key else work_payload.get(bucket_key)
        bucket = bucket_raw if isinstance(bucket_raw, dict) else {}
        bucket = dict(bucket)

        normalized_record = await WorkflowDraftAccess.build_record_from_templates(
            system_pool,
            table_name=table_name,
            record_uid=resolved_uid,
            workflow_name=workflow_name,
            workflow_type=workflow_type,
            target_table=target_table,
            incoming_record=payload if isinstance(payload, dict) else {},
        )
        if single_record:
            bucket = {resolved_uid: normalized_record}
        else:
            bucket[resolved_uid] = normalized_record
        if existing_key and existing_key != bucket_key:
            work_payload.pop(existing_key, None)
        work_payload[bucket_key] = bucket

        sanitized = await WorkflowDraftAccess.sanitize_work_container_payload(system_pool, work_payload)
        await WorkflowDraftService.save_draft_item(
            system_pool,
            draft_guid=draft_guid,
            item_type="work",
            item_key="container",
            payload=sanitized,
            updated_by_user_guid=updated_by_user_guid,
            draft_table=draft_table,
        )

        return {
            "table": WorkflowDraftAccess._normalize_table_name(table_name),
            "bucket": bucket_key,
            "record_uid": resolved_uid,
            "record": normalized_record,
        }

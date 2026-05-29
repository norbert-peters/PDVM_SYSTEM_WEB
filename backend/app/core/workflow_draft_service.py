"""Workflow Draft Service (Minimal Vertical Slice).

Stellt einen robusten Minimalfluss fuer Testdialoge bereit:
- create_draft
- save_draft_item (persistiert in DRAFT_DB)
- load_draft
- list_open_drafts
- validate_draft
"""
from __future__ import annotations

import copy
import json
import re
import uuid
from typing import Any, Dict, List, Optional

import asyncpg

from app.core.pdvm_datetime import now_pdvm_str
from app.core.pdvm_table_schema import PDVM_TABLE_COLUMNS, PDVM_TABLE_INDEXES


DRAFT_TABLE = "dev_workflow_draft"
UID_META = uuid.UUID("00000000-0000-0000-0000-000000000000")
UID_555 = uuid.UUID("55555555-5555-5555-5555-555555555555")
DEFAULT_TEMPLATE_UID = uuid.UUID("66666666-6666-6666-6666-666666666666")
VALID_STATUSES = {"draft", "in_review", "validated", "approved", "built", "archived"}
ITEM_KEY_RE = re.compile(r"^[A-Za-z0-9_\-:.]{1,120}$")
TABLE_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class WorkflowDraftService:
    """Service-Layer fuer Workflow-Draft-Container."""

    @staticmethod
    def _normalize_table_name(table_name: str, *, label: str) -> str:
        table = str(table_name or "").strip().lower()
        if not table:
            raise ValueError(f"{label} fehlt")
        if not TABLE_NAME_RE.match(table):
            raise ValueError(f"{label} enthaelt ungueltige Zeichen")
        return table

    @staticmethod
    def _as_json_dict(value: Any) -> Dict[str, Any]:
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
    def _merge_defined_fields(template_dict: Dict[str, Any], incoming: Dict[str, Any]) -> Dict[str, Any]:
        """Uebernimmt nur Keys, die im Template bereits definiert sind."""
        result = copy.deepcopy(template_dict) if isinstance(template_dict, dict) else {}
        if not isinstance(incoming, dict):
            return result

        for key, value in incoming.items():
            if key not in result:
                continue
            existing = result.get(key)
            if isinstance(existing, dict) and isinstance(value, dict):
                result[key] = WorkflowDraftService._merge_defined_fields(existing, value)
            else:
                result[key] = value
        return result

    @staticmethod
    def _fill_empty_groups_from_template(base: Dict[str, Any], fallback: Dict[str, Any]) -> Dict[str, Any]:
        """Fuellt nur leere Gruppen in base aus fallback auf (rekursiv)."""
        result = copy.deepcopy(base) if isinstance(base, dict) else {}
        tpl = fallback if isinstance(fallback, dict) else {}

        # Leere Gruppe wird komplett aus dem Template uebernommen.
        if not result and tpl:
            return copy.deepcopy(tpl)

        for key, value in list(result.items()):
            tpl_value = tpl.get(key)
            if not isinstance(value, dict):
                continue
            if not value and isinstance(tpl_value, dict):
                result[key] = copy.deepcopy(tpl_value)
                continue
            if isinstance(tpl_value, dict):
                result[key] = WorkflowDraftService._fill_empty_groups_from_template(value, tpl_value)
        return result

    @staticmethod
    async def _table_exists(conn: asyncpg.Connection, table_name: str) -> bool:
        return bool(
            await conn.fetchval(
                """
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_schema = 'public' AND table_name = $1
                )
                """,
                table_name,
            )
        )

    @staticmethod
    async def _load_template_daten(
        conn: asyncpg.Connection,
        *,
        table_name: str,
        template_uid: uuid.UUID = DEFAULT_TEMPLATE_UID,
    ) -> Dict[str, Any]:
        row = await conn.fetchrow(
            f"SELECT daten FROM {table_name} WHERE uid = $1::uuid AND COALESCE(historisch, 0) = 0",
            template_uid,
        )
        if not row:
            raise ValueError(f"Template-Datensatz nicht gefunden: {template_uid}")

        daten = WorkflowDraftService._as_json_dict(row["daten"])
        if not daten:
            raise ValueError(f"Template-Datensatz ungueltig: {template_uid}")
        return daten

    @staticmethod
    async def ensure_draft_tables(
        system_pool: asyncpg.Pool,
        *,
        draft_table: str = DRAFT_TABLE,
    ) -> Dict[str, Any]:
        draft_table_norm = WorkflowDraftService._normalize_table_name(draft_table, label="draft_table")
        created: List[str] = []

        async with system_pool.acquire() as conn:
            await conn.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')

            if not await WorkflowDraftService._table_exists(conn, draft_table_norm):
                columns = ", ".join([f"{col} {definition}" for col, definition in PDVM_TABLE_COLUMNS.items()])
                await conn.execute(
                    f"""
                    CREATE TABLE public.{draft_table_norm} (
                        {columns}
                    )
                    """
                )
                for idx_col in PDVM_TABLE_INDEXES:
                    if idx_col == "daten":
                        await conn.execute(
                            f"""
                            CREATE INDEX IF NOT EXISTS idx_{draft_table_norm}_{idx_col}
                            ON public.{draft_table_norm} USING GIN({idx_col})
                            """
                        )
                    else:
                        await conn.execute(
                            f"""
                            CREATE INDEX IF NOT EXISTS idx_{draft_table_norm}_{idx_col}
                            ON public.{draft_table_norm}({idx_col})
                            """
                        )
                created.append(draft_table_norm)

            await WorkflowDraftService._ensure_default_templates(
                conn,
                draft_table=draft_table_norm,
            )

        return {
            "success": True,
            "tables_created": created,
            "tables_existing": [t for t in [draft_table_norm] if t not in created],
        }

    @staticmethod
    async def _ensure_tables(
        system_pool: asyncpg.Pool,
        *,
        draft_table: str = DRAFT_TABLE,
    ) -> None:
        await WorkflowDraftService.ensure_draft_tables(
            system_pool,
            draft_table=draft_table,
        )

    @staticmethod
    async def _ensure_default_templates(
        conn: asyncpg.Connection,
        *,
        draft_table: str,
    ) -> None:
        draft_meta_payload = {
            "INFO": {
                "TABLE": draft_table,
                "DESCRIPTION": "Metadaten Datensatz",
            }
        }

        draft_555_payload = {
            "ROOT": {
                "SELF_GUID": str(UID_555),
                "SELF_NAME": "DEV_WORKFLOW_DRAFT_TEMPLATE_555",
            },
            "TEMPLATES": {
                "ROOT": {
                    "SELF_GUID": "",
                    "SELF_NAME": "",
                    "DRAFT_GUID": "",
                    "WORKFLOW_TYPE": "work",
                    "DIALOG_TYPE": "work",
                    "STATUS": "draft",
                    "OWNER_USER_GUID": "",
                    "MANDANT_GUID": "",
                    "CREATED_AT": "",
                    "UPDATED_AT": "",
                    "TITLE": "",
                    "REVISION": 1,
                    "IS_TEMPLATE": False,
                    "LAST_EDITOR_USER_GUID": "",
                },
                "DRAFT_DB": {
                    "_META": {
                        "SETUP": {},
                        "STATE": {},
                        "WORKFLOW": {},
                    },
                    "SYS_DIALOGDATEN": {},
                    "SYS_VIEWDATEN": {},
                    "SYS_FRAMEDATEN": {},
                },
            },
        }

        draft_template_payload = {
            "ROOT": {
                "SELF_GUID": str(DEFAULT_TEMPLATE_UID),
                "SELF_NAME": "WORKFLOW_DRAFT_TEMPLATE_6666",
                "WORKFLOW_TYPE": "work",
                "DIALOG_TYPE": "work",
                "STATUS": "template",
                "IS_TEMPLATE": True,
                "TITLE": "Workflow Draft Template",
                "REVISION": 1,
            },
            "TEMPLATES": {
                "DRAFT_DB": {
                    "_META": {
                        "SETUP": {
                            "WORKFLOW_NAME": "",
                            "TARGET_TABLE": "sys_dialogdaten",
                            "DIALOG_TYPE": "work",
                            "DESCRIPTION": "",
                        },
                        "STATE": {
                            "ACTIVE_TAB": 1,
                            "MAX_TAB": 1,
                            "STATUS": "draft",
                        },
                        "WORKFLOW": {
                            "DRAFT_GUID": "",
                            "WORKFLOW_TYPE": "work",
                            "WORKFLOW_NAME": "",
                            "DIALOG_TYPE": "work",
                            "TARGET_TABLE": "sys_dialogdaten",
                            "UPDATED_AT": "",
                        },
                    },
                    "SYS_DIALOGDATEN": {},
                    "SYS_VIEWDATEN": {},
                    "SYS_FRAMEDATEN": {},
                }
            },
        }

        await conn.execute(
            f"""
            INSERT INTO {draft_table} (uid, daten, name, historisch, created_at, modified_at)
            VALUES ($1::uuid, $2::jsonb, $3, 0, NOW(), NOW())
            ON CONFLICT (uid) DO UPDATE
            SET daten = EXCLUDED.daten,
                name = EXCLUDED.name,
                modified_at = NOW()
            """,
            UID_META,
            json.dumps(draft_meta_payload, ensure_ascii=False),
            "DEV_WORKFLOW_DRAFT_META_000",
        )

        await conn.execute(
            f"""
            INSERT INTO {draft_table} (uid, daten, name, historisch, created_at, modified_at)
            VALUES ($1::uuid, $2::jsonb, $3, 0, NOW(), NOW())
            ON CONFLICT (uid) DO UPDATE
            SET daten = EXCLUDED.daten,
                name = EXCLUDED.name,
                modified_at = NOW()
            """,
            UID_555,
            json.dumps(draft_555_payload, ensure_ascii=False),
            "DEV_WORKFLOW_DRAFT_TEMPLATE_555",
        )

        await conn.execute(
            f"""
            INSERT INTO {draft_table} (uid, daten, name, historisch, created_at, modified_at)
            VALUES ($1::uuid, $2::jsonb, $3, 0, NOW(), NOW())
            ON CONFLICT (uid) DO UPDATE
            SET daten = EXCLUDED.daten,
                name = EXCLUDED.name,
                modified_at = NOW()
            """,
            DEFAULT_TEMPLATE_UID,
            json.dumps(draft_template_payload, ensure_ascii=False),
            "WORKFLOW_DRAFT_TEMPLATE_6666",
        )

    @staticmethod
    def _normalize_item_key(item_key: str) -> str:
        key = str(item_key or "").strip()
        if not key:
            raise ValueError("item_key fehlt")
        if not ITEM_KEY_RE.match(key):
            raise ValueError("item_key enthaelt ungueltige Zeichen")
        return key

    @staticmethod
    def _deterministic_item_uid(draft_guid: str, item_type: str, item_key: str) -> uuid.UUID:
        namespace = uuid.UUID("3dfde5f6-43bd-4fda-a676-89fb9d9a791b")
        token = f"{draft_guid}:{item_type}:{item_key}"
        return uuid.uuid5(namespace, token)

    @staticmethod
    async def create_draft(
        system_pool: asyncpg.Pool,
        *,
        workflow_type: str,
        title: str,
        owner_user_guid: str,
        mandant_guid: str,
        initial_setup: Optional[Dict[str, Any]] = None,
        draft_table: str = DRAFT_TABLE,
    ) -> Dict[str, Any]:
        draft_table_norm = WorkflowDraftService._normalize_table_name(draft_table, label="draft_table")
        await WorkflowDraftService._ensure_tables(
            system_pool,
            draft_table=draft_table_norm,
        )

        workflow_type_norm = str(workflow_type or "").strip().lower()
        if not workflow_type_norm:
            raise ValueError("workflow_type fehlt")

        title_norm = str(title or "").strip()
        if not title_norm:
            raise ValueError("title fehlt")

        draft_uid = uuid.uuid4()
        now_ts = now_pdvm_str()
        async with system_pool.acquire() as conn:
            template_555 = await WorkflowDraftService._load_template_daten(
                conn,
                table_name=draft_table_norm,
                template_uid=UID_555,
            )
            template_666 = await WorkflowDraftService._load_template_daten(
                conn,
                table_name=draft_table_norm,
                template_uid=DEFAULT_TEMPLATE_UID,
            )

            tpl555_groups = template_555.get("TEMPLATES") if isinstance(template_555.get("TEMPLATES"), dict) else {}
            tpl666_groups = template_666.get("TEMPLATES") if isinstance(template_666.get("TEMPLATES"), dict) else {}

            daten: Dict[str, Any] = {}
            for group_name, group_value in tpl555_groups.items():
                if not isinstance(group_value, dict):
                    continue
                merged_group = WorkflowDraftService._fill_empty_groups_from_template(
                    group_value,
                    tpl666_groups.get(group_name) if isinstance(tpl666_groups.get(group_name), dict) else {},
                )
                daten[str(group_name)] = merged_group

            root_template = daten.get("ROOT") if isinstance(daten.get("ROOT"), dict) else {}
            root_values = {
                "SELF_GUID": str(draft_uid),
                "SELF_NAME": title_norm,
                "DRAFT_GUID": str(draft_uid),
                "WORKFLOW_TYPE": workflow_type_norm,
                "DIALOG_TYPE": "work",
                "STATUS": "draft",
                "OWNER_USER_GUID": str(uuid.UUID(str(owner_user_guid))),
                "MANDANT_GUID": str(uuid.UUID(str(mandant_guid))),
                "CREATED_AT": now_ts,
                "UPDATED_AT": now_ts,
                "TITLE": title_norm,
                "REVISION": 1,
                "IS_TEMPLATE": False,
            }
            daten["ROOT"] = WorkflowDraftService._merge_defined_fields(root_template, root_values)

            draft_db = daten.get("DRAFT_DB") if isinstance(daten.get("DRAFT_DB"), dict) else {}
            meta = draft_db.get("_META") if isinstance(draft_db.get("_META"), dict) else {}

            setup_template = meta.get("SETUP") if isinstance(meta.get("SETUP"), dict) else {}
            setup_values = initial_setup if isinstance(initial_setup, dict) else {}
            meta["SETUP"] = WorkflowDraftService._merge_defined_fields(setup_template, setup_values)

            state_template = meta.get("STATE") if isinstance(meta.get("STATE"), dict) else {}
            state_values = {
                "ACTIVE_TAB": 1,
                "MAX_TAB": 1,
                "STATUS": "draft",
            }
            meta["STATE"] = WorkflowDraftService._merge_defined_fields(state_template, state_values)

            workflow_template = meta.get("WORKFLOW") if isinstance(meta.get("WORKFLOW"), dict) else {}
            workflow_values = {
                "DRAFT_GUID": str(draft_uid),
                "WORKFLOW_TYPE": workflow_type_norm,
                "WORKFLOW_NAME": title_norm,
                "DIALOG_TYPE": "work",
                "TARGET_TABLE": str((initial_setup or {}).get("TARGET_TABLE") or "sys_dialogdaten"),
                "UPDATED_AT": now_ts,
            }
            meta["WORKFLOW"] = WorkflowDraftService._merge_defined_fields(workflow_template, workflow_values)

            draft_db["_META"] = meta
            daten["DRAFT_DB"] = draft_db

            await conn.execute(
                f"""
                INSERT INTO {draft_table_norm} (uid, daten, name, historisch, created_at, modified_at)
                VALUES ($1::uuid, $2::jsonb, $3, 0, NOW(), NOW())
                """,
                draft_uid,
                json.dumps(daten, ensure_ascii=False),
                title_norm,
            )

        return {
            "draft_guid": str(draft_uid),
            "workflow_type": workflow_type_norm,
            "title": title_norm,
            "status": "draft",
        }

    @staticmethod
    async def _load_draft_row(conn: asyncpg.Connection, draft_guid: str) -> Optional[asyncpg.Record]:
        return await WorkflowDraftService._load_draft_row_from_table(conn, draft_guid=draft_guid, draft_table=DRAFT_TABLE)

    @staticmethod
    async def _load_draft_row_from_table(
        conn: asyncpg.Connection,
        *,
        draft_guid: str,
        draft_table: str,
    ) -> Optional[asyncpg.Record]:
        return await conn.fetchrow(
            f"""
            SELECT uid, name, daten, created_at, modified_at
            FROM {draft_table}
            WHERE uid = $1::uuid AND COALESCE(historisch, 0) = 0
            """,
            uuid.UUID(str(draft_guid)),
        )

    @staticmethod
    async def save_draft_item(
        system_pool: asyncpg.Pool,
        *,
        draft_guid: str,
        item_type: str,
        item_key: str,
        payload: Dict[str, Any],
        updated_by_user_guid: str,
        draft_table: str = DRAFT_TABLE,
    ) -> Dict[str, Any]:
        draft_table_norm = WorkflowDraftService._normalize_table_name(draft_table, label="draft_table")
        await WorkflowDraftService._ensure_tables(
            system_pool,
            draft_table=draft_table_norm,
        )

        item_type_norm = str(item_type or "").strip().lower()
        if not item_type_norm:
            raise ValueError("item_type fehlt")

        item_key_norm = WorkflowDraftService._normalize_item_key(item_key)
        if not isinstance(payload, dict):
            raise ValueError("payload muss ein Objekt sein")

        draft_uuid = uuid.UUID(str(draft_guid))
        user_uuid = uuid.UUID(str(updated_by_user_guid))
        item_uid = WorkflowDraftService._deterministic_item_uid(str(draft_uuid), item_type_norm, item_key_norm)

        now_ts = now_pdvm_str()

        async with system_pool.acquire() as conn:
            draft_row = await WorkflowDraftService._load_draft_row_from_table(
                conn,
                draft_guid=str(draft_uuid),
                draft_table=draft_table_norm,
            )
            if not draft_row:
                raise ValueError("Draft nicht gefunden")

            draft_daten = WorkflowDraftService._as_json_dict(draft_row["daten"])
            draft_root = draft_daten.get("ROOT") if isinstance(draft_daten.get("ROOT"), dict) else {}
            draft_db = draft_daten.get("DRAFT_DB") if isinstance(draft_daten.get("DRAFT_DB"), dict) else {}
            draft_db = dict(draft_db)
            meta = draft_db.get("_META") if isinstance(draft_db.get("_META"), dict) else {}
            meta = dict(meta)

            status = str(draft_root.get("STATUS") or "draft").strip().lower()
            if status not in VALID_STATUSES:
                status = "draft"
            if status in {"built", "archived"}:
                raise ValueError(f"Draft ist nicht mehr editierbar (status={status})")

            if item_type_norm == "setup":
                setup_template = meta.get("SETUP") if isinstance(meta.get("SETUP"), dict) else None
                if setup_template is None:
                    raise ValueError("Template-Definition fehlt: DRAFT_DB._META.SETUP")
                meta["SETUP"] = WorkflowDraftService._merge_defined_fields(setup_template, dict(payload))
            elif item_type_norm == "state":
                state_meta = meta.get("STATE") if isinstance(meta.get("STATE"), dict) else None
                if state_meta is None:
                    raise ValueError("Template-Definition fehlt: DRAFT_DB._META.STATE")
                state_meta = dict(state_meta)
                state_meta = WorkflowDraftService._merge_defined_fields(state_meta, dict(payload))
                state_meta = WorkflowDraftService._merge_defined_fields(state_meta, {"UPDATED_AT": now_ts})
                meta["STATE"] = state_meta
            elif item_type_norm == "work" and item_key_norm == "container":
                workflow_meta = meta.get("WORKFLOW") if isinstance(meta.get("WORKFLOW"), dict) else None
                if workflow_meta is None:
                    raise ValueError("Template-Definition fehlt: DRAFT_DB._META.WORKFLOW")
                workflow_meta = dict(workflow_meta)
                incoming_workflow = payload.get("WORKFLOW") if isinstance(payload.get("WORKFLOW"), dict) else {}
                workflow_meta = WorkflowDraftService._merge_defined_fields(workflow_meta, dict(incoming_workflow))
                workflow_meta = WorkflowDraftService._merge_defined_fields(
                    workflow_meta,
                    {
                        "DRAFT_GUID": str(draft_uuid),
                        "UPDATED_AT": now_ts,
                    },
                )
                meta["WORKFLOW"] = workflow_meta

                for key, value in payload.items():
                    key_norm = str(key or "").strip()
                    if not key_norm or key_norm.upper() == "WORKFLOW":
                        continue
                    if not isinstance(value, dict):
                        continue
                    bucket_name = key_norm.upper()
                    if bucket_name not in draft_db:
                        raise ValueError(f"Nicht definierte DRAFT_DB-Gruppe: {bucket_name}")
                    # Harte Regel: Der uebergebene Bucket ist die komplette Wahrheit.
                    # Kein Merge, damit geloeschte/obsolet gewordene Records wirklich verschwinden.
                    draft_db[bucket_name] = dict(value)
            else:
                raise ValueError("item_type nicht erlaubt (erlaubt: setup, state, work/container)")

            revision = int(draft_root.get("REVISION") or 1)
            if item_type_norm == "state" and isinstance(payload, dict):
                try:
                    active_tab = int(payload.get("ACTIVE_TAB") or payload.get("active_tab") or 0)
                except Exception:
                    active_tab = 0
                try:
                    max_tab = int(payload.get("MAX_TAB") or payload.get("max_tab") or 0)
                except Exception:
                    max_tab = 0
                status_in = str(payload.get("STATUS") or payload.get("status") or "").strip().lower()

                if active_tab > 0:
                    draft_root["ACTIVE_TAB"] = active_tab
                if max_tab > 0:
                    draft_root["MAX_TAB"] = max_tab
                if status_in in VALID_STATUSES:
                    draft_root["STATUS"] = status_in

            draft_root["UPDATED_AT"] = now_ts
            draft_root["LAST_EDITOR_USER_GUID"] = str(user_uuid)
            draft_root["REVISION"] = revision + 1
            draft_daten["ROOT"] = draft_root
            draft_db["_META"] = meta
            draft_daten["DRAFT_DB"] = draft_db

            draft_payload = json.dumps(draft_daten, ensure_ascii=False)
            await conn.execute(
                f"""
                UPDATE {draft_table_norm}
                SET daten = $2::jsonb,
                    modified_at = NOW()
                WHERE uid = $1::uuid
                """,
                draft_uuid,
                draft_payload,
            )

        return {
            "draft_guid": str(draft_uuid),
            "item_uid": str(item_uid),
            "item_type": item_type_norm,
            "item_key": item_key_norm,
            "updated_at": now_ts,
        }

    @staticmethod
    async def load_draft(
        system_pool: asyncpg.Pool,
        *,
        draft_guid: str,
        draft_table: str = DRAFT_TABLE,
    ) -> Dict[str, Any]:
        draft_table_norm = WorkflowDraftService._normalize_table_name(draft_table, label="draft_table")
        await WorkflowDraftService._ensure_tables(
            system_pool,
            draft_table=draft_table_norm,
        )
        draft_uuid = uuid.UUID(str(draft_guid))

        async with system_pool.acquire() as conn:
            draft_row = await WorkflowDraftService._load_draft_row_from_table(
                conn,
                draft_guid=str(draft_uuid),
                draft_table=draft_table_norm,
            )
            if not draft_row:
                raise ValueError("Draft nicht gefunden")

        draft_daten = WorkflowDraftService._as_json_dict(draft_row["daten"])
        root = draft_daten.get("ROOT") if isinstance(draft_daten.get("ROOT"), dict) else {}
        draft_db = draft_daten.get("DRAFT_DB") if isinstance(draft_daten.get("DRAFT_DB"), dict) else {}
        draft_db = dict(draft_db)
        meta = draft_db.get("_META") if isinstance(draft_db.get("_META"), dict) else {}
        meta = dict(meta)

        items: List[Dict[str, Any]] = []
        setup_payload = meta.get("SETUP") if isinstance(meta.get("SETUP"), dict) else {}
        if setup_payload:
            items.append(
                {
                    "item_uid": str(WorkflowDraftService._deterministic_item_uid(str(draft_uuid), "setup", "setup")),
                    "item_type": "setup",
                    "item_key": "setup",
                    "payload": dict(setup_payload),
                    "updated_at": root.get("UPDATED_AT"),
                }
            )

        workflow_meta = meta.get("WORKFLOW") if isinstance(meta.get("WORKFLOW"), dict) else {}
        work_payload: Dict[str, Any] = {"WORKFLOW": dict(workflow_meta)}
        for bucket_name, bucket_value in draft_db.items():
            if str(bucket_name).startswith("_"):
                continue
            if not isinstance(bucket_value, dict):
                continue
            work_payload[str(bucket_name).lower()] = dict(bucket_value)

        has_work_data = any(k != "WORKFLOW" for k in work_payload.keys()) or bool(workflow_meta)
        if has_work_data:
            items.append(
                {
                    "item_uid": str(WorkflowDraftService._deterministic_item_uid(str(draft_uuid), "work", "container")),
                    "item_type": "work",
                    "item_key": "container",
                    "payload": work_payload,
                    "updated_at": root.get("UPDATED_AT"),
                }
            )

        state_payload = meta.get("STATE") if isinstance(meta.get("STATE"), dict) else {}
        if state_payload:
            items.append(
                {
                    "item_uid": str(WorkflowDraftService._deterministic_item_uid(str(draft_uuid), "state", "workflow_state")),
                    "item_type": "state",
                    "item_key": "workflow_state",
                    "payload": dict(state_payload),
                    "updated_at": state_payload.get("UPDATED_AT") or root.get("UPDATED_AT"),
                }
            )

        custom_items = draft_db.get("_ITEMS") if isinstance(draft_db.get("_ITEMS"), dict) else {}
        for map_key, map_payload in custom_items.items():
            map_payload = map_payload if isinstance(map_payload, dict) else {}
            token = str(map_key or "")
            if ":" in token:
                map_type, map_item_key = token.split(":", 1)
            else:
                map_type, map_item_key = "item", token
            items.append(
                {
                    "item_uid": str(WorkflowDraftService._deterministic_item_uid(str(draft_uuid), map_type, map_item_key)),
                    "item_type": map_type,
                    "item_key": map_item_key,
                    "payload": dict(map_payload),
                    "updated_at": root.get("UPDATED_AT"),
                }
            )

        return {
            "draft_guid": str(draft_row["uid"]),
            "name": draft_row["name"],
            "root": root,
            "items": items,
        }

    @staticmethod
    async def list_open_drafts(
        system_pool: asyncpg.Pool,
        *,
        owner_user_guid: str,
        mandant_guid: str,
        draft_table: str = DRAFT_TABLE,
    ) -> Dict[str, Any]:
        draft_table_norm = WorkflowDraftService._normalize_table_name(draft_table, label="draft_table")
        await WorkflowDraftService._ensure_tables(
            system_pool,
            draft_table=draft_table_norm,
        )
        owner_norm = str(uuid.UUID(str(owner_user_guid)))
        mandant_norm = str(uuid.UUID(str(mandant_guid)))

        async with system_pool.acquire() as conn:
            rows = await conn.fetch(
                f"""
                SELECT uid, name, daten, modified_at
                                FROM {draft_table_norm}
                WHERE COALESCE(historisch, 0) = 0
                  AND (daten->'ROOT'->>'OWNER_USER_GUID') = $1
                  AND (daten->'ROOT'->>'MANDANT_GUID') = $2
                ORDER BY modified_at DESC
                """,
                owner_norm,
                mandant_norm,
            )

        drafts: List[Dict[str, Any]] = []
        for row in rows:
            daten = WorkflowDraftService._as_json_dict(row["daten"])
            root = daten.get("ROOT") if isinstance(daten.get("ROOT"), dict) else {}
            status = str(root.get("STATUS") or "draft").strip().lower()
            if status in {"built", "archived"}:
                continue

            drafts.append(
                {
                    "draft_guid": str(row["uid"]),
                    "title": root.get("TITLE") or row["name"],
                    "workflow_type": root.get("WORKFLOW_TYPE"),
                    "status": status,
                    "updated_at": root.get("UPDATED_AT") or (row["modified_at"].isoformat() if row["modified_at"] else None),
                    "revision": int(root.get("REVISION") or 1),
                }
            )

        return {"drafts": drafts, "count": len(drafts)}

    @staticmethod
    async def validate_draft(
        system_pool: asyncpg.Pool,
        *,
        draft_guid: str,
        draft_table: str = DRAFT_TABLE,
    ) -> Dict[str, Any]:
        data = await WorkflowDraftService.load_draft(
            system_pool,
            draft_guid=draft_guid,
            draft_table=draft_table,
        )
        root = data.get("root") if isinstance(data.get("root"), dict) else {}
        items = data.get("items") if isinstance(data.get("items"), list) else []

        errors: List[Dict[str, Any]] = []

        title = str(root.get("TITLE") or "").strip()
        if not title:
            errors.append({"code": "MISSING_TITLE", "field": "ROOT.TITLE", "message": "Titel fehlt"})

        workflow_type = str(root.get("WORKFLOW_TYPE") or "").strip()
        if not workflow_type:
            errors.append(
                {"code": "MISSING_WORKFLOW_TYPE", "field": "ROOT.WORKFLOW_TYPE", "message": "Workflow-Typ fehlt"}
            )

        setup_item = None
        for item in items:
            if str(item.get("item_type") or "").strip().lower() == "setup":
                setup_item = item
                break

        if not setup_item:
            errors.append(
                {
                    "code": "MISSING_SETUP_ITEM",
                    "field": "items[setup]",
                    "message": "Setup-Block fehlt (item_type=setup)",
                }
            )
        else:
            payload = setup_item.get("payload") if isinstance(setup_item.get("payload"), dict) else {}
            wf_name = str(payload.get("WORKFLOW_NAME") or payload.get("workflow_name") or "").strip()
            if not wf_name:
                errors.append(
                    {
                        "code": "MISSING_SETUP_WORKFLOW_NAME",
                        "field": "setup.WORKFLOW_NAME",
                        "message": "Pflichtfeld WORKFLOW_NAME fehlt im Setup",
                    }
                )

            wf_type = str(payload.get("WORKFLOW_TYPE") or payload.get("workflow_type") or "").strip()
            if not wf_type:
                errors.append(
                    {
                        "code": "MISSING_SETUP_WORKFLOW_TYPE",
                        "field": "setup.WORKFLOW_TYPE",
                        "message": "Pflichtfeld WORKFLOW_TYPE fehlt im Setup",
                    }
                )

        tabs_item = None
        content_item = None
        work_container_item = None
        for item in items:
            item_type = str(item.get("item_type") or "").strip().lower()
            if item_type == "tabs" and tabs_item is None:
                tabs_item = item
            if item_type == "content" and content_item is None:
                content_item = item
            if item_type == "work" and str(item.get("item_key") or "").strip().lower() == "container" and work_container_item is None:
                work_container_item = item

        has_tabs = False
        has_content = False

        if work_container_item:
            payload = work_container_item.get("payload") if isinstance(work_container_item.get("payload"), dict) else {}
            dialog_bucket = payload.get("sys_dialogdaten") if isinstance(payload.get("sys_dialogdaten"), dict) else {}
            view_bucket = payload.get("sys_viewdaten") if isinstance(payload.get("sys_viewdaten"), dict) else {}
            frame_bucket = payload.get("sys_framedaten") if isinstance(payload.get("sys_framedaten"), dict) else {}

            has_tabs = len(dialog_bucket) >= 1
            # Mindestens View + Content-Struktur in den Zieltabellen vorhanden.
            has_content = len(view_bucket) >= 1 and len(frame_bucket) >= 1

        if not has_tabs and not tabs_item:
            errors.append(
                {
                    "code": "MISSING_TABS_ITEM",
                    "field": "items[tabs]",
                    "message": "Mindestens ein Tabs-Block ist erforderlich",
                }
            )
        elif not has_tabs:
            payload = tabs_item.get("payload") if isinstance(tabs_item.get("payload"), dict) else {}
            items_raw = payload.get("items") if isinstance(payload.get("items"), list) else []
            if len(items_raw) < 1:
                errors.append(
                    {
                        "code": "EMPTY_TABS",
                        "field": "tabs.items",
                        "message": "Mindestens ein Tab muss vorhanden sein",
                    }
                )

        if not has_content and not content_item:
            errors.append(
                {
                    "code": "MISSING_CONTENT_ITEM",
                    "field": "items[content]",
                    "message": "Mindestens ein Content-Block ist erforderlich",
                }
            )
        elif not has_content:
            payload = content_item.get("payload") if isinstance(content_item.get("payload"), dict) else {}
            items_raw = payload.get("items") if isinstance(payload.get("items"), list) else []
            if len(items_raw) < 1:
                errors.append(
                    {
                        "code": "EMPTY_CONTENT",
                        "field": "content.items",
                        "message": "Mindestens ein Content-Block muss vorhanden sein",
                    }
                )

        return {
            "draft_guid": data.get("draft_guid"),
            "valid": len(errors) == 0,
            "error_count": len(errors),
            "errors": errors,
        }

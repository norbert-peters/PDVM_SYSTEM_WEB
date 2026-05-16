"""
Control Dictionary Service

ARCHITECTURE_RULES-konform:
- Router enthält keine SQL-Statements
- Tabellenzugriff über PdvmDatabase (Routing system/mandant/auth zentral)
- Runtime-Template-Cache aus GCS (nicht persistent)
"""

from __future__ import annotations

import json
import time
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.core.central_write_service import update_record_central
from app.core.control_template_service import ControlTemplateService, create_control, switch_control_modul
from app.core.pdvm_datenbank import PdvmDatabase
from app.core.pdvm_central_systemsteuerung import PdvmCentralSystemsteuerung


_CONTROL_DICT_CACHE_GROUP = "CACHE.CONTROL_DICT"


def _table_prefix(table_name: str) -> str:
    table = str(table_name or "").strip()
    if not table:
        return "SYS"
    if "_" in table:
        return table.split("_", 1)[0].upper()
    return table[:3].upper() or "CTL"


def _canonical_control_name(table_name: str, field_name: str) -> str:
    prefix = _table_prefix(table_name)
    field = str(field_name or "").strip().upper()
    if not field:
        return prefix
    return f"{prefix}_{field}"


class ControlDictService:
    def __init__(self, gcs: PdvmCentralSystemsteuerung):
        self.gcs = gcs
        self.db = PdvmDatabase(
            "sys_control_dict",
            system_pool=gcs._system_pool,
            mandant_pool=gcs._mandant_pool,
        )

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
    def _to_iso(value: Any) -> str:
        if isinstance(value, datetime):
            return value.isoformat()
        return str(value or "").strip()

    @staticmethod
    def _norm_lower(value: Any, default: str = "*") -> str:
        s = str(value or "").strip().lower()
        return s if s else default

    def _control_cache_key(self, *, table: Optional[str], edit_type: Optional[str], frame_guid: Optional[str]) -> str:
        t = self._norm_lower(table, "*")
        e = self._norm_lower(edit_type, "*")
        f = self._norm_lower(frame_guid, "*")
        return f"CACHE.CONTROL_DICT::{t}::{e}::{f}"

    def _get_session_cache(self) -> Dict[str, Dict[str, Any]]:
        cache = getattr(self.gcs, "_pdvm_control_dict_cache", None)
        if isinstance(cache, dict):
            return cache
        cache = {}
        setattr(self.gcs, "_pdvm_control_dict_cache", cache)
        return cache

    def _record_cache_stat(self, key: str) -> None:
        stats = getattr(self.gcs, "_pdvm_control_dict_cache_stats", None)
        if not isinstance(stats, dict):
            stats = {"hits": 0, "persistent_hits": 0, "misses": 0, "rebuilds": 0}
            setattr(self.gcs, "_pdvm_control_dict_cache_stats", stats)
        stats[key] = int(stats.get(key, 0) or 0) + 1

    def _read_persistent_cache(self, cache_key: str) -> Optional[Dict[str, Any]]:
        try:
            raw, _ = self.gcs.anwendungsdaten.get_value(_CONTROL_DICT_CACHE_GROUP, cache_key, ab_zeit=float(self.gcs.stichtag))
        except Exception:
            return None
        return raw if isinstance(raw, dict) else None

    async def _write_persistent_cache(self, cache_key: str, payload: Dict[str, Any]) -> None:
        try:
            self.gcs.anwendungsdaten.set_value(_CONTROL_DICT_CACHE_GROUP, cache_key, payload, float(self.gcs.stichtag))
            await self.gcs.anwendungsdaten.save_all_values()
        except Exception:
            return

    async def _source_fingerprint(self) -> Dict[str, Any]:
        pool = self.db.get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT MAX(modified_at) AS max_modified_at, COUNT(*) AS cnt
                FROM sys_control_dict
                WHERE historisch = 0
                """
            )
        return {
            "max_modified_at": self._to_iso(row.get("max_modified_at") if row else None),
            "count": int((row.get("cnt") if row else 0) or 0),
        }

    async def _build_filtered_controls(self, *, modul_filter: str, table_filter: str) -> List[Dict[str, Any]]:
        rows = await self.db.get_all(where="historisch = 0", order_by="name ASC")

        items: List[Dict[str, Any]] = []
        for row in rows:
            source_data = self._as_dict(row.get("daten"))
            effective = await self._resolve_effective(source_data)
            extracted = self._extract_list_item_values(effective, source_data)

            item_modul = str(extracted.get("modul_type") or "").strip().lower()
            item_table = str(extracted.get("table") or "").strip().lower()
            if modul_filter and item_modul != modul_filter:
                continue
            if table_filter and item_table and item_table != table_filter:
                continue

            items.append(
                {
                    "uid": row.get("uid"),
                    "name": row.get("name") or "",
                    "modul_type": extracted.get("modul_type"),
                    "label": extracted.get("label"),
                    "type": extracted.get("type"),
                    "table": extracted.get("table"),
                    "gruppe": extracted.get("gruppe"),
                    "field": extracted.get("field"),
                }
            )
        return items

    async def _get_cached_control_items(
        self,
        *,
        table: Optional[str],
        edit_type: Optional[str],
        frame_guid: Optional[str],
    ) -> List[Dict[str, Any]]:
        cache_key = self._control_cache_key(table=table, edit_type=edit_type, frame_guid=frame_guid)
        session_cache = self._get_session_cache()
        fingerprint = await self._source_fingerprint()

        session_entry = session_cache.get(cache_key)
        if isinstance(session_entry, dict) and session_entry.get("source_fingerprint") == fingerprint:
            self._record_cache_stat("hits")
            items = session_entry.get("items")
            return items if isinstance(items, list) else []

        persisted = self._read_persistent_cache(cache_key)
        if isinstance(persisted, dict) and persisted.get("source_fingerprint") == fingerprint:
            items_p = persisted.get("items")
            if isinstance(items_p, list):
                session_cache[cache_key] = {
                    "source_fingerprint": fingerprint,
                    "items": items_p,
                    "ts": float(time.time()),
                }
                self._record_cache_stat("persistent_hits")
                return items_p

        self._record_cache_stat("misses")
        modul_filter = self._norm_lower(edit_type, "") if edit_type else ""
        table_filter = self._norm_lower(table, "") if table else ""
        items = await self._build_filtered_controls(modul_filter=modul_filter, table_filter=table_filter)

        payload = {
            "source_fingerprint": fingerprint,
            "items": items,
            "built_at": datetime.utcnow().isoformat(),
        }
        session_cache[cache_key] = {
            "source_fingerprint": fingerprint,
            "items": items,
            "ts": float(time.time()),
        }
        await self._write_persistent_cache(cache_key, payload)
        self._record_cache_stat("rebuilds")
        return items

    async def _invalidate_control_cache(self) -> None:
        session_cache = self._get_session_cache()
        keys_to_remove = [k for k in session_cache.keys() if str(k).startswith("CACHE.CONTROL_DICT::")]
        for key in keys_to_remove:
            session_cache.pop(key, None)

    def _extract_list_item_values(self, effective: Dict[str, Any], source_data: Dict[str, Any]) -> Dict[str, Any]:
        effective_control = effective.get("CONTROL") if isinstance(effective.get("CONTROL"), dict) else {}
        source_control = source_data.get("CONTROL") if isinstance(source_data.get("CONTROL"), dict) else {}

        return {
            "modul_type": (
                effective.get("modul_type")
                or effective.get("MODUL_TYPE")
                or effective_control.get("MODUL_TYPE")
                or source_data.get("modul_type")
                or source_data.get("MODUL_TYPE")
                or source_control.get("MODUL_TYPE")
            ),
            "label": (
                effective.get("label")
                or effective.get("LABEL")
                or effective_control.get("LABEL")
                or source_data.get("label")
                or source_data.get("LABEL")
                or source_control.get("LABEL")
            ),
            "type": (
                effective.get("type")
                or effective.get("TYPE")
                or effective_control.get("TYPE")
                or source_data.get("type")
                or source_data.get("TYPE")
                or source_control.get("TYPE")
            ),
            "table": (
                effective.get("table")
                or effective.get("TABLE")
                or effective_control.get("TABLE")
                or source_data.get("table")
                or source_data.get("TABLE")
                or source_control.get("TABLE")
            ),
            "gruppe": (
                effective.get("gruppe")
                or effective.get("GRUPPE")
                or effective_control.get("GRUPPE")
                or source_data.get("gruppe")
                or source_data.get("GRUPPE")
                or source_control.get("GRUPPE")
            ),
            "field": (
                effective.get("field")
                or effective.get("FIELD")
                or effective.get("feld")
                or effective.get("FELD")
                or effective_control.get("FIELD")
                or effective_control.get("FELD")
                or source_data.get("field")
                or source_data.get("FIELD")
                or source_data.get("feld")
                or source_data.get("FELD")
                or source_control.get("FIELD")
                or source_control.get("FELD")
            ),
        }

    def _actor_user_uid(self) -> Optional[uuid.UUID]:
        try:
            return uuid.UUID(str(getattr(self.gcs, "user_guid", "") or ""))
        except Exception:
            return None

    async def _resolve_effective(self, source_data: Dict[str, Any]) -> Dict[str, Any]:
        template_555 = self.gcs.get_control_template_555_cache()
        pool = self.db.get_pool()
        async with pool.acquire() as conn:
            service = ControlTemplateService(conn, template_555_data=template_555)
            effective = await service.resolve_effective_control_data(source_data)
            return effective if isinstance(effective, dict) else source_data

    async def _normalize_for_storage(self, effective_data: Dict[str, Any]) -> Dict[str, Any]:
        template_555 = self.gcs.get_control_template_555_cache()
        pool = self.db.get_pool()
        async with pool.acquire() as conn:
            service = ControlTemplateService(conn, template_555_data=template_555)
            out = await service.normalize_control_for_storage(effective_data)
            return out if isinstance(out, dict) else {}

    async def get_control(self, uid: uuid.UUID) -> Optional[Dict[str, Any]]:
        row = await self.db.get_by_uid(uid)
        if not row:
            return None
        source_data = self._as_dict(row.get("daten"))
        effective = await self._resolve_effective(source_data)
        return {
            "uid": row.get("uid"),
            "name": row.get("name") or "",
            "daten": effective,
            "historisch": int(row.get("historisch") or 0),
        }

    async def list_controls(
        self,
        *,
        modul_type: Optional[str] = None,
        table: Optional[str] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> Dict[str, Any]:
        items = await self._get_cached_control_items(table=table, edit_type=modul_type, frame_guid="*")

        total = len(items)
        s = max(0, int(skip or 0))
        l = max(1, int(limit or 100))
        paged = items[s : s + l]

        return {
            "total": total,
            "skip": s,
            "limit": l,
            "items": paged,
        }

    async def get_modul_template(self, modul_type: str) -> Dict[str, Any]:
        template_555 = self.gcs.get_control_template_555_cache()
        pool = self.db.get_pool()
        async with pool.acquire() as conn:
            service = ControlTemplateService(conn, template_555_data=template_555)
            return await service.load_modul_template(modul_type)

    async def create_control(self, *, modul_type: str, table_name: str, field_data: Dict[str, Any]) -> Dict[str, Any]:
        pool = self.db.get_pool()
        async with pool.acquire() as conn:
            control_uid = await create_control(conn, modul_type, table_name, field_data)
        await self._invalidate_control_cache()
        created = await self.get_control(control_uid)
        if not created:
            raise ValueError("Control konnte nach dem Erstellen nicht geladen werden")
        return created

    async def switch_modul(self, *, uid: uuid.UUID, new_modul_type: str) -> Dict[str, Any]:
        pool = self.db.get_pool()
        async with pool.acquire() as conn:
            await switch_control_modul(conn, uid, new_modul_type)
        await self._invalidate_control_cache()
        updated = await self.get_control(uid)
        if not updated:
            raise ValueError("Control nach MODUL-Switch nicht gefunden")
        return updated

    async def update_control(self, *, uid: uuid.UUID, field_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        row = await self.db.get_by_uid(uid)
        if not row:
            return None

        source_data = self._as_dict(row.get("daten"))
        effective_data = await self._resolve_effective(source_data)
        effective_data.update(field_data or {})

        table_name = str(
            effective_data.get("table")
            or effective_data.get("TABLE")
            or ""
        ).strip()
        field_name = str(
            effective_data.get("field")
            or effective_data.get("FIELD")
            or effective_data.get("feld")
            or effective_data.get("FELD")
            or ""
        ).strip().upper()
        if field_name:
            effective_data["field"] = field_name
            effective_data["FIELD"] = field_name
            effective_data["feld"] = field_name
            effective_data["FELD"] = field_name
            canonical_name = _canonical_control_name(table_name, field_name)
            effective_data["name"] = canonical_name
            effective_data["SELF_NAME"] = canonical_name

        data_to_store = await self._normalize_for_storage(effective_data)
        new_name = str(effective_data.get("SELF_NAME") or effective_data.get("name") or row.get("name") or "")

        await update_record_central(
            table_name="sys_control_dict",
            uid=uid,
            daten=data_to_store,
            name=new_name,
            gcs=self.gcs,
            actor_user_uid=self._actor_user_uid(),
            actor_ip=getattr(self.gcs, "actor_ip", None),
        )
        await self._invalidate_control_cache()

        return {
            "uid": uid,
            "name": new_name,
            "daten": effective_data,
            "historisch": int(row.get("historisch") or 0),
        }

    async def delete_control(self, uid: uuid.UUID) -> bool:
        row = await self.db.get_by_uid(uid)
        if not row:
            return False
        daten = self._as_dict(row.get("daten"))
        await update_record_central(
            table_name="sys_control_dict",
            uid=uid,
            daten=daten,
            historisch=1,
            gcs=self.gcs,
            actor_user_uid=self._actor_user_uid(),
            actor_ip=getattr(self.gcs, "actor_ip", None),
        )
        await self._invalidate_control_cache()
        return True

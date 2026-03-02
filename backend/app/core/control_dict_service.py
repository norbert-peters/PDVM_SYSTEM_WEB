"""
Control Dictionary Service

ARCHITECTURE_RULES-konform:
- Router enthält keine SQL-Statements
- Tabellenzugriff über PdvmDatabase (Routing system/mandant/auth zentral)
- Runtime-Template-Cache aus GCS (nicht persistent)
"""

from __future__ import annotations

import json
import uuid
from typing import Any, Dict, List, Optional

from app.core.control_template_service import ControlTemplateService, create_control, switch_control_modul
from app.core.pdvm_datenbank import PdvmDatabase
from app.core.pdvm_central_systemsteuerung import PdvmCentralSystemsteuerung


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
        rows = await self.db.get_all(where="historisch = 0", order_by="name ASC")

        items: List[Dict[str, Any]] = []
        modul_filter = str(modul_type or "").strip().lower()
        table_filter = str(table or "").strip().lower()

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
        created = await self.get_control(control_uid)
        if not created:
            raise ValueError("Control konnte nach dem Erstellen nicht geladen werden")
        return created

    async def switch_modul(self, *, uid: uuid.UUID, new_modul_type: str) -> Dict[str, Any]:
        pool = self.db.get_pool()
        async with pool.acquire() as conn:
            await switch_control_modul(conn, uid, new_modul_type)
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

        if "name" in (field_data or {}):
            table_name = str(effective_data.get("table") or "")
            table_prefix = table_name.split("_")[0] + "_" if "_" in table_name else (table_name[:3] + "_" if table_name else "")
            effective_data["SELF_NAME"] = f"{table_prefix}{field_data['name']}"

        data_to_store = await self._normalize_for_storage(effective_data)
        new_name = str(effective_data.get("SELF_NAME") or row.get("name") or "")

        await self.db.update(uid=uid, daten=data_to_store, name=new_name)

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
        await self.db.update(uid=uid, daten=daten, historisch=1)
        return True

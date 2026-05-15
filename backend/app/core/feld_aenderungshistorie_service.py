"""
Service für historischen Feld-Änderungsnachweis (V1).

V1-Prinzipien:
- Insert only
- Nur geänderte Felder
- Monatsschlüssel aus created_at
- link_uid = Bezugsdatensatz-UID
- name = Feld-UID (oder Übergangs-Fallback)
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

import asyncpg

from app.core.pdvm_datetime import datetime_to_pdvm, pdvm_to_str


class FieldChangeHistoryService:
    HISTORY_TABLE = "sys_feld_aenderungshistorie"
    CONFLICT_MESSAGE = "Daten zwischenzeitlich geändert. Bitte neu lesen"

    _SENSITIVE_KEYWORDS = (
        "passwort",
        "password",
        "token",
        "secret",
        "apikey",
        "api_key",
        "otp",
        "pin",
    )

    @staticmethod
    def _is_guid(value: str) -> bool:
        try:
            uuid.UUID(str(value))
            return True
        except Exception:
            return False

    @staticmethod
    def _normalize(value: Any) -> str:
        return json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)

    @staticmethod
    def _flatten_group_fields(data: Any) -> Dict[Tuple[str, str], Any]:
        """Flacht klassische PDVM Gruppe/Feld-Struktur zu (gruppe, feld) -> wert ab."""
        if not isinstance(data, dict):
            return {}

        flat: Dict[Tuple[str, str], Any] = {}
        for group, group_value in data.items():
            if not isinstance(group_value, dict):
                continue
            for field, field_value in group_value.items():
                flat[(str(group), str(field))] = field_value
        return flat

    @staticmethod
    def _value_type(value: Any) -> str:
        if value is None:
            return "null"
        if isinstance(value, bool):
            return "bool"
        if isinstance(value, int):
            return "int"
        if isinstance(value, float):
            return "float"
        if isinstance(value, str):
            return "str"
        if isinstance(value, list):
            return "array"
        if isinstance(value, dict):
            return "object"
        return type(value).__name__

    @classmethod
    def _policy_for_field(cls, field_name: str) -> str:
        field_norm = str(field_name or "").strip().lower()
        for marker in cls._SENSITIVE_KEYWORDS:
            if marker in field_norm:
                return "hash_only"
        return "none"

    @staticmethod
    def _mask_value(value: Any) -> str:
        text = "" if value is None else str(value)
        if len(text) <= 4:
            return "****"
        return f"{text[:2]}***{text[-2:]}"

    @staticmethod
    def _hash_value(value: Any) -> str:
        raw = json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    @classmethod
    async def _resolve_field_uid(
        cls,
        conn: asyncpg.Connection,
        *,
        field_name: str,
        cache: Dict[str, str],
        table_exists_cache: Dict[str, bool],
    ) -> str:
        """
        Liefert Feld-UID.
        Priorität:
        1) Feldname selbst ist GUID
        2) sys_contr_dict_man.name
        3) sys_control_dict.name
        4) Fallback auf Feldname
        """
        field_name = str(field_name or "").strip()
        if not field_name:
            return ""

        if cls._is_guid(field_name):
            return str(uuid.UUID(field_name))

        cache_key = field_name.lower()
        if cache_key in cache:
            return cache[cache_key]

        for table_name in ("sys_contr_dict_man", "sys_control_dict"):
            exists = table_exists_cache.get(table_name)
            if exists is None:
                exists = bool(
                    await conn.fetchval(
                        "SELECT to_regclass($1) IS NOT NULL",
                        f"public.{table_name}",
                    )
                )
                table_exists_cache[table_name] = exists

            if not exists:
                continue

            row = await conn.fetchrow(
                f"""
                SELECT uid::text AS uid
                FROM {table_name}
                WHERE lower(name) = lower($1)
                  AND COALESCE(historisch, 0) = 0
                ORDER BY modified_at DESC, created_at DESC
                LIMIT 1
                """,
                field_name,
            )
            if row and row.get("uid"):
                cache[cache_key] = str(row["uid"])
                return cache[cache_key]

        cache[cache_key] = field_name
        return field_name

    @classmethod
    async def write_history_entries(
        cls,
        conn: asyncpg.Connection,
        *,
        target_table: str,
        target_uid: uuid.UUID,
        old_data: Dict[str, Any],
        new_data: Dict[str, Any],
        actor_user_uid: Optional[uuid.UUID] = None,
        actor_ip: Optional[str] = None,
    ) -> int:
        """Schreibt Insert-only Historienzeilen für alle geänderten Felder."""
        if str(target_table).strip().lower() == cls.HISTORY_TABLE:
            return 0

        old_flat = cls._flatten_group_fields(old_data)
        new_flat = cls._flatten_group_fields(new_data)
        keys = set(old_flat.keys()) | set(new_flat.keys())

        if not keys:
            return 0

        now_utc = datetime.now(timezone.utc)
        month_key = now_utc.strftime("%Y-%m")
        changed_at_pdvm = pdvm_to_str(datetime_to_pdvm(now_utc.replace(tzinfo=None)))

        field_uid_cache: Dict[str, str] = {}
        table_exists_cache: Dict[str, bool] = {}
        inserted = 0

        for group_name, field_name in sorted(keys):
            old_value = old_flat.get((group_name, field_name))
            new_value = new_flat.get((group_name, field_name))

            if cls._normalize(old_value) == cls._normalize(new_value):
                continue

            field_uid = await cls._resolve_field_uid(
                conn,
                field_name=field_name,
                cache=field_uid_cache,
                table_exists_cache=table_exists_cache,
            )

            policy = cls._policy_for_field(field_name)
            sensitive = policy != "none"

            if policy == "hash_only":
                stored_old = cls._hash_value(old_value)
                stored_new = cls._hash_value(new_value)
            elif policy == "mask":
                stored_old = cls._mask_value(old_value)
                stored_new = cls._mask_value(new_value)
            else:
                stored_old = old_value
                stored_new = new_value

            payload = {
                "ROOT": {
                    "TABLE": cls.HISTORY_TABLE,
                    "SELF_LINK_UID": str(target_uid),
                },
                "META": {
                    "month_key": month_key,
                    "target_table": str(target_table),
                    "target_uid": str(target_uid),
                    "field_uid": str(field_uid),
                    "field_name": str(field_name),
                    "group_name": str(group_name),
                    "field_source": "dictionary_uid" if cls._is_guid(str(field_uid)) else "sys_control_dict_fallback",
                },
                "CHANGE": {
                    "old_value": stored_old,
                    "new_value": stored_new,
                    "old_value_type": cls._value_type(old_value),
                    "new_value_type": cls._value_type(new_value),
                },
                "ACTOR": {
                    "user_uid": str(actor_user_uid) if actor_user_uid else None,
                    "client_ip": str(actor_ip) if actor_ip else None,
                },
                "TIME": {
                    "changed_at_pdvm": changed_at_pdvm,
                    "changed_at_utc": now_utc.isoformat(),
                },
                "FLAGS": {
                    "sensitive": sensitive,
                    "sensitive_policy": policy,
                },
            }

            source_hash = hashlib.sha256(
                cls._normalize(
                    {
                        "target_uid": str(target_uid),
                        "field_uid": str(field_uid),
                        "old": stored_old,
                        "new": stored_new,
                        "changed_at_pdvm": changed_at_pdvm,
                    }
                ).encode("utf-8")
            ).hexdigest()

            await conn.execute(
                f"""
                INSERT INTO {cls.HISTORY_TABLE}
                    (uid, link_uid, daten, name, historisch, source_hash)
                VALUES
                    ($1, $2, $3::jsonb, $4, 0, $5)
                """,
                uuid.uuid4(),
                target_uid,
                json.dumps(payload, ensure_ascii=False, default=str),
                str(field_uid),
                source_hash,
            )
            inserted += 1

        return inserted

    @classmethod
    async def cleanup_retention(cls, conn: asyncpg.Connection, retention_months: int) -> int:
        """Löscht Historienzeilen außerhalb der Aufbewahrungszeit."""
        result = await conn.execute(
            f"""
            DELETE FROM {cls.HISTORY_TABLE}
            WHERE created_at < (NOW() - ($1::int * INTERVAL '1 month'))
            """,
            int(retention_months),
        )
        return int(str(result).split(" ")[-1]) if result else 0

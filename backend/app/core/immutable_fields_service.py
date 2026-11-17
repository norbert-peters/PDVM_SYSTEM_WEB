"""
Unveraenderliche Felder (CONTROL.IMMUTABLE=true im sys_control_dict, Regel 2.15 / 1.10a).

Ein Feld mit IMMUTABLE darf nach der Anlage nicht mehr geaendert werden. Gesetzt werden darf es einmalig, solange
es im bestehenden Satz leer ist (Set-Once). Optional macht `CONTROL.IMMUTABLE_AFTER` (Pfad `GRUPPE.FELD`, z. B.
`ROOT.DB_CREATED_AT`) die Sperre bedingt: das Feld bleibt aenderbar, bis das Bedingungsfeld im gespeicherten Satz
einen Wert hat (Mandant: Verbindungsdaten sind bis zur Einrichtung der Datenbank korrigierbar). Die Sperre im
Formular ist nur Komfort; verbindlich ist diese Pruefung im zentralen Schreibpfad (`central_write_service.update_record_central`).
"""
from __future__ import annotations

import json
import uuid
from typing import Any, Dict, List, Optional, Tuple

from app.core.pdvm_datenbank import PdvmDatabase


class ImmutableFieldError(ValueError):
    def __init__(self, violations: List[Dict[str, str]]):
        self.violations = violations
        fields = ", ".join(f"{v['group']}.{v['field']}" for v in violations)
        super().__init__(f"Unveränderliche Felder dürfen nicht geändert werden: {fields}")


def _read(daten: Any, group: str, field: str) -> Any:
    cursor = daten
    for part in [p.strip() for p in str(group or "ROOT").split(".") if p.strip()] + [field]:
        if not isinstance(cursor, dict):
            return None
        cursor = cursor.get(part)
    return cursor


def _normalize(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True, ensure_ascii=False) if value else None
    text = str(value).strip()
    return text or None


def _split_path(path: str) -> Tuple[str, str]:
    group, _, field = str(path or "").strip().rpartition(".")
    return (group or "ROOT"), field


def _is_unlocked_by_record(old_daten: Dict[str, Any], after: Optional[str]) -> bool:
    """Bedingte Sperre (`IMMUTABLE_AFTER`): frei, solange das Bedingungsfeld im gespeicherten Satz leer ist."""
    if not after:
        return False
    group, field = _split_path(after)
    value = _normalize(_read(old_daten, group, field))
    return value is None or value == "-eingeben-"


def find_immutable_violations(
    old_daten: Dict[str, Any], new_daten: Dict[str, Any], fields: List[Tuple[Any, ...]]
) -> List[Dict[str, str]]:
    """`fields`: (GRUPPE, FELD) oder (GRUPPE, FELD, IMMUTABLE_AFTER)."""
    violations = []
    for entry in fields:
        group, field = entry[0], entry[1]
        after = entry[2] if len(entry) > 2 else None
        if _is_unlocked_by_record(old_daten, after):
            continue
        old = _normalize(_read(old_daten, group, field))
        if old is not None and _normalize(_read(new_daten, group, field)) != old:
            violations.append({"group": group, "field": field})
    return violations


async def enforce_immutable_fields(
    *, table_name: str, uid: uuid.UUID, new_daten: Dict[str, Any], system_pool: Any, mandant_pool: Any
) -> None:
    if system_pool is None:
        from app.core.frame_runtime_service import resolve_pool_scope

        system_pool = (await resolve_pool_scope(None))._system_pool

    fields = await PdvmDatabase.load_immutable_control_fields(table_name, system_pool=system_pool)
    if not fields:
        return
    row = await PdvmDatabase(table_name, system_pool=system_pool, mandant_pool=mandant_pool).get_by_uid(uid)
    if not row:
        return
    daten = row.get("daten")
    old_daten = json.loads(daten) if isinstance(daten, str) else (daten or {})
    violations = find_immutable_violations(old_daten, new_daten, fields)
    if violations:
        raise ImmutableFieldError(violations)

"""
Geloeschte Mandanten (Aktion `mandant.delete`): der Satz in `asy_mandanten` bleibt erhalten, ist aber nicht mehr erreichbar.

Marker: `gilt_bis` wird auf `created_at` gesetzt (Gueltigkeit endet, wo sie begann). Anders als ein normales `gilt_bis` hat der Marker
keine Abhaengigkeit vom Stichtag: Ein Stichtag vor `created_at` wuerde den Satz sonst wieder sichtbar machen. Deshalb filtern alle
Lesepfade (`PdvmDatabase`, `PdvmDatabaseService`, `ConnectionManager`, View-Service) mit `is_deleted_record`.

Beim Schreiben wird `ROOT.SELF_GILT_BIS` im PDVM-Format (5 Nachkommastellen, rund 0,9 s) gesetzt; die Spalte folgt daraus. Der Vergleich
hat deshalb eine kleine Toleranz. Ein regulaerer Satz hat `gilt_bis` 9999-12-31 (oder NULL) und ist nie betroffen.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, List

MANDANT_TABLE = "asy_mandanten"
TOLERANCE = timedelta(seconds=5)


def _as_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return datetime.fromisoformat(value.strip())
        except ValueError:
            return None
    return None


def is_deleted_mandant_row(row: Dict[str, Any] | None) -> bool:
    """True, wenn der Mandantensatz als geloescht markiert ist (`gilt_bis` <= `created_at` + Toleranz)."""
    if not isinstance(row, dict):
        return False
    gilt_bis = _as_datetime(row.get("gilt_bis"))
    created_at = _as_datetime(row.get("created_at"))
    if gilt_bis is None or created_at is None:
        return False
    return gilt_bis <= created_at + TOLERANCE


def is_deleted_record(table_name: Any, row: Dict[str, Any] | None) -> bool:
    """Wie `is_deleted_mandant_row`, aber nur fuer die Mandantentabelle (alle anderen Tabellen: immer False)."""
    return str(table_name or "").strip().lower() == MANDANT_TABLE and is_deleted_mandant_row(row)


def without_deleted(table_name: Any, rows: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [r for r in rows if not is_deleted_record(table_name, r)]

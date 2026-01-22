"""Systemdaten Service

ARCHITECTURE_RULES: kein SQL im Router; DB-Zugriff via PdvmDatabase.

Zweck:
- Stellt systemweite, sprachabhängige Konfigurationen bereit.
- Für den Menüeditor: Liste der erlaubten Menu-Commands + Parameter-Schema.

Erwartete Struktur in sys_systemdaten.daten (Beispiel):
{
  "ROOT": {"DEFAULT_LANGUAGE": "DE-DE"},
  "DE-DE": {
    "menü_command": {
      "commands": [
        {"handler": "go_view", "label": "View öffnen", "params": [{"name": "view_guid", "type": "guid", "required": true, "lookup_table": "sys_viewdaten"}]},
        {"handler": "go_dialog", "label": "Dialog öffnen", "params": [{"name": "dialog_guid", "type": "guid", "required": true, "lookup_table": "sys_dialogdaten"}, {"name": "dialog_table", "type": "table", "required": false}]}
      ]
    }
  }
}

Hinweis: Feldnamen werden "diakritik-insensitiv" normalisiert ("menü_command" == "menu_command").
"""

from __future__ import annotations

import unicodedata
import uuid
from typing import Any, Dict, List, Optional, Tuple

from app.core.pdvm_datenbank import PdvmDatabase
from app.core.dropdown_service import get_user_language, DEFAULT_LANGUAGE_FALLBACK


def _norm_lang(value: Any) -> str:
    s = str(value or "").strip()
    return s.upper() if s else DEFAULT_LANGUAGE_FALLBACK


def _strip_diacritics(value: str) -> str:
    n = unicodedata.normalize("NFKD", value)
    return "".join(ch for ch in n if not unicodedata.combining(ch))


def _norm_field(value: Any) -> str:
    s = str(value or "").strip().lower()
    if not s:
        return ""
    s = _strip_diacritics(s)
    return s


async def _load_first_systemdaten_row(gcs) -> Optional[Dict[str, Any]]:
    """Best-effort: lädt den ersten sys_systemdaten Datensatz.

    Für produktive Nutzung sollte die GUID in sys_dialogdaten konfiguriert werden.
    """
    db = PdvmDatabase("sys_systemdaten", system_pool=gcs._system_pool, mandant_pool=gcs._mandant_pool)
    rows = await db.get_all(order_by="created_at ASC", limit=1)
    return rows[0] if rows else None


async def load_menu_command_catalog(
    gcs,
    *,
    language: Optional[str] = None,
    dataset_uid: Optional[str] = None,
    field: str = "menü_command",
) -> Dict[str, Any]:
    """Liefert das Command-Katalog-Objekt (commands[]) aus sys_systemdaten.

    Returns:
        {"commands": [...], "language": "DE-DE", "default_language": "DE-DE"}
    """
    lang = _norm_lang(language or get_user_language(gcs))
    field_key = _norm_field(field)

    row: Optional[Dict[str, Any]] = None
    if dataset_uid:
        try:
            uid_obj = uuid.UUID(str(dataset_uid))
            db = PdvmDatabase("sys_systemdaten", system_pool=gcs._system_pool, mandant_pool=gcs._mandant_pool)
            row = await db.get_by_uid(uid_obj)
        except Exception:
            row = None

    if row is None:
        row = await _load_first_systemdaten_row(gcs)

    daten = (row or {}).get("daten")
    if not isinstance(daten, dict):
        return {"commands": [], "language": lang, "default_language": DEFAULT_LANGUAGE_FALLBACK}

    root = daten.get("ROOT") if isinstance(daten.get("ROOT"), dict) else {}
    default_lang = _norm_lang((root or {}).get("DEFAULT_LANGUAGE") or DEFAULT_LANGUAGE_FALLBACK)

    lang_obj = daten.get(lang)
    if not isinstance(lang_obj, dict):
        lang_obj = daten.get(default_lang)

    if not isinstance(lang_obj, dict):
        return {"commands": [], "language": lang, "default_language": default_lang}

    # Feld im Sprachobjekt finden (diakritik-insensitiv)
    field_obj = None
    for k, v in lang_obj.items():
        if _norm_field(k) == field_key:
            field_obj = v
            break

    if not isinstance(field_obj, dict):
        return {"commands": [], "language": lang, "default_language": default_lang}

    commands = field_obj.get("commands")
    if not isinstance(commands, list):
        commands = []

    # leichte Normalisierung
    norm: List[Dict[str, Any]] = []
    for c in commands:
        if not isinstance(c, dict):
            continue
        handler = str(c.get("handler") or "").strip()
        if not handler:
            continue
        label = str(c.get("label") or handler).strip()
        params = c.get("params")
        if not isinstance(params, list):
            params = []
        norm.append({"handler": handler, "label": label, "params": params})

    return {"commands": norm, "language": lang, "default_language": default_lang}

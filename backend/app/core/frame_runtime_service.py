"""
Frame-Runtime: liefert ein Frame samt aufgeloesten Controls als ein Runtime-Modell.

Spezifikation: docs/specs/PDVM_FRAME_INPUT_RENDERING_SPEC_V1.md, Regel 2.15 in ARCHITECTURE_RULES.md.

- Frame (`sys_framedaten`) und alle Controls (`sys_control_dict`) werden mit zwei Abfragen geladen (Bulk).
- Das Ergebnis wird kurz gecacht (Schluessel: Pool + Frame-UID) und bei Schreibzugriffen auf
  `sys_framedaten`/`sys_control_dict` ueber `PdvmDatabase` verworfen.
- Der Dienst arbeitet mit der System-DB-Verbindung der GCS-Session; ohne Session (vor der Mandantenwahl)
  mit dem gemeinsamen Pool der System-DB (`PoolRegistry`).
"""
from __future__ import annotations

import copy
import time
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from app.core.connection_manager import ConnectionManager
from app.core.dialog_frame_helpers import _resolve_frame_fields
from app.core.i18n_policy import DEFAULT_LANGUAGE_FALLBACK as DEFAULT_LANGUAGE, normalize_language
from app.core.pdvm_datenbank import PdvmDatabase
from app.core.pool_registry import PoolRegistry

CACHE_TTL_SECONDS = 30.0

_cache: Dict[Tuple[int, str], Tuple[float, Any, Dict[str, Any]]] = {}


class FrameNotFoundError(KeyError):
    pass


@dataclass(frozen=True)
class PoolScope:
    """Pools in der Form, die `_resolve_frame_fields` erwartet (wie eine GCS-Session)."""

    _system_pool: Any
    _mandant_pool: Any = None


def invalidate_frame_runtime_cache() -> None:
    _cache.clear()


async def resolve_pool_scope(gcs: Optional[Any]) -> PoolScope:
    if gcs is not None:
        return PoolScope(gcs._system_pool, getattr(gcs, "_mandant_pool", None))
    config = await ConnectionManager.get_system_config("pdvm_system")
    url = config.to_url()
    pool = await PoolRegistry.get_pool(url, dsn=url, min_size=1, max_size=10)
    return PoolScope(pool, None)


def ensure_frame_access(current_user: Dict[str, Any], frame_root: Dict[str, Any]) -> None:
    """Zentrale Stelle fuer die Zugriffspruefung auf Frames.

    Heute darf jeder angemeldete Benutzer Frames lesen (die Daten selbst sind ueber ihre Endpunkte geschuetzt).
    Die Security ausserhalb der Menuepunkte wird hier ergaenzt, nicht in den Aufrufern.
    """
    return None


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _to_int(value: Any, default: int) -> int:
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return default


def _build_tabs(root: Dict[str, Any], fields: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    heads: Dict[int, str] = {}
    for entry in _as_dict(root.get("TAB_ELEMENTS")).values():
        item = _as_dict(entry)
        index = _to_int(item.get("TAB"), 0)
        if index > 0:
            heads[index] = str(item.get("HEAD") or item.get("GRUPPE") or "").strip()
    used = sorted({f["tab"] for f in fields})
    return [{"index": i, "head": heads.get(i) or f"Tab {i}"} for i in used]


def _build_field(key: str, item: Dict[str, Any]) -> Dict[str, Any]:
    feld = str(item.get("feld") or "").strip()
    warning = None
    if not item.get("type") or not feld:
        warning = "Control-Aufloesung fehlt: Control nicht in sys_control_dict gefunden."
    return {
        "key": key,
        "control_uid": str(item.get("dict_ref") or key) if _is_uuid(str(item.get("dict_ref") or key)) else None,
        "tab": _to_int(item.get("tab"), 1),
        "display_order": _to_int(item.get("display_order"), 0),
        "type": str(item.get("type") or "string").strip().lower(),
        "label": str(item.get("label") or feld or key).strip(),
        "tooltip": str(item.get("tooltip") or "").strip() or None,
        "gruppe": str(item.get("gruppe") or "ROOT").strip(),
        "feld": feld,
        "source_path": str(item.get("source_path") or "root").strip() or "root",
        "save_path": str(item.get("save_path") or "").strip() or None,
        "table": str(item.get("table") or "").strip() or None,
        "read_only": bool(item.get("read_only")),
        "immutable": bool(item.get("immutable")),
        "immutable_after": str(item.get("immutable_after") or "").strip() or None,
        "default": item.get("default"),
        "configs": copy.deepcopy(_as_dict(item.get("configs"))),
        "options": [],
        "resolution_warning": warning,
    }


def _is_uuid(value: str) -> bool:
    try:
        uuid.UUID(str(value))
        return True
    except (ValueError, AttributeError, TypeError):
        return False


def build_runtime_payload(frame_uid: str, name: str, daten: Dict[str, Any]) -> Dict[str, Any]:
    """Baut aus einem bereits aufgeloesten Frame (Controls gemerged) das Runtime-Modell."""
    root = _as_dict(daten.get("ROOT"))
    fields = [
        _build_field(str(key), _as_dict(item))
        for key, item in _as_dict(daten.get("FIELDS")).items()
    ]
    fields.sort(key=lambda f: (f["tab"], f["display_order"], f["label"].lower()))
    return {
        "uid": frame_uid,
        "name": name,
        "root": {
            "EDIT_TYPE": root.get("EDIT_TYPE"),
            "FRAME_TYPE": root.get("FRAME_TYPE"),
            "ROOT_TABLE": root.get("ROOT_TABLE"),
            "TABLE": root.get("TABLE"),
        },
        "tabs": _build_tabs(root, fields),
        "fields": fields,
    }


async def _dropdown_options(
    scope: PoolScope, key: str, language: str, own_language: bool = False
) -> List[Dict[str, str]]:
    """Optionen eines Dropdowns aus sys_dropdowndaten (Regel 2.16); ohne Session lesbar, nur System-DB.

    `own_language`: Sprachauswahl; der Optionsschluessel ist der Sprachcode und das Label steht in dieser Sprache
    (`OPTIONS.<code>.<code>`, z. B. Deutsch/English/Italiano). Fehlt es, gilt die Oberflaechensprache.
    """
    from app.core.dropdown_service import _parse_dataset

    try:
        row = await PdvmDatabase("sys_dropdowndaten", system_pool=scope._system_pool).get_by_uid(uuid.UUID(str(key)))
    except (ValueError, TypeError):
        return []
    if not row:
        return []
    daten = _as_dict(row.get("daten"))
    _, _, options_by_field = _parse_dataset(daten, language=language)
    first = next((opts for opts in options_by_field.values() if opts), [])
    own_labels = _as_dict(daten.get("OPTIONS")) if own_language else {}

    def label(option: Dict[str, str]) -> str:
        own = _as_dict(own_labels.get(option["key"])).get(normalize_language(option["key"]))
        return str(own).strip() if own else option["value"]

    return [{"value": o["key"], "label": label(o)} for o in first]


async def _attach_dropdown_options(scope: PoolScope, payload: Dict[str, Any], language: str) -> None:
    for field in payload["fields"]:
        if field["type"] != "dropdown":
            continue
        config = _as_dict(_as_dict(field.get("configs")).get("dropdown"))
        table = str(config.get("table") or "sys_dropdowndaten").strip().lower()
        key = str(config.get("key") or "").strip()
        if table != "sys_dropdowndaten" or not key:
            field["resolution_warning"] = field["resolution_warning"] or "Dropdown-Quelle fehlt (CONFIGS.dropdown.key in sys_dropdowndaten)"
            continue
        own = str(config.get("label_language") or "").strip().lower() == "own"
        field["options"] = await _dropdown_options(scope, key, language, own)


def _check_action_fields(payload: Dict[str, Any]) -> None:
    """Controls `action`/`info` verweisen nur auf registrierte Aktionen (frame_action_service); sonst Fehler am Feld."""
    from app.core.frame_action_service import is_registered

    for field in payload["fields"]:
        configs = _as_dict(field.get("configs"))
        if field["type"] == "action":
            action_id = str(_as_dict(configs.get("action")).get("id") or "").strip()
            if not action_id:
                field["resolution_warning"] = field["resolution_warning"] or "Aktion fehlt (CONFIGS.action.id)"
            elif not is_registered(action_id):
                field["resolution_warning"] = field["resolution_warning"] or f"Unbekannte Aktion '{action_id}'"
        elif field["type"] == "info":
            state_action = str(_as_dict(_as_dict(configs.get("info")).get("state")).get("action") or "").strip()
            if state_action and not is_registered(state_action):
                field["resolution_warning"] = field["resolution_warning"] or f"Unbekannte Aktion '{state_action}'"


PUBLIC_FORM_FRAME_TYPE = "public_form"


def _check_password_input_fields(payload: Dict[str, Any]) -> None:
    """`password_input` (Passwort ohne Speicherung) ist nur in fluechtigen Frames erlaubt (FRAME_TYPE `public_form`)."""
    if str(payload["root"].get("FRAME_TYPE") or "").strip().lower() == PUBLIC_FORM_FRAME_TYPE:
        return
    for field in payload["fields"]:
        if field["type"] == "password_input":
            field["resolution_warning"] = field["resolution_warning"] or (
                "Control-Typ 'password_input' ist nur in Frames mit FRAME_TYPE 'public_form' erlaubt"
            )


async def load_frame_runtime(scope: PoolScope, frame_uid: uuid.UUID, language: Optional[str] = None) -> Dict[str, Any]:
    lang = normalize_language(language) or DEFAULT_LANGUAGE
    cache_key = (id(scope._system_pool), f"{frame_uid}|{lang}")
    entry = _cache.get(cache_key)
    if entry is not None:
        expires, cached_pool, payload = entry
        if cached_pool is scope._system_pool and time.monotonic() < expires:
            return copy.deepcopy(payload)
        _cache.pop(cache_key, None)

    db = PdvmDatabase("sys_framedaten", system_pool=scope._system_pool, mandant_pool=scope._mandant_pool)
    row = await db.get_by_uid(frame_uid)
    if not row:
        raise FrameNotFoundError(f"Frame nicht gefunden: {frame_uid}")

    daten = await _resolve_frame_fields(scope, _as_dict(row.get("daten")))
    payload = build_runtime_payload(str(row.get("uid")), str(row.get("name") or ""), daten)
    await _attach_dropdown_options(scope, payload, lang)
    _check_action_fields(payload)
    _check_password_input_fields(payload)
    _cache[cache_key] = (time.monotonic() + CACHE_TTL_SECONDS, scope._system_pool, copy.deepcopy(payload))
    return payload

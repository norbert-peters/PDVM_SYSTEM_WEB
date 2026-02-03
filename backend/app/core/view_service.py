"""View Service

Architekturregel: keine SQL in Routern.
Dieses Modul kapselt Zugriff auf sys_viewdaten und View-Base-Daten.

Phase 0 (MVP):
- ViewDefinition laden (sys_viewdaten)
- Base-Rohdaten laden (aus ROOT.TABLE)
"""

from __future__ import annotations

import uuid
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.core.pdvm_central_systemsteuerung import PdvmCentralSystemsteuerung
from app.core.pdvm_central_datenbank import PdvmCentralDatabase
from app.core.pdvm_datenbank import PdvmDatabase
from app.core.config import settings
from app.core.pdvm_datetime import now_pdvm, datetime_to_pdvm, get_form_timestamp


def _normalize_uuid_hex(value: Any) -> str:
    """Normalisiert UUID-Strings auf 32 hex chars (ohne Bindestriche)."""
    try:
        s = str(value).strip().lower()
    except Exception:
        return ""
    return "".join(ch for ch in s if ch in "0123456789abcdef")


_EXCLUDED_UID_HEX = {"0" * 32, "5" * 32, "6" * 32}


def _is_excluded_uid(value: Any) -> bool:
    return _normalize_uuid_hex(value) in _EXCLUDED_UID_HEX


def _is_historical_map(value: Any) -> bool:
    """True wenn ein Dict wie {"2025043.0": <wert>, ...} aussieht."""
    if not isinstance(value, dict) or not value:
        return False

    any_numeric = False
    for k in value.keys():
        try:
            float(k)
            any_numeric = True
        except Exception:
            return False
    return any_numeric


def _select_historical_value(value_map: Dict[Any, Any], stichtag: float) -> Any:
    """Wählt den Wert mit größtem Zeitstempel <= stichtag (sonst None)."""
    st = float(stichtag)
    best_ts: Optional[float] = None
    best_val: Any = None
    for k, v in value_map.items():
        try:
            ts = float(k)
        except Exception:
            continue
        if ts <= st and (best_ts is None or ts > best_ts):
            best_ts = ts
            best_val = v
    return best_val if best_ts is not None else None


def _select_historical_value_with_ts(value_map: Dict[Any, Any], stichtag: float) -> tuple[Any, Optional[float]]:
    """Wie _select_historical_value, aber liefert zusätzlich das gewählte AB-Datum (Timestamp) zurück."""
    st = float(stichtag)
    best_ts: Optional[float] = None
    best_val: Any = None
    for k, v in value_map.items():
        try:
            ts = float(k)
        except Exception:
            continue
        if ts <= st and (best_ts is None or ts > best_ts):
            best_ts = ts
            best_val = v
    return best_val if best_ts is not None else None, best_ts


def _apply_stichtag_to_daten_copy(daten: Dict[str, Any], stichtag: float, *, form_country: str = "DEU") -> Dict[str, Any]:
    """Wendet Stichtag-Regeln auf PDVM-Historienfelder an (ohne das Eingabe-Dict zu mutieren)."""
    out = dict(daten)

    for gruppe, gruppe_data in daten.items():
        # SYSTEM ist technisch und wird separat injiziert; nicht in Historienlogik einbeziehen.
        if str(gruppe).upper() == "SYSTEM":
            continue
        if not isinstance(gruppe_data, dict):
            continue

        changed = False
        new_group = dict(gruppe_data)
        for feld, feld_data in gruppe_data.items():
            if _is_historical_map(feld_data):
                val, ab_ts = _select_historical_value_with_ts(feld_data, stichtag)
                new_group[feld] = val
                # AB-Datum zusätzlich ausgeben (für Tooltips/UI)
                new_group[f"{feld}__abdatum"] = ab_ts
                try:
                    new_group[f"{feld}__abdatum_formatiert"] = get_form_timestamp(float(ab_ts), form_country=form_country) if ab_ts is not None else None
                except Exception:
                    new_group[f"{feld}__abdatum_formatiert"] = None
                changed = True

        if changed:
            out[gruppe] = new_group

    return out


def _apply_stichtag_to_control_fields_copy(
    daten: Dict[str, Any],
    stichtag: float,
    control_fields: List[tuple[str, str]],
    *,
    form_country: str = "DEU",
) -> Dict[str, Any]:
    """Wendet Stichtag-Regeln nur auf View-relevante Felder an (gruppe, feld)."""
    if not control_fields:
        return daten

    out = dict(daten)
    st = float(stichtag)

    for gruppe, feld in control_fields:
        if str(gruppe).upper() == "SYSTEM":
            continue

        gruppe_data = daten.get(gruppe)
        if not isinstance(gruppe_data, dict):
            continue

        feld_data = gruppe_data.get(feld)
        if not _is_historical_map(feld_data):
            continue

        # Copy-on-write der Gruppe
        existing_out_group = out.get(gruppe)
        if existing_out_group is gruppe_data:
            new_group = dict(gruppe_data)
            out[gruppe] = new_group
        elif isinstance(existing_out_group, dict):
            new_group = existing_out_group
        else:
            new_group = dict(gruppe_data)
            out[gruppe] = new_group

        val, ab_ts = _select_historical_value_with_ts(feld_data, st)
        new_group[feld] = val
        new_group[f"{feld}__abdatum"] = ab_ts
        try:
            new_group[f"{feld}__abdatum_formatiert"] = get_form_timestamp(float(ab_ts), form_country=form_country) if ab_ts is not None else None
        except Exception:
            new_group[f"{feld}__abdatum_formatiert"] = None

    return out


async def load_view_definition(gcs: PdvmCentralSystemsteuerung, view_guid: uuid.UUID) -> Dict[str, Any]:
    # ARCHITECTURE_RULES: Factory Pattern via PdvmCentralDatabase.load
    view = await PdvmCentralDatabase.load(
        table_name="sys_viewdaten",
        guid=str(view_guid),
        stichtag=gcs.stichtag,
        system_pool=gcs._system_pool,
        mandant_pool=gcs._mandant_pool,
    )

    daten = view.data or {}
    root = daten.get("ROOT") or {}

    # Name steht als Spalte in der Tabelle. Für Phase 0/1 genügt ein Fallback.
    # (Wir können später optional den Namen über PdvmDatabase.get_by_uid lesen, falls benötigt.)
    return {
        "uid": str(view_guid),
        "name": "",
        "daten": daten,
        "root": root,
    }


async def load_view_base_rows(
    gcs: PdvmCentralSystemsteuerung,
    table_name: str,
    limit: int = 200,
    include_historisch: bool = True,
    control_fields: Optional[List[tuple[str, str]]] = None,
) -> List[Dict[str, Any]]:
    def _user_has_role(role_name: str) -> bool:
        try:
            roles, _ = gcs.benutzer.get_value("PERMISSIONS", "ROLES", ab_zeit=float(gcs.stichtag))
        except Exception:
            roles = None

        if roles is None:
            return False

        role_norm = str(role_name).strip().lower()
        if isinstance(roles, list):
            return any(str(r).strip().lower() == role_norm for r in roles)

        # Fallback: String-Listen erlauben (z.B. "admin,user")
        try:
            roles_str = str(roles)
        except Exception:
            return False

        candidates = [r.strip().lower() for r in roles_str.replace(";", ",").split(",") if r.strip()]
        return role_norm in candidates

    if str(table_name).strip().lower() == "sys_benutzer":
        # Zugriff auf sys_benutzer nur für Admin-Role
        if not _user_has_role("admin"):
            return []

    db = PdvmDatabase(
        table_name,
        system_pool=gcs._system_pool,
        mandant_pool=gcs._mandant_pool,
    )

    where = ""
    if not include_historisch:
        where = "historisch = 0"

    def _gilt_bis_is_expired(gilt_bis_value: Any, now_pdvm: float) -> bool:
        """True wenn gilt_bis < aktueller Tag (PDVM-Konzept: Taggenau)."""
        if gilt_bis_value is None:
            return False

        # Parse -> datetime or pdvm-float
        pdvm_val: Optional[float] = None
        if isinstance(gilt_bis_value, (int, float)):
            try:
                pdvm_val = float(gilt_bis_value)
            except Exception:
                pdvm_val = None
        elif isinstance(gilt_bis_value, datetime):
            try:
                pdvm_val = datetime_to_pdvm(gilt_bis_value)
            except Exception:
                pdvm_val = None
        else:
            s = str(gilt_bis_value).strip()
            if not s:
                return False
            # 1) PDVM-Float als String
            try:
                pdvm_val = float(s)
            except Exception:
                pdvm_val = None
            # 2) ISO / Timestamp
            if pdvm_val is None:
                try:
                    dt = datetime.fromisoformat(s)
                    pdvm_val = datetime_to_pdvm(dt)
                except Exception:
                    pdvm_val = None

        if pdvm_val is None:
            return False

        # Sentinel-Max -> nie abgelaufen
        try:
            if pdvm_val >= 9999365.0:
                return False
        except Exception:
            pass

        # Taggenauer Vergleich
        try:
            return int(pdvm_val) < int(now_pdvm)
        except Exception:
            return False

    # ---------------------------------------------------------------------
    # TABLE CACHE (Delta Refresh über modified_at)
    # ---------------------------------------------------------------------
    table_key = (str(table_name), bool(include_historisch))
    now_ts = time.time()

    try:
        table_cache = getattr(gcs, "_pdvm_table_cache", {}).get(table_key)
    except Exception:
        table_cache = None

    configured_max_rows = int(getattr(settings, "VIEW_TABLE_CACHE_MAX_ROWS", 20000) or 20000)
    cached_max_rows = 0
    try:
        if isinstance(table_cache, dict):
            cached_max_rows = int(table_cache.get("max_rows") or 0)
    except Exception:
        cached_max_rows = 0

    requested_max_rows = max(int(limit), cached_max_rows)
    requested_max_rows = min(requested_max_rows, configured_max_rows)
    chunk_size = int(getattr(settings, "VIEW_TABLE_CACHE_CHUNK_SIZE", 2000))
    refresh_min_interval = float(getattr(settings, "VIEW_TABLE_CACHE_REFRESH_MIN_INTERVAL_SECONDS", 2.0))

    # Initial load / grow cache
    need_full_reload = False
    if not isinstance(table_cache, dict):
        need_full_reload = True
    else:
        cached_max_rows = int(table_cache.get("max_rows") or 0)
        if requested_max_rows > cached_max_rows:
            # Wenn der Cache vergrößert werden soll, laden wir einmal sauber neu (einfach & konsistent).
            need_full_reload = True

    if need_full_reload:
        by_uid: Dict[str, Any] = {}
        max_modified_at: Optional[datetime] = None
        truncated = False

        offset = 0
        loaded = 0
        while True:
            page = await db.get_all(where=where, order_by="modified_at DESC", limit=chunk_size, offset=offset)
            if not page:
                break
            for r in page:
                uid_val = str(r.get("uid"))
                if not uid_val:
                    continue
                by_uid[uid_val] = r
                ma = r.get("modified_at")
                if isinstance(ma, datetime):
                    if max_modified_at is None or ma > max_modified_at:
                        max_modified_at = ma
            loaded += len(page)
            offset += len(page)
            if loaded >= requested_max_rows:
                truncated = True
                break

        table_cache = {
            "by_uid": by_uid,
            "max_modified_at": max_modified_at,
            "version": int((table_cache or {}).get("version") or 0) + 1,
            "max_rows": int(requested_max_rows),
            "last_refresh_ts": float(now_ts),
            "truncated": bool(truncated),
        }
        try:
            gcs._pdvm_table_cache[table_key] = table_cache
        except Exception:
            pass
    else:
        # Delta refresh (throttled)
        last_refresh = float(table_cache.get("last_refresh_ts") or 0.0)
        if (now_ts - last_refresh) >= refresh_min_interval:
            max_modified_at = table_cache.get("max_modified_at")
            if isinstance(max_modified_at, datetime):
                changed = await db.get_modified_since(
                    modified_after=max_modified_at,
                    where=where,
                    params=(),
                    order_by="modified_at ASC",
                    limit=None,
                )
                if changed:
                    by_uid = table_cache.get("by_uid")
                    if not isinstance(by_uid, dict):
                        by_uid = {}
                    any_change = False
                    for r in changed:
                        uid_val = str(r.get("uid"))
                        if not uid_val:
                            continue
                        by_uid[uid_val] = r
                        any_change = True
                        ma = r.get("modified_at")
                        if isinstance(ma, datetime) and (max_modified_at is None or ma > max_modified_at):
                            max_modified_at = ma

                    table_cache["by_uid"] = by_uid
                    table_cache["max_modified_at"] = max_modified_at
                    table_cache["last_refresh_ts"] = float(now_ts)
                    if any_change:
                        table_cache["version"] = int(table_cache.get("version") or 0) + 1
                        try:
                            gcs._pdvm_table_cache[table_key] = table_cache
                        except Exception:
                            pass
            else:
                table_cache["last_refresh_ts"] = float(now_ts)

    by_uid = table_cache.get("by_uid") if isinstance(table_cache, dict) else None
    if not isinstance(by_uid, dict):
        by_uid = {}

    # Stabil sortieren (modified_at DESC) und dann auf limit kappen
    rows_raw = list(by_uid.values())
    rows_raw.sort(key=lambda r: (r.get("modified_at") or datetime.min), reverse=True)
    rows = rows_raw[: int(limit)]

    # Normalisiere minimal für API
    # Spezialfall: gruppe=SYSTEM -> Spaltenwerte kommen aus DB-Spalten (nicht aus JSONB)
    out: List[Dict[str, Any]] = []
    now_pdvm_val = float(now_pdvm())

    for r in rows:
        if _is_excluded_uid(r.get("uid")):
            continue

        # gilt_bis: wenn < aktueller Tag → Datensatz gilt als gelöscht
        if _gilt_bis_is_expired(r.get("gilt_bis"), now_pdvm_val):
            continue

        daten_raw = r.get("daten") or {}
        if not isinstance(daten_raw, dict):
            daten_raw = {}

        system_group: Dict[str, Any] = {}
        for k, v in r.items():
            if k == "daten":
                continue
            if k in ("created_at", "modified_at") and v is not None:
                try:
                    system_group[k] = v.isoformat()
                except Exception:
                    system_group[k] = v
            else:
                system_group[k] = v

            # Optional: auch als UPPERCASE anbieten (robuster gegen alte sys_viewdaten Konventionen)
            try:
                system_group[str(k).upper()] = system_group[k]
            except Exception:
                pass

        # Merge: falls SYSTEM im JSON existiert, bleibt es erhalten und wird ergänzt
        # Daten nicht mutieren: Output-Daten sind eine neue Struktur
        daten = dict(daten_raw)
        existing_system = daten_raw.get("SYSTEM")
        if isinstance(existing_system, dict):
            merged_system = dict(existing_system)
            merged_system.update(system_group)
            daten["SYSTEM"] = merged_system
        else:
            daten["SYSTEM"] = system_group

        # Stichtag anwenden (feldbasiert):
        # In PDVM können Felder auch in nicht-historischen Rows als Zeitstempel-Map vorliegen.
        # Daher projizieren wir immer, aber nur tatsächlich betroffene Felder werden geändert.
        form_country = "DEU"
        try:
            # Benutzersprache (z.B. DE-DE, EN-US) -> Form-Format
            lang = None
            for gruppe in ("ROOT", "SYSTEM", "BENUTZER", "USER"):
                v, _ = gcs.benutzer.get_value(gruppe, "LANGUAGE", ab_zeit=float(gcs.stichtag))
                if v is not None and str(v).strip():
                    lang = str(v).strip().upper()
                    break
            if lang:
                if lang.startswith("DE"):
                    form_country = "DEU"
                elif lang.startswith("EN-US"):
                    form_country = "USA"
                elif lang.startswith("EN"):
                    form_country = "ENG"
        except Exception:
            form_country = "DEU"

        if control_fields:
            daten = _apply_stichtag_to_control_fields_copy(daten, gcs.stichtag, control_fields, form_country=form_country)
        else:
            daten = _apply_stichtag_to_daten_copy(daten, gcs.stichtag, form_country=form_country)

        out.append(
            {
                "uid": str(r.get("uid")),
                "name": r.get("name") or "",
                "daten": daten,
                "historisch": int(r.get("historisch") or 0),
                "modified_at": r.get("modified_at").isoformat() if r.get("modified_at") else None,
            }
        )

    return out

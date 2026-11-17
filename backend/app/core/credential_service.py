"""
Gespeicherte Zugangsdaten (Tabelle asy_credentials in der AUTH-DB).

- Ein Datensatz je Zugangsdatensatz: `name` = Credential-Name (Verweis aus `CREDENTIAL`-Feldern), `daten.CREDENTIAL`
  mit `USER`, `PASSWORD` (Chiffretext `enc:v1:...`, siehe secret_box), `SSL`, `UPDATED_AT`.
- Klartext steht nur im Speicher des Backends (Cache in credential_store). Das Passwort wird nie zurueckgegeben,
  geloggt oder in Fehlermeldungen genannt; `credential_info` liefert nur Metadaten.
- Eintraege aus der .env (PDVM_DB_CREDENTIALS) haben Vorrang und sind hier nicht ueberschreibbar.
- Schreiben ueber `central_write_service` (Regel 1.1).
- Spezifikation: docs/specs/PDVM_FRAME_INPUT_RENDERING_SPEC_V1.md (Abschnitt 9), PDVM_DB_VERBINDUNGEN_UND_ZUGANGSDATEN_SPEC_V1.md.
"""
from __future__ import annotations

import json
import logging
import re
import time
import uuid
from typing import Any, Dict, Optional

from app.core import credential_store, secret_box
from app.core.central_write_service import create_record_central, update_record_central
from app.core.pdvm_datenbank import PdvmDatabase
from app.core.pdvm_datetime import now_pdvm_str

logger = logging.getLogger(__name__)

TABLE = "asy_credentials"
NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
CACHE_TTL_SECONDS = 30.0
_NS = uuid.UUID("0b8d3c9e-4f61-4a7b-9d52-8c1e6a2f7b34")

_last_refresh = 0.0


class CredentialError(ValueError):
    pass


def credential_uid(name: str) -> uuid.UUID:
    return uuid.uuid5(_NS, name)


def validate_name(name: str) -> str:
    name = str(name or "").strip()
    if not NAME_RE.match(name):
        raise CredentialError("Ungültiger Name (erlaubt: Buchstaben, Ziffern, _ . -, höchstens 64 Zeichen)")
    return name


def _as_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return {}
    return value if isinstance(value, dict) else {}


async def _load_rows() -> list:
    return await PdvmDatabase(TABLE).get_all(limit=1000)


async def refresh_credentials() -> int:
    """Laedt alle gespeicherten Zugangsdaten entschluesselt in den Cache; liefert die Anzahl."""
    global _last_refresh
    stored: Dict[str, credential_store.Credential] = {}
    try:
        rows = await _load_rows()
    except Exception as exc:  # Tabelle fehlt noch o. ae.: dann gibt es keine gespeicherten Eintraege
        logger.warning("asy_credentials nicht lesbar: %s", exc)
        rows = []
    for row in rows:
        name = str(row.get("name") or "").strip()
        entry = _as_dict(_as_dict(row.get("daten")).get("CREDENTIAL"))
        value = str(entry.get("PASSWORD") or "")
        if not name or not value:
            continue
        try:
            stored[name] = credential_store.Credential(
                user=str(entry["USER"]) if entry.get("USER") else None,
                password=secret_box.decrypt(value),
                ssl=bool(entry.get("SSL", False)),
            )
        except (secret_box.SecretKeyError, ValueError) as exc:
            logger.error("Zugangsdaten '%s' nicht entschlüsselbar: %s", name, exc)
    credential_store.replace_stored_credentials(stored)
    _last_refresh = time.monotonic()
    return len(stored)


async def ensure_fresh() -> None:
    """Aktualisiert den Cache hoechstens alle CACHE_TTL_SECONDS (mehrere Backend-Instanzen bleiben nahezu aktuell)."""
    if time.monotonic() - _last_refresh > CACHE_TTL_SECONDS:
        await refresh_credentials()


async def _find_row(name: str) -> Optional[Dict[str, Any]]:
    uid = credential_uid(name)
    for row in await _load_rows():
        if str(row.get("uid")) == str(uid):
            return row
    return None


async def credential_info(name: str) -> Dict[str, Any]:
    """Metadaten ohne Passwort: vorhanden?, Quelle, Benutzer, SSL, Stand."""
    name = validate_name(name)
    if credential_store.is_env_credential(name):
        cred = credential_store.get_credential(name)
        return {"name": name, "exists": True, "source": "env", "user": cred.user if cred else None,
                "ssl": bool(cred.ssl) if cred else False, "updated_at": None}
    row = await _find_row(name)
    entry = _as_dict(_as_dict(row.get("daten") if row else None).get("CREDENTIAL"))
    exists = bool(entry.get("PASSWORD"))
    return {"name": name, "exists": exists, "source": "store" if exists else None,
            "user": entry.get("USER") or None, "ssl": bool(entry.get("SSL", False)),
            "updated_at": entry.get("UPDATED_AT")}


async def set_credential(
    name: str,
    password: str,
    *,
    user: Optional[str] = None,
    ssl: bool = False,
    actor_user_uid: Optional[Any] = None,
    actor_ip: Optional[str] = None,
) -> Dict[str, Any]:
    name = validate_name(name)
    if not password:
        raise CredentialError("Passwort darf nicht leer sein")
    if credential_store.is_env_credential(name):
        raise CredentialError(f"'{name}' ist in der Konfiguration (.env) definiert und hier nicht änderbar")

    uid = credential_uid(name)
    daten = {
        "ROOT": {"TABLE": TABLE, "SELF_NAME": name},
        "CREDENTIAL": {
            "USER": (user or "").strip(),
            "PASSWORD": secret_box.encrypt(password),
            "SSL": bool(ssl),
            "UPDATED_AT": now_pdvm_str(),
        },
    }
    if await _find_row(name):
        await update_record_central(
            table_name=TABLE, uid=uid, daten=daten, name=name, actor_user_uid=actor_user_uid, actor_ip=actor_ip
        )
    else:
        await create_record_central(
            table_name=TABLE, uid=uid, daten=daten, name=name, actor_user_uid=actor_user_uid, actor_ip=actor_ip
        )
    await refresh_credentials()
    logger.info("Zugangsdaten '%s' gesetzt", name)  # nie das Passwort loggen
    return await credential_info(name)

"""
Credential-Store fuer Datenbank-Zugangsdaten.

Zugangsdaten stehen nie in asy_mandanten, sondern im Backend. Die Quelle ist hinter `CredentialProvider`
gekapselt; Standard ist die Umgebungsvariable PDVM_DB_CREDENTIALS (JSON), spaeter austauschbar gegen einen
Secret-Store (siehe docs/specs/PDVM_DB_VERBINDUNGEN_UND_ZUGANGSDATEN_SPEC_V1.md).

Format: {"default": {"user": "...", "password": "..."}, "srv-berlin": {"user": "...", "password": "...", "ssl": true}}
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Dict, Optional, Protocol

from .config import settings

logger = logging.getLogger(__name__)

DEFAULT_CREDENTIAL = "default"


@dataclass(frozen=True)
class Credential:
    user: Optional[str]
    password: str
    ssl: bool = False

    def __repr__(self) -> str:  # Passwort nie in Logs oder Tracebacks
        return f"Credential(user={self.user!r}, password=***, ssl={self.ssl})"


class CredentialProvider(Protocol):
    def get(self, name: str) -> Optional[Credential]: ...


class EnvCredentialProvider:
    """Liest PDVM_DB_CREDENTIALS (JSON-Objekt) aus der Konfiguration."""

    def __init__(self) -> None:
        self._raw: Optional[str] = None
        self._parsed: Dict[str, Credential] = {}

    def _load(self) -> Dict[str, Credential]:
        raw = (settings.PDVM_DB_CREDENTIALS or "").strip()
        if raw == self._raw:
            return self._parsed
        parsed: Dict[str, Credential] = {}
        if raw:
            try:
                data = json.loads(raw)
            except ValueError:
                raise ValueError("PDVM_DB_CREDENTIALS ist kein gueltiges JSON") from None
            if not isinstance(data, dict):
                raise ValueError("PDVM_DB_CREDENTIALS muss ein JSON-Objekt sein")
            for name, entry in data.items():
                if not isinstance(entry, dict) or not entry.get("password"):
                    raise ValueError(f"PDVM_DB_CREDENTIALS: Eintrag '{name}' braucht mindestens 'password'")
                parsed[str(name)] = Credential(
                    user=(str(entry["user"]) if entry.get("user") else None),
                    password=str(entry["password"]),
                    ssl=bool(entry.get("ssl", False)),
                )
        self._raw, self._parsed = raw, parsed
        return parsed

    def get(self, name: str) -> Optional[Credential]:
        return self._load().get(name)


class ChainedCredentialProvider:
    """Reihenfolge: .env (schreibgeschuetzt, hat Vorrang) vor den in asy_credentials gespeicherten Eintraegen.

    Die gespeicherten Eintraege liegen entschluesselt im Speicher des Backends (Cache); befuellt wird er von
    `credential_service` (Start, nach dem Setzen, TTL-Aktualisierung vor Verbindungsaufbau und Versand).
    """

    def __init__(self) -> None:
        self._env = EnvCredentialProvider()
        self._stored: Dict[str, Credential] = {}

    def replace_stored(self, stored: Dict[str, Credential]) -> None:
        self._stored = dict(stored)

    def is_env(self, name: str) -> bool:
        return self._env.get(name) is not None

    def get(self, name: str) -> Optional[Credential]:
        return self._env.get(name) or self._stored.get(name)


_chain = ChainedCredentialProvider()
_provider: CredentialProvider = _chain


def set_credential_provider(provider: CredentialProvider) -> None:
    """Tauscht die Quelle der Zugangsdaten (z. B. gegen einen Secret-Store)."""
    global _provider
    _provider = provider


def get_credential(name: str) -> Optional[Credential]:
    return _provider.get(name)


def replace_stored_credentials(stored: Dict[str, Credential]) -> None:
    _chain.replace_stored(stored)


def is_env_credential(name: str) -> bool:
    return _chain.is_env(name)

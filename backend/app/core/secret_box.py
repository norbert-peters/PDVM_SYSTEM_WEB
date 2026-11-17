"""
Verschluesselung fuer gespeicherte Zugangsdaten (Fernet, Schluessel PDVM_SECRET_KEY).

Gespeichert wird nur Chiffretext mit Versionspraefix (`enc:v1:`). Der Schluessel steht ausserhalb der Datenbank
(.env oder Secret-Store); ein Verlust des Schluessels macht die gespeicherten Passwoerter unlesbar.
"""
from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken

from .config import settings

PREFIX = "enc:v1:"


class SecretKeyError(RuntimeError):
    pass


def _fernet() -> Fernet:
    key = (settings.PDVM_SECRET_KEY or "").strip()
    if not key:
        raise SecretKeyError("PDVM_SECRET_KEY ist nicht konfiguriert (Fernet-Schlüssel in der .env)")
    try:
        return Fernet(key.encode("ascii"))
    except (ValueError, UnicodeEncodeError):
        raise SecretKeyError("PDVM_SECRET_KEY ist kein gültiger Fernet-Schlüssel") from None


def generate_key() -> str:
    return Fernet.generate_key().decode("ascii")


def encrypt(plain: str) -> str:
    return PREFIX + _fernet().encrypt(plain.encode("utf-8")).decode("ascii")


def decrypt(value: str) -> str:
    if not value.startswith(PREFIX):
        raise ValueError("Wert ist nicht verschlüsselt")
    try:
        return _fernet().decrypt(value[len(PREFIX):].encode("ascii")).decode("utf-8")
    except InvalidToken:
        raise SecretKeyError("Zugangsdaten konnten nicht entschlüsselt werden (falscher PDVM_SECRET_KEY?)") from None

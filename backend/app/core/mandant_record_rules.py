"""
Regeln fuer Mandantensaetze (asy_mandanten) bei der Neuanlage.

- Zugangsdaten stehen nie im Satz, nur als Verweis (`CREDENTIAL`), siehe
  docs/specs/PDVM_DB_VERBINDUNGEN_UND_ZUGANGSDATEN_SPEC_V1.md und Regel 2.15 (ARCHITECTURE_RULES.md).
- Die Neuanlage-Maske ist das Frame `MANDANT_FRAME_GUID` (sys_framedaten); Felder entstehen dort, nicht im Code.
"""
from __future__ import annotations

import copy
from typing import Any, Dict, List

MANDANT_TABLE = "asy_mandanten"
MANDANT_TEMPLATE_UID = "66666666-6666-6666-6666-666666666666"
MANDANT_FRAME_GUID = "b7f0c1a2-5d3e-4c8a-9a61-3e2d7c5f4a10"
MANDANT_DIALOG_GUID = "3c9e1f50-8a2b-4d67-b1e4-7f0a5c2d9e31"
MANDANT_VIEW_GUID = "c41a7b92-6e0d-4f35-8b18-2d9f3a6e5c07"

# Tabellen, deren Saetze nicht ueber den generischen Dialog („Neuer Satz“) angelegt werden duerfen.
DIALOG_CREATE_BLOCKED_TABLES: Dict[str, str] = {
    MANDANT_TABLE: "Mandanten werden im Dashboard über „Neuer Mandant“ angelegt (nur Superadmin).",
}


def dialog_create_blocked_reason(table: Any) -> str:
    """Hinweistext, wenn die Tabelle im generischen Dialog nicht neu angelegt werden darf, sonst leer."""
    return DIALOG_CREATE_BLOCKED_TABLES.get(str(table or "").strip().lower(), "")

# Nach der Anlage unveraenderliche Felder (Control-Eigenschaft IMMUTABLE, Set-Once, siehe immutable_fields_service).
IMMUTABLE_MANDANT_FIELDS = [
    ("MANDANT", "DATABASE"), ("MANDANT", "HOST"), ("MANDANT", "PORT"),
    ("MANDANT", "SYSTEM_DB"), ("MANDANT", "SYSTEM_HOST"), ("MANDANT", "SYSTEM_PORT"),
]

# (Gruppe, Feld) -> Hinweis; Werte in diesen Feldern sind in Mandantensaetzen unzulaessig.
FORBIDDEN_SECRET_FIELDS: Dict[tuple, str] = {
    ("MANDANT", "PASSWORD"): "Datenbank-Passwort gehört in den Credential-Store (Feld CREDENTIAL)",
    ("SEND_EMAIL", "SMTP_PASS"): "SMTP-Passwort gehört in den Credential-Store (SEND_EMAIL.CREDENTIAL)",
}

# Gruppen der 666-Vorlage (TEMPLATES), die nicht in den neuen Satz uebernommen werden.
_TEMPLATE_SKIP_GROUPS = {"TABLE_INFO"}
_ROOT_SKIP_KEYS = {
    "TABLE", "SELF_NAME", "SELF_GUID", "SELF_LINK_UID", "SELF_CREATED_AT", "SELF_MODIFIED_AT", "DB_CREATED_AT",
}


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def strip_secrets(daten: Dict[str, Any]) -> Dict[str, Any]:
    out = copy.deepcopy(daten)
    for group, field in FORBIDDEN_SECRET_FIELDS:
        _as_dict(out.get(group)).pop(field, None)
    return out


def flatten_mandant_template(template_daten: Dict[str, Any]) -> Dict[str, Any]:
    """Wandelt die 666-Vorlage (ROOT + TEMPLATES.<GRUPPE>) in die Datensatzform (ROOT + <GRUPPE>)."""
    root = {k: v for k, v in _as_dict(template_daten.get("ROOT")).items() if k not in _ROOT_SKIP_KEYS}
    out: Dict[str, Any] = {"ROOT": copy.deepcopy(root)}
    for group, content in _as_dict(template_daten.get("TEMPLATES")).items():
        if group in _TEMPLATE_SKIP_GROUPS or not isinstance(content, dict):
            continue
        out[group] = copy.deepcopy(content)
    return strip_secrets(out)


def validate_new_mandant(daten: Dict[str, Any]) -> List[Dict[str, str]]:
    """Fachliche Pruefung vor dem Speichern; liefert Fehler mit Zielpfad (group, field, message)."""
    errors: List[Dict[str, str]] = []
    name = str(_as_dict(daten.get("ROOT")).get("NAME") or "").strip()
    if not name or name == "-eingeben-":
        errors.append({"group": "ROOT", "field": "NAME", "message": "Bezeichnung ist erforderlich"})
    database = str(_as_dict(daten.get("MANDANT")).get("DATABASE") or "").strip()
    if not database or database == "-eingeben-":
        errors.append({"group": "MANDANT", "field": "DATABASE", "message": "Mandanten-Datenbank ist erforderlich"})
    for (group, field), hint in FORBIDDEN_SECRET_FIELDS.items():
        if str(_as_dict(daten.get(group)).get(field) or "").strip():
            errors.append({"group": group, "field": field, "message": f"Nicht zulässig: {hint}"})
    return errors

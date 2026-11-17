"""
Textvorlagen (sys_textvorlagen / msy_textvorlagen), z. B. fuer E-Mails.

Spezifikation: docs/specs/PDVM_TEXTVORLAGEN_SPEC_V1.md, Regel 1.24 (ARCHITECTURE_RULES.md).

- Satzstruktur: `ROOT` (TEMPLATE_KEY, CHANNEL, VARIABLES, REQUIRED_VARIABLES, ACTIVE, SOURCE_UID, SOURCE_HASH) und je
  Sprache eine Gruppe (`DE-DE`, `EN-US`, ...) mit SUBJECT, BODY, optional BODY_HTML sowie den Freigabefeldern
  STATUS, VERSION, APPROVED_BY, APPROVED_AT (Freigabemodell, Regel 1.19).
- Aufloesung nach stabilem Schluessel (TEMPLATE_KEY): aktive Vorlage des Mandanten (ROOT.ACTIVE) -> Systemvorlage.
  Ohne Mandanten-DB (z. B. vor der Anmeldung) gilt die Systemvorlage. Verwendet werden nur freigegebene Sprachen.
- Platzhalter `{{name}}` (nur a-z, 0-9, _): reines Ersetzen, keine Ausdruecke. Unbekannte Platzhalter sind ein Fehler.
  In HTML werden die Werte maskiert.
- Die Systemvorlagen werden beim Mandantenwechsel einmalig in den Mandanten kopiert (neue UID, SOURCE_UID/SOURCE_HASH).
- Schreibzugriffe laufen ueber den zentralen Gateway; `guard_write`/`after_write` erzwingen Rollen, Statuslogik,
  Unveraenderlichkeit und Gueltigkeit (siehe central_write_service).
"""
from __future__ import annotations

import copy
import hashlib
import html
import json
import re
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from app.core.central_write_service import create_record_central, update_record_central
from app.core.i18n_policy import DEFAULT_LANGUAGE_FALLBACK, normalize_language
from app.core.pdvm_datenbank import PdvmDatabase
from app.core.security import normalized_roles

SYSTEM_TABLE = "sys_textvorlagen"
MANDANT_TABLE = "msy_textvorlagen"
TABLES = {SYSTEM_TABLE, MANDANT_TABLE}
RESERVED_UIDS = {
    "00000000-0000-0000-0000-000000000000",
    "55555555-5555-5555-5555-555555555555",
    "66666666-6666-6666-6666-666666666666",
}

PLACEHOLDER_RE = re.compile(r"\{\{\s*([A-Za-z0-9_]+)\s*\}\}")
VARIABLE_NAME_RE = re.compile(r"^[a-z0-9_]+$")
CACHE_TTL_SECONDS = 30.0
COPY_INTERVAL_SECONDS = 900.0

TEXT_FIELDS = ("SUBJECT", "BODY", "BODY_HTML")
# Nach der Anlage unveraenderlich (Vertrag mit dem Code): Schluessel, Kanal und Variablen.
IMMUTABLE_ROOT_FIELDS = ("TEMPLATE_KEY", "CHANNEL", "VARIABLES", "REQUIRED_VARIABLES")
LIST_ROOT_FIELDS = ("VARIABLES", "REQUIRED_VARIABLES")

# Rollen: Systemvorlagen pflegt 'vorlagen'; Vorlagen des Mandanten pflegen Mandanten-Administratoren (und 'vorlagen').
EDIT_ROLES = {
    SYSTEM_TABLE: {"vorlagen", "superadmin"},
    MANDANT_TABLE: {"admin", "superadmin", "man_admin", "vorlagen"},
}
APPROVE_ROLES = EDIT_ROLES

_cache: Dict[Tuple[Any, ...], Tuple[float, Any]] = {}
_last_copy: Dict[int, float] = {}


class TextTemplateError(ValueError):
    pass


class NoApprovedLanguageError(TextTemplateError):
    pass


@dataclass(frozen=True)
class TemplateRow:
    uid: str
    name: str
    daten: Dict[str, Any]
    origin: str  # "mandant" | "system"


def invalidate_text_template_cache() -> None:
    _cache.clear()
    _last_copy.clear()


def _as_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return {}
    return value if isinstance(value, dict) else {}


def _truthy(value: Any) -> bool:
    return value is True or str(value).strip().lower() in {"true", "1", "ja", "yes"}


def as_name_list(value: Any) -> List[str]:
    """Liste aus Liste oder Text (Komma, Semikolon, Leerzeichen getrennt)."""
    if isinstance(value, (list, tuple)):
        items = [str(v).strip() for v in value]
    else:
        items = re.split(r"[,;\s]+", str(value or "").strip())
    return [i for i in items if i]


# --- Freigabemodell (Regel 1.19, Quelle: backend/config/i18n_language_release_model_v1.json) -------------------


@lru_cache(maxsize=1)
def release_model() -> Dict[str, Any]:
    path = Path(__file__).resolve().parents[2] / "config" / "i18n_language_release_model_v1.json"
    return json.loads(path.read_text(encoding="utf-8"))


def status_values() -> Set[str]:
    return set(release_model().get("status_model", {}))


def _version_pattern() -> "re.Pattern[str]":
    return re.compile(release_model().get("version_field_rules", {}).get("pattern", r"^v[0-9]+\.[0-9]+\.[0-9]+$"))


def bump_version(version: Optional[str]) -> str:
    match = re.match(r"^v(\d+)\.(\d+)\.(\d+)$", str(version or ""))
    if not match:
        return "v1.0.0"
    major, minor, patch = (int(x) for x in match.groups())
    return f"v{major}.{minor}.{patch + 1}"


def language_groups(daten: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Sprachgruppen (normalisierter Code -> Gruppe); alles ausser ROOT mit Textfeldern gilt als Sprachgruppe."""
    out: Dict[str, Dict[str, Any]] = {}
    for key, value in _as_dict(daten).items():
        if key == "ROOT" or not isinstance(value, dict):
            continue
        if any(f in value for f in TEXT_FIELDS):
            out[normalize_language(key)] = value
    return out


def language_chain(*candidates: Optional[str]) -> List[str]:
    """Benutzersprache -> Mandantensprache -> Standardsprache, ohne Doppelte."""
    chain: List[str] = []
    for candidate in [*candidates, DEFAULT_LANGUAGE_FALLBACK]:
        if candidate and str(candidate).strip():
            lang = normalize_language(candidate)
            if lang not in chain:
                chain.append(lang)
    return chain


def used_placeholders(text: str) -> set:
    return {m.group(1) for m in PLACEHOLDER_RE.finditer(text or "")}


def render_text(text: str, variables: Dict[str, Any], *, escape: bool = False) -> str:
    def repl(match: "re.Match[str]") -> str:
        name = match.group(1)
        if name not in variables:
            raise TextTemplateError(f"Platzhalter '{name}' hat keinen Wert")
        value = str(variables[name])
        return html.escape(value) if escape else value

    return PLACEHOLDER_RE.sub(repl, text or "")


def validate_template(daten: Dict[str, Any]) -> List[str]:
    """Fachliche Pruefung einer Vorlage (vor dem Speichern); liefert Fehlertexte."""
    errors: List[str] = []
    root = _as_dict(_as_dict(daten).get("ROOT"))
    key = str(root.get("TEMPLATE_KEY") or "").strip()
    if not key:
        errors.append("Schlüssel (ROOT.TEMPLATE_KEY) fehlt")
    declared = {str(v) for v in as_name_list(root.get("VARIABLES"))}
    required = {str(v) for v in as_name_list(root.get("REQUIRED_VARIABLES"))}
    for name in declared | required:
        if not VARIABLE_NAME_RE.match(name):
            errors.append(f"Ungültiger Variablenname '{name}' (erlaubt: a-z, 0-9, _)")
    if not required <= declared:
        errors.append(f"Pflichtvariablen nicht in den Variablen deklariert: {sorted(required - declared)}")
    groups = language_groups(daten)
    if not groups:
        errors.append("Keine Sprachgruppe mit Text vorhanden")
    statuses, version_re = status_values(), _version_pattern()
    for lang, group in groups.items():
        subject, body = str(group.get("SUBJECT") or "").strip(), str(group.get("BODY") or "").strip()
        if not subject or not body:
            errors.append(f"{lang}: Betreff und Text sind Pflicht")
            continue
        used = used_placeholders(subject) | used_placeholders(body) | used_placeholders(str(group.get("BODY_HTML") or ""))
        unknown = used - declared
        if unknown:
            errors.append(f"{lang}: nicht deklarierte Platzhalter {sorted(unknown)}")
        missing = required - used_placeholders(body)
        if missing:
            errors.append(f"{lang}: Pflichtvariablen fehlen im Text {sorted(missing)}")
        status = str(group.get("STATUS") or "").strip().lower()
        if status and status not in statuses:
            errors.append(f"{lang}: unbekannter Status '{status}'")
        if status == "approved":
            if not str(group.get("APPROVED_BY") or "").strip() or not str(group.get("APPROVED_AT") or "").strip():
                errors.append(f"{lang}: freigegeben ohne Freigabe-Benutzer/-Zeitpunkt")
            if not version_re.match(str(group.get("VERSION") or "")):
                errors.append(f"{lang}: ungültige Version '{group.get('VERSION')}'")
    return errors


def source_hash(daten: Dict[str, Any]) -> str:
    """Stand des Inhalts (Sprachtexte und Variablen), unabhaengig von UID, Name, Freigabe und Zeitstempeln."""
    root = _as_dict(_as_dict(daten).get("ROOT"))
    payload = {
        "key": root.get("TEMPLATE_KEY"),
        "channel": root.get("CHANNEL"),
        "variables": sorted(as_name_list(root.get("VARIABLES"))),
        "required": sorted(as_name_list(root.get("REQUIRED_VARIABLES"))),
        "languages": {
            lang: {f: g.get(f) for f in TEXT_FIELDS} for lang, g in sorted(language_groups(daten).items())
        },
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


# --- Laden und Rendern ---------------------------------------------------------------------------------------


async def _fetch_rows(pool: Any, sql: str, *args: Any) -> List[Dict[str, Any]]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(sql, *args)
    return [{"uid": str(r["uid"]), "name": r["name"] or "", "daten": _as_dict(r["daten"])} for r in rows]


async def load_candidates(key: str, *, system_pool: Any, mandant_pool: Any = None) -> List[TemplateRow]:
    """Kandidaten in Verwendungsreihenfolge: aktive Vorlage des Mandanten, dann Systemvorlage (kurz gecacht)."""
    key = str(key or "").strip()
    cache_key = (id(system_pool), id(mandant_pool), key)
    hit = _cache.get(cache_key)
    if hit and time.monotonic() < hit[0]:
        return copy.deepcopy(hit[1])

    out: List[TemplateRow] = []
    base = (
        "SELECT uid, name, daten FROM {table} WHERE daten->'ROOT'->>'TEMPLATE_KEY' = $1 "
        "AND COALESCE(historisch, 0) = 0 AND (gilt_bis IS NULL OR gilt_bis > now()) {extra} "
        "ORDER BY created_at, uid LIMIT 1"
    )
    if mandant_pool is not None:
        try:
            rows = await _fetch_rows(
                mandant_pool, base.format(table=MANDANT_TABLE, extra="AND daten->'ROOT'->'ACTIVE' = 'true'::jsonb"), key
            )
        except Exception:  # Tabelle fehlt noch (Mandanten-Wartung steht aus): Systemvorlage verwenden
            rows = []
        out += [TemplateRow(r["uid"], r["name"], r["daten"], "mandant") for r in rows]
    rows = await _fetch_rows(system_pool, base.format(table=SYSTEM_TABLE, extra=""), key)
    out += [TemplateRow(r["uid"], r["name"], r["daten"], "system") for r in rows]
    if not out:
        raise TextTemplateError(f"Textvorlage '{key}' nicht gefunden")
    _cache[cache_key] = (time.monotonic() + CACHE_TTL_SECONDS, copy.deepcopy(out))
    return out


def _is_approved(group: Dict[str, Any]) -> bool:
    return (
        str(group.get("STATUS") or "").strip().lower() == "approved"
        and bool(str(group.get("SUBJECT") or "").strip())
        and bool(str(group.get("BODY") or "").strip())
    )


def select_group(candidates: Iterable[TemplateRow], languages: Iterable[str]) -> Tuple[TemplateRow, str]:
    """Erste freigegebene Sprache der Kette; Kandidaten ohne freigegebene Sprache werden uebersprungen.

    Reihenfolge: Mandantenvorlage vor Systemvorlage, innerhalb einer Vorlage die Sprachkette. So bleibt der Versand
    moeglich, wenn der Mandant eine Vorlage aendert und noch nicht freigegeben hat (dann gilt die Systemvorlage).
    """
    languages = list(languages)
    for template in candidates:
        groups = language_groups(template.daten)
        for lang in languages:
            group = groups.get(normalize_language(lang))
            if group and _is_approved(group):
                return template, normalize_language(lang)
    raise NoApprovedLanguageError("Keine freigegebene Sprachfassung der Textvorlage für die gewünschte Sprache")


def render_message(template: TemplateRow, language: str, variables: Dict[str, Any]) -> Dict[str, Any]:
    """Rendert Betreff und Text (und HTML, falls vorhanden) in der angegebenen, freigegebenen Sprache."""
    group = language_groups(template.daten).get(normalize_language(language))
    if not group or not _is_approved(group):
        raise NoApprovedLanguageError(f"Sprache {language} ist nicht freigegeben")
    required = set(as_name_list(_as_dict(template.daten.get("ROOT")).get("REQUIRED_VARIABLES")))
    missing = required - set(variables)
    if missing:
        raise TextTemplateError(f"Pflichtvariablen ohne Wert: {sorted(missing)}")
    body_html = str(group.get("BODY_HTML") or "").strip()
    return {
        "language": normalize_language(language),
        "subject": render_text(str(group["SUBJECT"]), variables),
        "body": render_text(str(group["BODY"]), variables),
        "body_html": render_text(body_html, variables, escape=True) if body_html else None,
        "origin": template.origin,
        "template_uid": template.uid,
    }


# --- Schreib-Guard (aufgerufen von central_write_service) -----------------------------------------------------


def _roles_of(gcs: Any) -> Set[str]:
    benutzer = getattr(gcs, "benutzer", None)
    return normalized_roles(getattr(benutzer, "data", None))


def _actor_label(gcs: Any, actor_user_uid: Any) -> str:
    return str(actor_user_uid or getattr(gcs, "user_guid", "") or "unbekannt")


async def guard_write(
    *,
    table: str,
    uid: Any,
    new_daten: Dict[str, Any],
    gcs: Any,
    actor_user_uid: Any,
    system_pool: Any,
    mandant_pool: Any,
) -> Dict[str, Any]:
    """Prueft und normalisiert einen Schreibzugriff auf eine Textvorlage; liefert die zu speichernden Daten.

    Ohne `gcs` (interne Aufrufe: Seed-Werkzeuge, Kopie in den Mandanten) gilt der Vorgang als vertrauenswuerdig:
    es wird nur normalisiert und geprueft, Rollen und Statuslogik entfallen.
    """
    if str(uid) in RESERVED_UIDS:
        return new_daten
    new = copy.deepcopy(_as_dict(new_daten))
    root = new.setdefault("ROOT", {})
    for field in LIST_ROOT_FIELDS:
        if field in root:
            root[field] = as_name_list(root[field])
    if "ACTIVE" in root:
        root["ACTIVE"] = _truthy(root["ACTIVE"])

    row = None
    try:
        row = await PdvmDatabase(table, system_pool=system_pool, mandant_pool=mandant_pool).get_by_uid(
            uid if isinstance(uid, uuid.UUID) else uuid.UUID(str(uid))
        )
    except Exception:
        row = None
    old = _as_dict(row.get("daten")) if row else {}
    old_root = _as_dict(old.get("ROOT"))

    for field in IMMUTABLE_ROOT_FIELDS:
        before = old_root.get(field)
        before_norm = as_name_list(before) if field in LIST_ROOT_FIELDS else str(before or "").strip()
        after = root.get(field)
        after_norm = as_name_list(after) if field in LIST_ROOT_FIELDS else str(after or "").strip()
        if before_norm and after_norm != before_norm:
            raise TextTemplateError(f"{field} ist nach der Anlage unveränderlich")

    if gcs is not None:
        roles = _roles_of(gcs)
        if not roles & EDIT_ROLES[table]:
            raise TextTemplateError(
                "Keine Berechtigung zur Pflege von Textvorlagen"
                + (" (Rolle 'vorlagen' erforderlich)" if table == SYSTEM_TABLE else " (Administrator erforderlich)")
            )
        if row:  # Herkunft ist nicht aenderbar
            for field in ("SOURCE_UID", "SOURCE_HASH"):
                if old_root.get(field) is None:
                    root.pop(field, None)
                else:
                    root[field] = old_root[field]
        can_approve = bool(roles & APPROVE_ROLES[table])
        old_groups = language_groups(old)
        for lang, group in language_groups(new).items():
            _apply_release_rules(group, old_groups.get(lang), can_approve, _actor_label(gcs, actor_user_uid), lang)

    errors = validate_template(new)
    if errors:
        raise TextTemplateError("; ".join(errors))
    return new


def _apply_release_rules(
    group: Dict[str, Any], old_group: Optional[Dict[str, Any]], can_approve: bool, actor: str, lang: str
) -> None:
    """Statuslogik je Sprache: Textaenderung -> review; Freigabe nur durch berechtigte Rolle (setzt Benutzer/Zeit/Version)."""
    statuses = status_values()
    changed = old_group is None or any(group.get(f) != old_group.get(f) for f in TEXT_FIELDS)
    old_status = str((old_group or {}).get("STATUS") or "").strip().lower()
    want = str(group.get("STATUS") or "").strip().lower()
    if want not in statuses:
        want = old_status if old_status in statuses else "new"

    if want == "approved" and old_group is not None and old_status == "approved":
        if changed:  # bearbeiteter, bisher freigegebener Text: erst erneut freigeben
            want = "review"
        else:
            for field in ("VERSION", "APPROVED_BY", "APPROVED_AT"):
                group[field] = old_group.get(field)
    elif want == "approved":
        if not can_approve:
            raise TextTemplateError(f"{lang}: Keine Berechtigung zur Freigabe")
        previous = (old_group or {}).get("VERSION")
        group["VERSION"] = bump_version(previous) if previous else "v1.0.0"
        group["APPROVED_BY"] = actor
        group["APPROVED_AT"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    elif changed and want == old_status:
        want = "review" if old_group is not None else "new"

    group["STATUS"] = want
    if want != "approved":
        group["APPROVED_BY"] = ""
        group["APPROVED_AT"] = ""
        group.setdefault("VERSION", (old_group or {}).get("VERSION") or "")


async def after_write(*, table: str, uid: Any, daten: Dict[str, Any], system_pool: Any, mandant_pool: Any) -> None:
    """Nach dem Schreiben: pro Schluessel ist hoechstens eine Vorlage des Mandanten aktiv."""
    root = _as_dict(_as_dict(daten).get("ROOT"))
    if table != MANDANT_TABLE or str(uid) in RESERVED_UIDS or root.get("ACTIVE") is not True:
        return
    key = str(root.get("TEMPLATE_KEY") or "").strip()
    if not key:
        return
    others = await _fetch_rows(
        mandant_pool,
        f"SELECT uid, name, daten FROM {MANDANT_TABLE} WHERE daten->'ROOT'->>'TEMPLATE_KEY' = $1 "
        "AND daten->'ROOT'->'ACTIVE' = 'true'::jsonb AND uid <> $2::uuid",
        key,
        str(uid),
    )
    for other in others:
        other["daten"].setdefault("ROOT", {})["ACTIVE"] = False
        await update_record_central(
            table_name=MANDANT_TABLE, uid=other["uid"], daten=other["daten"], name=other["name"],
            system_pool=system_pool, mandant_pool=mandant_pool,
        )


# --- Kopieren -------------------------------------------------------------------------------------------------


def _copy_root(daten: Dict[str, Any], table: str, source_uid: str, active: bool) -> Dict[str, Any]:
    root = _as_dict(daten.get("ROOT"))
    new_root = {
        "TABLE": table,
        "TEMPLATE_KEY": root.get("TEMPLATE_KEY"),
        "CHANNEL": root.get("CHANNEL"),
        "DESCRIPTION": root.get("DESCRIPTION"),
        "VARIABLES": list(as_name_list(root.get("VARIABLES"))),
        "REQUIRED_VARIABLES": list(as_name_list(root.get("REQUIRED_VARIABLES"))),
        "SOURCE_UID": source_uid,
        "SOURCE_HASH": source_hash(daten),
    }
    if table == MANDANT_TABLE:
        new_root["ACTIVE"] = active
    return new_root


def _copy_groups(daten: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Sprachgruppen einer Vorlage fuer eine Kopie: Texte uebernehmen, Freigabe zuruecksetzen (Status 'review')."""
    return {
        key: {
            **{f: group[f] for f in TEXT_FIELDS if group.get(f) is not None},
            "STATUS": "review", "VERSION": group.get("VERSION") or "", "APPROVED_BY": "", "APPROVED_AT": "",
        }
        for key, group in daten.items()
        if key != "ROOT" and isinstance(group, dict) and any(f in group for f in TEXT_FIELDS)
    }


async def copy_template(*, table: str, uid: Any, gcs: Any, new_name: Optional[str] = None) -> Dict[str, str]:
    """Legt eine Kopie einer Vorlage in derselben Tabelle an (nicht aktiv, Sprachen im Status 'review')."""
    if table not in TABLES:
        raise TextTemplateError("Unbekannte Tabelle")
    system_pool, mandant_pool = gcs._system_pool, getattr(gcs, "_mandant_pool", None)
    row = await PdvmDatabase(table, system_pool=system_pool, mandant_pool=mandant_pool).get_by_uid(uuid.UUID(str(uid)))
    if not row or str(row["uid"]) in RESERVED_UIDS:
        raise TextTemplateError("Vorlage nicht gefunden")
    daten = _as_dict(row.get("daten"))
    name = (new_name or "").strip() or f"{row.get('name') or 'Vorlage'} (Kopie)"
    new: Dict[str, Any] = {"ROOT": _copy_root(daten, table, str(row["uid"]), active=False)}
    new["ROOT"]["SELF_NAME"] = name
    new.update(_copy_groups(daten))
    created = await create_record_central(
        table_name=table, name=name, daten=new, gcs=gcs, system_pool=system_pool, mandant_pool=mandant_pool
    )
    return {"uid": str(created["uid"]), "name": name}


async def source_status(*, table: str, uid: Any, gcs: Any) -> Dict[str, Any]:
    """Herkunft einer Mandantenvorlage: Ist die Systemvorlage neuer als die Kopie (SOURCE_HASH-Vergleich)?

    `outdated` ist false, wenn der Mandant bereits eine Kopie mit dem aktuellen Systemstand hat (`adopted_uid`).
    """
    if table != MANDANT_TABLE:
        raise TextTemplateError("Herkunft gibt es nur bei Mandantenvorlagen")
    system_pool, mandant_pool = gcs._system_pool, gcs._mandant_pool
    row = await PdvmDatabase(table, system_pool=system_pool, mandant_pool=mandant_pool).get_by_uid(uuid.UUID(str(uid)))
    if not row or str(row["uid"]) in RESERVED_UIDS:
        raise TextTemplateError("Vorlage nicht gefunden")
    root = _as_dict(_as_dict(row.get("daten")).get("ROOT"))
    status: Dict[str, Any] = {"has_source": False, "source_missing": False, "outdated": False, "source_name": None,
                              "source_uid": None, "adopted_uid": None}
    try:
        source_uid = uuid.UUID(str(root.get("SOURCE_UID") or ""))
    except ValueError:
        return status
    status.update(has_source=True, source_uid=str(source_uid))
    source = await PdvmDatabase(SYSTEM_TABLE, system_pool=system_pool).get_by_uid(source_uid)
    if not source:
        status["source_missing"] = True
        return status
    status["source_name"] = source.get("name") or ""
    current = source_hash(_as_dict(source.get("daten")))
    if current == str(root.get("SOURCE_HASH") or ""):
        return status
    async with mandant_pool.acquire() as conn:
        adopted = await conn.fetchval(
            f"SELECT uid FROM {MANDANT_TABLE} WHERE daten->'ROOT'->>'SOURCE_UID' = $1 "
            "AND daten->'ROOT'->>'SOURCE_HASH' = $2 AND COALESCE(historisch, 0) = 0 LIMIT 1",
            str(source_uid), current,
        )
    if adopted:
        status["adopted_uid"] = str(adopted)
    else:
        status["outdated"] = True
    return status


async def adopt_source(*, table: str, uid: Any, gcs: Any) -> Dict[str, str]:
    """Uebernimmt die aktuelle Systemfassung als neue, inaktive Mandantenvorlage (Sprachen 'review'); nichts wird ueberschrieben."""
    status = await source_status(table=table, uid=uid, gcs=gcs)
    if not status["has_source"] or status["source_missing"]:
        raise TextTemplateError("Die Systemvorlage dieser Kopie existiert nicht mehr")
    if not status["outdated"]:
        raise TextTemplateError("Der aktuelle Systemstand ist bereits übernommen")
    system_pool, mandant_pool = gcs._system_pool, gcs._mandant_pool
    source = await PdvmDatabase(SYSTEM_TABLE, system_pool=system_pool).get_by_uid(uuid.UUID(status["source_uid"]))
    daten = _as_dict(source.get("daten"))
    name = f"{source.get('name') or 'Vorlage'} (Systemstand {datetime.now():%Y-%m-%d})"
    new: Dict[str, Any] = {"ROOT": _copy_root(daten, MANDANT_TABLE, status["source_uid"], active=False)}
    new["ROOT"]["SELF_NAME"] = name
    new.update(_copy_groups(daten))
    created = await create_record_central(
        table_name=MANDANT_TABLE, name=name, daten=new, gcs=gcs, system_pool=system_pool, mandant_pool=mandant_pool
    )
    return {"uid": str(created["uid"]), "name": name}


# --- Kopieren der Systemvorlagen in den Mandanten --------------------------------------------------------------


async def ensure_mandant_templates(
    *, system_pool: Any, mandant_pool: Any, actor_user_uid: Optional[Any] = None, force: bool = False,
    dry_run: bool = False,
) -> List[str]:
    """Kopiert fehlende Systemvorlagen einmalig in msy_textvorlagen (neue UID, SOURCE_UID/SOURCE_HASH, aktiv).

    Eine Vorlage gilt als uebernommen, wenn der Mandant einen Satz mit dieser SOURCE_UID hat; er darf ihn umbenennen
    und aendern. Freigabestand und Version werden uebernommen. Ohne Tabelle (Wartung steht aus) passiert nichts.
    Mit `dry_run` wird nichts geschrieben (nur die Namen der fehlenden Vorlagen).
    Rueckgabe: Namen der kopierten Vorlagen.
    """
    now = time.monotonic()
    if not force and now - _last_copy.get(id(mandant_pool), 0.0) < COPY_INTERVAL_SECONDS:
        return []
    async with mandant_pool.acquire() as conn:
        exists = await conn.fetchval("SELECT to_regclass('public.' || $1) IS NOT NULL", MANDANT_TABLE)
        if not exists:
            return []
        owned = {
            str(r["src"]) for r in await conn.fetch(
                f"SELECT daten->'ROOT'->>'SOURCE_UID' AS src FROM {MANDANT_TABLE} WHERE daten->'ROOT'->>'SOURCE_UID' IS NOT NULL"
            )
        }
    rows = await _fetch_rows(
        system_pool,
        f"SELECT uid, name, daten FROM {SYSTEM_TABLE} WHERE daten->'ROOT'->>'TEMPLATE_KEY' IS NOT NULL "
        "AND COALESCE(historisch, 0) = 0 ORDER BY name",
    )
    copied: List[str] = []
    for row in rows:
        if row["uid"] in owned:
            continue
        if dry_run:
            copied.append(row["name"] or row["uid"])
            continue
        new_daten: Dict[str, Any] = {"ROOT": _copy_root(row["daten"], MANDANT_TABLE, row["uid"], active=True)}
        new_daten["ROOT"]["SELF_NAME"] = row["name"]
        for key, value in row["daten"].items():
            if key != "ROOT" and isinstance(value, dict):
                new_daten[key] = copy.deepcopy(value)
        await create_record_central(
            table_name=MANDANT_TABLE,
            name=row["name"],
            daten=new_daten,
            system_pool=system_pool,
            mandant_pool=mandant_pool,
            actor_user_uid=actor_user_uid,
        )
        copied.append(row["name"] or row["uid"])
    if not dry_run:
        _last_copy[id(mandant_pool)] = now
    if copied and not dry_run:
        _cache.clear()
    return copied

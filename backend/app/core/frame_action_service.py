"""
Frame-Aktionen: Register der Aktionen, die Controls vom Typ `action` (Button) und `info` (Hinweis) ausloesen/anzeigen.

Spezifikation: docs/specs/PDVM_FRAME_ACTIONS_SPEC_V1.md, Regel 2.17 in ARCHITECTURE_RULES.md.

- Ein Control verweist nur auf eine Aktions-ID (`CONFIGS.action.id`). Was die Aktion tut und wer sie ausfuehren darf, steht
  ausschliesslich hier; ein Datenbankeintrag kann keine neue Funktion einfuehren.
- Zentrale Pruefung in `run_action`: bekannte ID, Tabelle, Rolle (Rollen der Sitzung), UID, Parameter (Typ, Laenge), Vorbedingung.
- Handler rufen die vorhandenen Services; geschrieben wird ueber den zentralen Gateway (Regel 1.1), hier steht kein SQL.
- `action_states` liefert fuer einen Satz gebuendelt, ob die Aktionen fuer den Benutzer erlaubt sind, und den Zustand fuer
  Hinweise (z. B. "Systemvorlage ist neuer"). Die Frame-Runtime ist je Frame gecacht, nicht je Benutzer; benutzerabhaengige
  Angaben kommen deshalb nur ueber diesen Weg.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, FrozenSet, Iterable, List, Optional

from app.core import text_template_service as texts
from app.core import mandant_delete_service
from app.core.mandant_setup_service import MANDANT_TABLE, grant_mandant_access, mandant_setup_state, setup_mandant_database
from app.core.password_reset_service import issue_password_reset, update_account_lock
from app.core.pdvm_central_benutzer import PdvmCentralBenutzer
from app.core.security import normalized_roles, session_has_admin_rights

logger = logging.getLogger(__name__)

PARAM_TYPES = {"string", "text"}
USER_TABLE = "asy_benutzer"
USER_ADMIN_ROLES = frozenset({"admin", "superadmin"})


class ActionError(ValueError):
    """Ungueltige Anfrage oder fachlicher Fehler; die Meldung ist fuer den Benutzer bestimmt (HTTP 400)."""


class ActionNotFound(KeyError):
    pass


class ActionDenied(PermissionError):
    """Keine Berechtigung (HTTP 403)."""


@dataclass(frozen=True)
class ParamSpec:
    type: str = "text"
    required: bool = False
    max_length: int = 500


@dataclass(frozen=True)
class ActionContext:
    gcs: Any
    table: str
    uid: str
    params: Dict[str, str]


Handler = Callable[[ActionContext], Awaitable[Dict[str, Any]]]
StateProvider = Callable[[ActionContext], Awaitable[Dict[str, Any]]]
Precheck = Callable[[ActionContext], Awaitable[None]]


@dataclass(frozen=True)
class Action:
    """Eine Aktion des Registers.

    `executor="server"`: ausgefuehrt ueber `run_action`. `executor="host"`: der Dialog fuehrt sie selbst aus (z. B. Aktionen des
    Workflow-Draft-Builders, die auf dem Editorzustand arbeiten); Sichtbarkeit und Rechte kommen trotzdem vom Server (`state`),
    und die zugehoerigen Endpunkte erzwingen die Rollen selbst. Der Tabellenschluessel `*` gilt fuer jede Tabelle.
    """

    id: str
    roles_by_table: Dict[str, FrozenSet[str]]
    handler: Optional[Handler] = None
    params: Dict[str, ParamSpec] = field(default_factory=dict)
    state: Optional[StateProvider] = None
    precheck: Optional[Precheck] = None
    executor: str = "server"
    needs_record: bool = True
    # Rollen, die zusaetzlich zu einer der `roles_by_table` ALLE vorhanden sein muessen (z. B. superadmin UND delmand)
    also_require: FrozenSet[str] = frozenset()

    @property
    def tables(self) -> FrozenSet[str]:
        return frozenset(self.roles_by_table)


def result(message: str, *, key: str, status: str = "ok", severity: str = "info", refresh: Iterable[str] = (), data: Optional[dict] = None) -> Dict[str, Any]:
    """Einheitliche Antwort: Meldung (Klartext) plus Meldungsschluessel fuer das spaetere Woerterbuch."""
    return {
        "status": status,
        "message": message,
        "message_key": key,
        "severity": severity,
        "refresh": list(refresh),
        "data": data or {},
    }


# --- Rollen und Pruefungen -----------------------------------------------------------------------------------


def session_roles(gcs: Any) -> set:
    benutzer = getattr(gcs, "benutzer", None)
    roles = set(normalized_roles(getattr(benutzer, "data", None)))
    if session_has_admin_rights(gcs):
        roles.add("admin")
    return roles


def _parse_uid(value: Any) -> str:
    try:
        return str(uuid.UUID(str(value)))
    except (ValueError, AttributeError, TypeError):
        raise ActionError("Ungültige UID")


def _allowed(action: Action, table: str, gcs: Any) -> tuple[bool, Optional[str]]:
    roles = action.roles_by_table.get(table)
    if roles is None:
        roles = action.roles_by_table.get("*")
    if roles is None:
        return False, "Aktion gilt nicht für diese Tabelle"
    if not (session_roles(gcs) & roles):
        return False, "Keine Berechtigung"
    missing = action.also_require - session_roles(gcs)
    if missing:
        return False, f"Keine Berechtigung (Rolle {', '.join(sorted(missing))} erforderlich)"
    return True, None


def _clean_params(action: Action, raw: Any) -> Dict[str, str]:
    given = raw if isinstance(raw, dict) else {}
    unknown = sorted(set(given) - set(action.params))
    if unknown:
        raise ActionError(f"Unbekannte Parameter: {', '.join(unknown)}")
    out: Dict[str, str] = {}
    for name, spec in action.params.items():
        value = given.get(name)
        text = "" if value is None else str(value).strip()
        if spec.type not in PARAM_TYPES:
            raise ActionError(f"Parameter {name}: Typ {spec.type} wird nicht unterstützt")
        if spec.required and not text:
            raise ActionError(f"Parameter {name} ist erforderlich")
        if len(text) > spec.max_length:
            raise ActionError(f"Parameter {name} ist zu lang (maximal {spec.max_length} Zeichen)")
        out[name] = text
    return out


# --- Benutzer-Aktionen ---------------------------------------------------------------------------------------


async def _require_user_of_session_mandant(ctx: ActionContext) -> None:
    """Benutzer-Aktionen wirken nur auf Benutzer, die dem Mandanten der Sitzung zugeordnet sind (superadmin: alle)."""
    if "superadmin" in session_roles(ctx.gcs):
        return
    user = await PdvmCentralBenutzer(uuid.UUID(ctx.uid)).get_user()
    if not user:
        raise ActionError("Benutzer nicht gefunden")
    daten = user.get("daten") if isinstance(user.get("daten"), dict) else {}
    mandanten = daten.get("MANDANTEN") if isinstance(daten.get("MANDANTEN"), dict) else {}
    assigned = {str(m).strip().lower() for m in (mandanten.get("LIST") or []) if m}
    if str(getattr(ctx.gcs, "mandant_guid", "") or "").strip().lower() not in assigned:
        raise ActionDenied("Der Benutzer gehört nicht zum aktuellen Mandanten")


def _actor(ctx: ActionContext) -> Dict[str, Any]:
    try:
        actor_user_uid = uuid.UUID(str(getattr(ctx.gcs, "user_guid", "") or ""))
    except (ValueError, TypeError):
        actor_user_uid = None
    return {"actor_user_uid": actor_user_uid, "actor_ip": getattr(ctx.gcs, "actor_ip", None)}


async def _user_password_reset(ctx: ActionContext) -> Dict[str, Any]:
    res = await issue_password_reset(gcs=ctx.gcs, user_uid=ctx.uid)
    if res.get("email_sent"):
        return result(f"OTP gesendet an {res.get('email')}. Gültig bis {res.get('expires_at')}.",
                      key="frame_action.user.password_reset.sent", refresh=["record"])
    return result(f"OTP erstellt, E-Mail fehlgeschlagen: {res.get('email_error') or 'unbekannt'}",
                  key="frame_action.user.password_reset.mail_failed", status="error", severity="error", refresh=["record"])


async def _user_lock(ctx: ActionContext) -> Dict[str, Any]:
    await update_account_lock(user_uid=ctx.uid, locked=True, reason=ctx.params.get("reason") or None, **_actor(ctx))
    return result("Account wurde gesperrt.", key="frame_action.user.lock.done", refresh=["record"])


async def _user_unlock(ctx: ActionContext) -> Dict[str, Any]:
    await update_account_lock(user_uid=ctx.uid, locked=False, reason=None, **_actor(ctx))
    return result("Account wurde entsperrt.", key="frame_action.user.unlock.done", refresh=["record"])


# --- Textvorlagen-Aktionen -----------------------------------------------------------------------------------


async def _texttemplate_copy(ctx: ActionContext) -> Dict[str, Any]:
    created = await texts.copy_template(table=ctx.table, uid=ctx.uid, gcs=ctx.gcs)
    return result(f"Kopie „{created['name']}“ angelegt (inaktiv, Sprachen im Status „review“).",
                  key="frame_action.texttemplate.copy.done", refresh=["rows"], data=created)


async def _texttemplate_adopt(ctx: ActionContext) -> Dict[str, Any]:
    created = await texts.adopt_source(table=ctx.table, uid=ctx.uid, gcs=ctx.gcs)
    return result(
        f"Neue Systemfassung als „{created['name']}“ übernommen (inaktiv, Sprachen im Status „review“). "
        "Prüfen, freigeben und aktivieren Sie sie im Frame.",
        key="frame_action.texttemplate.adopt_source.done", refresh=["rows", "state"], data=created,
    )


async def _texttemplate_source_state(ctx: ActionContext) -> Dict[str, Any]:
    return await texts.source_status(table=ctx.table, uid=ctx.uid, gcs=ctx.gcs)


# --- Mandanten-Aktion ----------------------------------------------------------------------------------------


async def _require_mandant_needs_setup(ctx: ActionContext) -> None:
    state = await mandant_setup_state(ctx.uid)
    if not state["exists"]:
        raise ActionError("Mandant nicht gefunden")
    if not state["needs_setup"]:
        raise ActionError("Die Datenbank dieses Mandanten ist bereits eingerichtet")


async def _mandant_setup(ctx: ActionContext) -> Dict[str, Any]:
    done = await setup_mandant_database(ctx.uid)
    actor_uid = _actor(ctx)["actor_user_uid"]
    access_granted = False
    if actor_uid is not None:
        try:
            access_granted = await grant_mandant_access(user_uid=actor_uid, mandant_id=ctx.uid, actor_ip=_actor(ctx)["actor_ip"])
        except Exception as exc:  # Zuweisung ist Komfort; die Datenbank ist eingerichtet
            logger.warning("Mandant %s: Zuweisung an Benutzer fehlgeschlagen: %s", ctx.uid, exc)
    # Neuanmeldung: Mandantenliste und Token stammen aus dem Login (Frontend meldet nach der Bestätigung ab)
    return result(
        f"Datenbank „{done['database']}“ erstellt. Die Tabellen werden beim ersten Login des Mandanten angelegt. "
        "Bitte melden Sie sich neu an.",
        key="frame_action.mandant.setup.done", refresh=["record", "state"], data={**done, "access_granted": access_granted, "relogin": True},
    )


async def _mandant_setup_state(ctx: ActionContext) -> Dict[str, Any]:
    return await mandant_setup_state(ctx.uid)


async def _mandant_delete_state(ctx: ActionContext) -> Dict[str, Any]:
    return await mandant_delete_service.delete_state(ctx.uid, getattr(ctx.gcs, "mandant_guid", None))


async def _require_mandant_deletable(ctx: ActionContext) -> None:
    state = await _mandant_delete_state(ctx)
    if not state["can_delete"]:
        raise ActionError(state["reason"] or "Mandant nicht gefunden")


async def _mandant_delete(ctx: ActionContext) -> Dict[str, Any]:
    actor = _actor(ctx)
    done = await mandant_delete_service.delete_mandant(
        ctx.uid, confirm_name=ctx.params.get("confirm_name", ""), session_mandant_id=getattr(ctx.gcs, "mandant_guid", None),
        actor_uid=actor["actor_user_uid"], actor_ip=actor["actor_ip"],
    )
    backup = f" Sicherung: {done['backup_file']}." if done["backup_file"] else " Es gab keine Datenbank zu sichern."
    return result(
        f"Mandant „{done['name']}“ gelöscht.{backup} Aus {done['users_updated']} Benutzer(n) entfernt. "
        "Bitte melden Sie sich neu an.",
        key="frame_action.mandant.delete.done", refresh=["rows", "state"], data={**done, "relogin": True},
    )


# --- Host-Aktionen des Workflow-Draft-Builders --------------------------------------------------------------

_WORKFLOW_ROLES = frozenset({"admin", "superadmin", "develop", "developer"})
_WORKFLOW_APPLY_ROLES = frozenset({"admin", "superadmin"})  # Live-Commit nur fuer Administratoren (Endpunkt erzwingt es ebenfalls)
WORKFLOW_HOST_ACTIONS = (
    "workflow.validate", "workflow.save", "workflow.build", "workflow.save_view", "workflow.save_content",
    "workflow.create_control", "workflow.create_property", "workflow.abort", "workflow.dry_run",
)


def _host_action(action_id: str, roles: FrozenSet[str]) -> Action:
    return Action(action_id, {"*": roles}, executor="host", needs_record=False)


def _register(*actions: Action) -> Dict[str, Action]:
    return {a.id: a for a in actions}


_USER_ROLES = {USER_TABLE: USER_ADMIN_ROLES}

REGISTRY: Dict[str, Action] = _register(
    Action("user.password_reset", _USER_ROLES, _user_password_reset, precheck=_require_user_of_session_mandant),
    Action("user.lock", _USER_ROLES, _user_lock, params={"reason": ParamSpec("text", max_length=500)},
           precheck=_require_user_of_session_mandant),
    Action("user.unlock", _USER_ROLES, _user_unlock, precheck=_require_user_of_session_mandant),
    Action("texttemplate.copy", {t: frozenset(r) for t, r in texts.EDIT_ROLES.items()}, _texttemplate_copy),
    Action("texttemplate.adopt_source", {texts.MANDANT_TABLE: frozenset(texts.EDIT_ROLES[texts.MANDANT_TABLE])},
           _texttemplate_adopt, state=_texttemplate_source_state),
    Action("mandant.setup", {MANDANT_TABLE: frozenset({"superadmin"})}, _mandant_setup,
           precheck=_require_mandant_needs_setup, state=_mandant_setup_state),
    Action("mandant.delete", {MANDANT_TABLE: frozenset({"superadmin"})}, _mandant_delete,
           params={"confirm_name": ParamSpec("string", required=True, max_length=200)},
           precheck=_require_mandant_deletable, state=_mandant_delete_state, also_require=frozenset({"delmand"})),
    *(_host_action(action_id, _WORKFLOW_ROLES) for action_id in WORKFLOW_HOST_ACTIONS),
    _host_action("workflow.apply", _WORKFLOW_APPLY_ROLES),
)


def is_registered(action_id: str) -> bool:
    return str(action_id or "").strip() in REGISTRY


def get_action(action_id: str) -> Action:
    action = REGISTRY.get(str(action_id or "").strip())
    if action is None:
        raise ActionNotFound(f"Unbekannte Aktion: {action_id}")
    return action


# --- Ausfuehren und Zustaende --------------------------------------------------------------------------------


async def run_action(action_id: str, *, gcs: Any, table: str, uid: Any, params: Any = None) -> Dict[str, Any]:
    """Fuehrt eine Aktion nach zentraler Pruefung aus (Reihenfolge: ID, Tabelle/Rolle, UID, Parameter, Vorbedingung)."""
    action = get_action(action_id)
    table_norm = str(table or "").strip().lower()
    ok, reason = _allowed(action, table_norm, gcs)
    if not ok:
        logger.warning("frame_action %s abgelehnt: table=%s user=%s grund=%s", action.id, table_norm, getattr(gcs, "user_guid", None), reason)
        raise ActionDenied(reason)
    if action.executor != "server" or action.handler is None:
        raise ActionError("Diese Aktion wird vom Dialog selbst ausgeführt")
    ctx = ActionContext(gcs, table_norm, _parse_uid(uid), _clean_params(action, params))
    if action.precheck is not None:
        await action.precheck(ctx)
    try:
        outcome = await action.handler(ctx)
    except ValueError as exc:  # fachliche Fehler der Services (z. B. "Benutzer nicht gefunden")
        logger.info("frame_action %s fehlgeschlagen: table=%s uid=%s user=%s fehler=%s", action.id, ctx.table, ctx.uid, getattr(gcs, "user_guid", None), exc)
        raise ActionError(str(exc))
    logger.info("frame_action %s: table=%s uid=%s user=%s status=%s", action.id, ctx.table, ctx.uid, getattr(gcs, "user_guid", None), outcome.get("status"))
    return outcome


async def action_states(*, gcs: Any, table: str, uid: Any = None, ids: Iterable[str]) -> Dict[str, Dict[str, Any]]:
    """Je Aktions-ID: `allowed`, Begruendung, `executor` und (falls die Aktion einen Zustand liefert) `state`.

    Gebuendelt fuer einen Satz. Ohne `uid` (z. B. Workflow-Builder) sind nur Aktionen ohne Datensatzbezug erlaubt.
    """
    table_norm = str(table or "").strip().lower()
    record_uid = _parse_uid(uid) if uid not in (None, "") else None
    out: Dict[str, Dict[str, Any]] = {}
    for raw_id in dict.fromkeys(str(i or "").strip() for i in ids):
        action = REGISTRY.get(raw_id)
        if action is None:
            out[raw_id] = {"allowed": False, "reason": "Unbekannte Aktion", "state": None, "executor": None}
            continue
        ok, reason = _allowed(action, table_norm, gcs)
        if ok and record_uid is None and action.needs_record:
            ok, reason = False, "Kein Datensatz ausgewählt"
        state = None
        if ok and action.state is not None and record_uid is not None:
            try:
                state = await action.state(ActionContext(gcs, table_norm, record_uid, {}))
            except ValueError as exc:
                state, ok, reason = None, False, str(exc)
        out[raw_id] = {"allowed": ok, "reason": reason, "state": state, "executor": action.executor}
    return out


def unknown_action_ids(ids: Iterable[str]) -> List[str]:
    return sorted({str(i or "").strip() for i in ids if not is_registered(i)})

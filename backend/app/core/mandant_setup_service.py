"""
Mandanten-Datenbank einrichten (Aktion `mandant.setup`, Regel 2.17).

Legt nur die PostgreSQL-Datenbank an (mit uuid-ossp und Init-Marker) und setzt `ROOT.DB_CREATED_AT`. Die Tabellen entstehen beim
ersten Login des Mandanten (Mandanten-Wartung), weil der Setup-Benutzer evtl. keine Rechte fuer Tabellen in der neuen
Datenbank hat. Aufgerufen wird die Funktion ausschliesslich ueber das Aktionsregister (`frame_action_service`).
Fachliche Fehler werden als `ValueError` gemeldet (Meldung fuer den Benutzer).
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any, Dict

from app.core import mandant_db_provisioning_service as provisioning
from app.core.connection_manager import ConnectionConfig, ConnectionManager
from app.core.pdvm_central_datenbank import PdvmCentralDatabase
from app.core.pdvm_datenbank import PdvmDatabase
from app.core.pdvm_datetime import PdvmDateTime

logger = logging.getLogger(__name__)

MANDANT_TABLE = "asy_mandanten"
RESERVED_MANDANT_UIDS = {
    "66666666-6666-6666-6666-666666666666",  # Vorlage
    "55555555-5555-5555-5555-555555555555",  # Eigenschaften-Control
    "00000000-0000-0000-0000-000000000000",  # Tabellen-Metadaten
}


async def _load(mandant_id: str) -> Dict[str, Any] | None:
    try:
        uid = uuid.UUID(str(mandant_id))
    except (ValueError, TypeError):
        return None
    if str(uid) in RESERVED_MANDANT_UIDS:
        return None
    return await PdvmDatabase(MANDANT_TABLE).get_by_uid(uid)


def _needs_setup(daten: Dict[str, Any]) -> bool:
    created = (daten.get("ROOT") or {}).get("DB_CREATED_AT")
    return not created or created == "-eingeben-"


async def grant_mandant_access(*, user_uid: Any, mandant_id: str, actor_ip: str | None = None) -> bool:
    """Traegt den Mandanten in `MANDANTEN.LIST` des Benutzers ein (idempotent); True, wenn der Satz geaendert wurde.

    Der Benutzer sieht den Mandanten nach der naechsten Anmeldung in der Auswahl.
    """
    from app.core.central_write_service import update_record_central
    from app.core.pdvm_central_benutzer import PdvmCentralBenutzer

    try:
        user_uuid = uuid.UUID(str(user_uid))
        mandant = str(uuid.UUID(str(mandant_id)))
    except (ValueError, TypeError):
        raise ValueError("Ungültige GUID")
    user = await PdvmCentralBenutzer(user_uuid).get_user()
    if not user:
        raise ValueError("Benutzer nicht gefunden")

    daten = dict(user.get("daten") or {})
    mandanten = dict(daten.get("MANDANTEN") or {})
    current = [str(m) for m in (mandanten.get("LIST") or [])]
    if mandant in current:
        return False
    mandanten["LIST"] = current + [mandant]
    daten["MANDANTEN"] = mandanten
    await update_record_central(
        table_name="asy_benutzer",
        uid=user_uuid,
        daten=daten,
        name=user.get("name"),
        historisch=user.get("historisch"),
        gcs=None,
        actor_user_uid=user_uuid,
        actor_ip=actor_ip,
    )
    return True


class MandantValidationError(Exception):
    """Eingabefehler der Neuanlage; `errors` = Liste {group, field, message} (HTTP 422)."""

    def __init__(self, errors: list):
        super().__init__("Mandantendaten ungültig")
        self.errors = errors


async def create_mandant(
    *, mandant_data: Dict[str, Any], actor_uid: Any, actor_ip: str | None = None, setup_database: bool = True
) -> Dict[str, Any]:
    """Legt einen Mandanten an: pruefen, Satz speichern, dem Anleger zuweisen, Datenbank einrichten.

    Der Satz wird vor der Datenbank gespeichert; scheitert die Datenbank, bleibt der Satz (`needs_setup`) und die
    Aktion `mandant.setup` wiederholt nur diesen Schritt (kein Rollback). Fehler der Eingabe: `MandantValidationError`.
    Teilfehler stehen im Ergebnis (`access_error`, `database.status == "failed"`), nur ein nicht gespeicherter Satz wirft.
    """
    from app.core.mandant_record_rules import validate_new_mandant

    errors = validate_new_mandant(mandant_data)
    if errors:
        raise MandantValidationError(errors)

    new_guid = str(uuid.uuid4())
    now_str = PdvmDateTime().now().pdvm_datetime_str
    root = mandant_data.setdefault("ROOT", {})
    root["SELF_GUID"] = new_guid
    root["SELF_NAME"] = str(root.get("NAME") or "").strip()
    root["CREATED_AT"] = now_str
    root["MODIFIED_AT"] = now_str

    central = PdvmCentralDatabase(MANDANT_TABLE, new_guid)
    central.set_data(mandant_data, new_guid)
    saved_guid = str(await central.save_all_values())
    logger.info("Mandant gespeichert: %s - %s", saved_guid, root.get("NAME"))

    result: Dict[str, Any] = {
        "mandant_id": saved_guid,
        "name": root["SELF_NAME"],
        "saved": True,
        "access_granted": False,
        "access_error": None,
        "database": {"status": "skipped", "name": (mandant_data.get("MANDANT") or {}).get("DATABASE"), "message": ""},
    }

    try:
        result["access_granted"] = await grant_mandant_access(user_uid=actor_uid, mandant_id=saved_guid, actor_ip=actor_ip)
    except Exception as exc:
        logger.warning("Mandant %s gespeichert, Zuweisung an Benutzer fehlgeschlagen: %s", saved_guid, exc)
        result["access_error"] = str(exc)

    if setup_database:
        try:
            await setup_mandant_database(saved_guid)
            result["database"]["status"] = "created"
        except ValueError as exc:
            result["database"].update(status="failed", message=str(exc))
        except Exception as exc:
            logger.error("Datenbank fuer Mandant %s konnte nicht eingerichtet werden: %s", saved_guid, exc)
            result["database"].update(status="failed", message=str(exc))
    return result


async def mandant_setup_state(mandant_id: str) -> Dict[str, Any]:
    """Zustand fuer Hinweis und Schaltflaeche: `needs_setup` = Datenbank noch nicht eingerichtet."""
    record = await _load(mandant_id)
    if not record:
        return {"exists": False, "needs_setup": False, "database": None}
    daten = record.get("daten") or {}
    database = (daten.get("MANDANT") or {}).get("DATABASE")
    return {"exists": True, "needs_setup": _needs_setup(daten), "database": database or None}


async def setup_mandant_database(mandant_id: str) -> Dict[str, Any]:
    record = await _load(mandant_id)
    if not record:
        raise ValueError("Mandant nicht gefunden")
    daten = record.get("daten") or {}
    if not _needs_setup(daten):
        raise ValueError("Die Datenbank dieses Mandanten ist bereits eingerichtet")

    db_name = (daten.get("MANDANT") or {}).get("DATABASE")
    if not db_name or db_name == "-eingeben-":
        raise ValueError("Datenbank-Name nicht konfiguriert")

    try:
        _, mandant_config = await ConnectionManager.get_mandant_config(str(mandant_id))
        postgres_config = ConnectionConfig(
            host=mandant_config.host,
            port=mandant_config.port,
            user=mandant_config.user,
            password=mandant_config.password,
            ssl=mandant_config.ssl,
            database="postgres",  # Datenbank zum Anlegen der neuen Datenbank
        )
        conn = await provisioning.connect(**postgres_config.to_dict())
        try:
            if not await conn.lookup_database(db_name):
                await conn.create_database(db_name, from_template0=True)
                logger.info("Datenbank '%s' erstellt", db_name)
                await asyncio.sleep(1.0)  # PostgreSQL braucht einen Moment nach CREATE DATABASE
                try:
                    init_conn = await provisioning.connect(**mandant_config.to_dict(), timeout=10)
                    try:
                        await init_conn.install_uuid_ossp()
                        await init_conn.write_init_marker(provisioning.INIT_MARKER_SETUP)
                    finally:
                        await init_conn.close()
                except Exception as init_error:  # nicht kritisch: die Wartung beim ersten Login holt es nach
                    logger.warning("Init-Tabelle in '%s' konnte nicht angelegt werden: %s", db_name, init_error)
            else:
                logger.info("Datenbank '%s' existiert bereits", db_name)
        finally:
            await conn.close()
    except provisioning.ProvisioningConnectionError as exc:
        raise ValueError(f"Kann nicht mit PostgreSQL verbinden: {exc}")
    except provisioning.ProvisioningDatabaseError as exc:
        raise ValueError(f"Datenbankfehler: {exc}")

    now_pdvm = PdvmDateTime().now().pdvm_datetime_str
    central = PdvmCentralDatabase(MANDANT_TABLE, str(mandant_id))
    central.set_data(daten, str(mandant_id))
    central.set_value("ROOT", "DB_CREATED_AT", now_pdvm)
    await central.save_all_values()
    logger.info("Mandant '%s': Datenbank '%s' eingerichtet", record.get("name"), db_name)
    return {"mandant_id": str(mandant_id), "database": db_name, "db_created_at": now_pdvm, "name": record.get("name")}

"""
Mandant loeschen (Aktion `mandant.delete`, Regel 2.17).

Ablauf (jeder Schritt bricht bei Fehler ab, davor Geschriebenes bleibt bestehen und die Aktion ist wiederholbar):
  1. Sicherung der Mandanten-Datenbank (`pg_dump`, Custom-Format, mit `pg_restore --list` geprueft) und des Mandantensatzes (JSON)
  2. Datenbank loeschen (Sessions und Pools des Mandanten schliessen, Verbindungen beenden, `DROP DATABASE`)
  3. Mandanten-UID aus `MANDANTEN.LIST`/`DEFAULT` aller Benutzer entfernen
  4. Mandantensatz als geloescht markieren: `gilt_bis` = `created_at` (stichtagsunabhaengig unerreichbar, siehe `mandant_tombstone`)

Der Satz in `asy_mandanten` bleibt erhalten. Ohne erfolgreiche Sicherung wird nichts geloescht. Fehlt die Datenbank schon (Wiederholung
nach einem Abbruch, oder nie eingerichtet), entfallen Schritt 1 und 2. Aufgerufen wird die Funktion ausschliesslich ueber das
Aktionsregister (`frame_action_service`, Rollen `superadmin` und `delmand`). Fachliche Fehler: `ValueError` (Meldung fuer den Benutzer).
"""
from __future__ import annotations

import asyncio
import copy
import glob
import json
import logging
import os
import re
import shutil
import subprocess
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from app.core import mandant_db_provisioning_service as provisioning
from app.core.config import settings
from app.core.connection_manager import ConnectionConfig, ConnectionManager
from app.core.mandant_tombstone import is_deleted_mandant_row
from app.core.pdvm_datenbank import PdvmDatabase
from app.core.pdvm_datetime import datetime_to_pdvm
from app.core.pool_registry import PoolRegistry

logger = logging.getLogger(__name__)

MANDANT_TABLE = "asy_mandanten"
USER_TABLE = "asy_benutzer"
RESERVED_MANDANT_UIDS = {
    "66666666-6666-6666-6666-666666666666",
    "55555555-5555-5555-5555-555555555555",
    "00000000-0000-0000-0000-000000000000",
}
# Verwaltungs- und Systemdatenbanken, die nie als Mandanten-Datenbank geloescht werden
PROTECTED_DATABASES = {"postgres", "template0", "template1", "auth", "pdvm_system"}
BACKUP_TIMEOUT_SECONDS = 600


def _backup_dir() -> Path:
    configured = str(settings.MANDANT_DELETE_BACKUP_DIR or "").strip()
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parents[3] / "database" / "backups" / "mandant_geloescht"


def _find_pg_tool(name: str) -> str:
    """pg_dump/pg_restore: `PG_BIN_DIR`, dann PATH, dann Standardpfade der Installation (jeweils neueste Version)."""
    exe = f"{name}.exe" if os.name == "nt" else name
    configured = str(settings.PG_BIN_DIR or "").strip()
    if configured and (Path(configured) / exe).is_file():
        return str(Path(configured) / exe)
    found = shutil.which(name)
    if found:
        return found
    patterns = (
        [rf"C:\Program Files\PostgreSQL\*\bin\{exe}"] if os.name == "nt" else [f"/usr/lib/postgresql/*/bin/{exe}", f"/usr/pgsql-*/bin/{exe}"]
    )
    candidates = [p for pattern in patterns for p in glob.glob(pattern)]
    if candidates:
        return sorted(candidates, key=lambda p: [int(x) for x in re.findall(r"\d+", p)])[-1]
    raise ValueError(f"{name} nicht gefunden: Ohne PostgreSQL-Client-Werkzeuge ist keine Sicherung möglich (Einstellung PG_BIN_DIR).")


def _safe_filename_part(value: Any) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "_", str(value or "")).strip("_")[:60] or "mandant"


def _run_tool(cmd: list, config: ConnectionConfig) -> None:
    """Fuehrt ein PostgreSQL-Werkzeug aus; das Passwort geht nur ueber die Umgebung, nie ueber die Kommandozeile."""
    env = {**os.environ, "PGPASSWORD": str(config.password or ""), "PGCONNECT_TIMEOUT": "15"}
    if config.ssl:
        env["PGSSLMODE"] = "require"
    done = subprocess.run(
        cmd, env=env, capture_output=True, text=True, encoding="mbcs" if os.name == "nt" else "utf-8", errors="replace",
        timeout=BACKUP_TIMEOUT_SECONDS,
    )
    if done.returncode != 0:
        raise ValueError((done.stderr or done.stdout or f"Exit-Code {done.returncode}").strip()[:500])


def _dump_database(config: ConnectionConfig, target: Path) -> None:
    _run_tool(
        [_find_pg_tool("pg_dump"), "-h", str(config.host), "-p", str(config.port), "-U", str(config.user),
         "-d", str(config.database), "-F", "c", "-f", str(target)],
        config,
    )
    if not target.is_file() or target.stat().st_size == 0:
        raise ValueError("Die Sicherungsdatei ist leer")
    _run_tool([_find_pg_tool("pg_restore"), "--list", str(target)], config)


async def _load(mandant_id: str) -> Optional[Dict[str, Any]]:
    try:
        uid = uuid.UUID(str(mandant_id))
    except (ValueError, TypeError):
        return None
    if str(uid) in RESERVED_MANDANT_UIDS:
        return None
    return await PdvmDatabase(MANDANT_TABLE).get_by_uid(uid)  # geloeschte Mandanten sind nicht erreichbar


def _database_name(daten: Dict[str, Any]) -> str:
    name = str((daten.get("MANDANT") or {}).get("DATABASE") or "").strip()
    return "" if name == "-eingeben-" else name


async def _shared_with_other_mandant(mandant_id: str, db_name: str) -> Optional[str]:
    for row in await PdvmDatabase(MANDANT_TABLE).get_all():
        if str(row.get("uid")).lower() == str(mandant_id).lower() or str(row.get("uid")) in RESERVED_MANDANT_UIDS:
            continue
        if _database_name(row.get("daten") or {}).lower() == db_name.lower():
            return str(row.get("name") or row.get("uid"))
    return None


async def _check_deletable(mandant_id: str, session_mandant_id: Any) -> Dict[str, Any]:
    """Prueft die Voraussetzungen; wirft `ValueError` mit Klartext. Liefert Satz, Datenbankname und Verbindungskonfiguration."""
    record = await _load(mandant_id)
    if not record:
        raise ValueError("Mandant nicht gefunden")
    if str(session_mandant_id or "").strip().lower() == str(record["uid"]).lower():
        raise ValueError("Der Mandant der aktuellen Sitzung kann nicht gelöscht werden. Bitte in einen anderen Mandanten wechseln.")
    daten = record.get("daten") or {}
    db_name = _database_name(daten)
    config: Optional[ConnectionConfig] = None
    if db_name:
        system_config, config = await ConnectionManager.get_mandant_config(str(record["uid"]))
        db_name = config.database
        protected = PROTECTED_DATABASES | {str(system_config.database or "").lower()}
        if db_name.lower() in protected:
            raise ValueError(f"Die Datenbank „{db_name}“ ist eine Systemdatenbank und wird nicht gelöscht.")
        other = await _shared_with_other_mandant(str(record["uid"]), db_name)
        if other:
            raise ValueError(f"Die Datenbank „{db_name}“ wird auch vom Mandanten „{other}“ verwendet und wird nicht gelöscht.")
    return {"record": record, "database": db_name, "config": config}


async def delete_state(mandant_id: str, session_mandant_id: Any) -> Dict[str, Any]:
    """Zustand fuer die Schaltflaeche: `can_delete` und, falls nicht, der Grund (`reason`)."""
    try:
        checked = await _check_deletable(mandant_id, session_mandant_id)
    except ValueError as exc:
        return {"exists": await _load(mandant_id) is not None, "can_delete": False, "reason": str(exc), "database": None}
    return {"exists": True, "can_delete": True, "reason": "", "database": checked["database"] or None}


async def _database_exists(config: ConnectionConfig) -> bool:
    admin = ConnectionConfig(config.host, config.port, config.user, config.password, "postgres", ssl=config.ssl)
    conn = await provisioning.connect(**admin.to_dict())
    try:
        return bool(await conn.lookup_database(config.database))
    finally:
        await conn.close()


async def _drop_database(config: ConnectionConfig, mandant_id: str) -> int:
    from app.core.pdvm_central_systemsteuerung import close_sessions_of_mandant

    sessions = await close_sessions_of_mandant(mandant_id)
    await PoolRegistry.close_for_database(config.database)
    admin = ConnectionConfig(config.host, config.port, config.user, config.password, "postgres", ssl=config.ssl)
    conn = await provisioning.connect(**admin.to_dict())
    try:
        await conn.terminate_connections(config.database)
        await conn.drop_database_if_exists(config.database)
        if await conn.lookup_database(config.database):
            raise ValueError(f"Die Datenbank „{config.database}“ konnte nicht gelöscht werden")
    except provisioning.ProvisioningError as exc:
        raise ValueError(f"Datenbank „{config.database}“ konnte nicht gelöscht werden: {exc}")
    finally:
        await conn.close()
    return sessions


async def _remove_from_users(mandant_id: str, *, actor_uid: Any, actor_ip: Optional[str]) -> int:
    """Entfernt die Mandanten-UID aus `MANDANTEN.LIST` und leert `MANDANTEN.DEFAULT`, wenn sie darauf zeigt; liefert die Anzahl Benutzer."""
    from app.core.central_write_service import update_record_central

    target = str(mandant_id).strip().lower()
    changed = 0
    for user in await PdvmDatabase(USER_TABLE).get_all():
        daten = user.get("daten") if isinstance(user.get("daten"), dict) else {}
        mandanten = daten.get("MANDANTEN") if isinstance(daten.get("MANDANTEN"), dict) else None
        if not mandanten:
            continue
        raw_list = mandanten.get("LIST") if isinstance(mandanten.get("LIST"), list) else []
        kept = [m for m in raw_list if str(m or "").strip().lower() != target]
        default_hit = str(mandanten.get("DEFAULT") or "").strip().lower() == target
        if len(kept) == len(raw_list) and not default_hit:
            continue
        new_daten = copy.deepcopy(daten)
        new_daten["MANDANTEN"]["LIST"] = kept
        if default_hit:
            new_daten["MANDANTEN"]["DEFAULT"] = ""
        await update_record_central(
            table_name=USER_TABLE, uid=user["uid"], daten=new_daten, name=user.get("name"), historisch=user.get("historisch"),
            gcs=None, actor_user_uid=actor_uid, actor_ip=actor_ip,
        )
        changed += 1
    return changed


async def _mark_deleted(record: Dict[str, Any], *, actor_uid: Any, actor_ip: Optional[str]) -> None:
    """`gilt_bis` auf `created_at` setzen (ueber ROOT.SELF_GILT_BIS, Regel 1.23) und das Ergebnis pruefen."""
    from app.core.central_write_service import update_record_central

    created_at = record.get("created_at")
    if not isinstance(created_at, datetime):
        raise ValueError("created_at des Mandantensatzes fehlt")
    daten = copy.deepcopy(record.get("daten") or {})
    daten.setdefault("ROOT", {})["SELF_GILT_BIS"] = f"{datetime_to_pdvm(created_at):.5f}"
    await update_record_central(
        table_name=MANDANT_TABLE, uid=record["uid"], daten=daten, name=record.get("name"), historisch=record.get("historisch"),
        gcs=None, actor_user_uid=actor_uid, actor_ip=actor_ip,
    )
    after = await PdvmDatabase(MANDANT_TABLE).get_by_uid(record["uid"], include_deleted=True)
    if not is_deleted_mandant_row(after):
        raise ValueError("Der Mandantensatz konnte nicht als gelöscht markiert werden")


async def delete_mandant(
    mandant_id: str, *, confirm_name: str, session_mandant_id: Any, actor_uid: Any = None, actor_ip: Optional[str] = None
) -> Dict[str, Any]:
    checked = await _check_deletable(mandant_id, session_mandant_id)
    record, config = checked["record"], checked["config"]
    mandant_uid = str(record["uid"])
    name = str(record.get("name") or "").strip()
    if str(confirm_name or "").strip() != name:
        raise ValueError("Die Bestätigung stimmt nicht mit dem Mandantennamen überein")

    result: Dict[str, Any] = {
        "mandant_id": mandant_uid, "name": name, "database": checked["database"] or None, "backup_file": None,
        "database_dropped": False, "users_updated": 0, "sessions_closed": 0,
    }

    # 1. und 2.: Sicherung, dann Datenbank loeschen (entfaellt, wenn die Datenbank nicht (mehr) existiert)
    if config is not None and await _database_exists(config):
        target_dir = _backup_dir()
        target_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base = f"{_safe_filename_part(name)}_{_safe_filename_part(config.database)}_{stamp}"
        dump_file = target_dir / f"{base}.dump"
        try:
            await asyncio.to_thread(_dump_database, config, dump_file)
        except (ValueError, subprocess.SubprocessError, OSError) as exc:
            dump_file.unlink(missing_ok=True)
            raise ValueError(f"Sicherung fehlgeschlagen, es wurde nichts gelöscht: {exc}")
        (target_dir / f"{base}.mandant.json").write_text(
            json.dumps({"uid": mandant_uid, "name": name, "daten": record.get("daten"), "created_at": record.get("created_at")},
                       ensure_ascii=False, indent=1, default=str),
            encoding="utf-8",
        )
        result["backup_file"] = str(dump_file)
        logger.warning("Mandant %s (%s): Datenbank %s gesichert nach %s", mandant_uid, name, config.database, dump_file)
        try:
            result["sessions_closed"] = await _drop_database(config, mandant_uid)
        except ValueError as exc:
            raise ValueError(f"{exc}. Die Sicherung liegt unter {dump_file}; der Vorgang kann wiederholt werden.")
        result["database_dropped"] = True
        logger.warning("Mandant %s (%s): Datenbank %s gelöscht", mandant_uid, name, config.database)

    # 3. und 4.: Zuordnungen entfernen, Satz als geloescht markieren
    result["users_updated"] = await _remove_from_users(mandant_uid, actor_uid=actor_uid, actor_ip=actor_ip)
    await _mark_deleted(record, actor_uid=actor_uid, actor_ip=actor_ip)
    logger.warning("Mandant %s (%s) gelöscht: %s", mandant_uid, name, {k: v for k, v in result.items() if k != "name"})
    return result

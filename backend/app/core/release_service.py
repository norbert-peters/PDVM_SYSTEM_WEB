"""
Release Service (Phase 1)

Zentrale Business-Logik fuer Release-Paket-Phase 1:
- Standard-Tabellen fuer Release-Tracking anlegen
- Installierte Releases aus Systemdatenbank lesen
- (MVP) Verfuegbarkeitsvergleich gegen uebergebenen Katalog

Architekturregel-konform:
- Kein SQL in Routern
- Service-Layer kapselt Datenbankzugriff
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
import re
import time
import json
from datetime import datetime

import asyncpg
import httpx

from app.core.pdvm_table_schema import PDVM_TABLE_COLUMNS, PDVM_TABLE_INDEXES
from app.core.config import settings
from app.core.pdvm_datetime import now_pdvm_str


RELEASE_TABLES = [
    "sys_release_state",
    "sys_release_log",
    "dev_release",
    "dev_release_item",
    "sys_change_log",
]

POLICY_MODES = {"manual", "auto", "deferred"}
VALID_OPERATIONS = {"upsert", "delete"}
GILT_BIS_MAX = "9999-12-31 23:59:59"


class ReleaseService:
    """Service fuer Release-Paket-MVP (Phase 1)."""

    @staticmethod
    async def ensure_release_tables(system_pool: asyncpg.Pool) -> Dict[str, Any]:
        """
        Legt alle Release-relevanten Tabellen in der Systemdatenbank an (falls fehlend).

        Returns:
            dict mit angelegten Tabellen und Meta-Infos.
        """
        created: List[str] = []

        async with system_pool.acquire() as conn:
            await conn.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')

            for table_name in RELEASE_TABLES:
                exists = await conn.fetchval(
                    """
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables
                        WHERE table_schema = 'public' AND table_name = $1
                    )
                    """,
                    table_name,
                )
                if exists:
                    continue

                columns = ", ".join(
                    [f"{col} {definition}" for col, definition in PDVM_TABLE_COLUMNS.items()]
                )
                await conn.execute(
                    f"""
                    CREATE TABLE {table_name} (
                        {columns}
                    )
                    """
                )

                for idx_col in PDVM_TABLE_INDEXES:
                    if idx_col == "daten":
                        await conn.execute(
                            f"""
                            CREATE INDEX IF NOT EXISTS idx_{table_name}_{idx_col}
                            ON {table_name} USING GIN({idx_col})
                            """
                        )
                    else:
                        await conn.execute(
                            f"""
                            CREATE INDEX IF NOT EXISTS idx_{table_name}_{idx_col}
                            ON {table_name}({idx_col})
                            """
                        )

                created.append(table_name)

        return {
            "success": True,
            "tables_created": created,
            "tables_existing": [t for t in RELEASE_TABLES if t not in created],
        }

    @staticmethod
    async def get_installed_releases(system_pool: asyncpg.Pool) -> List[Dict[str, Any]]:
        """
        Liest installierte Releases aus sys_release_state.

        Erwartete Struktur in daten:
        daten.ROOT.APP_ID, daten.ROOT.VERSION, daten.ROOT.STATUS, daten.ROOT.APPLIED_AT
        """
        async with system_pool.acquire() as conn:
            table_exists = await conn.fetchval(
                """
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_schema = 'public' AND table_name = 'sys_release_state'
                )
                """
            )
            if not table_exists:
                return []

            rows = await conn.fetch(
                """
                SELECT uid, name, daten, modified_at
                FROM sys_release_state
                WHERE COALESCE(historisch, 0) = 0
                ORDER BY modified_at DESC
                """
            )

        result: List[Dict[str, Any]] = []
        for row in rows:
            daten = row["daten"]
            root = (daten or {}).get("ROOT", {}) if isinstance(daten, dict) else {}
            result.append(
                {
                    "uid": str(row["uid"]),
                    "name": row["name"],
                    "release_id": root.get("RELEASE_ID"),
                    "app_id": root.get("APP_ID"),
                    "version": root.get("VERSION"),
                    "status": root.get("STATUS"),
                    "applied_at": root.get("APPLIED_AT"),
                    "modified_at": row["modified_at"].isoformat() if row["modified_at"] else None,
                }
            )

        return result

    @staticmethod
    async def check_updates(
        system_pool: asyncpg.Pool,
        available_releases: Optional[List[Dict[str, Any]]] = None,
        policy_mode: str = "manual",
        check_source: str = "manual_catalog",
    ) -> Dict[str, Any]:
        """
        MVP-Update-Check:
        - Liefert installierte Releases
        - Vergleicht optional gegen uebergebenen Katalog

        Hinweis: GitHub-Release-Integration folgt in Phase 1, Schritt 2.
        """
        installed = await ReleaseService.get_installed_releases(system_pool)
        normalized_policy = (policy_mode or "manual").strip().lower()
        if normalized_policy not in POLICY_MODES:
            normalized_policy = "manual"

        latest_installed_by_app: Dict[str, Dict[str, Any]] = {}
        for item in installed:
            app_id = str(item.get("app_id") or "").strip()
            if not app_id:
                continue
            if app_id not in latest_installed_by_app:
                latest_installed_by_app[app_id] = item

        updates_available: List[Dict[str, Any]] = []
        for available in available_releases or []:
            app_id = str(available.get("app_id") or "").strip()
            available_version = str(available.get("version") or "").strip()
            if not app_id or not available_version:
                continue

            installed_item = latest_installed_by_app.get(app_id)
            installed_version = str((installed_item or {}).get("version") or "").strip()
            is_newer = False
            if not installed_version:
                is_newer = True
            else:
                is_newer = ReleaseService._compare_versions(available_version, installed_version) > 0

            if is_newer:
                updates_available.append(
                    {
                        "app_id": app_id,
                        "installed_version": installed_version or None,
                        "available_version": available_version,
                        "release_id": available.get("release_id"),
                    }
                )

        action = "show_dialog"
        if normalized_policy == "auto" and updates_available:
            action = "auto_apply"
        elif normalized_policy == "deferred" and updates_available:
            action = "defer"

        result = {
            "installed": installed,
            "latest_installed_by_app": latest_installed_by_app,
            "updates_available": updates_available,
            "has_updates": len(updates_available) > 0,
            "policy_mode": normalized_policy,
            "recommended_action": action,
        }

        # Logging darf den Check niemals scheitern lassen.
        try:
            await ReleaseService.append_release_log(
                system_pool,
                release_id="CHECK",
                step="check",
                level="info",
                message="Release-Check ausgefuehrt",
                details={
                    "source": check_source,
                    "policy_mode": normalized_policy,
                    "available_count": len(available_releases or []),
                    "updates_count": len(updates_available),
                    "recommended_action": action,
                },
            )
        except Exception:
            pass

        return result

    @staticmethod
    def _version_parts(version: str) -> List[Any]:
        """Zerlegt semver-aehnliche Version in vergleichbare Teile."""
        clean = str(version or "").strip().lower()
        if not clean:
            return []
        tokens = re.findall(r"\d+|[a-z]+", clean)
        parts: List[Any] = []
        for token in tokens:
            if token.isdigit():
                parts.append(int(token))
            else:
                parts.append(token)
        return parts

    @staticmethod
    def _compare_versions(a: str, b: str) -> int:
        """
        Vergleicht zwei semver-aehnliche Strings.

        Returns:
            >0 wenn a > b, 0 wenn gleich, <0 wenn a < b
        """
        pa = ReleaseService._version_parts(a)
        pb = ReleaseService._version_parts(b)
        max_len = max(len(pa), len(pb))

        for i in range(max_len):
            va = pa[i] if i < len(pa) else 0
            vb = pb[i] if i < len(pb) else 0

            if isinstance(va, int) and isinstance(vb, int):
                if va != vb:
                    return 1 if va > vb else -1
                continue

            sa = str(va)
            sb = str(vb)
            if sa != sb:
                return 1 if sa > sb else -1

        return 0

    @staticmethod
    def _parse_jsonl(content: str, label: str) -> List[Dict[str, Any]]:
        """Parst JSONL-Text in eine Liste von Objekten."""
        lines = [line.strip() for line in str(content or "").splitlines() if line.strip()]
        result: List[Dict[str, Any]] = []
        for idx, line in enumerate(lines):
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{label}: Zeile {idx + 1} ist kein gueltiges JSON ({exc})")
            if not isinstance(obj, dict):
                raise ValueError(f"{label}: Zeile {idx + 1} muss ein JSON-Objekt sein")
            result.append(obj)
        return result

    @staticmethod
    def build_package_from_jsonl_payload(
        manifest: Dict[str, Any],
        items_jsonl: str,
        data_jsonl_by_table: Dict[str, str],
    ) -> Dict[str, Any]:
        """
        Baut ein internes package-Dict aus manifest + items.jsonl + data/<table>.jsonl.
        """
        if not isinstance(manifest, dict):
            raise ValueError("manifest muss ein Objekt sein")

        release_id = str(manifest.get("release_id") or manifest.get("RELEASE_ID") or "").strip()
        app_id = str(manifest.get("app_id") or manifest.get("APP_ID") or "").strip().upper()
        version = str(manifest.get("version") or manifest.get("VERSION") or "").strip()

        if not release_id:
            raise ValueError("manifest.release_id fehlt")
        if not app_id:
            raise ValueError("manifest.app_id fehlt")
        if not version:
            raise ValueError("manifest.version fehlt")

        items_raw = ReleaseService._parse_jsonl(items_jsonl, "items.jsonl")

        table_data_by_uid: Dict[str, Dict[str, Dict[str, Any]]] = {}
        for table_name, data_jsonl in (data_jsonl_by_table or {}).items():
            table_norm = str(table_name or "").strip().lower()
            rows = ReleaseService._parse_jsonl(data_jsonl, f"data/{table_norm}.jsonl")
            uid_map: Dict[str, Dict[str, Any]] = {}
            for row in rows:
                uid = str(row.get("uid") or row.get("UID") or "").strip()
                if uid:
                    uid_map[uid] = row
            table_data_by_uid[table_norm] = uid_map

        items: List[Dict[str, Any]] = []
        for idx, item in enumerate(items_raw):
            table_name = str(item.get("table_name") or item.get("TABLE_NAME") or "").strip().lower()
            operation = str(item.get("operation") or item.get("OPERATION") or "upsert").strip().lower()
            record_uid = str(item.get("record_uid") or item.get("RECORD_UID") or "").strip()
            order_no = int(item.get("order_no") or item.get("ORDER_NO") or idx)

            mapped_item: Dict[str, Any] = {
                "table_name": table_name,
                "operation": operation,
                "record_uid": record_uid or None,
                "order_no": order_no,
            }

            if operation == "upsert":
                direct_data = item.get("data") if isinstance(item.get("data"), dict) else None
                data_from_table = (table_data_by_uid.get(table_name) or {}).get(record_uid)
                payload_data = direct_data or data_from_table
                if payload_data:
                    mapped_item["data"] = payload_data

            if item.get("gilt_bis") is not None:
                mapped_item["gilt_bis"] = item.get("gilt_bis")

            items.append(mapped_item)

        return {
            "release_id": release_id,
            "app_id": app_id,
            "version": version,
            "package_hash": manifest.get("package_hash") or manifest.get("PACKAGE_HASH"),
            "source_commit": manifest.get("source_commit") or manifest.get("SOURCE_COMMIT"),
            "items": items,
        }

    @staticmethod
    def _is_valid_sys_table_name(table_name: str) -> bool:
        return bool(re.match(r"^sys_[a-z0-9_]+$", (table_name or "").strip().lower()))

    @staticmethod
    async def _table_exists(conn: asyncpg.Connection, table_name: str) -> bool:
        return bool(
            await conn.fetchval(
                """
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_schema = 'public' AND table_name = $1
                )
                """,
                table_name,
            )
        )

    @staticmethod
    async def append_release_log(
        system_pool: asyncpg.Pool,
        release_id: str,
        step: str,
        level: str,
        message: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Schreibt ein Ereignis in sys_release_log (best effort)."""
        async with system_pool.acquire() as conn:
            if not await ReleaseService._table_exists(conn, "sys_release_log"):
                return

            data = {
                "ROOT": {
                    "RELEASE_ID": str(release_id or "UNKNOWN"),
                    "STEP": str(step or "unknown"),
                    "LEVEL": str(level or "info"),
                    "MESSAGE": str(message or ""),
                    "EVENT_AT": now_pdvm_str(),
                    "DETAILS": details or {},
                }
            }

            name = f"{data['ROOT']['RELEASE_ID']}:{data['ROOT']['STEP']}"
            await conn.execute(
                """
                INSERT INTO sys_release_log (daten, name, historisch, created_at, modified_at)
                VALUES ($1::jsonb, $2, 0, NOW(), NOW())
                """,
                data,
                name,
            )

    @staticmethod
    async def append_release_state(
        system_pool: asyncpg.Pool,
        *,
        release_id: str,
        app_id: str,
        version: str,
        status: str,
        applied_by: str,
        package_hash: Optional[str] = None,
        source_commit: Optional[str] = None,
        duration_ms: Optional[int] = None,
        error_summary: Optional[str] = None,
        target_system_db: str = "pdvm_system",
    ) -> None:
        """Schreibt Status-Record in sys_release_state (append-only)."""
        async with system_pool.acquire() as conn:
            if not await ReleaseService._table_exists(conn, "sys_release_state"):
                return

            data = {
                "ROOT": {
                    "RELEASE_ID": release_id,
                    "APP_ID": app_id,
                    "VERSION": version,
                    "PACKAGE_HASH": package_hash,
                    "SOURCE_COMMIT": source_commit,
                    "APPLIED_AT": now_pdvm_str(),
                    "APPLIED_BY": applied_by,
                    "STATUS": status,
                    "DURATION_MS": duration_ms,
                    "ERROR_SUMMARY": error_summary,
                    "TARGET_SYSTEM_DB": target_system_db,
                }
            }

            await conn.execute(
                """
                INSERT INTO sys_release_state (daten, name, historisch, created_at, modified_at)
                VALUES ($1::jsonb, $2, 0, NOW(), NOW())
                """,
                data,
                f"{app_id}:{version}",
            )

    @staticmethod
    async def validate_release_package(
        system_pool: asyncpg.Pool,
        package: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Preflight-Validierung fuer manuelle Apply-Aufrufe.
        """
        items = package.get("items") or []
        if not isinstance(items, list) or not items:
            raise ValueError("Package muss eine nicht-leere items-Liste enthalten")

        app_id = str(package.get("app_id") or "").strip().upper()
        version = str(package.get("version") or "").strip()
        release_id = str(package.get("release_id") or "").strip()

        if not app_id:
            raise ValueError("app_id fehlt")
        if not version:
            raise ValueError("version fehlt")
        if not release_id:
            raise ValueError("release_id fehlt")

        errors: List[str] = []
        validated_items: List[Dict[str, Any]] = []

        async with system_pool.acquire() as conn:
            for index, raw in enumerate(items):
                if not isinstance(raw, dict):
                    errors.append(f"items[{index}] ist kein Objekt")
                    continue

                table_name = str(raw.get("table_name") or "").strip().lower()
                operation = str(raw.get("operation") or "upsert").strip().lower()
                order_no = int(raw.get("order_no") or 0)
                record_uid = str(raw.get("record_uid") or "").strip() or None
                data = raw.get("data") if isinstance(raw.get("data"), dict) else None

                if not ReleaseService._is_valid_sys_table_name(table_name):
                    errors.append(f"items[{index}].table_name ungueltig: {table_name}")
                    continue
                if operation not in VALID_OPERATIONS:
                    errors.append(f"items[{index}].operation ungueltig: {operation}")
                    continue
                if not await ReleaseService._table_exists(conn, table_name):
                    errors.append(f"items[{index}] Zieltabelle existiert nicht: {table_name}")
                    continue

                if operation == "upsert":
                    candidate_uid = record_uid or str((data or {}).get("uid") or "").strip()
                    if not candidate_uid:
                        errors.append(f"items[{index}] upsert benoetigt record_uid oder data.uid")
                        continue
                    if not data:
                        errors.append(f"items[{index}] upsert benoetigt data")
                        continue
                    record_uid = candidate_uid
                elif operation == "delete" and not record_uid:
                    errors.append(f"items[{index}] delete benoetigt record_uid")
                    continue

                validated_items.append(
                    {
                        "table_name": table_name,
                        "operation": operation,
                        "order_no": order_no,
                        "record_uid": record_uid,
                        "data": data,
                        "gilt_bis": raw.get("gilt_bis"),
                    }
                )

        if errors:
            raise ValueError("; ".join(errors))

        return {
            "release_id": release_id,
            "app_id": app_id,
            "version": version,
            "package_hash": package.get("package_hash"),
            "source_commit": package.get("source_commit"),
            "items": sorted(validated_items, key=lambda x: x["order_no"]),
            "items_count": len(validated_items),
        }

    @staticmethod
    async def apply_release_package(
        system_pool: asyncpg.Pool,
        package: Dict[str, Any],
        applied_by: str,
    ) -> Dict[str, Any]:
        """
        Phase 1 / Schritt 3:
        Validiert und wendet ein Release-Paket transaktional auf sys_* Tabellen an.
        """
        await ReleaseService.ensure_release_tables(system_pool)
        validated = await ReleaseService.validate_release_package(system_pool, package)

        release_id = str(validated["release_id"])
        app_id = str(validated["app_id"])
        version = str(validated["version"])
        package_hash = validated.get("package_hash")
        source_commit = validated.get("source_commit")
        items = validated["items"]

        await ReleaseService.append_release_log(
            system_pool,
            release_id=release_id,
            step="preflight",
            level="info",
            message="Preflight erfolgreich",
            details={"items_count": len(items)},
        )

        started = time.perf_counter()
        applied_count = 0

        try:
            async with system_pool.acquire() as conn:
                async with conn.transaction():
                    for item in items:
                        table_name = item["table_name"]
                        operation = item["operation"]
                        record_uid = item["record_uid"]

                        if operation == "upsert":
                            row_data = item.get("data") or {}
                            daten = row_data.get("daten") if isinstance(row_data.get("daten"), dict) else row_data
                            name = str(row_data.get("name") or "")
                            historisch = int(row_data.get("historisch") or 0)
                            source_hash = row_data.get("source_hash") or package_hash
                            sec_id = row_data.get("sec_id")
                            gilt_bis = row_data.get("gilt_bis") or GILT_BIS_MAX

                            await conn.execute(
                                f"""
                                INSERT INTO {table_name}
                                (uid, daten, name, historisch, source_hash, sec_id, gilt_bis, created_at, modified_at)
                                VALUES ($1::uuid, $2::jsonb, $3, $4, $5, $6::uuid, $7::timestamp, NOW(), NOW())
                                ON CONFLICT (uid)
                                DO UPDATE SET
                                    daten = EXCLUDED.daten,
                                    name = EXCLUDED.name,
                                    historisch = EXCLUDED.historisch,
                                    source_hash = EXCLUDED.source_hash,
                                    sec_id = EXCLUDED.sec_id,
                                    gilt_bis = EXCLUDED.gilt_bis,
                                    modified_at = NOW()
                                """,
                                record_uid,
                                daten,
                                name,
                                historisch,
                                source_hash,
                                sec_id,
                                gilt_bis,
                            )
                        else:
                            gilt_bis = item.get("gilt_bis") or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            await conn.execute(
                                f"""
                                UPDATE {table_name}
                                SET historisch = 1,
                                    gilt_bis = $2::timestamp,
                                    modified_at = NOW()
                                WHERE uid = $1::uuid
                                """,
                                record_uid,
                                gilt_bis,
                            )

                        applied_count += 1

            duration_ms = int((time.perf_counter() - started) * 1000)

            await ReleaseService.append_release_state(
                system_pool,
                release_id=release_id,
                app_id=app_id,
                version=version,
                status="applied",
                applied_by=applied_by,
                package_hash=package_hash,
                source_commit=source_commit,
                duration_ms=duration_ms,
            )
            await ReleaseService.append_release_log(
                system_pool,
                release_id=release_id,
                step="commit",
                level="info",
                message="Release erfolgreich angewendet",
                details={"applied_items": applied_count, "duration_ms": duration_ms},
            )

            return {
                "success": True,
                "release_id": release_id,
                "app_id": app_id,
                "version": version,
                "applied_items": applied_count,
                "duration_ms": duration_ms,
                "status": "applied",
            }
        except Exception as exc:
            duration_ms = int((time.perf_counter() - started) * 1000)
            error_summary = str(exc)

            await ReleaseService.append_release_state(
                system_pool,
                release_id=release_id,
                app_id=app_id,
                version=version,
                status="failed",
                applied_by=applied_by,
                package_hash=package_hash,
                source_commit=source_commit,
                duration_ms=duration_ms,
                error_summary=error_summary,
            )
            await ReleaseService.append_release_log(
                system_pool,
                release_id=release_id,
                step="rollback",
                level="error",
                message="Release apply fehlgeschlagen, Transaktion wurde rollbacked",
                details={"error": error_summary, "duration_ms": duration_ms},
            )
            raise

    @staticmethod
    def _parse_release_name(name: str) -> Dict[str, Optional[str]]:
        """
        Erwartetes GitHub Release Name Pattern:
        APP_ID@VERSION  (z. B. SYSTEM@1.2.0)
        """
        value = (name or "").strip()
        if not value or "@" not in value:
            return {"app_id": None, "version": None}

        app_id, version = value.split("@", 1)
        app_id = app_id.strip().upper()
        version = version.strip()

        if not app_id or not version:
            return {"app_id": None, "version": None}

        # Sehr einfache Version-Validierung fuer MVP
        if not re.match(r"^[A-Za-z0-9._-]+$", version):
            return {"app_id": None, "version": None}

        return {"app_id": app_id, "version": version}

    @staticmethod
    async def fetch_available_releases_from_github(
        repo: Optional[str] = None,
        token: Optional[str] = None,
        timeout_seconds: float = 10.0,
    ) -> List[Dict[str, Any]]:
        """
        Holt verfuegbare Releases aus GitHub API.

        Repo-Format: owner/name
        Release Name Pattern (MVP): APP_ID@VERSION
        """
        target_repo = (repo or settings.GITHUB_RELEASE_REPO or "").strip()
        if not target_repo:
            return []

        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "pdvm-release-check/1.0",
        }
        auth_token = (token or settings.GITHUB_RELEASE_TOKEN or "").strip()
        if auth_token:
            headers["Authorization"] = f"Bearer {auth_token}"

        url = f"https://api.github.com/repos/{target_repo}/releases"

        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            payload = response.json()

        available: List[Dict[str, Any]] = []
        for item in payload if isinstance(payload, list) else []:
            release_name = str(item.get("name") or "").strip()
            parsed = ReleaseService._parse_release_name(release_name)
            app_id = parsed.get("app_id")
            version = parsed.get("version")
            if not app_id or not version:
                continue

            available.append(
                {
                    "app_id": app_id,
                    "version": version,
                    "release_id": item.get("id"),
                    "source": "github",
                    "repo": target_repo,
                    "tag_name": item.get("tag_name"),
                    "published_at": item.get("published_at"),
                    "html_url": item.get("html_url"),
                }
            )

        return available

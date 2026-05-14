"""
Release API (Phase 1)

Stellt schlanke Endpunkte fuer die erste Implementierungsphase bereit:
- Bootstrap der Release-Tabellen in pdvm_system
- Update-Check auf Basis installierter Releases
"""
from typing import Any, Dict, List, Optional
import json
import os

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from pydantic import BaseModel, Field

from app.core.security import (
    get_current_user,
    has_admin_rights,
    require_admin_or_develop_user,
)
from app.core.pdvm_central_systemsteuerung import get_gcs_session
from app.core.release_service import ReleaseService


router = APIRouter()


class AvailableReleaseItem(BaseModel):
    app_id: str = Field(..., description="Applikations-ID")
    version: str = Field(..., description="Verfuegbare Version")
    release_id: Optional[str] = Field(default=None, description="Release Paket-ID")


class ReleaseCheckRequest(BaseModel):
    available_releases: Optional[List[AvailableReleaseItem]] = Field(
        default=None,
        description="Optionaler Katalog verfuegbarer Releases",
    )
    policy_mode: str = Field(
        default="manual",
        description="Policy-Modus: manual | auto | deferred",
    )


class GitHubCatalogRequest(BaseModel):
    repo: Optional[str] = Field(
        default=None,
        description="GitHub Repo im Format owner/name. Leer = Config-Default.",
    )


class ReleaseApplyItem(BaseModel):
    table_name: str = Field(..., description="Zieltabelle (sys_*)")
    operation: str = Field(default="upsert", description="upsert | delete")
    order_no: int = Field(default=0, description="Deterministische Reihenfolge")
    record_uid: Optional[str] = Field(default=None, description="Datensatz UID")
    data: Optional[Dict[str, Any]] = Field(default=None, description="Datensatzdaten fuer upsert")
    gilt_bis: Optional[str] = Field(default=None, description="Optionales Enddatum fuer delete")


class ReleaseApplyRequest(BaseModel):
    release_id: str
    app_id: str
    version: str
    package_hash: Optional[str] = None
    source_commit: Optional[str] = None
    dry_run: bool = Field(default=False, description="Nur Validierung ohne Apply")
    items: List[ReleaseApplyItem]


class ReleaseImportJsonlRequest(BaseModel):
    manifest: Dict[str, Any] = Field(..., description="manifest.json als Objekt")
    items_jsonl: str = Field(..., description="Inhalt von items.jsonl")
    data_jsonl_by_table: Dict[str, str] = Field(
        default_factory=dict,
        description="Map: table_name -> Inhalt von data/<table_name>.jsonl",
    )
    dry_run: bool = Field(default=False, description="Nur Validierung ohne Apply")


async def get_gcs_instance(current_user: dict = Depends(get_current_user)):
    """Holt PdvmCentralSystemsteuerung aus der Session des JWT-Tokens."""
    token = current_user.get("token")
    if not token:
        raise HTTPException(status_code=401, detail="Kein Session-Token gefunden")

    gcs = get_gcs_session(token)
    if not gcs:
        raise HTTPException(
            status_code=404,
            detail="Keine GCS-Session gefunden. Bitte Mandant auswaehlen.",
        )

    return gcs


async def require_release_operator(current_user: dict = Depends(get_current_user)):
    """
    Rollen-Check fuer Release-Workflow: Admin oder Develop.
    """
    return await require_admin_or_develop_user(current_user)


def _parse_form_bool(value: str, default: bool = False) -> bool:
    raw = str(value or "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "y", "on"}


def _table_name_from_data_filename(filename: str) -> str:
    """
    Erwartete Dateinamen fuer data-Dateien, z. B.:
    - sys_systemdaten.jsonl
    - data_sys_systemdaten.jsonl
    - data-sys_systemdaten.jsonl
    """
    name = os.path.basename(str(filename or "")).strip().lower()
    if name.endswith(".jsonl"):
        name = name[:-6]

    for prefix in ("data_", "data-"):
        if name.startswith(prefix):
            name = name[len(prefix):]

    return name


@router.post("/bootstrap")
async def bootstrap_release_tables(gcs=Depends(get_gcs_instance)):
    """
    Phase 1 / Schritt 1:
    Legt Release-Tabellen in der Systemdatenbank an (idempotent).
    """
    if not getattr(gcs, "_pool_system", None):
        raise HTTPException(status_code=500, detail="Systemdatenbank-Pool nicht verfuegbar")

    result = await ReleaseService.ensure_release_tables(gcs._pool_system)
    return {
        "success": True,
        "message": "Release-Tabellen geprueft/angelegt",
        **result,
    }


@router.post("/check")
async def check_release_updates(
    payload: ReleaseCheckRequest,
    gcs=Depends(get_gcs_instance),
):
    """
    Phase 1 / Schritt 1:
    Liest installierte Releases und vergleicht optional mit einem uebergebenen Katalog.
    """
    if not getattr(gcs, "_pool_system", None):
        raise HTTPException(status_code=500, detail="Systemdatenbank-Pool nicht verfuegbar")

    available: Optional[List[Dict[str, Any]]] = None
    if payload.available_releases:
        available = [item.model_dump() for item in payload.available_releases]

    result = await ReleaseService.check_updates(
        gcs._pool_system,
        available,
        payload.policy_mode,
        "manual_catalog",
    )
    return {
        "success": True,
        "message": "Release-Check ausgefuehrt",
        **result,
    }


@router.post("/catalog/github")
async def fetch_github_release_catalog(
    payload: GitHubCatalogRequest,
    gcs=Depends(get_gcs_instance),
):
    """
    Phase 1 / Schritt 2:
    Holt den verfuegbaren Release-Katalog aus GitHub.

    Hinweis: gcs-Dependency stellt sicher, dass nur authentifizierte Sessions zugreifen.
    """
    try:
        available = await ReleaseService.fetch_available_releases_from_github(payload.repo)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"GitHub-Katalog konnte nicht geladen werden: {exc}")

    return {
        "success": True,
        "message": "GitHub-Release-Katalog geladen",
        "repo": payload.repo,
        "available_releases": available,
        "count": len(available),
    }


@router.post("/check/github")
async def check_release_updates_from_github(
    payload: ReleaseCheckRequest,
    gcs=Depends(get_gcs_instance),
):
    """
    Phase 1 / Schritt 2:
    Liest verfuegbare Releases aus GitHub und vergleicht sie mit installierten Releases.
    """
    if not getattr(gcs, "_pool_system", None):
        raise HTTPException(status_code=500, detail="Systemdatenbank-Pool nicht verfuegbar")

    try:
        available = await ReleaseService.fetch_available_releases_from_github()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"GitHub-Katalog konnte nicht geladen werden: {exc}")

    result = await ReleaseService.check_updates(
        gcs._pool_system,
        available,
        payload.policy_mode,
        "github_catalog",
    )
    return {
        "success": True,
        "message": "Release-Check gegen GitHub-Katalog ausgefuehrt",
        "catalog_count": len(available),
        **result,
    }


@router.post("/admin/apply")
async def apply_release_package_manually(
    payload: ReleaseApplyRequest,
    gcs=Depends(get_gcs_instance),
    operator_user: dict = Depends(require_release_operator),
):
    """
    Phase 1 / Schritt 3:
    Kontrollierter Admin-Endpunkt fuer Validate/Apply eines Release-Pakets.
    """
    if not getattr(gcs, "_pool_system", None):
        raise HTTPException(status_code=500, detail="Systemdatenbank-Pool nicht verfuegbar")

    package_dict = {
        "release_id": payload.release_id,
        "app_id": payload.app_id,
        "version": payload.version,
        "package_hash": payload.package_hash,
        "source_commit": payload.source_commit,
        "items": [item.model_dump() for item in payload.items],
    }

    try:
        if payload.dry_run:
            validated = await ReleaseService.validate_release_package(gcs._pool_system, package_dict)
            return {
                "success": True,
                "message": "Release-Paket validiert (dry_run)",
                "validation": validated,
            }

        if not has_admin_rights(operator_user):
            raise HTTPException(status_code=403, detail="Apply erfordert Admin-Recht")

        applied_by = str(operator_user.get("email") or operator_user.get("name") or "system")
        result = await ReleaseService.apply_release_package(
            gcs._pool_system,
            package_dict,
            applied_by=applied_by,
        )
        return {
            "success": True,
            "message": "Release-Paket angewendet",
            **result,
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Release-Apply fehlgeschlagen: {exc}")


@router.post("/admin/import-jsonl")
async def import_release_package_from_jsonl(
    payload: ReleaseImportJsonlRequest,
    gcs=Depends(get_gcs_instance),
    operator_user: dict = Depends(require_release_operator),
):
    """
    Phase 1 / Schritt 4:
    Importiert Release-Paket aus manifest/items/data JSONL-Inhalten und fuehrt dry_run oder Apply aus.
    """
    if not getattr(gcs, "_pool_system", None):
        raise HTTPException(status_code=500, detail="Systemdatenbank-Pool nicht verfuegbar")

    try:
        package_dict = ReleaseService.build_package_from_jsonl_payload(
            manifest=payload.manifest,
            items_jsonl=payload.items_jsonl,
            data_jsonl_by_table=payload.data_jsonl_by_table,
        )

        if payload.dry_run:
            validated = await ReleaseService.validate_release_package(gcs._pool_system, package_dict)
            return {
                "success": True,
                "message": "JSONL-Release-Paket validiert (dry_run)",
                "package": {
                    "release_id": package_dict.get("release_id"),
                    "app_id": package_dict.get("app_id"),
                    "version": package_dict.get("version"),
                    "items": len(package_dict.get("items") or []),
                },
                "validation": validated,
            }

        if not has_admin_rights(operator_user):
            raise HTTPException(status_code=403, detail="Apply erfordert Admin-Recht")

        applied_by = str(operator_user.get("email") or operator_user.get("name") or "system")
        result = await ReleaseService.apply_release_package(
            gcs._pool_system,
            package_dict,
            applied_by=applied_by,
        )
        return {
            "success": True,
            "message": "JSONL-Release-Paket importiert und angewendet",
            **result,
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"JSONL-Import fehlgeschlagen: {exc}")


@router.post("/admin/import-files")
async def import_release_package_from_files(
    manifest_file: UploadFile = File(..., description="manifest.json Datei"),
    items_file: UploadFile = File(..., description="items.jsonl Datei"),
    data_files: List[UploadFile] = File(default=[]),
    dry_run: str = Form(default="false"),
    gcs=Depends(get_gcs_instance),
    operator_user: dict = Depends(require_release_operator),
):
    """
    Phase 1 / Schritt 4 Erweiterung:
    Importiert ein Release-Paket ueber echte Multipart-Dateien.
    """
    if not getattr(gcs, "_pool_system", None):
        raise HTTPException(status_code=500, detail="Systemdatenbank-Pool nicht verfuegbar")

    try:
        manifest_text = (await manifest_file.read()).decode("utf-8")
        items_text = (await items_file.read()).decode("utf-8")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Dateien konnten nicht gelesen werden: {exc}")

    try:
        manifest = json.loads(manifest_text)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"manifest.json ist ungueltig: {exc}")

    if not isinstance(manifest, dict):
        raise HTTPException(status_code=400, detail="manifest.json muss ein JSON-Objekt enthalten")

    data_jsonl_by_table: Dict[str, str] = {}
    for df in data_files or []:
        table_name = _table_name_from_data_filename(df.filename)
        if not table_name:
            raise HTTPException(status_code=400, detail=f"Ungueltiger data-Dateiname: {df.filename}")

        try:
            content = (await df.read()).decode("utf-8")
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"data-Datei konnte nicht gelesen werden ({df.filename}): {exc}")

        data_jsonl_by_table[table_name] = content

    try:
        package_dict = ReleaseService.build_package_from_jsonl_payload(
            manifest=manifest,
            items_jsonl=items_text,
            data_jsonl_by_table=data_jsonl_by_table,
        )

        do_dry_run = _parse_form_bool(dry_run, default=False)
        if do_dry_run:
            validated = await ReleaseService.validate_release_package(gcs._pool_system, package_dict)
            return {
                "success": True,
                "message": "Datei-Import validiert (dry_run)",
                "files": {
                    "manifest": manifest_file.filename,
                    "items": items_file.filename,
                    "data_count": len(data_jsonl_by_table),
                },
                "package": {
                    "release_id": package_dict.get("release_id"),
                    "app_id": package_dict.get("app_id"),
                    "version": package_dict.get("version"),
                    "items": len(package_dict.get("items") or []),
                },
                "validation": validated,
            }

        if not has_admin_rights(operator_user):
            raise HTTPException(status_code=403, detail="Apply erfordert Admin-Recht")

        applied_by = str(operator_user.get("email") or operator_user.get("name") or "system")
        result = await ReleaseService.apply_release_package(
            gcs._pool_system,
            package_dict,
            applied_by=applied_by,
        )
        return {
            "success": True,
            "message": "Datei-Import angewendet",
            "files": {
                "manifest": manifest_file.filename,
                "items": items_file.filename,
                "data_count": len(data_jsonl_by_table),
            },
            **result,
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Datei-Import fehlgeschlagen: {exc}")

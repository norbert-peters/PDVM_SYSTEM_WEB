"""Lookups API

Kleine Hilfs-Views (uid, name) für GUID-Auswahl.
ARCHITECTURE_RULES: kein SQL im Router.

Nutzt PdvmDatabase.get_all() und validiert Tabellennamen strikt.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.security import get_current_user
from app.core.pdvm_central_systemsteuerung import get_gcs_session
from app.core.pdvm_datenbank import PdvmDatabase

router = APIRouter()

_TABLE_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


async def get_gcs_instance(current_user: dict = Depends(get_current_user)):
    token = current_user.get("token")
    if not token:
        raise HTTPException(status_code=401, detail="Kein Session-Token gefunden")

    gcs = get_gcs_session(token)
    if not gcs:
        raise HTTPException(status_code=404, detail="Keine GCS-Session gefunden. Bitte Mandant auswählen.")

    return gcs


class LookupRow(BaseModel):
    uid: str
    name: str


class LookupResponse(BaseModel):
    table: str
    rows: List[LookupRow]
    meta: Dict[str, Any] = Field(default_factory=dict)


@router.get("/{table}", response_model=LookupResponse)
async def get_lookup(
    table: str,
    limit: int = 200,
    offset: int = 0,
    q: Optional[str] = None,
    gcs=Depends(get_gcs_instance),
):
    t = str(table or "").strip()
    if not _TABLE_NAME_RE.match(t):
        raise HTTPException(status_code=400, detail="Ungültige Tabelle")

    if limit < 1 or limit > 2000:
        raise HTTPException(status_code=400, detail="limit muss zwischen 1 und 2000 liegen")
    if offset < 0:
        raise HTTPException(status_code=400, detail="offset muss >= 0 sein")

    where = ""
    params: tuple = ()
    if q and str(q).strip():
        # Simple case-insensitive name filter.
        where = "name ILIKE $1"
        params = (f"%{str(q).strip()}%",)

    db = PdvmDatabase(t, system_pool=gcs._system_pool, mandant_pool=gcs._mandant_pool)
    raw = await db.get_all(where=where, params=params, order_by="name ASC", limit=limit, offset=offset)

    rows = [{"uid": str(r.get("uid")), "name": r.get("name") or ""} for r in raw]
    return {"table": t, "rows": rows, "meta": {"limit": limit, "offset": offset, "q": q}}

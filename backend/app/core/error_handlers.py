"""Zentrale Fehlerabbildung fuer Datenbankfehler (4xx statt 500)."""
from __future__ import annotations

import logging

import asyncpg
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


async def undefined_table_handler(request: Request, exc: asyncpg.exceptions.UndefinedTableError) -> JSONResponse:
    """Verweist ein Pfad/Menue/Dialog auf eine nicht vorhandene Tabelle, ist das ein Konfigurationsfehler
    der Daten (404), kein Serverfehler."""
    logger.warning("Tabelle nicht vorhanden (%s %s): %s", request.method, request.url.path, exc)
    return JSONResponse(
        status_code=404,
        content={"detail": f"Tabelle nicht vorhanden: {exc}"},
    )


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(asyncpg.exceptions.UndefinedTableError, undefined_table_handler)

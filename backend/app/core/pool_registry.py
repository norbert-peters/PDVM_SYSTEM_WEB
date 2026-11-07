"""Gemeinsam genutzte asyncpg-Pools (Phase 4, Performance).

Auf dem Zielsystem kostet jeder neue Datenbank-Verbindungsaufbau ca. 150 ms. Pools werden deshalb pro
Verbindungs-URL einmal je Prozess angelegt und von allen Sessions/Diensten wiederverwendet, statt je Login
neue Pools zu erzeugen und beim Logout zu schliessen.

- get_pool(dsn): liefert den gemeinsamen Pool (legt ihn beim ersten Aufruf an).
- close_all(): schliesst alle Pools (App-Shutdown).
- PooledConnection: Verbindung aus dem Pool mit `close()`-Semantik (gibt zurueck statt zu schliessen),
  damit bestehender Code mit `conn = await ...; try: ... finally: await conn.close()` unveraendert bleibt.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, Optional

import asyncpg

logger = logging.getLogger(__name__)


class PoolRegistry:
    _pools: Dict[str, asyncpg.Pool] = {}
    _locks: Dict[str, asyncio.Lock] = {}

    @classmethod
    async def get_pool(
        cls,
        key: str,
        *,
        dsn: Optional[str] = None,
        min_size: int = 1,
        max_size: int = 10,
        **connect_kwargs: Any,
    ) -> asyncpg.Pool:
        """Gemeinsamer Pool je `key`; verbunden wird ueber `dsn` oder `connect_kwargs` (host, user, ...)."""
        pool = cls._pools.get(key)
        if pool is not None:
            return pool
        lock = cls._locks.setdefault(key, asyncio.Lock())
        async with lock:
            pool = cls._pools.get(key)
            if pool is None:
                if dsn is not None:
                    pool = await asyncpg.create_pool(dsn, min_size=min_size, max_size=max_size, **connect_kwargs)
                else:
                    pool = await asyncpg.create_pool(min_size=min_size, max_size=max_size, **connect_kwargs)
                cls._pools[key] = pool
        return pool

    @classmethod
    def is_shared(cls, pool: Any) -> bool:
        return any(pool is p for p in cls._pools.values())

    @classmethod
    async def close_all(cls) -> None:
        pools = list(cls._pools.values())
        cls._pools.clear()
        cls._locks.clear()
        for pool in pools:
            try:
                await pool.close()
            except Exception as exc:  # Shutdown darf nicht an einem Pool scheitern
                logger.warning("Pool konnte nicht geschlossen werden: %s", exc)


class PooledConnection:
    """Verbindung aus einem Pool; `close()` gibt sie an den Pool zurueck."""

    def __init__(self, pool: asyncpg.Pool, connection: asyncpg.Connection):
        self._pool = pool
        self._connection: Optional[asyncpg.Connection] = connection

    def __getattr__(self, name: str) -> Any:
        if self._connection is None:
            raise RuntimeError("Verbindung wurde bereits zurueckgegeben")
        return getattr(self._connection, name)

    async def close(self) -> None:
        connection, self._connection = self._connection, None
        if connection is not None:
            await self._pool.release(connection)


async def acquire_pooled_connection(key: str, **pool_kwargs: Any) -> PooledConnection:
    pool = await PoolRegistry.get_pool(key, **pool_kwargs)
    return PooledConnection(pool, await pool.acquire())

import asyncio

import asyncpg

from app.core.pool_registry import PoolRegistry, PooledConnection, acquire_pooled_connection


class _FakeConn:
    def __init__(self):
        self.queries = []

    async def fetchval(self, query, *args):
        self.queries.append(query)
        return 1


class _FakePool:
    def __init__(self):
        self.acquired = 0
        self.released = []
        self.closed = False

    async def acquire(self):
        self.acquired += 1
        return _FakeConn()

    async def release(self, conn):
        self.released.append(conn)

    async def close(self):
        self.closed = True


def _patch_create_pool(monkeypatch):
    created = []

    async def _create_pool(*args, **kwargs):
        pool = _FakePool()
        created.append((args, kwargs, pool))
        return pool

    monkeypatch.setattr(asyncpg, "create_pool", _create_pool)
    monkeypatch.setattr(PoolRegistry, "_pools", {})
    monkeypatch.setattr(PoolRegistry, "_locks", {})
    return created


def test_same_key_shares_one_pool_even_when_requested_concurrently(monkeypatch):
    created = _patch_create_pool(monkeypatch)

    async def _run():
        return await asyncio.gather(*[PoolRegistry.get_pool("k", dsn="postgresql://x/y") for _ in range(5)])

    pools = asyncio.run(_run())
    assert len(created) == 1
    assert all(p is pools[0] for p in pools)
    assert PoolRegistry.is_shared(pools[0])


def test_different_keys_get_different_pools(monkeypatch):
    created = _patch_create_pool(monkeypatch)

    async def _run():
        a = await PoolRegistry.get_pool("a", dsn="postgresql://x/a")
        b = await PoolRegistry.get_pool("b", host="h", database="b")
        return a, b

    a, b = asyncio.run(_run())
    assert a is not b and len(created) == 2
    # kwargs-Variante verbindet ohne DSN
    assert created[1][0] == () and created[1][1]["host"] == "h"


def test_pooled_connection_close_releases_instead_of_closing(monkeypatch):
    _patch_create_pool(monkeypatch)

    async def _run():
        conn = await acquire_pooled_connection("k", dsn="postgresql://x/y")
        assert await conn.fetchval("select 1") == 1
        pool = PoolRegistry._pools["k"]
        await conn.close()
        await conn.close()  # doppeltes close() ist harmlos
        return conn, pool

    conn, pool = asyncio.run(_run())
    assert isinstance(conn, PooledConnection)
    assert pool.acquired == 1 and len(pool.released) == 1


def test_close_all_closes_and_clears(monkeypatch):
    _patch_create_pool(monkeypatch)

    async def _run():
        pool = await PoolRegistry.get_pool("k", dsn="postgresql://x/y")
        await PoolRegistry.close_all()
        return pool

    pool = asyncio.run(_run())
    assert pool.closed is True
    assert PoolRegistry._pools == {}

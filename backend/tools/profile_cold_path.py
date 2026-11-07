"""Profiling der Kaltpfade (Login, Mandantenwahl) im selben Prozess.

Zaehlt asyncpg-Verbindungsaufbauten je Aufrufer und misst deren Dauer.
Zugangsdaten per Umgebungsvariablen PDVM_USER / PDVM_PASSWORD.

Aufruf (aus backend/):
    $env:PYTHONUTF8="1"; ..\\.venv\\Scripts\\python.exe tools\\profile_cold_path.py
"""
import os
import sys
import time
import traceback
from collections import defaultdict
from pathlib import Path

import asyncpg

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

stats = defaultdict(lambda: [0, 0.0])


def _caller() -> str:
    for frame in reversed(traceback.extract_stack()[:-2]):
        if "app" + os.sep in frame.filename and "profile_cold_path" not in frame.filename:
            return f"{Path(frame.filename).name}:{frame.name}"
    return "?"


def _wrap(name):
    original = getattr(asyncpg, name)

    async def wrapper(*args, **kwargs):
        t0 = time.perf_counter()
        try:
            return await original(*args, **kwargs)
        finally:
            entry = stats[f"{name} <- {_caller()}"]
            entry[0] += 1
            entry[1] += (time.perf_counter() - t0) * 1000

    setattr(asyncpg, name, wrapper)


def main() -> None:
    _wrap("connect")
    _wrap("create_pool")
    from fastapi.testclient import TestClient
    from app.main import app

    user, pw = os.environ["PDVM_USER"], os.environ["PDVM_PASSWORD"]
    with TestClient(app) as client:
        stats.clear()
        t0 = time.perf_counter()
        r = client.post("/api/auth/login", data={"username": user, "password": pw})
        t_login = (time.perf_counter() - t0) * 1000
        login_stats = dict(stats)
        stats.clear()
        token = r.json()["access_token"]
        mandant = r.json()["mandanten"][0]["id"]
        t0 = time.perf_counter()
        client.post("/api/mandanten/select", json={"mandant_id": mandant},
                    headers={"Authorization": f"Bearer {token}"})
        t_select = (time.perf_counter() - t0) * 1000
        select_stats = dict(stats)

    for title, total, data in (("login", t_login, login_stats), ("mandanten/select", t_select, select_stats)):
        print(f"\n== {title}: {total:.0f} ms gesamt")
        for key, (n, ms) in sorted(data.items(), key=lambda kv: -kv[1][1]):
            print(f"  {n:>3}x {ms:>7.0f} ms  {key}")


if __name__ == "__main__":
    main()

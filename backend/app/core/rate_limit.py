"""
Einfache Begrenzung je Schluessel (z. B. IP) im Speicher: maximal `limit` Ereignisse je `window` Sekunden.

Gedacht fuer oeffentliche Endpunkte (Login-Frames, Anmeldung, Passwort vergessen). Gilt je Prozess; bei mehreren Workern
ist die Grenze entsprechend grosszuegiger. Kein Ersatz fuer eine Begrenzung am Reverse-Proxy.
"""
from __future__ import annotations

import time
from collections import deque
from typing import Deque, Dict


class RateLimiter:
    def __init__(self, limit: int, window_seconds: float, max_keys: int = 10_000):
        self.limit = limit
        self.window = window_seconds
        self.max_keys = max_keys
        self._events: Dict[str, Deque[float]] = {}

    def allow(self, key: str, now: float | None = None) -> bool:
        """Zaehlt das Ereignis und liefert False, wenn die Grenze im Zeitfenster erreicht ist."""
        now = time.monotonic() if now is None else now
        bucket = self._events.setdefault(str(key or "unknown"), deque())
        while bucket and now - bucket[0] > self.window:
            bucket.popleft()
        if len(bucket) >= self.limit:
            return False
        bucket.append(now)
        if len(self._events) > self.max_keys:  # Speicher begrenzen: abgelaufene Schluessel verwerfen
            for k in [k for k, b in self._events.items() if not b or now - b[-1] > self.window]:
                self._events.pop(k, None)
        return True

    def is_blocked(self, key: str, now: float | None = None) -> bool:
        """True, wenn die Grenze im Zeitfenster erreicht ist (ohne ein Ereignis zu zaehlen)."""
        now = time.monotonic() if now is None else now
        bucket = self._events.get(str(key or "unknown"))
        if not bucket:
            return False
        while bucket and now - bucket[0] > self.window:
            bucket.popleft()
        return len(bucket) >= self.limit

    def record(self, key: str, now: float | None = None) -> None:
        """Zaehlt ein Ereignis (z. B. einen Fehlversuch), ohne es abzulehnen."""
        now = time.monotonic() if now is None else now
        self._events.setdefault(str(key or "unknown"), deque()).append(now)

    def reset(self) -> None:
        self._events.clear()

"""In-memory live log buffer for the web log viewer.

A single ``LiveLogBuffer`` is installed as a logging handler on the root
logger. It keeps the most recent records in a ring buffer (so a page can
show backlog immediately) and fans new records out to any connected
Server-Sent Events subscribers (so the page updates live).

Everything is in memory and process-local — this is a lightweight viewer,
not a durable log store.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from queue import Empty, Full, Queue
from typing import Any


class LiveLogBuffer(logging.Handler):
    def __init__(self, capacity: int = 500) -> None:
        super().__init__()
        self._buf: "deque[dict[str, Any]]" = deque(maxlen=capacity)
        self._subscribers: list[Queue] = []
        self._lock = threading.Lock()
        self._seq = 0
        # Only the raw message; the page renders time/level itself. A
        # formatter still lets exception tracebacks come through.
        self.setFormatter(logging.Formatter("%(message)s"))

    # -- logging.Handler ---------------------------------------------------

    def emit(self, record: logging.LogRecord) -> None:
        try:
            message = self.format(record)
        except Exception:  # noqa: BLE001 - never let logging crash a request
            try:
                message = record.getMessage()
            except Exception:  # noqa: BLE001
                return
        entry: dict[str, Any] = {
            "seq": 0,
            "time": record.created,
            "level": record.levelname,
            "logger": record.name,
            "message": message,
        }
        with self._lock:
            self._seq += 1
            entry["seq"] = self._seq
            self._buf.append(entry)
            subscribers = list(self._subscribers)
        for q in subscribers:
            try:
                q.put_nowait(entry)
            except Full:
                # A slow/stuck client: drop rather than block the logger.
                pass

    # -- viewer API --------------------------------------------------------

    def recent(self, limit: int = 200) -> list[dict[str, Any]]:
        with self._lock:
            items = list(self._buf)
        return items[-limit:] if limit else items

    def subscribe(self) -> Queue:
        q: Queue = Queue(maxsize=2000)
        with self._lock:
            self._subscribers.append(q)
        return q

    def unsubscribe(self, q: Queue) -> None:
        with self._lock:
            if q in self._subscribers:
                self._subscribers.remove(q)

    def drain(self, q: Queue) -> list[dict[str, Any]]:
        """Pull everything currently waiting on a subscriber queue."""
        out: list[dict[str, Any]] = []
        while True:
            try:
                out.append(q.get_nowait())
            except Empty:
                break
        return out


# Single process-wide buffer, created lazily by install().
buffer: LiveLogBuffer | None = None


def install(capacity: int = 500, level: int = logging.INFO) -> LiveLogBuffer:
    """Attach the live buffer to the root logger (idempotent)."""
    global buffer
    if buffer is not None:
        return buffer
    buffer = LiveLogBuffer(capacity=capacity)
    buffer.setLevel(level)
    root = logging.getLogger()
    root.addHandler(buffer)
    if root.level > level:
        root.setLevel(level)
    return buffer

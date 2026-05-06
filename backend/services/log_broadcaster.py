"""Log Broadcaster — captures Python logging + stdout and fans out to SSE clients."""

import asyncio
import json
import logging
import sys
from datetime import datetime, timezone
from typing import List


# One asyncio.Queue per connected SSE client
_subscribers: List[asyncio.Queue] = []


async def broadcast(entry: dict) -> None:
    """Send a log entry to all connected clients. Drops slow/dead clients."""
    dead = []
    for q in list(_subscribers):
        try:
            q.put_nowait(json.dumps(entry))
        except asyncio.QueueFull:
            dead.append(q)
    for q in dead:
        try:
            _subscribers.remove(q)
        except ValueError:
            pass


def subscribe() -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue(maxsize=500)
    _subscribers.append(q)
    return q


def unsubscribe(q: asyncio.Queue) -> None:
    try:
        _subscribers.remove(q)
    except ValueError:
        pass


def _schedule_broadcast(entry: dict) -> None:
    """Schedule a broadcast from any thread (sync or async)."""
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(broadcast(entry))
    except RuntimeError:
        # No running loop yet (e.g. during import/startup) — drop silently
        pass


class _BroadcastHandler(logging.Handler):
    """Logging handler that forwards records to all SSE subscribers."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            entry = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "level": record.levelname,
                "logger": record.name,
                "message": self.format(record),
            }
            _schedule_broadcast(entry)
        except Exception:
            pass  # Never let the log handler crash the app


class _TeeStream:
    """Wraps stdout/stderr: writes to original stream AND broadcasts each line."""

    def __init__(self, original, stream_name: str):
        self._original = original
        self._name = stream_name
        self._buf = ""

    def write(self, text: str) -> int:
        self._original.write(text)
        # Buffer until we have a complete line
        self._buf += text
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            stripped = line.rstrip()
            if stripped:
                entry = {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "level": "PRINT",
                    "logger": self._name,
                    "message": stripped,
                }
                _schedule_broadcast(entry)
        return len(text)

    def flush(self) -> None:
        self._original.flush()

    def __getattr__(self, name: str):
        return getattr(self._original, name)


def install() -> None:
    """Install log capture on the root logger and stdout/stderr. Call once at startup."""
    handler = _BroadcastHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    # Attach to root so we catch everything (uvicorn, fastapi, backend.*)
    root = logging.getLogger()
    # Avoid double-installing if reload fires this again
    if not any(isinstance(h, _BroadcastHandler) for h in root.handlers):
        root.addHandler(handler)

    # Tee stdout/stderr (captures print() calls)
    if not isinstance(sys.stdout, _TeeStream):
        sys.stdout = _TeeStream(sys.stdout, "stdout")
    if not isinstance(sys.stderr, _TeeStream):
        sys.stderr = _TeeStream(sys.stderr, "stderr")

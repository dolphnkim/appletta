"""Logs route — SSE endpoint that streams live backend terminal output."""

import asyncio
import json
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from backend.services.log_broadcaster import subscribe, unsubscribe

router = APIRouter(prefix="/api/v1/logs", tags=["logs"])

_DEBUG_LOG = Path.home() / ".appletta" / "logs" / "debug.jsonl"
_HISTORY_LINES = 50


def _load_history() -> list[str]:
    """Return the last N raw SSE data strings from debug.jsonl."""
    if not _DEBUG_LOG.exists():
        return []
    try:
        with open(_DEBUG_LOG, "r", encoding="utf-8") as f:
            raw_lines = f.readlines()
        results = []
        for line in raw_lines[-_HISTORY_LINES:]:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                # Re-shape to match live broadcast format
                shaped = {
                    "timestamp": entry.get("timestamp", ""),
                    "level": "HISTORY",
                    "logger": entry.get("category", "debug"),
                    "message": entry.get("message", line),
                }
                results.append(json.dumps(shaped))
            except json.JSONDecodeError:
                pass
        return results
    except Exception:
        return []


@router.get("/stream")
async def stream_logs():
    """Stream live backend logs as Server-Sent Events."""

    async def event_generator():
        q = subscribe()
        try:
            # Seed with recent history from debug.jsonl
            for entry_json in _load_history():
                yield f"data: {entry_json}\n\n"

            while True:
                try:
                    line = await asyncio.wait_for(q.get(), timeout=15.0)
                    yield f"data: {line}\n\n"
                except asyncio.TimeoutError:
                    # Keepalive ping so the EventSource doesn't time out
                    yield 'data: {"type":"ping"}\n\n'
        finally:
            unsubscribe(q)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )

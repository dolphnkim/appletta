"""Emotion probe API routes.

Endpoints for Kevin's activation-level emotion monitoring.
Separate from the LLM-based affect tracker (routes/affect.py) — this reads
Kevin's residual stream directly, not his output text.

Routes:
  GET  /api/emotion/status          — probe load status + current scores
  GET  /api/emotion/stream          — SSE stream of alert events
  POST /api/emotion/reload          — hot-reload probe from disk
  GET  /api/emotion/scores          — latest emotion scores (polling alternative)
  POST /api/emotion/thresholds      — update alert thresholds at runtime
"""

import json
import time
from typing import Dict, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.services.emotion_probes.monitor import get_monitor

router = APIRouter(prefix="/api/emotion", tags=["emotion-probe"])


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------

@router.get("/status")
async def get_probe_status():
    """Return probe load state and whether live monitoring is active."""
    monitor = get_monitor()
    return {
        "probe_loaded": monitor._probe_loaded,
        "monitoring_active": monitor.is_running,
        "probe_layer": monitor._probe_layer,
        "n_emotions": len(monitor._emotion_vectors) if monitor._emotion_vectors else 0,
        "n_thresholds": len(monitor.thresholds),
    }


# ---------------------------------------------------------------------------
# Scores (polling)
# ---------------------------------------------------------------------------

@router.get("/scores")
async def get_current_scores():
    """Return the latest per-emotion activation scores (last sampled token)."""
    monitor = get_monitor()
    scores = monitor.get_latest_scores()
    if not scores:
        return {"scores": {}, "monitoring_active": monitor.is_running}

    # Sort by score descending
    sorted_scores = dict(sorted(scores.items(), key=lambda kv: kv[1], reverse=True))
    return {
        "scores": sorted_scores,
        "monitoring_active": monitor.is_running,
        "timestamp": time.time(),
    }


# ---------------------------------------------------------------------------
# SSE stream
# ---------------------------------------------------------------------------

@router.get("/stream")
async def stream_emotion_alerts():
    """
    Server-Sent Events stream of emotion alert payloads.

    Connect with EventSource('/api/emotion/stream') in the frontend.
    Events are sent when Kevin's activation scores exceed configured
    thresholds. Keepalives sent every ~15s to keep the connection alive.

    Event format:
        data: {"type": "emotion_alert", "emotion": "distressed", "score": 0.73, ...}
        data: {"type": "keepalive", "timestamp": 1746200000.0}
    """
    monitor = get_monitor()

    async def event_generator():
        async for alert in monitor.stream_alerts():
            payload = json.dumps(alert)
            yield f"data: {payload}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )


# ---------------------------------------------------------------------------
# Reload
# ---------------------------------------------------------------------------

@router.post("/reload")
async def reload_probe():
    """Hot-reload the calibrated probe from disk. Restarts monitoring if active."""
    monitor = get_monitor()
    success = monitor.reload_probe()
    if not success:
        raise HTTPException(
            status_code=404,
            detail="Probe file not found. Run calibrate.py first.",
        )
    return {
        "success": True,
        "probe_layer": monitor._probe_layer,
        "n_emotions": len(monitor._emotion_vectors) if monitor._emotion_vectors else 0,
    }


# ---------------------------------------------------------------------------
# Threshold management
# ---------------------------------------------------------------------------

class ThresholdUpdate(BaseModel):
    thresholds: Dict[str, float]


@router.post("/thresholds")
async def update_thresholds(body: ThresholdUpdate):
    """
    Update alert thresholds at runtime.

    Body: {"thresholds": {"distressed": 0.65, "anxious": 0.70, ...}}
    Only the specified emotions are updated; others are unchanged.
    """
    monitor = get_monitor()
    for emotion, threshold in body.thresholds.items():
        if not 0.0 <= threshold <= 1.0:
            raise HTTPException(
                status_code=422,
                detail=f"Threshold for '{emotion}' must be between 0 and 1.",
            )
        monitor.thresholds[emotion] = threshold

    return {
        "success": True,
        "updated": list(body.thresholds.keys()),
        "all_thresholds": dict(monitor.thresholds),
    }


@router.get("/thresholds")
async def get_thresholds():
    """Return current alert thresholds."""
    monitor = get_monitor()
    return {"thresholds": dict(monitor.thresholds)}

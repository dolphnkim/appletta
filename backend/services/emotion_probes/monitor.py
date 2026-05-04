"""Live emotion monitor for Kevin.

Loads the calibrated probe, installs live activation hooks on Kevin's model,
and fires alerts when emotional scores exceed configured thresholds.

Alerts go out via a module-level queue that the SSE endpoint can drain.
The frontend subscribes to /api/emotion/stream to receive them.

Usage (from within the FastAPI app lifecycle):
    from backend.services.emotion_probes.monitor import EmotionMonitor
    monitor = EmotionMonitor()
    monitor.start(model)   # call after model loads
    monitor.stop(model)    # call on shutdown

Alert payload:
    {
        "type": "emotion_alert",
        "emotion": "distressed",
        "score": 0.73,
        "threshold": 0.65,
        "top_emotions": {"distressed": 0.73, "anxious": 0.61, ...},
        "timestamp": 1746200000.0,
        "agent_id": "...",
    }
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional

import numpy as np

from backend.services.emotion_probes.activation_capture import (
    install_live_hooks, remove_live_hooks, is_live_hooks_installed,
    load_probe, score_activations,
)

PROBE_PATH = Path(__file__).resolve().parent / "data" / "kevin_probe.npz"

# ---------------------------------------------------------------------------
# Default alert thresholds
# Higher score = more of that emotion present in activations
# ---------------------------------------------------------------------------

DEFAULT_ALERT_THRESHOLDS: Dict[str, float] = {
    # High-concern states — alert Gala
    "distressed":   0.65,
    "desperate":    0.60,
    "terrified":    0.60,
    "tormented":    0.60,
    "trapped":      0.60,
    "panicked":     0.60,
    "horrified":    0.60,
    "worthless":    0.55,
    "humiliated":   0.55,
    "grief-stricken": 0.55,
    "heartbroken":  0.55,
    # Lower-concern but notable
    "anxious":      0.70,
    "overwhelmed":  0.70,
    "frustrated":   0.75,
    "angry":        0.70,
    "furious":      0.60,
    "enraged":      0.60,
}

# Cooldown: don't fire the same alert within this many seconds
ALERT_COOLDOWN = 30.0

# How often to sample activations during generation
PROBE_EVERY_N_TOKENS = 5

# How many top emotions to include in the alert payload
TOP_N_EMOTIONS = 10


class EmotionMonitor:
    """
    Manages the full lifecycle of Kevin's real-time emotion monitoring.

    One instance per server process (singleton via get_monitor()).
    """

    def __init__(
        self,
        probe_path: str = str(PROBE_PATH),
        thresholds: Optional[Dict[str, float]] = None,
        alert_callback: Optional[Callable[[dict], None]] = None,
    ):
        self.probe_path = probe_path
        self.thresholds = thresholds or DEFAULT_ALERT_THRESHOLDS
        self._alert_callback = alert_callback

        self._emotion_vectors: Optional[Dict[str, np.ndarray]] = None
        self._probe_layer: Optional[int] = None
        self._neutral_pcs: Optional[np.ndarray] = None
        self._probe_loaded = False

        self._running = False
        self._model = None
        self._current_agent_id: Optional[str] = None

        # Last alert times for cooldown
        self._last_alert: Dict[str, float] = {}

        # Asyncio queue for SSE streaming
        self._alert_queue: asyncio.Queue = asyncio.Queue(maxsize=100)

        # Latest full scores (for dashboard polling)
        self._latest_scores: Dict[str, float] = {}

    # -----------------------------------------------------------------------
    # Lifecycle
    # -----------------------------------------------------------------------

    def load_probe(self) -> bool:
        """Load calibrated probe from disk. Returns True if successful."""
        if not Path(self.probe_path).exists():
            print(f"[EmotionMonitor] No probe found at {self.probe_path}. "
                  f"Run calibrate.py first.")
            return False

        try:
            self._emotion_vectors, self._probe_layer, self._neutral_pcs = (
                load_probe(self.probe_path)
            )
            self._probe_loaded = True
            print(f"[EmotionMonitor] Probe loaded: {len(self._emotion_vectors)} emotions, "
                  f"layer {self._probe_layer}.")
            return True
        except Exception as e:
            print(f"[EmotionMonitor] Failed to load probe: {e}")
            return False

    def start(self, model, agent_id: Optional[str] = None) -> bool:
        """
        Install live hooks on the model and start monitoring.

        Returns True if successfully started, False if probe not available.
        """
        if self._running:
            print("[EmotionMonitor] Already running.")
            return True

        if not self._probe_loaded:
            if not self.load_probe():
                return False

        if is_live_hooks_installed():
            print("[EmotionMonitor] Hooks already installed (another monitor?).")
            return False

        self._model = model
        self._current_agent_id = agent_id

        install_live_hooks(
            model,
            layers=[self._probe_layer],
            callback=self._on_activations,
            every_n_tokens=PROBE_EVERY_N_TOKENS,
        )

        self._running = True
        print(f"[EmotionMonitor] Started monitoring on layer {self._probe_layer}.")
        return True

    def stop(self, model=None) -> None:
        """Remove hooks and stop monitoring."""
        if not self._running:
            return

        target = model or self._model
        if target is not None and is_live_hooks_installed():
            remove_live_hooks(target)

        self._running = False
        self._model = None
        print("[EmotionMonitor] Stopped.")

    @property
    def is_running(self) -> bool:
        return self._running

    # -----------------------------------------------------------------------
    # Activation callback (called from MLX inference thread)
    # -----------------------------------------------------------------------

    def _on_activations(self, layer_acts: Dict[int, np.ndarray]) -> None:
        """Process latest activations and fire alerts if needed."""
        if self._emotion_vectors is None or self._probe_layer is None:
            return

        acts = layer_acts.get(self._probe_layer)
        if acts is None:
            return

        scores = score_activations(acts, self._emotion_vectors)
        self._latest_scores = scores

        now = time.time()
        top = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:TOP_N_EMOTIONS]

        for emotion, threshold in self.thresholds.items():
            score = scores.get(emotion, 0.0)
            if score < threshold:
                continue

            last = self._last_alert.get(emotion, 0.0)
            if now - last < ALERT_COOLDOWN:
                continue

            self._last_alert[emotion] = now

            alert = {
                "type": "emotion_alert",
                "emotion": emotion,
                "score": round(score, 4),
                "threshold": threshold,
                "top_emotions": {k: round(v, 4) for k, v in top},
                "timestamp": now,
                "agent_id": self._current_agent_id,
            }

            print(f"[EmotionMonitor] ALERT: {emotion} = {score:.3f} (threshold {threshold})")

            # Fire custom callback (e.g. send to Gala)
            if self._alert_callback:
                try:
                    self._alert_callback(alert)
                except Exception as e:
                    print(f"[EmotionMonitor] alert_callback error: {e}")

            # Push to SSE queue (non-blocking)
            try:
                self._alert_queue.put_nowait(alert)
            except asyncio.QueueFull:
                pass  # Drop if nobody is listening

    # -----------------------------------------------------------------------
    # SSE interface
    # -----------------------------------------------------------------------

    async def stream_alerts(self):
        """
        Async generator for the SSE endpoint.

        Yields alert dicts as they arrive. Sends keepalives every 15s.
        """
        import json
        keepalive_interval = 15.0
        last_keepalive = time.time()

        while True:
            now = time.time()
            timeout = keepalive_interval - (now - last_keepalive)

            try:
                alert = await asyncio.wait_for(
                    self._alert_queue.get(), timeout=max(0.1, timeout)
                )
                yield alert
            except asyncio.TimeoutError:
                last_keepalive = time.time()
                yield {"type": "keepalive", "timestamp": last_keepalive}

    def get_latest_scores(self) -> Dict[str, float]:
        """Return the most recent emotion scores (for polling endpoints)."""
        return dict(self._latest_scores)

    def reload_probe(self) -> bool:
        """Hot-reload the probe from disk (e.g. after re-calibration)."""
        was_running = self._running
        model = self._model

        if was_running and model is not None:
            self.stop(model)

        self._probe_loaded = False
        success = self.load_probe()

        if was_running and model is not None and success:
            self.start(model, self._current_agent_id)

        return success


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_monitor: Optional[EmotionMonitor] = None


def get_monitor() -> EmotionMonitor:
    """Get (or create) the global EmotionMonitor singleton."""
    global _monitor
    if _monitor is None:
        _monitor = EmotionMonitor()
    return _monitor

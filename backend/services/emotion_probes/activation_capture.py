"""Activation capture for Kevin's emotion probes.

Hooks into MiniMax-M2.5's forward pass by monkey-patching
MiniMaxDecoderLayer.__call__ to intercept the residual stream output
(shape [B, T, D]) at specified transformer layers.

Two modes
---------
1. **One-shot capture** (calibration) — run a single forward pass on a
   batch of tokenized stories, return per-layer activations. Used to
   compute emotion direction vectors.

2. **Live capture** (inference monitoring) — install persistent hooks into
   the already-loaded model. Every token generated fires the hooks; a
   configurable callback receives the latest last-token activations so the
   calling code can score them against pre-computed emotion vectors.

Architecture note
-----------------
MiniMaxDecoderLayer.__call__(self, x, mask, cache) → mx.array [B, T, D]

The residual stream r is the final return value of each decoder layer.
Capturing it gives the hidden state *after* both attention and MoE for
that layer — equivalent to what Anthropic used in their emotion probes
paper (transformer-circuits.pub/2026/emotions/index.html).

mx.eval() is required to force MLX lazy evaluation before reading values
out as numpy. Without it you get uncomputed placeholders.

Usage
-----
    # Calibration:
    from backend.services.emotion_probes.activation_capture import capture_activations
    acts = capture_activations(model, tokenizer, texts, layers=[20, 30, 40])
    # acts: {layer_idx: np.ndarray [n_texts, hidden_dim]}

    # Live monitoring:
    from backend.services.emotion_probes.activation_capture import (
        install_live_hooks, remove_live_hooks
    )
    def on_token(layer_acts: dict[int, np.ndarray]):
        # layer_acts: {layer_idx: [hidden_dim]}
        score = np.dot(layer_acts[30], emotion_vector)
        if score > threshold: alert()

    install_live_hooks(model, layers=[30], callback=on_token)
    # ... run stream_generate as normal ...
    remove_live_hooks(model)
"""

from __future__ import annotations

import threading
from typing import Callable, Dict, List, Optional

import numpy as np

try:
    import mlx.core as mx
    MLX_AVAILABLE = True
except ImportError:
    MLX_AVAILABLE = False


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_decoder_layers(model) -> list:
    """
    Return the list of MiniMaxDecoderLayer objects from a loaded model.

    mlx_lm wraps the model as Model → model.model (MiniMaxModel) → .layers
    But the outer Model also exposes .layers as a property, so both work.
    """
    # Prefer the outer .layers property (mlx_lm Model convention)
    if hasattr(model, "layers"):
        return model.layers
    # Fallback: unwrap one level
    if hasattr(model, "model") and hasattr(model.model, "layers"):
        return model.model.layers
    raise AttributeError(
        "Cannot find decoder layers on model — expected model.layers or "
        "model.model.layers."
    )


def _num_layers(model) -> int:
    return len(_get_decoder_layers(model))


# ---------------------------------------------------------------------------
# One-shot calibration capture
# ---------------------------------------------------------------------------

def capture_activations(
    model,
    tokenizer,
    texts: List[str],
    layers: Optional[List[int]] = None,
    batch_size: int = 1,
    last_token_only: bool = True,
) -> Dict[int, np.ndarray]:
    """
    Run a forward pass on each text and return residual-stream activations.

    Parameters
    ----------
    model       : loaded mlx_lm Model (from mlx_lm.load)
    tokenizer   : loaded mlx_lm tokenizer
    texts       : list of strings to encode and forward
    layers      : which layer indices to capture; None = all layers
    batch_size  : texts to process per forward call (keep at 1 — MoE models
                  are memory-hungry and MiniMax is huge)
    last_token  : if True, return only the last-token activation per text
                  (shape [n_texts, hidden_dim]); if False, full sequence
                  (shape [n_texts, seq_len, hidden_dim]) — ragged, returned
                  as a list of arrays

    Returns
    -------
    Dict mapping layer_idx → np.ndarray of shape [n_texts, hidden_dim]
    (when last_token_only=True)
    """
    if not MLX_AVAILABLE:
        raise ImportError("MLX not available.")

    all_layers = _get_decoder_layers(model)
    n_layers = len(all_layers)
    target_layers = set(layers) if layers is not None else set(range(n_layers))

    # Validate
    for l in target_layers:
        if l < 0 or l >= n_layers:
            raise ValueError(f"Layer {l} out of range (model has {n_layers} layers).")

    # Storage: layer → list of per-text activations
    captured: Dict[int, list] = {l: [] for l in target_layers}

    # Patch target layers
    originals = {}
    for idx in target_layers:
        layer = all_layers[idx]
        orig_call = layer.__call__

        def make_hook(layer_idx, original):
            def hooked_call(x, mask=None, cache=None):
                result = original(x, mask=mask, cache=cache)
                # result shape: [B, T, D]
                # Force evaluation so we can read the array
                mx.eval(result)
                if last_token_only:
                    # Last token: [B, D]
                    act = np.array(result[:, -1, :])
                else:
                    act = np.array(result)
                _tls.current_capture[layer_idx] = act
                return result
            return hooked_call

        originals[idx] = orig_call
        # mlx.nn.Module doesn't use normal Python method binding —
        # we assign directly to the instance's __call__
        layer.__call__ = make_hook(idx, orig_call)

    # Thread-local storage for per-forward-pass activations
    _tls = threading.local()

    try:
        for text in texts:
            _tls.current_capture = {}

            # Tokenize
            tokens = tokenizer.encode(text, add_special_tokens=False)
            token_array = mx.array([tokens])  # [1, T]

            # Forward pass (no cache, no generation)
            _ = model(token_array)
            mx.eval(_)  # ensure full graph is evaluated

            # Collect from this forward pass
            for l in target_layers:
                act = _tls.current_capture.get(l)
                if act is not None:
                    # act shape: [1, D] (batch=1, last_token)
                    captured[l].append(act[0])  # [D]

    finally:
        # Always restore original __call__ methods
        for idx, orig in originals.items():
            all_layers[idx].__call__ = orig

    # Stack into arrays
    result = {}
    for l in target_layers:
        acts = captured[l]
        if acts:
            result[l] = np.stack(acts, axis=0)  # [n_texts, D]
        else:
            result[l] = np.empty((0,))

    return result


# ---------------------------------------------------------------------------
# Live inference hooks (persistent, for real-time monitoring)
# ---------------------------------------------------------------------------

# Module-level state for live hooks
_live_hooks_installed: bool = False
_live_hooks_originals: Dict[int, object] = {}
_live_hooks_layers: List[int] = []
_live_hooks_callback: Optional[Callable[[Dict[int, np.ndarray]], None]] = None
_live_hooks_lock = threading.Lock()
# Latest activations, written by inference thread, read by callback
_latest_acts: Dict[int, np.ndarray] = {}
# Accumulate per-token activations for the current generation
_generation_acts: Dict[int, list] = {}


def install_live_hooks(
    model,
    layers: List[int],
    callback: Callable[[Dict[int, np.ndarray]], None],
    every_n_tokens: int = 1,
) -> None:
    """
    Install persistent hooks into the live model.

    After installation, every token generated by stream_generate will
    trigger the hooks, which capture last-token activations and call
    `callback(layer_acts)` where layer_acts is {layer_idx: [hidden_dim]}.

    Parameters
    ----------
    model          : the live model (already loaded, same instance used for chat)
    layers         : which layer indices to monitor
    callback       : called with {layer_idx: np.ndarray [hidden_dim]} per token
                     (called from the MLX inference thread — keep it fast)
    every_n_tokens : only invoke callback every N tokens (reduces overhead)
    """
    global _live_hooks_installed, _live_hooks_originals, _live_hooks_layers
    global _live_hooks_callback, _latest_acts, _generation_acts

    if _live_hooks_installed:
        raise RuntimeError(
            "Live hooks already installed. Call remove_live_hooks() first."
        )

    all_layers = _get_decoder_layers(model)
    n_layers = len(all_layers)

    for l in layers:
        if l < 0 or l >= n_layers:
            raise ValueError(f"Layer {l} out of range (model has {n_layers} layers).")

    _live_hooks_layers = list(layers)
    _live_hooks_callback = callback
    _live_hooks_originals = {}
    _latest_acts = {}
    _generation_acts = {l: [] for l in layers}

    token_counter = [0]

    for idx in layers:
        layer = all_layers[idx]
        orig_call = layer.__call__

        def make_live_hook(layer_idx, original):
            def hooked_call(x, mask=None, cache=None):
                result = original(x, mask=mask, cache=cache)
                # During generation, x is [1, 1, D] (single new token)
                # During prefill, x is [1, T, D]
                # We only want the last-token activation
                mx.eval(result)
                act = np.array(result[0, -1, :])  # [D]
                with _live_hooks_lock:
                    _latest_acts[layer_idx] = act
                return result
            return hooked_call

        _live_hooks_originals[idx] = orig_call
        layer.__call__ = make_live_hook(idx, orig_call)

    # Wrap the final layer to fire the callback after all target layers ran
    # (The last target layer fires last because layers run in order)
    last_target = max(layers)
    last_layer = all_layers[last_target]
    penultimate_hook = last_layer.__call__

    def final_hook(x, mask=None, cache=None):
        result = penultimate_hook(x, mask=mask, cache=cache)
        token_counter[0] += 1
        if token_counter[0] % every_n_tokens == 0:
            with _live_hooks_lock:
                snapshot = dict(_latest_acts)
            if len(snapshot) == len(layers) and callback is not None:
                try:
                    callback(snapshot)
                except Exception as e:
                    print(f"[EmotionProbe] callback error: {e}")
        return result

    last_layer.__call__ = final_hook
    # Track that we double-patched the last target layer
    _live_hooks_originals[f"_final_{last_target}"] = penultimate_hook

    _live_hooks_installed = True
    print(
        f"[EmotionProbe] Live hooks installed on layers {layers} "
        f"(every {every_n_tokens} token(s))."
    )


def remove_live_hooks(model) -> None:
    """Remove live hooks and restore original layer __call__ methods."""
    global _live_hooks_installed, _live_hooks_originals, _live_hooks_layers
    global _live_hooks_callback, _latest_acts, _generation_acts

    if not _live_hooks_installed:
        return

    all_layers = _get_decoder_layers(model)

    # Restore the final-layer double-patch first
    for key, orig in list(_live_hooks_originals.items()):
        if isinstance(key, str) and key.startswith("_final_"):
            layer_idx = int(key.split("_final_")[1])
            all_layers[layer_idx].__call__ = orig

    # Restore all target layers
    for idx, orig in _live_hooks_originals.items():
        if isinstance(idx, int):
            all_layers[idx].__call__ = orig

    _live_hooks_originals = {}
    _live_hooks_layers = []
    _live_hooks_callback = None
    _latest_acts = {}
    _generation_acts = {}
    _live_hooks_installed = False
    print("[EmotionProbe] Live hooks removed.")


def is_live_hooks_installed() -> bool:
    return _live_hooks_installed


def get_latest_activations() -> Dict[int, np.ndarray]:
    """Return the most recent per-layer activations (thread-safe snapshot)."""
    with _live_hooks_lock:
        return dict(_latest_acts)


# ---------------------------------------------------------------------------
# Calibration helpers
# ---------------------------------------------------------------------------

def select_best_layer(
    emotion_acts: Dict[str, Dict[int, np.ndarray]],
    neutral_acts: Dict[int, np.ndarray],
) -> int:
    """
    Pick the layer with the highest between-emotion variance relative to
    within-emotion variance — the most discriminative layer for probing.

    Parameters
    ----------
    emotion_acts  : {emotion_label: {layer_idx: [n_stories, D]}}
    neutral_acts  : {layer_idx: [n_neutral, D]}

    Returns
    -------
    best_layer_idx : int
    """
    layers = list(next(iter(emotion_acts.values())).keys())
    scores = {}

    for layer in layers:
        # Collect all emotion means
        emotion_means = []
        within_vars = []
        for label, layer_acts in emotion_acts.items():
            acts = layer_acts[layer]  # [n, D]
            mean = acts.mean(axis=0)
            emotion_means.append(mean)
            within_vars.append(acts.var(axis=0).mean())

        emotion_means = np.stack(emotion_means, axis=0)  # [n_emotions, D]
        between_var = emotion_means.var(axis=0).mean()
        within_var = np.mean(within_vars)

        # Higher is better: between / (within + eps)
        scores[layer] = between_var / (within_var + 1e-10)

    best = max(scores, key=lambda l: scores[l])
    print(f"[EmotionProbe] Layer scores (between/within): "
          f"{ {l: f'{s:.4f}' for l, s in sorted(scores.items())} }")
    print(f"[EmotionProbe] Best layer: {best} (score={scores[best]:.4f})")
    return best


def compute_emotion_vectors(
    emotion_acts: Dict[str, np.ndarray],
    neutral_acts: np.ndarray,
    n_neutral_pcs: int = 5,
) -> Dict[str, np.ndarray]:
    """
    Compute per-emotion direction vectors (calibrated, style-projected).

    For each emotion e:
        raw_vector_e = mean(emotion_acts[e]) - mean(neutral_acts)

    Then project out the top `n_neutral_pcs` principal components of the
    neutral activations to remove style/format variance.

    Parameters
    ----------
    emotion_acts  : {emotion_label: [n_stories, D]}  (single layer)
    neutral_acts  : [n_neutral, D]  (single layer)
    n_neutral_pcs : how many neutral PCs to project out

    Returns
    -------
    {emotion_label: direction_vector [D]}  (unit-normed)
    """
    neutral_mean = neutral_acts.mean(axis=0)  # [D]
    centered_neutral = neutral_acts - neutral_mean

    # PCA on neutral activations to get style directions
    # Use SVD on the covariance structure
    U, S, Vt = np.linalg.svd(centered_neutral, full_matrices=False)
    # Vt rows are principal component directions [D]
    neutral_pcs = Vt[:n_neutral_pcs]  # [n_pcs, D]

    def project_out(v: np.ndarray, pcs: np.ndarray) -> np.ndarray:
        """Remove the components of v along each PC in pcs."""
        for pc in pcs:
            pc_norm = pc / (np.linalg.norm(pc) + 1e-10)
            v = v - np.dot(v, pc_norm) * pc_norm
        return v

    emotion_vectors = {}
    for label, acts in emotion_acts.items():
        emotion_mean = acts.mean(axis=0)  # [D]
        raw_vector = emotion_mean - neutral_mean
        projected = project_out(raw_vector, neutral_pcs)
        # Unit-normalize
        norm = np.linalg.norm(projected)
        if norm > 1e-10:
            projected = projected / norm
        emotion_vectors[label] = projected

    return emotion_vectors


def score_activations(
    activations: np.ndarray,
    emotion_vectors: Dict[str, np.ndarray],
) -> Dict[str, float]:
    """
    Dot-product activations against all emotion vectors.

    Parameters
    ----------
    activations    : [D] — single token's hidden state at the probe layer
    emotion_vectors: {label: [D]} — pre-computed unit-normed direction vectors

    Returns
    -------
    {label: float} — cosine similarity scores, higher = more of that emotion
    """
    acts_norm = np.linalg.norm(activations)
    if acts_norm < 1e-10:
        return {label: 0.0 for label in emotion_vectors}

    acts_unit = activations / acts_norm
    return {label: float(np.dot(acts_unit, vec)) for label, vec in emotion_vectors.items()}


# ---------------------------------------------------------------------------
# Probe state persistence
# ---------------------------------------------------------------------------

def save_probe(
    emotion_vectors: Dict[str, np.ndarray],
    probe_layer: int,
    neutral_pcs: np.ndarray,
    path: str,
) -> None:
    """Save calibrated probe data to a .npz file."""
    np.savez(
        path,
        probe_layer=np.array(probe_layer),
        neutral_pcs=neutral_pcs,
        labels=np.array(list(emotion_vectors.keys())),
        vectors=np.stack(list(emotion_vectors.values()), axis=0),
    )
    print(f"[EmotionProbe] Saved probe ({len(emotion_vectors)} emotions) to {path}")


def load_probe(path: str) -> tuple[Dict[str, np.ndarray], int, np.ndarray]:
    """
    Load a calibrated probe from a .npz file.

    Returns
    -------
    (emotion_vectors, probe_layer, neutral_pcs)
    """
    data = np.load(path, allow_pickle=True)
    labels = list(data["labels"])
    vectors = data["vectors"]  # [n_emotions, D]
    emotion_vectors = {label: vectors[i] for i, label in enumerate(labels)}
    probe_layer = int(data["probe_layer"])
    neutral_pcs = data["neutral_pcs"]
    print(f"[EmotionProbe] Loaded probe ({len(emotion_vectors)} emotions) from {path}")
    return emotion_vectors, probe_layer, neutral_pcs

"""Stateful Inference Engine

In-process MLX inference with per-conversation KV cache continuity.

Unlike mlx_lm.server (subprocess + REST API), this loads the model once
and keeps a live KV cache per conversation in unified memory. Each turn
only needs to prefill the NEW tokens — prior history is already cached.

Usage:
    engine = get_inference_engine()
    async for text in engine.stream_chat(conversation_id, messages, agent):
        yield text
"""

import asyncio
import hashlib
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import AsyncGenerator, Dict, List, Optional, Tuple
from uuid import UUID

try:
    import mlx.core as mx
    from mlx_lm import load, stream_generate
    from mlx_lm.models.cache import make_prompt_cache
    from mlx_lm.sample_utils import make_sampler
    MLX_AVAILABLE = True
except ImportError:
    MLX_AVAILABLE = False


class ConversationCache:
    """Live KV state for one conversation."""

    def __init__(self, system_hash: str, model_key: str, prompt_cache):
        self.system_hash = system_hash    # MD5 of system prompt content
        self.model_key = model_key        # model_path + adapter_path
        self.prompt_cache = prompt_cache  # list of KVCache objects (one per layer)
        self.last_used_at = time.time()

    def touch(self):
        self.last_used_at = time.time()

    def idle_seconds(self) -> float:
        return time.time() - self.last_used_at

    @property
    def offset(self) -> int:
        """Tokens already processed (prompt + all generated tokens so far)."""
        if self.prompt_cache:
            return self.prompt_cache[0].offset
        return 0


class StatefulInferenceEngine:
    """
    In-process MLX inference with per-conversation KV cache continuity.

    After the first message in a conversation, only the NEW tokens need
    prefilling — all prior history is served from the live KV cache in
    unified memory. This matches what Inferencer and similar apps do
    internally vs the stateless REST API approach of mlx_lm.server.

    Limitation: one model at a time. Switching agents with different models
    triggers a model reload and clears all conversation caches.
    """

    # Evict conversation caches idle longer than this
    CACHE_TTL = 30 * 60  # 30 minutes

    def __init__(self):
        if not MLX_AVAILABLE:
            raise ImportError(
                "MLX is not available. Install mlx and mlx-lm."
            )

        self._model = None
        self._tokenizer = None
        self._model_key: Optional[str] = None  # "model_path|adapter_path"

        # Single-threaded executor — MLX operations are not safe to interleave
        self._executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="mlx-inference"
        )

        # Per-conversation KV state: conversation_id → ConversationCache
        self._caches: Dict[UUID, ConversationCache] = {}

    # -------------------------------------------------------------------------
    # Model management
    # -------------------------------------------------------------------------

    def _make_model_key(self, model_path: str, adapter_path: Optional[str]) -> str:
        return f"{model_path}|{adapter_path or ''}"

    async def ensure_model(self, model_path: str, adapter_path: Optional[str] = None):
        """Load model if not already loaded. Clears conversation caches on switch."""
        key = self._make_model_key(model_path, adapter_path)
        if self._model_key == key and self._model is not None:
            return

        resolved = str(Path(model_path).expanduser())
        print(f"[StatefulInference] Loading model: {resolved}")

        loop = asyncio.get_running_loop()

        def _load():
            kwargs = {}
            if adapter_path:
                kwargs["adapter_path"] = str(Path(adapter_path).expanduser())
            return load(resolved, **kwargs)

        self._model, self._tokenizer = await loop.run_in_executor(self._executor, _load)

        if self._model_key != key:
            # Different model — old conversation caches are worthless
            self._caches.clear()

        self._model_key = key
        print(f"[StatefulInference] Model ready.")

    async def unload_model(self):
        """Free the loaded model from memory."""
        self._model = None
        self._tokenizer = None
        self._model_key = None
        self._caches.clear()
        print("[StatefulInference] Model unloaded.")

    # -------------------------------------------------------------------------
    # Conversation cache management
    # -------------------------------------------------------------------------

    def _get_or_create_cache(
        self, conversation_id: UUID, system_hash: str
    ) -> Tuple["ConversationCache", bool]:
        """Return (cache, is_fresh). Creates a new cache if missing or stale."""
        existing = self._caches.get(conversation_id)
        if (
            existing
            and existing.system_hash == system_hash
            and existing.model_key == self._model_key
        ):
            existing.touch()
            return existing, False

        new_cache = ConversationCache(
            system_hash=system_hash,
            model_key=self._model_key,
            prompt_cache=make_prompt_cache(self._model),
        )
        self._caches[conversation_id] = new_cache
        return new_cache, True

    def invalidate_conversation(self, conversation_id: UUID):
        """Force a full re-prefill on the next turn (e.g. after history edit)."""
        self._caches.pop(conversation_id, None)

    def evict_idle_caches(self):
        """Remove conversation caches that haven't been used recently."""
        cutoff = time.time() - self.CACHE_TTL
        stale = [cid for cid, c in self._caches.items() if c.last_used_at < cutoff]
        for cid in stale:
            del self._caches[cid]
        if stale:
            print(f"[StatefulInference] Evicted {len(stale)} idle conversation cache(s).")

    # -------------------------------------------------------------------------
    # Tokenization
    # -------------------------------------------------------------------------

    def _tokenize_messages(self, messages: List[dict]) -> List[int]:
        """Apply the model's chat template and return a flat list of token IDs."""
        tokenizer = self._tokenizer
        # TokenizerWrapper delegates unknown attributes to the underlying HF tokenizer
        underlying = getattr(tokenizer, "_tokenizer", tokenizer)

        if hasattr(underlying, "apply_chat_template"):
            try:
                tokens = underlying.apply_chat_template(
                    messages,
                    add_generation_prompt=True,
                    tokenize=True,
                )
                # Some tokenizers return a formatted string even with tokenize=True
                if isinstance(tokens, str):
                    return list(tokenizer.encode(tokens))
                tokens = tokens if isinstance(tokens, list) else list(tokens)
                # Guard: if elements are strings, re-encode
                if tokens and isinstance(tokens[0], str):
                    text = "".join(tokens)
                    return list(tokenizer.encode(text))
                return tokens
            except Exception as e:
                print(f"[StatefulInference] apply_chat_template failed ({e}), using text fallback")

        # Last-resort fallback: no chat template — format as plain dialogue.
        # Note: this often produces poor results; the model may not follow instructions.
        text = "\n".join(f"{m['role']}: {m['content']}" for m in messages)
        return list(tokenizer.encode(text))

    # -------------------------------------------------------------------------
    # Inference
    # -------------------------------------------------------------------------

    async def stream_chat(
        self,
        conversation_id: UUID,
        messages: List[dict],
        model_path: str,
        adapter_path: Optional[str] = None,
        temperature: float = 1.0,
        top_p: float = 1.0,
        top_k: int = 100,
        max_tokens: int = 4096,
    ) -> AsyncGenerator[str, None]:
        """
        Stream a chat response with stateful KV cache continuation.

        First turn:  prefills the full conversation (slow, model loads full context).
        Later turns: prefills ONLY the new tokens since last time (fast).

        Yields decoded text chunks as they are generated.
        """
        await self.ensure_model(model_path, adapter_path)

        # Hash system prompt — if it changes we must do a full re-prefill
        system_content = next(
            (m["content"] for m in messages if m["role"] == "system"), ""
        )
        system_hash = hashlib.md5(system_content.encode()).hexdigest()

        conv_cache, is_fresh = self._get_or_create_cache(conversation_id, system_hash)

        # Tokenize the full conversation as it stands now
        full_tokens = self._tokenize_messages(messages)

        # Compute delta: tokens not yet in the cache
        cache_offset = conv_cache.offset

        if not is_fresh and cache_offset > len(full_tokens):
            # Shouldn't happen (e.g. messages were deleted), but reset gracefully
            print(
                f"[StatefulInference] Cache offset {cache_offset} > full tokens "
                f"{len(full_tokens)} for conv {conversation_id} — resetting cache."
            )
            conv_cache.prompt_cache = make_prompt_cache(self._model)
            cache_offset = 0

        delta_tokens = full_tokens[cache_offset:]

        if is_fresh:
            print(
                f"[StatefulInference] conv {conversation_id}: "
                f"full prefill ({len(full_tokens)} tokens)"
            )
        else:
            print(
                f"[StatefulInference] conv {conversation_id}: "
                f"delta prefill ({len(delta_tokens)} new tokens, "
                f"{cache_offset} already cached)"
            )

        sampler = make_sampler(temp=temperature, top_p=top_p, top_k=top_k)

        # Capture locals for the thread
        model = self._model
        tokenizer = self._tokenizer
        prompt_cache = conv_cache.prompt_cache
        delta_array = mx.array(delta_tokens)

        # Bridge: synchronous stream_generate → async generator via queue
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        sentinel = object()

        def _run_generation():
            try:
                for response in stream_generate(
                    model,
                    tokenizer,
                    delta_array,
                    max_tokens=max_tokens,
                    sampler=sampler,
                    prompt_cache=prompt_cache,
                ):
                    asyncio.run_coroutine_threadsafe(
                        queue.put(response.text), loop
                    ).result()
            except Exception as exc:
                asyncio.run_coroutine_threadsafe(queue.put(exc), loop).result()
            finally:
                asyncio.run_coroutine_threadsafe(queue.put(sentinel), loop).result()

        loop.run_in_executor(self._executor, _run_generation)

        try:
            while True:
                item = await queue.get()
                if item is sentinel:
                    break
                if isinstance(item, Exception):
                    raise item
                yield item
        finally:
            conv_cache.touch()


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_engine: Optional[StatefulInferenceEngine] = None


def get_inference_engine() -> StatefulInferenceEngine:
    """Get (or create) the global StatefulInferenceEngine singleton."""
    global _engine
    if _engine is None:
        _engine = StatefulInferenceEngine()
    return _engine

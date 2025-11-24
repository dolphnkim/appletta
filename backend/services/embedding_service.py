"""Embedding service for semantic search

PURPOSE:
Provides text embeddings for the memory/RAG system. This is the main interface
that the rest of the backend uses for embeddings.

ARCHITECTURE:
- Uses Qwen3-Embedding-8B (8-bit quantized) via MLX
- Embedding server runs as separate process (qwen_embedding_server.py)
- This service is an HTTP client to that server
- Falls back to local gte-base if Qwen server unavailable (legacy support)

EMBEDDING DETAILS:
- Model: Qwen3-Embedding-8B
- Dimensions: 4096
- Pooling: Last-token (per Qwen3-Embedding spec)
- Normalization: L2

USAGE:
    from backend.services.embedding_service import get_embedding_service

    service = get_embedding_service()
    embedding = service.embed_text("Hello world")  # Returns 4096-dim vector
    embedding = service.embed_with_tags("Hello", ["greeting", "casual"])

MIGRATION NOTE (Nov 2024):
Previously used thenlper/gte-base (768 dimensions). Now uses Qwen3-Embedding-8B
(4096 dimensions). Database vectors need to be migrated from Vector(768) to Vector(4096).
"""

import os
import numpy as np
from typing import List, Optional
import logging

from backend.services.qwen_embedding_client import get_embedding_client, QwenEmbeddingClient

logger = logging.getLogger(__name__)

# Flag to use legacy gte-base if Qwen server unavailable
USE_LEGACY_FALLBACK = os.getenv("USE_LEGACY_EMBEDDING", "false").lower() == "true"


class EmbeddingService:
    """
    Service for generating embeddings.

    Uses Qwen3-Embedding-8B via HTTP server for high-quality 4096-dim embeddings.
    Falls back to local gte-base (768-dim) if configured and server unavailable.
    """

    def __init__(self):
        """Initialize embedding service"""
        self._qwen_client: Optional[QwenEmbeddingClient] = None
        self._legacy_model = None
        self._using_legacy = False

        # Try to connect to Qwen server
        self._qwen_client = get_embedding_client()

        if self._qwen_client.is_server_available():
            self.dimensions = 4096
            logger.info("Using Qwen3-Embedding-8B (4096 dimensions)")
        else:
            logger.warning("Qwen embedding server not available")
            if USE_LEGACY_FALLBACK:
                self._init_legacy_model()
            else:
                # Server not available but we'll try on each request
                # (maybe it starts up later)
                self.dimensions = 4096
                logger.info("Will retry Qwen server on requests")

    def _init_legacy_model(self):
        """Initialize legacy gte-base model for fallback"""
        try:
            from sentence_transformers import SentenceTransformer
            self._legacy_model = SentenceTransformer("thenlper/gte-base")
            self._using_legacy = True
            self.dimensions = 768
            logger.warning("Falling back to legacy gte-base model (768 dimensions)")
        except Exception as e:
            logger.error(f"Failed to load legacy model: {e}")
            raise RuntimeError("No embedding model available")

    def embed_text(self, text: str) -> List[float]:
        """Generate embedding for a single text

        Args:
            text: Input text to embed

        Returns:
            List of floats representing the embedding vector (4096 or 768 dims)
        """
        if self._using_legacy:
            embedding = self._legacy_model.encode(text, convert_to_numpy=True)
            return embedding.tolist()

        try:
            return self._qwen_client.embed_text(text)
        except Exception as e:
            logger.error(f"Qwen embedding failed: {e}")
            if USE_LEGACY_FALLBACK and self._legacy_model is None:
                self._init_legacy_model()
                return self.embed_text(text)
            raise

    def embed_with_tags(self, text: str, tags: List[str]) -> List[float]:
        """Generate embedding for text with thematic tags appended

        Tags enhance the semantic embedding with conceptual/thematic metadata.
        The [THEMES: ...] format anchors the embedding to thematic concepts,
        improving retrieval for related topics.

        Args:
            text: Input text to embed
            tags: List of thematic tags/concepts

        Returns:
            List of floats representing the embedding vector
        """
        if self._using_legacy:
            if tags and len(tags) > 0:
                tags_str = ", ".join(tags)
                augmented_text = f"{text}\n[THEMES: {tags_str}]"
                embedding = self._legacy_model.encode(augmented_text, convert_to_numpy=True)
                return embedding.tolist()
            else:
                return self.embed_text(text)

        return self._qwen_client.embed_with_tags(text, tags)

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for multiple texts

        Args:
            texts: List of input texts

        Returns:
            List of embedding vectors
        """
        if not texts:
            return []

        if self._using_legacy:
            embeddings = self._legacy_model.encode(texts, convert_to_numpy=True)
            return embeddings.tolist()

        try:
            return self._qwen_client.embed_batch(texts)
        except Exception as e:
            logger.error(f"Qwen batch embedding failed: {e}")
            if USE_LEGACY_FALLBACK and self._legacy_model is None:
                self._init_legacy_model()
                return self.embed_batch(texts)
            raise

    def cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """Calculate cosine similarity between two vectors

        Works with both 768-dim and 4096-dim vectors.

        Args:
            vec1: First embedding vector
            vec2: Second embedding vector

        Returns:
            Cosine similarity score (0-1)
        """
        v1 = np.array(vec1)
        v2 = np.array(vec2)

        return float(np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2)))


# Global singleton instance
_embedding_service: Optional[EmbeddingService] = None


def get_embedding_service() -> EmbeddingService:
    """Get the global embedding service instance (singleton)"""
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = EmbeddingService()
    return _embedding_service

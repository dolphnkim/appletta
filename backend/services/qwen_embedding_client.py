"""
Qwen3-Embedding Client Service for Appletta

PURPOSE:
HTTP client that talks to the Qwen3-Embedding server (qwen_embedding_server.py).
This is what the main backend uses to get embeddings.

The embedding server runs as a separate process to keep the model loaded.
This client just makes HTTP calls to it.

USAGE:
    from backend.services.qwen_embedding_client import get_embedding_client

    client = get_embedding_client()
    embedding = client.embed_text("Hello world")
    embeddings = client.embed_batch(["Hello", "World"])

CONFIGURATION:
    Set EMBEDDING_SERVER_URL environment variable to override the default URL.
    Default: http://localhost:8100
"""

import os
import logging
from typing import List, Optional

import httpx

# Configuration
EMBEDDING_SERVER_URL = os.getenv("EMBEDDING_SERVER_URL", "http://localhost:8100")

logger = logging.getLogger(__name__)


class QwenEmbeddingClient:
    """
    HTTP client for Qwen3-Embedding server.

    Provides the same interface as the old EmbeddingService but uses
    the Qwen3-Embedding-8B model via HTTP instead of sentence-transformers.
    """

    def __init__(self, base_url: str = EMBEDDING_SERVER_URL, timeout: float = 30.0):
        """
        Initialize the embedding client.

        Args:
            base_url: URL of the embedding server
            timeout: Request timeout in seconds
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.dimensions = 4096  # Qwen3-Embedding-8B output size
        self._client = None

    def _get_client(self) -> httpx.Client:
        """Get or create HTTP client"""
        if self._client is None:
            self._client = httpx.Client(timeout=self.timeout)
        return self._client

    def is_server_available(self) -> bool:
        """Check if the embedding server is running and healthy"""
        try:
            response = self._get_client().get(f"{self.base_url}/health")
            if response.status_code == 200:
                data = response.json()
                return data.get("model_loaded", False)
            return False
        except Exception as e:
            logger.warning(f"Embedding server not available: {e}")
            return False

    def embed_text(self, text: str, instruction: Optional[str] = None) -> List[float]:
        """
        Generate embedding for a single text.

        Args:
            text: The text to embed
            instruction: Optional instruction (e.g., "Given a question, retrieve relevant documents")

        Returns:
            4096-dimensional embedding vector

        Raises:
            RuntimeError: If server is unavailable or returns error
        """
        try:
            response = self._get_client().post(
                f"{self.base_url}/embed",
                json={"text": text, "instruction": instruction}
            )
            response.raise_for_status()
            return response.json()["embedding"]
        except httpx.HTTPStatusError as e:
            logger.error(f"Embedding server error: {e.response.text}")
            raise RuntimeError(f"Embedding failed: {e.response.text}")
        except Exception as e:
            logger.error(f"Embedding request failed: {e}")
            raise RuntimeError(f"Embedding request failed: {e}")

    def embed_with_tags(self, text: str, tags: List[str]) -> List[float]:
        """
        Generate embedding for text with thematic tags appended.

        This enhances the semantic embedding with conceptual/thematic metadata,
        same pattern as the old gte-base embedding service.

        Args:
            text: The text to embed
            tags: List of thematic tags/concepts

        Returns:
            4096-dimensional embedding vector
        """
        if tags and len(tags) > 0:
            tags_str = ", ".join(tags)
            augmented_text = f"{text}\n[THEMES: {tags_str}]"
            return self.embed_text(augmented_text)
        else:
            return self.embed_text(text)

    def embed_batch(self, texts: List[str], instruction: Optional[str] = None) -> List[List[float]]:
        """
        Generate embeddings for multiple texts.

        Args:
            texts: List of texts to embed
            instruction: Optional instruction prefix

        Returns:
            List of 4096-dimensional embedding vectors
        """
        if not texts:
            return []

        try:
            response = self._get_client().post(
                f"{self.base_url}/embed_batch",
                json={"texts": texts, "instruction": instruction}
            )
            response.raise_for_status()
            return response.json()["embeddings"]
        except httpx.HTTPStatusError as e:
            logger.error(f"Batch embedding server error: {e.response.text}")
            raise RuntimeError(f"Batch embedding failed: {e.response.text}")
        except Exception as e:
            logger.error(f"Batch embedding request failed: {e}")
            raise RuntimeError(f"Batch embedding request failed: {e}")

    def close(self):
        """Close the HTTP client"""
        if self._client:
            self._client.close()
            self._client = None


# ============================================================================
# Singleton Pattern (matches old embedding_service.py interface)
# ============================================================================

_embedding_client: Optional[QwenEmbeddingClient] = None


def get_embedding_client() -> QwenEmbeddingClient:
    """Get the global embedding client instance (singleton)"""
    global _embedding_client
    if _embedding_client is None:
        _embedding_client = QwenEmbeddingClient()
    return _embedding_client

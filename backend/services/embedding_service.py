"""Embedding service for semantic search using gte-base model

Handles text embedding generation for:
- User messages
- RAG chunks
- Journal blocks
- Conversation messages

Uses thenlper/gte-base (768 dimensions)
"""

import numpy as np
from typing import List, Optional
from sentence_transformers import SentenceTransformer


class EmbeddingService:
    """Service for generating embeddings"""

    def __init__(self, model_name: str = "thenlper/gte-base"):
        """Initialize embedding model

        Args:
            model_name: HuggingFace model name (default: thenlper/gte-base)
        """
        self.model = SentenceTransformer(model_name)
        self.dimensions = 768  # gte-base outputs 768 dimensions

    def embed_text(self, text: str) -> List[float]:
        """Generate embedding for a single text

        Args:
            text: Input text to embed

        Returns:
            List of floats representing the embedding vector
        """
        embedding = self.model.encode(text, convert_to_numpy=True)
        return embedding.tolist()

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for multiple texts

        Args:
            texts: List of input texts

        Returns:
            List of embedding vectors
        """
        embeddings = self.model.encode(texts, convert_to_numpy=True)
        return embeddings.tolist()

    def cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """Calculate cosine similarity between two vectors

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

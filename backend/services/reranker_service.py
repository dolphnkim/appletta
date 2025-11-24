"""
Qwen3-Reranker-8B Service for Appletta

PURPOSE:
Reranks memory candidates from pgvector search to select the most relevant ones.
This replaces the "selection" part of the memory coordinator with a purpose-built
reranking model.

HOW IT WORKS:
1. Takes a query (user message) and list of memory candidates
2. For each candidate, formats as: <Instruct>...<Query>...<Document>...
3. Runs forward pass through Qwen3-Reranker-8B
4. Extracts logits for "yes"/"no" tokens at last position
5. Computes relevance probability: softmax([no_logit, yes_logit])[1]
6. Returns candidates sorted by relevance score

MODEL DETAILS:
- Model: Qwen3-Reranker-8B (8-bit quantized via MLX)
- Location: /Users/kimwhite/models/Qwen/Reranker-8B-mlx-8bit
- Input: Query + Document formatted with instruction
- Output: Relevance score (0-1)

USAGE:
    from backend.services.reranker_service import get_reranker, rerank_memories

    # Get singleton reranker
    reranker = get_reranker()

    # Rerank candidates
    scored = reranker.rerank(
        query="What did we discuss about AI ethics?",
        candidates=[candidate1, candidate2, ...],
        top_k=10
    )
"""

import os
import logging
from typing import List, Tuple, Optional, NamedTuple
from dataclasses import dataclass

import mlx.core as mx
from mlx_lm import load

logger = logging.getLogger(__name__)

# Configuration
MODEL_PATH = os.getenv(
    "RERANKER_MODEL_PATH",
    "/Users/kimwhite/models/Qwen/Reranker-8B-mlx-8bit"
)


@dataclass
class MemoryCandidate:
    """A memory candidate from vector search"""
    id: str
    source_type: str  # 'message', 'journal_block', 'rag_chunk'
    content: str
    similarity_score: float
    metadata: Optional[dict] = None


@dataclass
class RankedMemory:
    """A memory with reranker score"""
    candidate: MemoryCandidate
    relevance_score: float


class QwenReranker:
    """
    Qwen3-Reranker-8B for memory candidate reranking.

    Uses the reranker's "yes/no" logits to compute relevance scores.
    This is more accurate than raw vector similarity for determining
    if a memory is actually relevant to the current query.
    """

    def __init__(self, model_path: str = MODEL_PATH):
        """Initialize the reranker"""
        self.model_path = model_path
        self.model = None
        self.tokenizer = None

        # Token IDs for yes/no (will be set on load)
        self.token_yes_id = None
        self.token_no_id = None

        # Prompt templates (from Qwen3-Reranker docs)
        self.system_prompt = (
            "Judge whether the Document meets the requirements based on the "
            "Query and the Instruct provided. Note that the answer can only be "
            '"yes" or "no".'
        )

        self.default_instruction = (
            "Given a user's message, retrieve relevant memories that provide "
            "context, background, or related information."
        )

    def load(self):
        """Load the model (lazy loading)"""
        if self.model is not None:
            return

        logger.info(f"Loading Qwen3-Reranker from {self.model_path}...")

        try:
            self.model, self.tokenizer = load(self.model_path)

            # Get token IDs for "yes" and "no"
            self.token_yes_id = self.tokenizer.encode("yes")[-1]
            self.token_no_id = self.tokenizer.encode("no")[-1]

            logger.info(f"Reranker loaded. yes_id={self.token_yes_id}, no_id={self.token_no_id}")

        except Exception as e:
            logger.error(f"Failed to load reranker: {e}")
            raise

    def _format_input(self, query: str, document: str, instruction: Optional[str] = None) -> str:
        """
        Format input for the reranker.

        Uses the chat template format:
        <|im_start|>system
        [system prompt]<|im_end|>
        <|im_start|>user
        <Instruct>: ...
        <Query>: ...
        <Document>: ...<|im_end|>
        <|im_start|>assistant
        <think>

        </think>

        """
        if instruction is None:
            instruction = self.default_instruction

        user_content = (
            f"<Instruct>: {instruction}\n"
            f"<Query>: {query}\n"
            f"<Document>: {document}"
        )

        # Build full prompt
        prompt = (
            f"<|im_start|>system\n{self.system_prompt}<|im_end|>\n"
            f"<|im_start|>user\n{user_content}<|im_end|>\n"
            f"<|im_start|>assistant\n<think>\n\n</think>\n\n"
        )

        return prompt

    def score_single(self, query: str, document: str, instruction: Optional[str] = None) -> float:
        """
        Compute relevance score for a single query-document pair.

        Returns probability of "yes" (relevance score 0-1).
        """
        self.load()

        # Format and tokenize
        prompt = self._format_input(query, document, instruction)
        input_ids = mx.array([self.tokenizer.encode(prompt)])

        # Forward pass to get logits
        logits = self.model(input_ids)

        # Get logits at the last position
        last_logits = logits[:, -1, :]  # Shape: (1, vocab_size)

        # Extract yes/no logits
        yes_logit = last_logits[:, self.token_yes_id]
        no_logit = last_logits[:, self.token_no_id]

        # Stack and softmax
        pair_logits = mx.stack([no_logit, yes_logit], axis=1)  # Shape: (1, 2)
        probs = mx.softmax(pair_logits, axis=1)

        # Get probability of "yes"
        mx.eval(probs)
        relevance_score = float(probs[0, 1])

        return relevance_score

    def rerank(
        self,
        query: str,
        candidates: List[MemoryCandidate],
        top_k: int = 10,
        instruction: Optional[str] = None
    ) -> List[RankedMemory]:
        """
        Rerank memory candidates by relevance to query.

        Args:
            query: The user's message/query
            candidates: List of MemoryCandidate from vector search
            top_k: Number of top candidates to return
            instruction: Optional custom instruction

        Returns:
            List of RankedMemory sorted by relevance_score (highest first)
        """
        if not candidates:
            return []

        self.load()

        scored_candidates = []

        for candidate in candidates:
            try:
                score = self.score_single(query, candidate.content, instruction)
                scored_candidates.append(RankedMemory(
                    candidate=candidate,
                    relevance_score=score
                ))
            except Exception as e:
                logger.warning(f"Failed to score candidate {candidate.id}: {e}")
                # Fallback to similarity score
                scored_candidates.append(RankedMemory(
                    candidate=candidate,
                    relevance_score=candidate.similarity_score
                ))

        # Sort by relevance score (highest first)
        scored_candidates.sort(key=lambda x: x.relevance_score, reverse=True)

        return scored_candidates[:top_k]

    def unload(self):
        """Unload the model to free memory"""
        self.model = None
        self.tokenizer = None
        logger.info("Reranker unloaded")


# ============================================================================
# Singleton Pattern
# ============================================================================

_reranker: Optional[QwenReranker] = None


def get_reranker() -> QwenReranker:
    """Get the global reranker instance (singleton)"""
    global _reranker
    if _reranker is None:
        _reranker = QwenReranker()
    return _reranker


def rerank_memories(
    query: str,
    candidates: List[MemoryCandidate],
    top_k: int = 10
) -> List[RankedMemory]:
    """Convenience function to rerank memories"""
    return get_reranker().rerank(query, candidates, top_k)

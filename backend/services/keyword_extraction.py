"""Keyword extraction service for generating initial tags

Extracts candidate phrases from text and ranks them by cosine similarity
to the full document embedding — same algorithm as KeyBERT, but using
the Qwen3-Embedding-8B server that's already running. No separate BERT
model needed.
"""

import re
import numpy as np
from typing import List

# Common English stopwords (subset sufficient for keyword filtering)
_STOPWORDS = {
    "a", "about", "above", "after", "again", "against", "all", "am", "an",
    "and", "any", "are", "as", "at", "be", "because", "been", "before",
    "being", "below", "between", "both", "but", "by", "can", "did", "do",
    "does", "doing", "down", "during", "each", "few", "for", "from",
    "further", "get", "got", "had", "has", "have", "having", "he", "her",
    "here", "hers", "herself", "him", "himself", "his", "how", "i", "if",
    "in", "into", "is", "it", "its", "itself", "just", "me", "more",
    "most", "my", "myself", "no", "not", "now", "of", "off", "on", "once",
    "only", "or", "other", "our", "ours", "ourselves", "out", "over",
    "own", "s", "same", "she", "should", "so", "some", "such", "t",
    "than", "that", "the", "their", "theirs", "them", "themselves", "then",
    "there", "these", "they", "this", "those", "through", "to", "too",
    "under", "until", "up", "us", "very", "was", "we", "were", "what",
    "when", "where", "which", "while", "who", "whom", "why", "will",
    "with", "would", "you", "your", "yours", "yourself", "yourselves",
}


def _extract_candidates(text: str) -> List[str]:
    """Extract 1- and 2-word candidate phrases, filtering stopwords."""
    words = re.findall(r"\b[a-zA-Z][a-zA-Z'-]{1,}\b", text.lower())
    words = [w for w in words if w not in _STOPWORDS and len(w) > 2]

    candidates = list(dict.fromkeys(words))  # dedup, preserve order

    # Add bigrams
    bigrams = [
        f"{words[i]} {words[i+1]}"
        for i in range(len(words) - 1)
        if words[i] not in _STOPWORDS and words[i+1] not in _STOPWORDS
    ]
    candidates += list(dict.fromkeys(bigrams))

    return candidates[:99]  # cap to 99 — embed_batch receives [doc] + candidates (max 100 total)


def extract_keywords(text: str, max_keywords: int = 5) -> List[str]:
    """Extract keywords from text ranked by semantic similarity to the document.

    Uses the running Qwen embedding server. Returns an empty list (silently)
    if the server is unavailable — the memory agent will create tags itself.

    Args:
        text: The text to extract keywords from
        max_keywords: Maximum number of keywords to return

    Returns:
        List of keyword strings
    """
    if not text or len(text.strip()) < 10:
        return []

    try:
        from backend.services.qwen_embedding_client import get_embedding_client

        client = get_embedding_client()
        candidates = _extract_candidates(text)
        if not candidates:
            return []

        # Embed document and all candidates in one round-trip
        all_texts = [text] + candidates
        all_embeddings = np.array(client.embed_batch(all_texts))

        doc_emb = all_embeddings[0]          # shape (4096,)
        cand_embs = all_embeddings[1:]        # shape (N, 4096)

        # Qwen vectors are already L2-normalised — dot product == cosine sim
        scores = cand_embs @ doc_emb

        # Max-marginal-relevance: pick diverse top-k
        selected: List[int] = []
        remaining = list(range(len(candidates)))

        for _ in range(min(max_keywords, len(candidates))):
            if not remaining:
                break
            if not selected:
                # First pick: highest document similarity
                best = max(remaining, key=lambda i: scores[i])
            else:
                # Subsequent picks: maximise relevance - redundancy
                sel_embs = cand_embs[selected]
                def mmr_score(i):
                    rel = scores[i]
                    red = float(np.max(cand_embs[i] @ sel_embs.T))
                    return 0.5 * rel - 0.5 * red
                best = max(remaining, key=mmr_score)
            selected.append(best)
            remaining.remove(best)

        return [candidates[i] for i in selected]

    except Exception as e:
        print(f"Keyword extraction failed (embedding server may be down): {e}")
        return []

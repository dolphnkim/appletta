"""Keyword extraction service for generating initial tags

Uses KeyBERT to extract keywords from text that serve as initial tags
for the memory agent to refine.
"""

from typing import List
from keybert import KeyBERT

# Initialize KeyBERT with the same model we use for embeddings
# This ensures keywords are semantically aligned with our embedding space
_kw_model = None


def get_keyword_model():
    """Get or initialize the KeyBERT model"""
    global _kw_model
    if _kw_model is None:
        # Use same embedding model as our main embeddings for consistency
        _kw_model = KeyBERT(model='thenlper/gte-base')
    return _kw_model


def extract_keywords(text: str, max_keywords: int = 5) -> List[str]:
    """Extract keywords from text to use as initial tags

    Args:
        text: The text to extract keywords from
        max_keywords: Maximum number of keywords to extract

    Returns:
        List of keyword strings
    """
    if not text or len(text.strip()) < 10:
        return []

    try:
        kw_model = get_keyword_model()

        # Extract keywords using KeyBERT
        # keyphrase_ngram_range=(1, 2) allows single words and 2-word phrases
        # stop_words='english' removes common words
        keywords = kw_model.extract_keywords(
            text,
            keyphrase_ngram_range=(1, 2),
            stop_words='english',
            top_n=max_keywords,
            use_mmr=True,  # Maximal Marginal Relevance for diversity
            diversity=0.5
        )

        # keywords is list of tuples: (keyword, score)
        # Return just the keyword strings
        return [kw[0] for kw in keywords]

    except Exception as e:
        # If keyword extraction fails, return empty list
        # Memory agent will create tags from scratch
        print(f"Keyword extraction failed: {e}")
        return []

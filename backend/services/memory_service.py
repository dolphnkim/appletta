"""Memory retrieval service

PURPOSE:
Searches across all memory sources and returns the most relevant candidates.
This is the "subconscious" that surfaces memories based on semantic relevance.

MEMORY SOURCES:
- Conversation history (past messages)
- RAG chunks (attached files)
- Journal blocks (user-defined notes)

ARCHITECTURE (Nov 2024 upgrade):
1. Vector search (pgvector) - Fast approximate search using Qwen3-Embedding-8B
2. Reranking (Qwen3-Reranker-8B) - Precise relevance scoring on top candidates

The two-stage approach gives both speed (vector search) and accuracy (reranking).
Vector search returns ~50 candidates, reranker picks the best 7-10.

USAGE:
    from backend.services.memory_service import search_and_rerank_memories

    # Get reranked memories
    memories = search_and_rerank_memories(
        query_text="What did we discuss about X?",
        agent_id=agent.id,
        db=db,
        top_k=10
    )
"""

from typing import List, Dict, Any, Tuple, Optional
from uuid import UUID
from sqlalchemy.orm import Session
from sqlalchemy import text
import logging

from backend.services.embedding_service import get_embedding_service

logger = logging.getLogger(__name__)


class MemoryCandidate:
    """Represents a potential memory to surface"""

    def __init__(
        self,
        id: str,
        source_type: str,  # 'message', 'rag_chunk', 'journal_block'
        content: str,
        similarity_score: float,
        metadata: Dict[str, Any] = None
    ):
        self.id = id
        self.source_type = source_type
        self.content = content
        self.similarity_score = similarity_score
        self.metadata = metadata or {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "source_type": self.source_type,
            "content": self.content[:500],  # Truncate for coordinator
            "similarity_score": self.similarity_score,
            "metadata": self.metadata
        }


def search_memories(
    query_text: str,
    agent_id: UUID,
    db: Session,
    limit: int = 50,
    exclude_message_ids: List[str] = None
) -> List[MemoryCandidate]:
    """Search for relevant memories across all sources

    Args:
        query_text: The text to search for (usually current message)
        agent_id: ID of the agent
        db: Database session
        limit: Maximum number of candidates to return
        exclude_message_ids: Optional list of message IDs to exclude (e.g., messages in active context)

    Returns:
        List of memory candidates sorted by similarity
    """

    # Generate embedding for query
    embedding_service = get_embedding_service()
    query_embedding = embedding_service.embed_text(query_text)

    # Convert embedding to pgvector format
    embedding_str = f"[{','.join(map(str, query_embedding))}]"

    candidates = []

    # Search journal blocks (simplest - direct agent_id)
    journal_query = text("""
        SELECT
            id,
            'journal_block' as source_type,
            value as content,
            1 - (embedding <=> CAST(:embedding AS vector)) as similarity
        FROM journal_blocks
        WHERE agent_id = :agent_id
        AND embedding IS NOT NULL
        ORDER BY embedding <=> CAST(:embedding AS vector)
        LIMIT :limit
    """)

    journal_results = db.execute(
        journal_query,
        {
            "embedding": embedding_str,
            "agent_id": str(agent_id),
            "limit": limit
        }
    ).fetchall()

    for row in journal_results:
        candidates.append(MemoryCandidate(
            id=str(row.id),
            source_type=row.source_type,
            content=row.content,
            similarity_score=float(row.similarity),
            metadata={"source": "journal"}
        ))

    # Search RAG chunks (needs joins to get agent_id)
    rag_query = text("""
        SELECT
            c.id,
            'rag_chunk' as source_type,
            c.content,
            1 - (c.embedding <=> CAST(:embedding AS vector)) as similarity
        FROM rag_chunks c
        JOIN rag_files f ON c.file_id = f.id
        JOIN rag_folders folder ON f.folder_id = folder.id
        WHERE folder.agent_id = :agent_id
        AND c.embedding IS NOT NULL
        ORDER BY c.embedding <=> CAST(:embedding AS vector)
        LIMIT :limit
    """)

    rag_results = db.execute(
        rag_query,
        {
            "embedding": embedding_str,
            "agent_id": str(agent_id),
            "limit": limit
        }
    ).fetchall()

    for row in rag_results:
        candidates.append(MemoryCandidate(
            id=str(row.id),
            source_type=row.source_type,
            content=row.content,
            similarity_score=float(row.similarity),
            metadata={"source": "rag"}
        ))

    # Search conversation messages (needs join to conversations)
    # Exclude messages in active context window to avoid redundancy
    exclude_clause = ""
    if exclude_message_ids:
        exclude_ids_str = "','".join(exclude_message_ids)
        exclude_clause = f"AND m.id NOT IN ('{exclude_ids_str}')"

    message_query = text(f"""
        SELECT
            m.id,
            'message' as source_type,
            m.content,
            1 - (m.embedding <=> CAST(:embedding AS vector)) as similarity
        FROM messages m
        JOIN conversations conv ON m.conversation_id = conv.id
        WHERE conv.agent_id = :agent_id
        AND m.embedding IS NOT NULL
        {exclude_clause}
        ORDER BY m.embedding <=> CAST(:embedding AS vector)
        LIMIT :limit
    """)

    message_results = db.execute(
        message_query,
        {
            "embedding": embedding_str,
            "agent_id": str(agent_id),
            "limit": limit
        }
    ).fetchall()

    for row in message_results:
        candidates.append(MemoryCandidate(
            id=str(row.id),
            source_type=row.source_type,
            content=row.content,
            similarity_score=float(row.similarity),
            metadata={"source": "conversation"}
        ))

    # Sort all candidates by similarity and return top N
    candidates.sort(key=lambda x: x.similarity_score, reverse=True)
    return candidates[:limit]


def fetch_full_memories(
    memory_ids: List[str],
    db: Session
) -> List[Dict[str, Any]]:
    """Fetch full content of specific memories by ID

    This is called by the main LLM after the memory coordinator
    has selected which memories to surface.

    Args:
        memory_ids: List of memory IDs to fetch
        db: Database session

    Returns:
        List of memory dictionaries with full content
    """

    memories = []

    for memory_id in memory_ids:
        # Query the search_results view for this specific ID
        query = text("""
            SELECT
                id,
                source_type,
                title,
                snippet as content,
                created_at,
                metadata
            FROM search_results
            WHERE id = :memory_id
        """)

        result = db.execute(query, {"memory_id": memory_id}).fetchone()

        if result:
            memories.append({
                "id": str(result.id),
                "source_type": result.source_type,
                "title": result.title,
                "content": result.content,
                "created_at": result.created_at.isoformat() if result.created_at else None,
                "metadata": result.metadata
            })

    return memories


# ============================================================================
# Reranking Integration (Nov 2024)
# ============================================================================

def search_and_rerank_memories(
    query_text: str,
    agent_id: UUID,
    db: Session,
    top_k: int = 10,
    vector_limit: int = 50,
    exclude_message_ids: List[str] = None,
    use_reranker: bool = True
) -> List[MemoryCandidate]:
    """
    Search for memories and rerank them using Qwen3-Reranker-8B.

    This is the recommended function for memory retrieval. It combines:
    1. Fast vector search (pgvector with Qwen3-Embedding-8B)
    2. Precise reranking (Qwen3-Reranker-8B)

    Args:
        query_text: The text to search for (usually current user message)
        agent_id: ID of the agent
        db: Database session
        top_k: Number of top memories to return after reranking
        vector_limit: Number of candidates to get from vector search
        exclude_message_ids: Message IDs to exclude (e.g., messages in context)
        use_reranker: Whether to use reranker (if False, just returns vector search results)

    Returns:
        List of MemoryCandidate objects, sorted by relevance
    """

    # Step 1: Vector search to get candidates
    candidates = search_memories(
        query_text=query_text,
        agent_id=agent_id,
        db=db,
        limit=vector_limit,
        exclude_message_ids=exclude_message_ids
    )

    if not candidates:
        return []

    # Step 2: Rerank candidates (if enabled)
    if use_reranker and len(candidates) > 0:
        try:
            from backend.services.reranker_service import (
                get_reranker,
                MemoryCandidate as RerankerCandidate
            )

            reranker = get_reranker()

            # Convert to reranker's MemoryCandidate format
            reranker_candidates = [
                RerankerCandidate(
                    id=c.id,
                    source_type=c.source_type,
                    content=c.content,
                    similarity_score=c.similarity_score,
                    metadata=c.metadata
                )
                for c in candidates
            ]

            # Rerank
            ranked = reranker.rerank(
                query=query_text,
                candidates=reranker_candidates,
                top_k=top_k
            )

            # Convert back to our MemoryCandidate format with reranker scores
            result = []
            for r in ranked:
                result.append(MemoryCandidate(
                    id=r.candidate.id,
                    source_type=r.candidate.source_type,
                    content=r.candidate.content,
                    similarity_score=r.relevance_score,  # Use reranker score
                    metadata={
                        **r.candidate.metadata,
                        "reranker_score": r.relevance_score,
                        "original_similarity": r.candidate.similarity_score
                    }
                ))

            logger.info(f"Reranked {len(candidates)} candidates -> {len(result)} memories")
            return result

        except Exception as e:
            logger.warning(f"Reranker failed, falling back to vector search: {e}")
            # Fall back to vector search results
            return candidates[:top_k]

    else:
        # No reranking, just return top-k from vector search
        return candidates[:top_k]


def format_memories_for_context(
    memories: List[MemoryCandidate],
    max_chars: int = 5000
) -> str:
    """
    Format memories for inclusion in the system prompt.

    This creates a simple formatted block of memories without the
    narrative synthesis that the memory coordinator used to do.

    Args:
        memories: List of MemoryCandidate objects
        max_chars: Maximum total characters

    Returns:
        Formatted string for system prompt
    """
    if not memories:
        return ""

    lines = ["=== Relevant Memories ===\n"]
    total_chars = len(lines[0])

    for i, mem in enumerate(memories, 1):
        # Format based on source type
        source_label = {
            "message": "Past conversation",
            "journal_block": "Note",
            "rag_chunk": "Document"
        }.get(mem.source_type, "Memory")

        # Truncate content if needed
        content = mem.content
        if len(content) > 500:
            content = content[:500] + "..."

        score_pct = int(mem.similarity_score * 100)
        entry = f"\n[{i}. {source_label} ({score_pct}% relevant)]\n{content}\n"

        if total_chars + len(entry) > max_chars:
            lines.append("\n[...additional memories truncated...]\n")
            break

        lines.append(entry)
        total_chars += len(entry)

    return "".join(lines)

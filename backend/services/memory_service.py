"""Memory retrieval service

Searches across all memory sources:
- Conversation history
- RAG chunks (attached files)
- Journal blocks

Uses vector similarity search to find relevant memories.
"""

from typing import List, Dict, Any, Tuple
from uuid import UUID
from sqlalchemy.orm import Session
from sqlalchemy import text

from backend.services.embedding_service import get_embedding_service


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

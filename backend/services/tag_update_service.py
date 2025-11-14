"""Tag update service for applying memory agent's tag edits

Handles updating memory tags and re-embedding with new thematic concepts.
"""

from typing import Dict, List
from uuid import UUID
from sqlalchemy.orm import Session
from sqlalchemy import text

from backend.services.embedding_service import get_embedding_service
from backend.db.models.conversation import Message
from backend.db.models.journal_block import JournalBlock
from backend.db.models.rag import RagChunk


def apply_tag_updates(
    tag_updates: Dict[str, List[str]],
    db: Session
) -> int:
    """Apply tag updates from memory agent and re-embed affected memories

    Args:
        tag_updates: Dict mapping memory IDs to new tag lists
        db: Database session

    Returns:
        Number of memories updated
    """
    if not tag_updates:
        return 0

    embedding_service = get_embedding_service()
    updated_count = 0

    for memory_id, new_tags in tag_updates.items():
        try:
            # Skip system memories (they're synthetic and don't exist in database)
            if memory_id.startswith("sys-"):
                continue

            # Validate that memory_id is a valid UUID format before attempting to parse
            # The memory agent sometimes hallucinates non-UUID strings as memory IDs
            try:
                uuid_obj = UUID(memory_id)
            except (ValueError, AttributeError):
                # Not a valid UUID, skip it
                continue

            # Try to find the memory in messages table first
            message = db.query(Message).filter(Message.id == uuid_obj).first()

            if message:
                # Update tags in metadata
                if message.metadata_ is None:
                    message.metadata_ = {}
                message.metadata_["tags"] = new_tags

                # Re-embed with new tags
                message.embedding = embedding_service.embed_with_tags(message.content, new_tags)

                updated_count += 1
                continue

            # Try journal blocks
            journal_block = db.query(JournalBlock).filter(JournalBlock.id == uuid_obj).first()

            if journal_block:
                # Update tags in metadata
                if journal_block.metadata_ is None:
                    journal_block.metadata_ = {}
                journal_block.metadata_["tags"] = new_tags

                # Re-embed with new tags
                journal_block.embedding = embedding_service.embed_with_tags(journal_block.value, new_tags)

                updated_count += 1
                continue

            # Try RAG chunks
            rag_chunk = db.query(RagChunk).filter(RagChunk.id == uuid_obj).first()

            if rag_chunk:
                # Update tags in metadata
                if rag_chunk.metadata_ is None:
                    rag_chunk.metadata_ = {}
                rag_chunk.metadata_["tags"] = new_tags

                # Re-embed with new tags
                rag_chunk.embedding = embedding_service.embed_with_tags(rag_chunk.content, new_tags)

                updated_count += 1
                continue

        except Exception as e:
            # If any error occurs updating a specific memory, log and continue
            print(f"Error updating tags for memory {memory_id}: {e}")
            continue

    # Commit all updates
    if updated_count > 0:
        db.commit()

    return updated_count

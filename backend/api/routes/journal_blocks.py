"""API routes for journal block management"""

from typing import List
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.db.session import get_db
from backend.db.models.journal_block import JournalBlock
from backend.db.models.agent import Agent
from backend.schemas.journal_block import (
    JournalBlockCreate,
    JournalBlockUpdate,
    JournalBlockResponse,
    JournalBlockList,
)
from backend.services.embedding_service import get_embedding_service

router = APIRouter(prefix="/api/v1/journal-blocks", tags=["journal-blocks"])


# ============================================================================
# Journal Block CRUD
# ============================================================================

@router.post("/", response_model=JournalBlockResponse)
async def create_journal_block(
    data: JournalBlockCreate,
    db: Session = Depends(get_db)
):
    """Create a new journal block"""

    # Verify agent exists
    agent = db.query(Agent).filter(Agent.id == UUID(data.agent_id)).first()
    if not agent:
        raise HTTPException(404, f"Agent {data.agent_id} not found")

    # Generate block_id if not provided
    block_id = data.block_id if data.block_id else JournalBlock.generate_block_id(data.label)

    # Check if block_id already exists for this agent
    existing = db.query(JournalBlock).filter(
        JournalBlock.agent_id == UUID(data.agent_id),
        JournalBlock.block_id == block_id
    ).first()
    if existing:
        raise HTTPException(409, f"Journal block with block_id '{block_id}' already exists for this agent")

    # Generate embedding for the block value
    embedding_service = get_embedding_service()
    block_embedding = embedding_service.embed_text(data.value)

    block = JournalBlock(
        agent_id=UUID(data.agent_id),
        label=data.label,
        block_id=block_id,
        description=data.description,
        value=data.value,
        read_only=data.read_only,
        editable_by_main_agent=data.editable_by_main_agent,
        editable_by_memory_agent=data.editable_by_memory_agent,
        embedding=block_embedding,
        metadata_=data.metadata,
    )

    db.add(block)
    db.commit()
    db.refresh(block)

    return block.to_dict()


@router.get("/", response_model=List[JournalBlockResponse])
async def list_journal_blocks(
    agent_id: str,
    db: Session = Depends(get_db)
):
    """List all journal blocks for an agent (labels only)"""

    blocks = db.query(JournalBlock).filter(
        JournalBlock.agent_id == UUID(agent_id)
    ).order_by(JournalBlock.updated_at.desc()).all()

    return [block.to_dict() for block in blocks]


@router.get("/{block_id}", response_model=JournalBlockResponse)
async def get_journal_block(
    block_id: UUID,
    db: Session = Depends(get_db)
):
    """Get a specific journal block with full content"""

    block = db.query(JournalBlock).filter(JournalBlock.id == block_id).first()
    if not block:
        raise HTTPException(404, f"Journal block {block_id} not found")

    return block.to_dict()


@router.patch("/{block_id}", response_model=JournalBlockResponse)
async def update_journal_block(
    block_id: UUID,
    updates: JournalBlockUpdate,
    db: Session = Depends(get_db)
):
    """Update a journal block"""

    block = db.query(JournalBlock).filter(JournalBlock.id == block_id).first()
    if not block:
        raise HTTPException(404, f"Journal block {block_id} not found")

    # Check if block is read-only
    if block.read_only:
        raise HTTPException(403, f"Journal block '{block.label}' is read-only and cannot be modified")

    # Update fields
    if updates.label is not None:
        block.label = updates.label
    if updates.description is not None:
        block.description = updates.description
    if updates.value is not None:
        block.value = updates.value
        # Re-generate embedding if value changed
        embedding_service = get_embedding_service()
        block.embedding = embedding_service.embed_text(updates.value)
    if updates.read_only is not None:
        block.read_only = updates.read_only
    if updates.editable_by_main_agent is not None:
        block.editable_by_main_agent = updates.editable_by_main_agent
    if updates.editable_by_memory_agent is not None:
        block.editable_by_memory_agent = updates.editable_by_memory_agent
    if updates.metadata is not None:
        block.metadata_ = updates.metadata

    db.commit()
    db.refresh(block)

    return block.to_dict()


@router.delete("/{block_id}")
async def delete_journal_block(
    block_id: UUID,
    db: Session = Depends(get_db)
):
    """Delete a journal block"""

    block = db.query(JournalBlock).filter(JournalBlock.id == block_id).first()
    if not block:
        raise HTTPException(404, f"Journal block {block_id} not found")

    # Check if block is read-only
    if block.read_only:
        raise HTTPException(403, f"Journal block '{block.label}' is read-only and cannot be deleted")

    db.delete(block)
    db.commit()

    return {"message": f"Journal block {block_id} deleted"}

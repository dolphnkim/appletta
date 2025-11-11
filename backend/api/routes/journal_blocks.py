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

    block = JournalBlock(
        agent_id=UUID(data.agent_id),
        label=data.label,
        value=data.value,
        metadata=data.metadata,
    )

    db.add(block)
    db.commit()
    db.refresh(block)

    return block.to_dict()


@router.get("/", response_model=List[JournalBlockList])
async def list_journal_blocks(
    agent_id: str,
    db: Session = Depends(get_db)
):
    """List all journal blocks for an agent (labels only)"""

    blocks = db.query(JournalBlock).filter(
        JournalBlock.agent_id == UUID(agent_id)
    ).order_by(JournalBlock.updated_at.desc()).all()

    return [
        {
            "id": str(block.id),
            "agent_id": str(block.agent_id),
            "label": block.label,
            "created_at": block.created_at,
            "updated_at": block.updated_at,
        }
        for block in blocks
    ]


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

    if updates.label is not None:
        block.label = updates.label
    if updates.value is not None:
        block.value = updates.value
    if updates.metadata is not None:
        block.metadata = updates.metadata

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

    db.delete(block)
    db.commit()

    return {"message": f"Journal block {block_id} deleted"}

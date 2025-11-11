"""API routes for agent attachment management"""

from typing import List
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.db.session import get_db
from backend.db.models.agent_attachment import AgentAttachment
from backend.db.models.agent import Agent
from backend.schemas.agent_attachment import (
    AgentAttachmentCreate,
    AgentAttachmentUpdate,
    AgentAttachmentResponse,
    AgentAttachmentList,
)

router = APIRouter(prefix="/api/v1/agent-attachments", tags=["agent-attachments"])


# ============================================================================
# Agent Attachment CRUD
# ============================================================================

@router.post("/", response_model=AgentAttachmentResponse)
async def create_agent_attachment(
    data: AgentAttachmentCreate,
    db: Session = Depends(get_db)
):
    """Attach an agent to another agent"""

    # Verify both agents exist
    agent = db.query(Agent).filter(Agent.id == UUID(data.agent_id)).first()
    if not agent:
        raise HTTPException(404, f"Agent {data.agent_id} not found")

    attached_agent = db.query(Agent).filter(Agent.id == UUID(data.attached_agent_id)).first()
    if not attached_agent:
        raise HTTPException(404, f"Attached agent {data.attached_agent_id} not found")

    # Prevent self-attachment
    if data.agent_id == data.attached_agent_id:
        raise HTTPException(400, "An agent cannot attach to itself")

    # Check if attachment already exists
    existing = db.query(AgentAttachment).filter(
        AgentAttachment.agent_id == UUID(data.agent_id),
        AgentAttachment.attached_agent_id == UUID(data.attached_agent_id),
        AgentAttachment.attachment_type == data.attachment_type
    ).first()

    if existing:
        raise HTTPException(409, f"Agent already has this attachment of type '{data.attachment_type}'")

    # Create attachment
    attachment = AgentAttachment(
        agent_id=UUID(data.agent_id),
        attached_agent_id=UUID(data.attached_agent_id),
        attachment_type=data.attachment_type,
        label=data.label or f"{attached_agent.name} ({data.attachment_type})",
        priority=data.priority,
        enabled=data.enabled
    )

    db.add(attachment)
    db.commit()
    db.refresh(attachment)

    return attachment.to_dict()


@router.get("/", response_model=List[AgentAttachmentList])
async def list_agent_attachments(
    agent_id: str,
    attachment_type: str = None,
    enabled_only: bool = True,
    db: Session = Depends(get_db)
):
    """List all attachments for an agent"""

    query = db.query(AgentAttachment).filter(
        AgentAttachment.agent_id == UUID(agent_id)
    )

    if attachment_type:
        query = query.filter(AgentAttachment.attachment_type == attachment_type)

    if enabled_only:
        query = query.filter(AgentAttachment.enabled == True)

    attachments = query.order_by(
        AgentAttachment.attachment_type,
        AgentAttachment.priority
    ).all()

    return [attachment.to_dict() for attachment in attachments]


@router.get("/{attachment_id}", response_model=AgentAttachmentResponse)
async def get_agent_attachment(
    attachment_id: UUID,
    db: Session = Depends(get_db)
):
    """Get a specific agent attachment"""

    attachment = db.query(AgentAttachment).filter(
        AgentAttachment.id == attachment_id
    ).first()

    if not attachment:
        raise HTTPException(404, f"Agent attachment {attachment_id} not found")

    return attachment.to_dict()


@router.patch("/{attachment_id}", response_model=AgentAttachmentResponse)
async def update_agent_attachment(
    attachment_id: UUID,
    updates: AgentAttachmentUpdate,
    db: Session = Depends(get_db)
):
    """Update an agent attachment"""

    attachment = db.query(AgentAttachment).filter(
        AgentAttachment.id == attachment_id
    ).first()

    if not attachment:
        raise HTTPException(404, f"Agent attachment {attachment_id} not found")

    if updates.label is not None:
        attachment.label = updates.label
    if updates.priority is not None:
        attachment.priority = updates.priority
    if updates.enabled is not None:
        attachment.enabled = updates.enabled

    db.commit()
    db.refresh(attachment)

    return attachment.to_dict()


@router.delete("/{attachment_id}")
async def delete_agent_attachment(
    attachment_id: UUID,
    db: Session = Depends(get_db)
):
    """Delete an agent attachment"""

    attachment = db.query(AgentAttachment).filter(
        AgentAttachment.id == attachment_id
    ).first()

    if not attachment:
        raise HTTPException(404, f"Agent attachment {attachment_id} not found")

    db.delete(attachment)
    db.commit()

    return {"message": f"Agent attachment {attachment_id} deleted"}

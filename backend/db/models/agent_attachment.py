"""Agent attachment model for connecting agents together

Allows main agents to attach helper agents (memory agents, tool agents, etc.)
"""

from datetime import datetime
from uuid import uuid4
from sqlalchemy import Column, String, Integer, ForeignKey, DateTime, Boolean, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from backend.db.base import Base


class AgentAttachment(Base):
    """Links agents together in parent-child relationships

    A main agent can have multiple attached agents serving different roles:
    - memory: Memory coordination/selection
    - tool: Tool execution/delegation
    - reflection: Self-reflection and analysis
    - etc.
    """
    __tablename__ = "agent_attachments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)

    # The main agent that has the attachment
    agent_id = Column(UUID(as_uuid=True), ForeignKey("agents.id", ondelete="CASCADE"), nullable=False)

    # The agent being attached
    attached_agent_id = Column(UUID(as_uuid=True), ForeignKey("agents.id", ondelete="CASCADE"), nullable=False)

    # Type of attachment: 'memory', 'tool', 'reflection', etc.
    attachment_type = Column(String(50), nullable=False)

    # Display label (e.g., "Primary Memory Coordinator")
    label = Column(String(255))

    # Order/priority for multiple attachments of same type
    priority = Column(Integer, default=0)

    # Enable/disable without deleting
    enabled = Column(Boolean, default=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    agent = relationship("Agent", foreign_keys=[agent_id], back_populates="attachments")
    attached_agent = relationship("Agent", foreign_keys=[attached_agent_id])

    # Unique constraint: agent can't attach the same agent twice for same type
    __table_args__ = (
        UniqueConstraint('agent_id', 'attached_agent_id', 'attachment_type',
                        name='uq_agent_attachment'),
    )

    def to_dict(self):
        return {
            "id": str(self.id),
            "agent_id": str(self.agent_id),
            "attached_agent_id": str(self.attached_agent_id),
            "attached_agent_name": self.attached_agent.name if self.attached_agent else None,
            "attachment_type": self.attachment_type,
            "label": self.label,
            "priority": self.priority,
            "enabled": self.enabled,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

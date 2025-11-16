"""Junction table for agent-journal block many-to-many relationship"""

from datetime import datetime
from uuid import uuid4
from sqlalchemy import Column, ForeignKey, DateTime, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from backend.db.base import Base


class AgentJournalBlock(Base):
    """Associates agents with journal blocks (many-to-many)"""
    __tablename__ = "agent_journal_blocks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    agent_id = Column(UUID(as_uuid=True), ForeignKey("agents.id", ondelete="CASCADE"), nullable=False)
    journal_block_id = Column(UUID(as_uuid=True), ForeignKey("journal_blocks.id", ondelete="CASCADE"), nullable=False)

    # When this association was created
    attached_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    agent = relationship("Agent", back_populates="journal_block_associations")
    journal_block = relationship("JournalBlock", back_populates="agent_associations")

    # Unique constraint to prevent duplicate associations
    __table_args__ = (
        UniqueConstraint('agent_id', 'journal_block_id', name='uq_agent_journal_block'),
    )

    def to_dict(self):
        return {
            "id": str(self.id),
            "agent_id": str(self.agent_id),
            "journal_block_id": str(self.journal_block_id),
            "attached_at": self.attached_at.isoformat() if self.attached_at else None,
        }

"""Database model for journal blocks"""

from datetime import datetime
from uuid import uuid4
from sqlalchemy import Column, String, Text, ForeignKey, DateTime
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from pgvector.sqlalchemy import Vector

from backend.db.base import Base


class JournalBlock(Base):
    __tablename__ = "journal_blocks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    agent_id = Column(UUID(as_uuid=True), ForeignKey("agents.id", ondelete="CASCADE"), nullable=False)

    label = Column(String(255), nullable=False)  # e.g., "User Info", "Project Notes"
    value = Column(Text, nullable=False)  # The actual content

    # Embedding for semantic search
    embedding = Column(Vector(768))

    # Metadata (flexible storage for future use)
    metadata = Column(JSONB)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    agent = relationship("Agent")

    def to_dict(self):
        return {
            "id": str(self.id),
            "agent_id": str(self.agent_id),
            "label": self.label,
            "value": self.value,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

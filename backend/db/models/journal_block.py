"""Database model for journal blocks"""

from datetime import datetime
from uuid import uuid4
import re
from sqlalchemy import Column, String, Text, DateTime, Boolean, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from pgvector.sqlalchemy import Vector

from backend.db.base import Base


class JournalBlock(Base):
    __tablename__ = "journal_blocks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)

    # Block identification
    label = Column(String(255), nullable=False)  # e.g., "User Info", "Project Notes"
    block_id = Column(String(255), nullable=False, unique=True)  # User-friendly ID (auto-generated from label)

    # Content
    description = Column(Text, nullable=True)  # Optional description of what this block contains
    value = Column(Text, nullable=False)  # The actual content

    # Access control
    read_only = Column(Boolean, default=False)  # If true, cannot be modified
    editable_by_main_agent = Column(Boolean, default=True)  # Main LLM can edit
    editable_by_memory_agent = Column(Boolean, default=False)  # Memory coordinator can edit

    # Context control
    always_in_context = Column(Boolean, default=False)  # If true, always included in system prompt

    # Embedding for semantic search
    embedding = Column(Vector(768))

    # Metadata (flexible storage for future use, using metadata_ to avoid SQLAlchemy reserved name)
    metadata_ = Column("metadata", JSONB)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships - many-to-many with agents through junction table
    agent_associations = relationship("AgentJournalBlock", back_populates="journal_block", cascade="all, delete-orphan")

    @staticmethod
    def generate_block_id(label: str) -> str:
        """Generate a URL-safe block_id from label

        Examples:
            "User Info" -> "user-info"
            "Project: Appletta" -> "project-appletta"
        """
        # Convert to lowercase
        block_id = label.lower()
        # Replace non-alphanumeric with hyphens
        block_id = re.sub(r'[^a-z0-9]+', '-', block_id)
        # Remove leading/trailing hyphens
        block_id = block_id.strip('-')
        return block_id

    def to_dict(self):
        return {
            "id": str(self.id),
            "label": self.label,
            "block_id": self.block_id,
            "description": self.description,
            "value": self.value,
            "read_only": self.read_only,
            "editable_by_main_agent": self.editable_by_main_agent,
            "editable_by_memory_agent": self.editable_by_memory_agent,
            "always_in_context": self.always_in_context,
            "metadata": self.metadata_,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

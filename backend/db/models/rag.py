"""RAG Filesystem database models

Stores folders, files, and chunks for retrieval augmented generation
"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Column, String, Integer, BigInteger, Text, DateTime, ForeignKey, Boolean
from sqlalchemy.dialects.postgresql import UUID as pgUUID, JSONB
from sqlalchemy.orm import relationship
from pgvector.sqlalchemy import Vector

from backend.db.base import Base


class RagFolder(Base):
    """Attached filesystem folder"""

    __tablename__ = "rag_folders"

    id = Column(pgUUID(as_uuid=True), primary_key=True, default=uuid4)
    agent_id = Column(pgUUID(as_uuid=True), ForeignKey("agents.id", ondelete="CASCADE"))

    path = Column(String(2048), nullable=False)
    name = Column(String(512), nullable=False)

    # Settings
    max_files_open = Column(Integer, default=5)
    per_file_char_limit = Column(Integer, default=15000)

    # Source instructions
    source_instructions = Column(Text)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    files = relationship("RagFile", back_populates="folder", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<RagFolder(id={self.id}, name='{self.name}', path='{self.path}')>"

    def to_dict(self):
        return {
            "id": str(self.id),
            "agent_id": str(self.agent_id),
            "path": self.path,
            "name": self.name,
            "max_files_open": self.max_files_open,
            "per_file_char_limit": self.per_file_char_limit,
            "source_instructions": self.source_instructions,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "file_count": len(self.files) if self.files else 0,
        }


class RagFile(Base):
    """Individual file within a folder"""

    __tablename__ = "rag_files"

    id = Column(pgUUID(as_uuid=True), primary_key=True, default=uuid4)
    folder_id = Column(pgUUID(as_uuid=True), ForeignKey("rag_folders.id", ondelete="CASCADE"))

    path = Column(String(2048), nullable=False)
    filename = Column(String(512), nullable=False)
    extension = Column(String(50))

    # File metadata
    size_bytes = Column(BigInteger)
    mime_type = Column(String(255))

    # Content
    raw_content = Column(Text)

    # File hash for change detection
    content_hash = Column(String(64))

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    last_indexed_at = Column(DateTime)

    # Relationships
    folder = relationship("RagFolder", back_populates="files")
    chunks = relationship("RagChunk", back_populates="file", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<RagFile(id={self.id}, filename='{self.filename}')>"

    def to_dict(self):
        return {
            "id": str(self.id),
            "folder_id": str(self.folder_id),
            "path": self.path,
            "filename": self.filename,
            "extension": self.extension,
            "size_bytes": self.size_bytes,
            "mime_type": self.mime_type,
            "content_hash": self.content_hash,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "last_indexed_at": self.last_indexed_at.isoformat() if self.last_indexed_at else None,
            "chunk_count": len(self.chunks) if self.chunks else 0,
        }


class RagChunk(Base):
    """Text chunk with embedding for semantic search"""

    __tablename__ = "rag_chunks"

    id = Column(pgUUID(as_uuid=True), primary_key=True, default=uuid4)
    file_id = Column(pgUUID(as_uuid=True), ForeignKey("rag_files.id", ondelete="CASCADE"))

    # Chunk content
    content = Column(Text, nullable=False)
    chunk_index = Column(Integer, nullable=False)

    # Character positions
    start_char = Column(Integer)
    end_char = Column(Integer)

    # Embedding (4096 dimensions for Qwen3-Embedding-8B)
    embedding = Column(Vector(4096))

    # Metadata (using metadata_ to avoid SQLAlchemy reserved name)
    metadata_ = Column("metadata", JSONB)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    file = relationship("RagFile", back_populates="chunks")

    def __repr__(self):
        return f"<RagChunk(id={self.id}, file_id={self.file_id}, chunk_index={self.chunk_index})>"

    def to_dict(self):
        return {
            "id": str(self.id),
            "file_id": str(self.file_id),
            "content": self.content,
            "chunk_index": self.chunk_index,
            "start_char": self.start_char,
            "end_char": self.end_char,
            "metadata": self.metadata_,
            "created_at": self.created_at.isoformat(),
        }

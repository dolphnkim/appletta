"""Pydantic schemas for RAG API"""

from datetime import datetime
from typing import Optional, List
from uuid import UUID

from pydantic import BaseModel, Field


# ============================================================================
# RAG Folder Schemas
# ============================================================================

class RagFolderCreate(BaseModel):
    """Create a new RAG folder"""
    agent_id: UUID
    path: str = Field(..., description="Filesystem path to folder")
    name: Optional[str] = Field(None, description="Display name (defaults to folder name)")
    max_files_open: int = Field(5, ge=1, le=100)
    per_file_char_limit: int = Field(15000, ge=100, le=1000000)
    source_instructions: Optional[str] = Field(None, description="How to interpret files in this folder")


class RagFolderUpdate(BaseModel):
    """Update RAG folder settings"""
    name: Optional[str] = None
    max_files_open: Optional[int] = Field(None, ge=1, le=100)
    per_file_char_limit: Optional[int] = Field(None, ge=100, le=1000000)
    source_instructions: Optional[str] = None


class RagFolderResponse(BaseModel):
    """RAG folder response"""
    id: UUID
    agent_id: UUID
    path: str
    name: str
    max_files_open: int
    per_file_char_limit: int
    source_instructions: Optional[str]
    created_at: datetime
    updated_at: datetime
    file_count: int

    class Config:
        from_attributes = True


# ============================================================================
# RAG File Schemas
# ============================================================================

class RagFileResponse(BaseModel):
    """RAG file response"""
    id: UUID
    folder_id: UUID
    path: str
    filename: str
    extension: Optional[str]
    size_bytes: Optional[int]
    mime_type: Optional[str]
    content_hash: Optional[str]
    created_at: datetime
    updated_at: datetime
    last_indexed_at: Optional[datetime]
    chunk_count: int

    class Config:
        from_attributes = True


# ============================================================================
# Search Schemas
# ============================================================================

class SearchQuery(BaseModel):
    """Search query"""
    query: str = Field(..., min_length=1, description="Search query")
    agent_id: Optional[UUID] = Field(None, description="Filter by agent")
    source_types: Optional[List[str]] = Field(
        None,
        description="Filter by source type: rag_chunk, journal_block, message"
    )
    limit: int = Field(20, ge=1, le=100)
    semantic: bool = Field(True, description="Use semantic similarity search")
    full_text: bool = Field(True, description="Use full-text search")


class SearchResult(BaseModel):
    """Search result"""
    id: UUID
    source_type: str  # 'rag_chunk', 'journal_block', 'message'
    title: str
    snippet: str
    created_at: datetime
    score: float  # Relevance score
    metadata: Optional[dict] = None

    class Config:
        from_attributes = True


class SearchResponse(BaseModel):
    """Search results response"""
    results: List[SearchResult]
    total: int
    query: str

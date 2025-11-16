"""Pydantic schemas for journal block API"""

from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field


# ============================================================================
# Journal Block Schemas
# ============================================================================

class JournalBlockCreate(BaseModel):
    """Schema for creating a journal block"""
    agent_id: str
    label: str = Field(..., min_length=1, max_length=255, description="Label/title for the block")
    description: Optional[str] = Field(None, description="Optional description of the block")
    value: str = Field(..., min_length=1, description="Content of the journal block")
    block_id: Optional[str] = Field(None, description="User-friendly ID (auto-generated from label if not provided)")
    read_only: bool = Field(default=False, description="If true, block cannot be modified")
    editable_by_main_agent: bool = Field(default=True, description="Main LLM can edit this block")
    editable_by_memory_agent: bool = Field(default=False, description="Memory coordinator can edit this block")
    always_in_context: bool = Field(default=False, description="If true, always included in system prompt")
    metadata: Optional[dict] = None


class JournalBlockUpdate(BaseModel):
    """Schema for updating a journal block"""
    label: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    value: Optional[str] = Field(None, min_length=1)
    read_only: Optional[bool] = None
    editable_by_main_agent: Optional[bool] = None
    editable_by_memory_agent: Optional[bool] = None
    always_in_context: Optional[bool] = None
    metadata: Optional[dict] = None


class JournalBlockResponse(BaseModel):
    """Schema for journal block responses"""
    id: str
    agent_id: str
    label: str
    block_id: str
    description: Optional[str]
    value: str
    read_only: bool
    editable_by_main_agent: bool
    editable_by_memory_agent: bool
    always_in_context: bool
    metadata: Optional[dict]
    created_at: datetime
    updated_at: datetime


class JournalBlockList(BaseModel):
    """Schema for listing journal blocks (minimal info)"""
    id: str
    agent_id: str
    label: str
    block_id: str
    description: Optional[str]
    created_at: datetime
    updated_at: datetime

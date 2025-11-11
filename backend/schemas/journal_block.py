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
    value: str = Field(..., min_length=1, description="Content of the journal block")
    metadata: Optional[dict] = None


class JournalBlockUpdate(BaseModel):
    """Schema for updating a journal block"""
    label: Optional[str] = Field(None, min_length=1, max_length=255)
    value: Optional[str] = Field(None, min_length=1)
    metadata: Optional[dict] = None


class JournalBlockResponse(BaseModel):
    """Schema for journal block responses"""
    id: str
    agent_id: str
    label: str
    value: str
    metadata: Optional[dict]
    created_at: datetime
    updated_at: datetime


class JournalBlockList(BaseModel):
    """Schema for listing journal blocks (minimal info)"""
    id: str
    agent_id: str
    label: str
    created_at: datetime
    updated_at: datetime

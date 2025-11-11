"""Pydantic schemas for agent attachment API"""

from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field


# ============================================================================
# Agent Attachment Schemas
# ============================================================================

class AgentAttachmentCreate(BaseModel):
    """Schema for creating an agent attachment"""
    agent_id: str = Field(..., description="The main agent ID")
    attached_agent_id: str = Field(..., description="The agent to attach")
    attachment_type: str = Field(..., min_length=1, max_length=50, description="Type: 'memory', 'tool', etc.")
    label: Optional[str] = Field(None, max_length=255, description="Display label")
    priority: int = Field(default=0, description="Order/priority")
    enabled: bool = Field(default=True, description="Whether attachment is active")


class AgentAttachmentUpdate(BaseModel):
    """Schema for updating an agent attachment"""
    label: Optional[str] = Field(None, max_length=255)
    priority: Optional[int] = None
    enabled: Optional[bool] = None


class AgentAttachmentResponse(BaseModel):
    """Schema for agent attachment responses"""
    id: str
    agent_id: str
    attached_agent_id: str
    attached_agent_name: Optional[str]
    attachment_type: str
    label: Optional[str]
    priority: int
    enabled: bool
    created_at: datetime
    updated_at: datetime


class AgentAttachmentList(BaseModel):
    """Schema for listing agent attachments (minimal info)"""
    id: str
    attached_agent_id: str
    attached_agent_name: Optional[str]
    attachment_type: str
    label: Optional[str]
    priority: int
    enabled: bool

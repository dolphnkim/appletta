"""Pydantic schemas for conversation and message API"""

from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field


# ============================================================================
# Conversation Schemas
# ============================================================================

class ConversationCreate(BaseModel):
    agent_id: str
    title: Optional[str] = None


class ConversationUpdate(BaseModel):
    title: Optional[str] = None


class ConversationResponse(BaseModel):
    id: str
    agent_id: str
    title: Optional[str]
    created_at: datetime
    updated_at: datetime
    message_count: int


# ============================================================================
# Message Schemas
# ============================================================================

class MessageCreate(BaseModel):
    content: str
    role: str = "user"  # 'user', 'assistant', 'system'


class MessageResponse(BaseModel):
    id: str
    conversation_id: str
    role: str
    content: str
    metadata: Optional[dict] = None
    created_at: datetime


class ChatRequest(BaseModel):
    """Request to send a message and get LLM response"""
    message: str


class ChatResponse(BaseModel):
    """Response containing both user message and assistant reply"""
    user_message: MessageResponse
    assistant_message: MessageResponse

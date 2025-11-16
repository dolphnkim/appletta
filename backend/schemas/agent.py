"""Pydantic schemas for Agent API requests/responses"""

 #agent_settings tab

from datetime import datetime

from typing import Optional, Literal, List

from uuid import UUID



from pydantic import BaseModel, Field, ConfigDict

 

 

# Sub-schemas for nested config

class LLMConfig(BaseModel):

    """LLM generation parameters"""

    reasoning_enabled: bool = False

    temperature: float = Field(default=0.7, ge=0.0, le=2.0)

    top_p: float = Field(default=1.0, ge=0.0, le=1.0)

    top_k: int = Field(default=0, ge=0)

    seed: Optional[int] = None

    max_output_tokens_enabled: bool = False

    max_output_tokens: int = Field(default=8192, gt=0)

    max_context_tokens: int = Field(default=4096, gt=0)

 

 

class EmbeddingConfig(BaseModel):

    """Embedding model configuration"""

    model_config = ConfigDict(protected_namespaces=())

    model_path: str = Field(..., description="Path to embedding model directory")

    dimensions: int = Field(default=2000, gt=0)

    chunk_size: int = Field(default=300, gt=0)



class FreeChoiceConfig(BaseModel):
    """Free choice mode configuration for autonomous exploration"""
    enabled: bool = Field(default=False, description="Enable autonomous free choice sessions")
    interval_minutes: int = Field(default=10, ge=1, le=1440, description="Minutes between sessions")
    last_session_at: Optional[datetime] = Field(None, description="When last session occurred")



# Request schemas

class AgentCreate(BaseModel):

    """Schema for creating a new agent"""

    model_config = ConfigDict(protected_namespaces=())

    name: str = Field(..., min_length=1, max_length=255)

    description: Optional[str] = None

    agent_type: Literal["main", "memory", "tool", "reflection", "other"] = Field(default="main")

    is_template: bool = Field(default=False, description="Whether this agent is a template")

    enabled_tools: Optional[List[str]] = Field(None, description="List of enabled tool names for this agent")

    model_path: str = Field(..., description="Path to local MLX model directory")

    adapter_path: Optional[str] = Field(None, description="Path to LoRA adapter directory")

    project_instructions: str = Field(..., min_length=1)



    llm_config: LLMConfig = Field(default_factory=LLMConfig)

    embedding_config: EmbeddingConfig

 

    # TODO: Validate that paths exist and contain valid models

 

 

class AgentUpdate(BaseModel):

    """Schema for updating an agent (all fields optional)"""

    model_config = ConfigDict(protected_namespaces=())

    name: Optional[str] = Field(None, min_length=1, max_length=255)

    description: Optional[str] = None

    agent_type: Optional[Literal["main", "memory", "tool", "reflection", "other"]] = None

    is_template: Optional[bool] = None

    enabled_tools: Optional[List[str]] = None

    model_path: Optional[str] = None

    adapter_path: Optional[str] = None

    project_instructions: Optional[str] = Field(None, min_length=1)



    llm_config: Optional[LLMConfig] = None

    embedding_config: Optional[EmbeddingConfig] = None

    free_choice_config: Optional[FreeChoiceConfig] = None



# Response schemas

class AgentResponse(BaseModel):

    """Schema for agent API responses"""

    model_config = ConfigDict(protected_namespaces=(), from_attributes=True)

    id: UUID

    name: str

    description: Optional[str]

    agent_type: str

    is_template: bool

    enabled_tools: List[str]

    model_path: str

    adapter_path: Optional[str]

    project_instructions: str

    llm_config: LLMConfig

    embedding_config: EmbeddingConfig

    free_choice_config: FreeChoiceConfig

    created_at: datetime

    updated_at: datetime



class AgentListResponse(BaseModel):

    """Schema for listing multiple agents"""

    agents: list[AgentResponse]

    total: int

 

 

# Agent file format (.af)

class AgentFileData(BaseModel):

    """Schema for .af file import/export"""

    model_config = ConfigDict(protected_namespaces=())

    name: str

    description: Optional[str]

    agent_type: Literal["main", "memory", "tool", "reflection", "other"] = Field(default="main")

    enabled_tools: Optional[List[str]] = None

    model_path: str

    adapter_path: Optional[str]

    project_instructions: str

    llm_config: LLMConfig

    embedding_config: EmbeddingConfig





class AgentFile(BaseModel):

    """Complete .af file structure"""

    version: str = "1.0"

    agent: AgentFileData

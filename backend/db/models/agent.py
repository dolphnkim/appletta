
"""Agent database model for Appletta

 #agent_settings tab

Stores all configuration for an agent instance, including:

- Model/adapter/embedding paths

- System instructions

- LLM generation parameters

- Embedding configuration

"""

 

from datetime import datetime

from uuid import UUID, uuid4

 

from sqlalchemy import Boolean, Column, Float, Integer, String, Text, DateTime

from sqlalchemy.dialects.postgresql import UUID as pgUUID

from sqlalchemy.orm import relationship



from backend.db.base import Base



class Agent(Base):

    """Agent configuration and settings"""

 

    __tablename__ = "agents"

 

    # Identity

    id = Column(pgUUID(as_uuid=True), primary_key=True, default=uuid4)

    name = Column(String(255), nullable=False, index=True)

    description = Column(Text, nullable=True)

 

    # Model Configuration - Filepaths to local MLX models

    model_path = Column(String(1024), nullable=False)

    adapter_path = Column(String(1024), nullable=True)  # Optional LoRA adapter

 

    # System Instructions - The agent's personality/role/rules

    system_instructions = Column(Text, nullable=False)

 

    # LLM Config

    reasoning_enabled = Column(Boolean, default=False)

    # TODO: Consider moving to model config file instead of DB

    # Controls whether model uses <think></think> tags for chain-of-thought

 

    temperature = Column(Float, default=0.7)  # 0.0 - 2.0

    top_p = Column(Float, default=1.0)  # 0.0 - 1.0, nucleus sampling

    top_k = Column(Integer, default=0)  # 0 = disabled, else top-k sampling

    seed = Column(Integer, nullable=True)  # For reproducible outputs

    max_output_tokens_enabled = Column(Boolean, default=False)

    max_output_tokens = Column(Integer, default=8192)

    max_context_tokens = Column(Integer, default=4096)  # Shifting context window size



    # Embedding Config

    embedding_model_path = Column(String(1024), nullable=False)

    embedding_dimensions = Column(Integer, default=2000)

    embedding_chunk_size = Column(Integer, default=300)

 

    # TODO: Projects integration (future)

    # project_id = Column(pgUUID(as_uuid=True), ForeignKey('projects.id'), nullable=True)

 

    # Timestamps

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)



    # Relationships

    attachments = relationship("AgentAttachment", foreign_keys="AgentAttachment.agent_id",

                              back_populates="agent", cascade="all, delete-orphan")



    def __repr__(self):

        return f"<Agent(id={self.id}, name='{self.name}')>"

 

    def to_dict(self):

        """Convert to dictionary for API responses"""

        return {

            "id": str(self.id),

            "name": self.name,

            "description": self.description,

            "model_path": self.model_path,

            "adapter_path": self.adapter_path,

            "system_instructions": self.system_instructions,

            "llm_config": {

                "reasoning_enabled": self.reasoning_enabled,

                "temperature": self.temperature,

                "top_p": self.top_p,

                "top_k": self.top_k,

                "seed": self.seed,

                "max_output_tokens_enabled": self.max_output_tokens_enabled,

                "max_output_tokens": self.max_output_tokens,

                "max_context_tokens": self.max_context_tokens,

            },

            "embedding_config": {

                "model_path": self.embedding_model_path,

                "dimensions": self.embedding_dimensions,

                "chunk_size": self.embedding_chunk_size,

            },

            "created_at": self.created_at.isoformat(),

            "updated_at": self.updated_at.isoformat(),

        }

 

    def to_agent_file(self):

        """Export as .af file format (JSON)"""

        return {

            "version": "1.0",

            "agent": {

                "name": self.name,

                "description": self.description,

                "model_path": self.model_path,

                "adapter_path": self.adapter_path,

                "system_instructions": self.system_instructions,

                "llm_config": {

                    "reasoning_enabled": self.reasoning_enabled,

                    "temperature": self.temperature,

                    "top_p": self.top_p,

                    "top_k": self.top_k,

                    "seed": self.seed,

                    "max_output_tokens_enabled": self.max_output_tokens_enabled,

                    "max_output_tokens": self.max_output_tokens,

                    "max_context_tokens": self.max_context_tokens,

                },

                "embedding_config": {

                    "model_path": self.embedding_model_path,

                    "dimensions": self.embedding_dimensions,

                    "chunk_size": self.embedding_chunk_size,

                },

            }

        }

 

    @classmethod

    def from_agent_file(cls, agent_data: dict):

        """Create Agent from .af file data"""

        agent_dict = agent_data.get("agent", {})

        llm_config = agent_dict.get("llm_config", {})

        embedding_config = agent_dict.get("embedding_config", {})

 

        # TODO: Add validation that paths exist before creating agent

 

        return cls(

            name=agent_dict.get("name"),

            description=agent_dict.get("description"),

            model_path=agent_dict.get("model_path"),

            adapter_path=agent_dict.get("adapter_path"),

            system_instructions=agent_dict.get("system_instructions"),

            reasoning_enabled=llm_config.get("reasoning_enabled", False),

            temperature=llm_config.get("temperature", 0.7),

            top_p=llm_config.get("top_p", 1.0),

            top_k=llm_config.get("top_k", 0),

            seed=llm_config.get("seed"),

            max_output_tokens_enabled=llm_config.get("max_output_tokens_enabled", False),

            max_output_tokens=llm_config.get("max_output_tokens", 8192),

            max_context_tokens=llm_config.get("max_context_tokens", 4096),

            embedding_model_path=embedding_config.get("model_path"),

            embedding_dimensions=embedding_config.get("dimensions", 2000),

            embedding_chunk_size=embedding_config.get("chunk_size", 300),

        )

 

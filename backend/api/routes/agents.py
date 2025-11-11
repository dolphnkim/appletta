"""API routes for agent management

 

Handles:

- CRUD operations for agents

- Clone agent

- Import/export agent files (.af)

"""

 

import json

from typing import List

from uuid import UUID

 

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File

from fastapi.responses import JSONResponse

from sqlalchemy.orm import Session

 

from backend.db.session import get_db

from backend.db.models.agent import Agent

from backend.schemas.agent import (

    AgentCreate,

    AgentUpdate,

    AgentResponse,

    AgentFile,

)

 

router = APIRouter(prefix="/api/v1/agents", tags=["agents"])

 

 

# ============================================================================

# CRUD Operations

# ============================================================================

 

@router.post("/", response_model=AgentResponse)

async def create_agent(

    agent_data: AgentCreate,

    db: Session = Depends(get_db)

):

    """Create a new agent



    Validates:

    - Model path exists and contains valid MLX model

    - Adapter path exists (if provided)

    - Embedding model path exists

    """

    # Create agent from request data

    # Flatten the nested config structures to match DB columns

    agent = Agent(

        name=agent_data.name,

        description=agent_data.description,

        model_path=agent_data.model_path,

        adapter_path=agent_data.adapter_path,

        system_instructions=agent_data.system_instructions,

        reasoning_enabled=agent_data.llm_config.reasoning_enabled,

        temperature=agent_data.llm_config.temperature,

        top_p=agent_data.llm_config.top_p,

        top_k=agent_data.llm_config.top_k,

        seed=agent_data.llm_config.seed,

        max_output_tokens_enabled=agent_data.llm_config.max_output_tokens_enabled,

        max_output_tokens=agent_data.llm_config.max_output_tokens,

        max_context_tokens=agent_data.llm_config.max_context_tokens,

        embedding_model_path=agent_data.embedding_config.model_path,

        embedding_dimensions=agent_data.embedding_config.dimensions,

        embedding_chunk_size=agent_data.embedding_config.chunk_size,

    )



    db.add(agent)

    db.commit()

    db.refresh(agent)

    return agent.to_dict()

 

 

@router.get("/", response_model=List[AgentResponse])

async def list_agents(

    db: Session = Depends(get_db)

):

    """List all agents



    Returns agents sorted by creation date (newest first)

    """

    agents = db.query(Agent).order_by(Agent.created_at.desc()).all()

    return [agent.to_dict() for agent in agents]

 

 

@router.get("/{agent_id}", response_model=AgentResponse)

async def get_agent(

    agent_id: UUID,

    db: Session = Depends(get_db)

):

    """Get a specific agent by ID"""

    agent = db.query(Agent).filter(Agent.id == agent_id).first()

    if not agent:

        raise HTTPException(404, f"Agent {agent_id} not found")

    return agent.to_dict()

 

 

@router.patch("/{agent_id}", response_model=AgentResponse)

async def update_agent(

    agent_id: UUID,

    updates: AgentUpdate,

    db: Session = Depends(get_db)

):

    """Update an agent's settings



    Only updates fields that are provided (partial update)

    """

    agent = db.query(Agent).filter(Agent.id == agent_id).first()

    if not agent:

        raise HTTPException(404, f"Agent {agent_id} not found")



    update_data = updates.model_dump(exclude_unset=True)



    # Flatten nested configs if provided

    if "llm_config" in update_data:

        for key, value in update_data["llm_config"].items():

            setattr(agent, key, value)

        del update_data["llm_config"]



    if "embedding_config" in update_data:

        embed_config = update_data["embedding_config"]

        if "model_path" in embed_config:

            agent.embedding_model_path = embed_config["model_path"]

        if "dimensions" in embed_config:

            agent.embedding_dimensions = embed_config["dimensions"]

        if "chunk_size" in embed_config:

            agent.embedding_chunk_size = embed_config["chunk_size"]

        del update_data["embedding_config"]



    # Apply remaining updates

    for key, value in update_data.items():

        setattr(agent, key, value)



    db.commit()

    db.refresh(agent)

    return agent.to_dict()

 

 

@router.delete("/{agent_id}")

async def delete_agent(

    agent_id: UUID,

    db: Session = Depends(get_db)

):

    """Delete an agent



    Note: This doesn't delete the model files, just the agent configuration

    """

    agent = db.query(Agent).filter(Agent.id == agent_id).first()

    if not agent:

        raise HTTPException(404, f"Agent {agent_id} not found")



    db.delete(agent)

    db.commit()

    return {"message": f"Agent {agent_id} deleted successfully"}

 

 

# ============================================================================

# Agent Operations (Clone, Import, Export)

# ============================================================================

 

@router.post("/{agent_id}/clone", response_model=AgentResponse)

async def clone_agent(

    agent_id: UUID,

    db: Session = Depends(get_db)

):

    """Clone an agent with all its settings



    Creates a new agent with:

    - Same model/adapter/embedding paths

    - Same system instructions

    - Same LLM config

    - Name with "-copy" suffix

    """

    original = db.query(Agent).filter(Agent.id == agent_id).first()

    if not original:

        raise HTTPException(404, f"Agent {agent_id} not found")



    # Create new agent with same settings

    cloned = Agent(

        name=f"{original.name}-copy",

        description=original.description,

        model_path=original.model_path,

        adapter_path=original.adapter_path,

        system_instructions=original.system_instructions,

        reasoning_enabled=original.reasoning_enabled,

        temperature=original.temperature,

        top_p=original.top_p,

        top_k=original.top_k,

        seed=original.seed,

        max_output_tokens_enabled=original.max_output_tokens_enabled,

        max_output_tokens=original.max_output_tokens,

        max_context_tokens=original.max_context_tokens,

        embedding_model_path=original.embedding_model_path,

        embedding_dimensions=original.embedding_dimensions,

        embedding_chunk_size=original.embedding_chunk_size,

    )



    db.add(cloned)

    db.commit()

    db.refresh(cloned)

    return cloned.to_dict()

 

 

@router.get("/{agent_id}/export")

async def export_agent(

    agent_id: UUID,

    db: Session = Depends(get_db)

):

    """Export agent as .af file (JSON download)



    Returns a JSON file that can be imported to recreate the agent

    """

    agent = db.query(Agent).filter(Agent.id == agent_id).first()

    if not agent:

        raise HTTPException(404, f"Agent {agent_id} not found")



    agent_file = agent.to_agent_file()

    filename = f"{agent.name.replace(' ', '_')}.af"



    return JSONResponse(

        content=agent_file,

        headers={

            "Content-Disposition": f'attachment; filename="{filename}"'

        }

    )

 

 

@router.post("/import", response_model=AgentResponse)

async def import_agent(

    file: UploadFile = File(...),

    db: Session = Depends(get_db)

):

    """Import agent from .af file



    Validates:

    - File is valid JSON

    - Contains required fields

    - Model paths exist



    Creates new agent with imported settings

    """

    if not file.filename.endswith('.af'):

        raise HTTPException(400, "File must be .af format")



    try:

        content = await file.read()

        agent_data = json.loads(content)

    except json.JSONDecodeError:

        raise HTTPException(400, "Invalid JSON in .af file")



    # Validate structure

    try:

        agent_file = AgentFile(**agent_data)

    except Exception as e:

        raise HTTPException(400, f"Invalid .af file structure: {e}")



    # Create agent from file

    agent = Agent.from_agent_file(agent_data)

    db.add(agent)

    db.commit()

    db.refresh(agent)

    return agent.to_dict()

 

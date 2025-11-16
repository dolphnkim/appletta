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

from backend.db.models.agent import Agent, AgentType

from backend.schemas.agent import (

    AgentCreate,

    AgentUpdate,

    AgentResponse,

    AgentFile,

)

from backend.services.token_counter import count_tokens

from backend.services.tools import JOURNAL_BLOCK_TOOLS, get_enabled_tools, get_tools_description, ALL_TOOLS

 

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

        agent_type=agent_data.agent_type,

        model_path=agent_data.model_path,

        adapter_path=agent_data.adapter_path,

        project_instructions=agent_data.project_instructions,

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



    # agent_type is already a string, no conversion needed



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



    if "free_choice_config" in update_data:
        free_config = update_data["free_choice_config"]
        if "enabled" in free_config:
            agent.free_choice_enabled = free_config["enabled"]
        if "interval_minutes" in free_config:
            agent.free_choice_interval_minutes = free_config["interval_minutes"]
        # Note: last_session_at is managed internally, not through updates
        del update_data["free_choice_config"]



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

# Context Window

# ============================================================================



@router.get("/{agent_id}/context-window")

async def get_agent_context_window(

    agent_id: UUID,

    db: Session = Depends(get_db)

):

    """Get baseline context window for an agent (without conversation)



    Shows token usage for:

    - Project instructions

    - Tool descriptions

    - Total tokens and percentage of max context

    """

    agent = db.query(Agent).filter(Agent.id == agent_id).first()

    if not agent:

        raise HTTPException(404, f"Agent {agent_id} not found")



    # Count system instructions tokens

    project_instructions_tokens = count_tokens(agent.project_instructions or "")



    # Count tool descriptions tokens

    enabled_tools = get_enabled_tools(agent.enabled_tools)

    tools_json = json.dumps(enabled_tools)

    tools_tokens = count_tokens(tools_json)



    # Build external summary (RAG files, journal blocks, datetime)
    from datetime import datetime
    from backend.db.models.rag import RagFolder, RagFile
    from backend.services.tools import list_journal_blocks

    external_summary_parts = []

    # Add current datetime
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S %Z")
    external_summary_parts.append(f"Current time: {current_time}")

    # Add RAG folders/files
    rag_folders = db.query(RagFolder).filter(RagFolder.agent_id == agent.id).all()
    if rag_folders:
        external_summary_parts.append("\n=== RAG Folders/Files ===")
        for folder in rag_folders:
            external_summary_parts.append(f"Folder: {folder.name}")
            rag_files = db.query(RagFile).filter(RagFile.folder_id == folder.id).all()
            for file in rag_files:
                external_summary_parts.append(f"  - {file.name}")

    # Add journal blocks
    journal_blocks_info = list_journal_blocks(agent.id, db)
    journal_blocks_list = journal_blocks_info.get("blocks", [])
    if journal_blocks_list:
        external_summary_parts.append("\n=== Journal Blocks ===")
        for block in journal_blocks_list:
            external_summary_parts.append(f"- {block['label']}")

    external_summary_text = "\n".join(external_summary_parts) if external_summary_parts else "No external resources"
    external_summary_tokens = count_tokens(external_summary_text)



    total_tokens = project_instructions_tokens + tools_tokens + external_summary_tokens

    max_tokens = agent.max_context_tokens

    percentage_used = (total_tokens / max_tokens * 100) if max_tokens > 0 else 0



    return {

        "sections": [

            {

                "name": "Project Instructions",

                "tokens": project_instructions_tokens,

                "percentage": (project_instructions_tokens / max_tokens * 100) if max_tokens > 0 else 0,

                "content": agent.project_instructions[:500] if agent.project_instructions else ""

            },

            {

                "name": "Tools descriptions",

                "tokens": tools_tokens,

                "percentage": (tools_tokens / max_tokens * 100) if max_tokens > 0 else 0,

                "content": tools_json[:500]

            },

            {

                "name": "External summary",

                "tokens": external_summary_tokens,

                "percentage": (external_summary_tokens / max_tokens * 100) if max_tokens > 0 else 0,

                "content": external_summary_text

            },

            {

                "name": "Available for messages",

                "tokens": max_tokens - total_tokens,

                "percentage": ((max_tokens - total_tokens) / max_tokens * 100) if max_tokens > 0 else 0,

                "content": None

            }

        ],

        "total_tokens": total_tokens,

        "max_context_tokens": max_tokens,

        "percentage_used": percentage_used

    }





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

    - Same project instructions

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

        project_instructions=original.project_instructions,

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

 

# ============================================================================
# Tools Management
# ============================================================================

@router.get("/tools/available")
async def get_available_tools():
    """Get list of all available tools

    Returns tool metadata for frontend display:
    - name: Tool name
    - description: Tool description
    """
    tools_list = []
    for tool_name, tool_def in ALL_TOOLS.items():
        tools_list.append({
            "name": tool_name,
            "description": tool_def["function"]["description"]
        })

    return {
        "tools": tools_list,
        "total": len(tools_list)
    }


@router.get("/{agent_id}/tools/description")
async def get_agent_tools_description(
    agent_id: UUID,
    db: Session = Depends(get_db)
):
    """Get auto-generated tools description for agent

    Returns a formatted description of the agent's enabled tools.
    If no tools are enabled, returns description of all available tools.
    """
    agent = db.query(Agent).filter(Agent.id == agent_id).first()

    if not agent:
        raise HTTPException(404, f"Agent {agent_id} not found")

    description = get_tools_description(agent.enabled_tools)

    return {
        "agent_id": str(agent_id),
        "enabled_tools": agent.enabled_tools if agent.enabled_tools else [],
        "tools_description": description
    }


# ============================================================================
# Free Choice Mode
# ============================================================================

@router.post("/{agent_id}/free-choice")
async def start_free_choice_session(
    agent_id: UUID,
    db: Session = Depends(get_db)
):
    """Start a free choice session for the agent

    Checks if enough time has passed since last session, then creates
    a free choice conversation where the agent can explore autonomously.
    """
    from datetime import datetime, timedelta
    from backend.db.models.conversation import Conversation, Message

    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(404, f"Agent {agent_id} not found")

    if not agent.free_choice_enabled:
        raise HTTPException(400, "Free choice mode is not enabled for this agent")

    # Check if enough time has passed
    now = datetime.utcnow()
    if agent.last_free_choice_at:
        time_since_last = now - agent.last_free_choice_at
        required_interval = timedelta(minutes=agent.free_choice_interval_minutes)
        if time_since_last < required_interval:
            remaining = required_interval - time_since_last
            return {
                "status": "too_soon",
                "message": f"Next session available in {int(remaining.total_seconds() / 60)} minutes",
                "next_available_at": (agent.last_free_choice_at + required_interval).isoformat()
            }

    # Create free choice conversation
    conversation = Conversation(
        agent_id=agent_id,
        title=f"Free Choice Session - {now.strftime('%Y-%m-%d %H:%M')}",
        conversation_type="free_choice"
    )
    db.add(conversation)
    db.flush()  # Get the conversation ID

    # Create the initial system prompt for free choice
    free_choice_prompt = """You have free time to explore and learn autonomously. You can:

- **Search the web** for topics that interest you (web_search, fetch_url) - max 10 pages
- **Review your memories** to find patterns or insights (search_memories, fetch_memories)
- **Organize your thoughts** by updating journal blocks (list_journal_blocks, update_journal_block)
- **Explore your knowledge base** (list_rag_files)

What would you like to explore or reflect on? This is your time to learn, think, and grow.

Remember: You're limited to 10 web page fetches and 20 total tool calls per session."""

    # Add the prompt as a system message
    system_message = Message(
        conversation_id=conversation.id,
        role="system",
        content=free_choice_prompt,
        metadata_={"type": "free_choice_prompt"}
    )
    db.add(system_message)

    # Update the last free choice timestamp
    agent.last_free_choice_at = now

    db.commit()
    db.refresh(conversation)

    return {
        "status": "started",
        "conversation_id": str(conversation.id),
        "message": "Free choice session started. Agent is ready to explore.",
        "started_at": now.isoformat()
    }

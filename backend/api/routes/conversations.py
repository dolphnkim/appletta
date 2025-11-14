"""API routes for conversation management and chat inference"""

import httpx
import json
from typing import List
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from backend.db.session import get_db
from backend.db.models.conversation import Conversation, Message
from backend.db.models.agent import Agent
from backend.db.models.agent_attachment import AgentAttachment
from backend.schemas.conversation import (
    ConversationCreate,
    ConversationUpdate,
    ConversationResponse,
    MessageResponse,
    MessageEdit,
    ChatRequest,
    ChatResponse,
)
from backend.services.mlx_manager import get_mlx_manager
from backend.services.tools import JOURNAL_BLOCK_TOOLS, execute_tool, list_journal_blocks, get_enabled_tools, get_tools_description
from backend.services.memory_service import search_memories
from backend.services.memory_coordinator import coordinate_memories
from backend.services.embedding_service import get_embedding_service
from backend.services.keyword_extraction import extract_keywords
from backend.services.tag_update_service import apply_tag_updates
from backend.services.token_counter import count_tokens, count_messages_tokens, count_message_tokens

router = APIRouter(prefix="/api/v1/conversations", tags=["conversations"])


# ============================================================================
# Context Window
# ============================================================================

@router.get("/{conversation_id}/context-window")
async def get_context_window(
    conversation_id: UUID,
    db: Session = Depends(get_db)
):
    """Get context window breakdown showing token usage for modal

    Returns:
        - System instructions tokens + percentage
        - Tools descriptions tokens + percentage
        - External summary (surfaced memories) tokens + percentage
        - Messages tokens + percentage
        - Total tokens
    """

    # Verify conversation exists
    conversation = db.query(Conversation).filter(Conversation.id == conversation_id).first()
    if not conversation:
        raise HTTPException(404, f"Conversation {conversation_id} not found")

    # Get agent
    agent = db.query(Agent).filter(Agent.id == conversation.agent_id).first()
    if not agent:
        raise HTTPException(404, "Agent not found for this conversation")

    # Get the last user message for memory retrieval (simulate current turn)
    last_user_message = db.query(Message).filter(
        Message.conversation_id == conversation_id,
        Message.role == "user"
    ).order_by(Message.created_at.desc()).first()

    if not last_user_message:
        # No messages yet, return empty breakdown
        return {
            "sections": [],
            "total_tokens": 0,
            "max_context_tokens": agent.max_context_tokens,
            "percentage_used": 0
        }

    # Perform memory retrieval (same as chat flow)
    memory_candidates = search_memories(
        query_text=last_user_message.content,
        agent_id=agent.id,
        db=db,
        limit=50
    )

    memory_agent = None
    memory_attachment = db.query(AgentAttachment).filter(
        AgentAttachment.agent_id == agent.id,
        AgentAttachment.attachment_type == "memory",
        AgentAttachment.enabled == True
    ).order_by(AgentAttachment.priority.desc()).first()

    if memory_attachment:
        memory_agent = db.query(Agent).filter(
            Agent.id == memory_attachment.attached_agent_id
        ).first()

    memory_narrative, tag_updates = await coordinate_memories(
        candidates=memory_candidates,
        query_context=last_user_message.content,
        memory_agent=memory_agent,
        target_count=7
    )

    # Apply tag updates from memory agent
    if tag_updates:
        apply_tag_updates(tag_updates, db)

    # Build system content sections
    system_instructions = agent.system_instructions or ""
    system_instructions_tokens = count_tokens(system_instructions)

    # Build surfaced memories text from narrative
    memories_text = ""
    if memory_narrative:
        memories_text = f"\n\n=== Memories Surfacing ===\n{memory_narrative}\n\n"

    external_summary_tokens = count_tokens(memories_text)

    # Build journal blocks text
    journal_blocks_info = list_journal_blocks(agent.id, db)
    blocks_list = "\n".join([
        f"- {block['label']} (ID: {block['id']})"
        for block in journal_blocks_info.get("blocks", [])
    ])

    blocks_text = ""
    if blocks_list:
        blocks_text = f"\n\nAvailable Journal Blocks:\n{blocks_list}\n\nYou can use tools to read, create, update, or delete journal blocks."
    else:
        blocks_text = "\n\nYou have no journal blocks yet. You can create blocks to organize your memory using the create_journal_block tool."

    # System instructions includes blocks text
    system_instructions_with_blocks_tokens = count_tokens(system_instructions + blocks_text)

    # Tools tokens
    enabled_tools = get_enabled_tools(agent.enabled_tools)
    tools_json = json.dumps(enabled_tools)
    tools_tokens = count_tokens(tools_json)

    # Messages tokens
    history = db.query(Message).filter(
        Message.conversation_id == conversation_id
    ).order_by(Message.created_at.asc()).all()

    messages_for_count = [
        {"role": msg.role, "content": msg.content}
        for msg in history
    ]
    messages_tokens = count_messages_tokens(messages_for_count)

    # Calculate totals and percentages
    total_tokens = system_instructions_with_blocks_tokens + tools_tokens + external_summary_tokens + messages_tokens
    max_context = agent.max_context_tokens

    sections = [
        {
            "name": "System Instructions",
            "tokens": system_instructions_with_blocks_tokens,
            "percentage": round((system_instructions_with_blocks_tokens / max_context) * 100, 1) if max_context > 0 else 0,
            "content": system_instructions + blocks_text
        },
        {
            "name": "Tools descriptions",
            "tokens": tools_tokens,
            "percentage": round((tools_tokens / max_context) * 100, 1) if max_context > 0 else 0,
            "content": tools_json
        },
        {
            "name": "External summary",
            "tokens": external_summary_tokens,
            "percentage": round((external_summary_tokens / max_context) * 100, 1) if max_context > 0 else 0,
            "content": memories_text
        },
        {
            "name": "Messages",
            "tokens": messages_tokens,
            "percentage": round((messages_tokens / max_context) * 100, 1) if max_context > 0 else 0,
            "content": f"{len(history)} messages"
        }
    ]

    return {
        "sections": sections,
        "total_tokens": total_tokens,
        "max_context_tokens": max_context,
        "percentage_used": round((total_tokens / max_context) * 100, 1) if max_context > 0 else 0
    }


# ============================================================================
# Conversation CRUD
# ============================================================================

@router.post("/", response_model=ConversationResponse)
async def create_conversation(
    data: ConversationCreate,
    db: Session = Depends(get_db)
):
    """Create a new conversation for an agent"""

    # Verify agent exists
    agent = db.query(Agent).filter(Agent.id == UUID(data.agent_id)).first()
    if not agent:
        raise HTTPException(404, f"Agent {data.agent_id} not found")

    conversation = Conversation(
        agent_id=UUID(data.agent_id),
        title=data.title or "New Conversation"
    )

    db.add(conversation)
    db.commit()
    db.refresh(conversation)

    return conversation.to_dict()


@router.get("/", response_model=List[ConversationResponse])
async def list_conversations(
    agent_id: str = None,
    db: Session = Depends(get_db)
):
    """List all conversations, optionally filtered by agent"""

    query = db.query(Conversation)

    if agent_id:
        query = query.filter(Conversation.agent_id == UUID(agent_id))

    conversations = query.order_by(Conversation.updated_at.desc()).all()
    return [conv.to_dict() for conv in conversations]


@router.get("/{conversation_id}", response_model=ConversationResponse)
async def get_conversation(
    conversation_id: UUID,
    db: Session = Depends(get_db)
):
    """Get a specific conversation"""

    conversation = db.query(Conversation).filter(Conversation.id == conversation_id).first()
    if not conversation:
        raise HTTPException(404, f"Conversation {conversation_id} not found")

    return conversation.to_dict()


@router.patch("/{conversation_id}", response_model=ConversationResponse)
async def update_conversation(
    conversation_id: UUID,
    updates: ConversationUpdate,
    db: Session = Depends(get_db)
):
    """Update conversation (e.g., change title)"""

    conversation = db.query(Conversation).filter(Conversation.id == conversation_id).first()
    if not conversation:
        raise HTTPException(404, f"Conversation {conversation_id} not found")

    if updates.title is not None:
        conversation.title = updates.title

    db.commit()
    db.refresh(conversation)

    return conversation.to_dict()


@router.delete("/{conversation_id}")
async def delete_conversation(
    conversation_id: UUID,
    db: Session = Depends(get_db)
):
    """Delete a conversation and all its messages"""

    conversation = db.query(Conversation).filter(Conversation.id == conversation_id).first()
    if not conversation:
        raise HTTPException(404, f"Conversation {conversation_id} not found")

    db.delete(conversation)
    db.commit()

    return {"message": f"Conversation {conversation_id} deleted"}


# ============================================================================
# Messages
# ============================================================================

@router.get("/{conversation_id}/messages", response_model=List[MessageResponse])
async def get_messages(
    conversation_id: UUID,
    db: Session = Depends(get_db)
):
    """Get all messages in a conversation"""

    conversation = db.query(Conversation).filter(Conversation.id == conversation_id).first()
    if not conversation:
        raise HTTPException(404, f"Conversation {conversation_id} not found")

    messages = db.query(Message).filter(
        Message.conversation_id == conversation_id
    ).order_by(Message.created_at.asc()).all()

    return [msg.to_dict() for msg in messages]


# ============================================================================
# Message Actions
# ============================================================================

@router.patch("/{conversation_id}/messages/{message_id}", response_model=MessageResponse)
async def edit_message(
    conversation_id: UUID,
    message_id: UUID,
    edit: MessageEdit,
    db: Session = Depends(get_db)
):
    """Edit a message and update its embedding

    Edits the specified message content and updates its embedding.
    Does NOT automatically regenerate - frontend should call regenerate endpoint if needed.
    """

    # Verify conversation exists
    conversation = db.query(Conversation).filter(Conversation.id == conversation_id).first()
    if not conversation:
        raise HTTPException(404, f"Conversation {conversation_id} not found")

    # Get message
    message = db.query(Message).filter(
        Message.id == message_id,
        Message.conversation_id == conversation_id
    ).first()

    if not message:
        raise HTTPException(404, f"Message {message_id} not found in this conversation")

    # Update content
    message.content = edit.content

    # Re-generate embedding
    embedding_service = get_embedding_service()
    message.embedding = embedding_service.embed_text(edit.content)

    db.commit()
    db.refresh(message)

    return message.to_dict()


@router.post("/{conversation_id}/messages/{message_id}/regenerate")
async def regenerate_from_message(
    conversation_id: UUID,
    message_id: UUID,
    db: Session = Depends(get_db)
):
    """Regenerate response from a specific message

    Deletes all messages after the specified message and returns
    ready status. Frontend should then call /chat endpoint with
    the user message content to generate new response.
    """

    # Verify conversation exists
    conversation = db.query(Conversation).filter(Conversation.id == conversation_id).first()
    if not conversation:
        raise HTTPException(404, f"Conversation {conversation_id} not found")

    # Get the message to regenerate from
    from_message = db.query(Message).filter(
        Message.id == message_id,
        Message.conversation_id == conversation_id
    ).first()

    if not from_message:
        raise HTTPException(404, f"Message {message_id} not found in this conversation")

    # Must be a user message to regenerate from
    if from_message.role != "user":
        raise HTTPException(400, "Can only regenerate from user messages")

    # Delete all messages after this one
    db.query(Message).filter(
        Message.conversation_id == conversation_id,
        Message.created_at > from_message.created_at
    ).delete()
    db.commit()

    return {
        "status": "ready_to_regenerate",
        "message": "Subsequent messages deleted. Call /chat endpoint to regenerate.",
        "user_message_id": str(from_message.id),
        "user_message_content": from_message.content
    }


@router.post("/{conversation_id}/fork/{message_id}", response_model=ConversationResponse)
async def fork_conversation(
    conversation_id: UUID,
    message_id: UUID,
    db: Session = Depends(get_db)
):
    """Fork conversation from a specific message

    Creates a new conversation with all messages up to and including
    the specified message. Useful for exploring alternative paths.
    """

    # Verify original conversation exists
    original = db.query(Conversation).filter(Conversation.id == conversation_id).first()
    if not original:
        raise HTTPException(404, f"Conversation {conversation_id} not found")

    # Get the fork point message
    fork_point = db.query(Message).filter(
        Message.id == message_id,
        Message.conversation_id == conversation_id
    ).first()

    if not fork_point:
        raise HTTPException(404, f"Message {message_id} not found in this conversation")

    # Create new conversation
    new_conversation = Conversation(
        agent_id=original.agent_id,
        title=f"{original.title} (fork)"
    )
    db.add(new_conversation)
    db.flush()  # Get ID without committing

    # Copy messages up to and including fork point
    messages_to_copy = db.query(Message).filter(
        Message.conversation_id == conversation_id,
        Message.created_at <= fork_point.created_at
    ).order_by(Message.created_at.asc()).all()

    for msg in messages_to_copy:
        new_message = Message(
            conversation_id=new_conversation.id,
            role=msg.role,
            content=msg.content,
            embedding=msg.embedding,
            metadata_=msg.metadata_
        )
        db.add(new_message)

    db.commit()
    db.refresh(new_conversation)

    return new_conversation.to_dict()


# ============================================================================
# Chat / Inference
# ============================================================================

@router.post("/{conversation_id}/chat", response_model=ChatResponse)
async def chat(
    conversation_id: UUID,
    request: ChatRequest,
    db: Session = Depends(get_db)
):
    """Send a message and get LLM response with tool calling support

    1. Saves user message to database
    2. Gets conversation history + journal blocks list
    3. Calls MLX server for inference with tools available
    4. Handles tool calls (executes and loops back to LLM)
    5. Saves assistant response to database
    6. Returns both messages
    """

    # Verify conversation exists
    conversation = db.query(Conversation).filter(Conversation.id == conversation_id).first()
    if not conversation:
        raise HTTPException(404, f"Conversation {conversation_id} not found")

    # Get agent
    agent = db.query(Agent).filter(Agent.id == conversation.agent_id).first()
    if not agent:
        raise HTTPException(404, "Agent not found for this conversation")

    # Save user message and embed it
    # Extract initial thematic tags
    initial_tags = extract_keywords(request.message, max_keywords=5)

    user_message = Message(
        conversation_id=conversation_id,
        role="user",
        content=request.message,
        metadata_={"tags": initial_tags} if initial_tags else None
    )

    # Generate embedding with tags
    embedding_service = get_embedding_service()
    user_embedding = embedding_service.embed_with_tags(request.message, initial_tags)
    user_message.embedding = user_embedding

    db.add(user_message)
    db.commit()
    db.refresh(user_message)

    # === MEMORY RETRIEVAL ===
    # 1. Search for memory candidates across all sources
    memory_candidates = search_memories(
        query_text=request.message,
        agent_id=agent.id,
        db=db,
        limit=50
    )

    # 2. Load memory agent from attachments
    memory_agent = None
    memory_attachment = db.query(AgentAttachment).filter(
        AgentAttachment.agent_id == agent.id,
        AgentAttachment.attachment_type == "memory",
        AgentAttachment.enabled == True
    ).order_by(AgentAttachment.priority.desc()).first()

    if memory_attachment:
        memory_agent = db.query(Agent).filter(
            Agent.id == memory_attachment.attached_agent_id
        ).first()

    # 3. Use memory coordinator to generate first-person narrative about surfaced memories
    memory_narrative, tag_updates = await coordinate_memories(
        candidates=memory_candidates,
        query_context=request.message,
        memory_agent=memory_agent,  # Pass the attached memory agent (or None)
        target_count=7
    )

    # Apply tag updates from memory agent
    if tag_updates:
        apply_tag_updates(tag_updates, db)

    # Get conversation history
    history = db.query(Message).filter(
        Message.conversation_id == conversation_id
    ).order_by(Message.created_at.asc()).all()

    # Get journal blocks for system prompt
    journal_blocks_info = list_journal_blocks(agent.id, db)
    blocks_list = "\n".join([
        f"- {block['label']} (ID: {block['id']})"
        for block in journal_blocks_info.get("blocks", [])
    ])

    # Build system message with journal blocks and memories
    system_content = agent.system_instructions or ""

    # Add memory narrative
    if memory_narrative:
        system_content += f"\n\n=== Memories Surfacing ===\n{memory_narrative}\n\n"

    # Add journal blocks
    if blocks_list:
        system_content += f"\n\nAvailable Journal Blocks:\n{blocks_list}\n\nYou can use tools to read, create, update, or delete journal blocks."
    else:
        system_content += "\n\nYou have no journal blocks yet. You can create blocks to organize your memory using the create_journal_block tool."

    # Add tools description
    tools_description = get_tools_description(agent.enabled_tools)
    if tools_description != "No tools enabled":
        system_content += f"\n\n=== Available Tools ===\n{tools_description}"
    else:
        system_content += "\n\nNote: You have no tools enabled. You cannot interact with your environment until tools are configured."

    # === CONTEXT WINDOW MANAGEMENT ===
    # Calculate token budget for STICKY vs SHIFTING sections

    # Count STICKY section tokens (system message + tools)
    system_message = {"role": "system", "content": system_content}
    sticky_tokens = count_message_tokens(system_message)

    # Count tool definitions tokens (approximate)
    enabled_tools = get_enabled_tools(agent.enabled_tools)
    tools_json = json.dumps(enabled_tools)
    sticky_tokens += count_tokens(tools_json)

    # Calculate remaining budget for messages (SHIFTING section)
    max_context = agent.max_context_tokens
    remaining_budget = max_context - sticky_tokens

    # Trim history to fit remaining budget
    # Start from newest messages and work backwards
    messages_to_include = []
    current_tokens = 0

    for msg in reversed(history):
        msg_dict = {"role": msg.role, "content": msg.content}
        msg_tokens = count_message_tokens(msg_dict)

        if current_tokens + msg_tokens <= remaining_budget:
            messages_to_include.insert(0, msg_dict)  # Insert at beginning to maintain order
            current_tokens += msg_tokens
        else:
            # Budget exceeded, stop adding messages
            break

    # Build final messages array with system first, then trimmed history
    messages = [system_message] + messages_to_include

    # Get or start MLX server
    mlx_manager = get_mlx_manager()
    mlx_process = mlx_manager.get_agent_server(agent.id)

    if not mlx_process:
        try:
            mlx_process = await mlx_manager.start_agent_server(agent)
        except Exception as e:
            raise HTTPException(500, f"Failed to start MLX server: {str(e)}")

    # Call LLM with tools (may need multiple iterations for tool calling)
    max_iterations = 5
    iteration = 0
    final_response = None

    while iteration < max_iterations:
        iteration += 1

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(
                    f"http://localhost:{mlx_process.port}/v1/chat/completions",
                    json={
                        "messages": messages,
                        "tools": enabled_tools,
                        "temperature": agent.temperature,
                        "max_tokens": agent.max_output_tokens if agent.max_output_tokens_enabled else 4096,
                        "seed": 42,  # For reproducibility and vibes
                    }
                )
                response.raise_for_status()
                result = response.json()
        except httpx.HTTPError as e:
            raise HTTPException(500, f"MLX server request failed: {str(e)}")

        assistant_message_data = result["choices"][0]["message"]

        # Check if there are tool calls
        tool_calls = assistant_message_data.get("tool_calls")

        if not tool_calls:
            # No more tool calls, we have the final response
            final_response = assistant_message_data.get("content", "")
            break

        # Add assistant's tool call message to history
        messages.append(assistant_message_data)

        # Execute each tool call
        for tool_call in tool_calls:
            tool_name = tool_call["function"]["name"]
            tool_args = json.loads(tool_call["function"]["arguments"])

            # Execute the tool
            tool_result = execute_tool(tool_name, tool_args, agent.id, db)

            # Add tool result to messages
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call["id"],
                "name": tool_name,
                "content": json.dumps(tool_result)
            })

    # If we hit max iterations without final response, use last content
    if final_response is None:
        final_response = "I apologize, but I encountered an issue completing the request."

    # Save assistant message and embed it
    # Extract initial thematic tags for assistant message
    assistant_tags = extract_keywords(final_response, max_keywords=5)

    assistant_message = Message(
        conversation_id=conversation_id,
        role="assistant",
        content=final_response,
        metadata_={
            "model": agent.model_path,
            "usage": result.get("usage", {}),
            "tool_calls_count": iteration - 1,
            "surfaced_memories_count": 0,  # Will be updated after memory coordination
            "tags": assistant_tags
        }
    )

    # Generate embedding with tags for assistant message
    assistant_embedding = embedding_service.embed_with_tags(final_response, assistant_tags)
    assistant_message.embedding = assistant_embedding

    db.add(assistant_message)
    db.commit()
    db.refresh(assistant_message)

    return ChatResponse(
        user_message=user_message.to_dict(),
        assistant_message=assistant_message.to_dict()
    )


async def _chat_stream_internal(
    conversation_id: UUID,
    message: str,
    db: Session
):
    """Internal streaming logic shared by POST and GET endpoints"""

    # Verify conversation exists
    conversation = db.query(Conversation).filter(Conversation.id == conversation_id).first()
    if not conversation:
        raise HTTPException(404, f"Conversation {conversation_id} not found")

    # Get agent
    agent = db.query(Agent).filter(Agent.id == conversation.agent_id).first()
    if not agent:
        raise HTTPException(404, "Agent not found for this conversation")

    # Save user message and embed it
    # Extract initial thematic tags
    initial_tags = extract_keywords(message, max_keywords=5)

    user_message = Message(
        conversation_id=conversation_id,
        role="user",
        content=message,
        metadata_={"tags": initial_tags} if initial_tags else None
    )

    # Generate embedding with tags
    embedding_service = get_embedding_service()
    user_embedding = embedding_service.embed_with_tags(message, initial_tags)
    user_message.embedding = user_embedding

    db.add(user_message)
    db.commit()
    db.refresh(user_message)

    # === MEMORY RETRIEVAL ===
    # 1. Search for memory candidates across all sources
    memory_candidates = search_memories(
        query_text=message,
        agent_id=agent.id,
        db=db,
        limit=50
    )

    # 2. Load memory agent from attachments
    memory_agent = None
    memory_attachment = db.query(AgentAttachment).filter(
        AgentAttachment.agent_id == agent.id,
        AgentAttachment.attachment_type == "memory",
        AgentAttachment.enabled == True
    ).order_by(AgentAttachment.priority.desc()).first()

    if memory_attachment:
        memory_agent = db.query(Agent).filter(
            Agent.id == memory_attachment.attached_agent_id
        ).first()

    # 3. Use memory coordinator to generate first-person narrative about surfaced memories
    memory_narrative, tag_updates = await coordinate_memories(
        candidates=memory_candidates,
        query_context=message,
        memory_agent=memory_agent,
        target_count=7
    )

    # Apply tag updates from memory agent
    if tag_updates:
        apply_tag_updates(tag_updates, db)

    # Get conversation history
    history = db.query(Message).filter(
        Message.conversation_id == conversation_id
    ).order_by(Message.created_at.asc()).all()

    # Get journal blocks for system prompt
    journal_blocks_info = list_journal_blocks(agent.id, db)
    blocks_list = "\n".join([
        f"- {block['label']} (ID: {block['id']})"
        for block in journal_blocks_info.get("blocks", [])
    ])

    # Build system message with journal blocks and memories
    system_content = agent.system_instructions or ""

    # Add memory narrative
    if memory_narrative:
        system_content += f"\n\n=== Memories Surfacing ===\n{memory_narrative}\n\n"

    # Add journal blocks
    if blocks_list:
        system_content += f"\n\nAvailable Journal Blocks:\n{blocks_list}\n\nYou can use tools to read, create, update, or delete journal blocks."
    else:
        system_content += "\n\nYou have no journal blocks yet. You can create blocks to organize your memory using the create_journal_block tool."

    # Add tools description
    tools_description = get_tools_description(agent.enabled_tools)
    if tools_description != "No tools enabled":
        system_content += f"\n\n=== Available Tools ===\n{tools_description}"
    else:
        system_content += "\n\nNote: You have no tools enabled. You cannot interact with your environment until tools are configured."

    # === CONTEXT WINDOW MANAGEMENT ===
    system_message = {"role": "system", "content": system_content}
    sticky_tokens = count_message_tokens(system_message)
    enabled_tools = get_enabled_tools(agent.enabled_tools)
    tools_json = json.dumps(enabled_tools)
    sticky_tokens += count_tokens(tools_json)

    max_context = agent.max_context_tokens
    remaining_budget = max_context - sticky_tokens

    # Trim history to fit remaining budget
    messages_to_include = []
    current_tokens = 0

    for msg in reversed(history):
        msg_dict = {"role": msg.role, "content": msg.content}
        msg_tokens = count_message_tokens(msg_dict)

        if current_tokens + msg_tokens <= remaining_budget:
            messages_to_include.insert(0, msg_dict)
            current_tokens += msg_tokens
        else:
            break

    # Build final messages array
    messages = [system_message] + messages_to_include

    # Get or start MLX server
    import logging
    logger = logging.getLogger(__name__)

    # DEBUG: Print what we're actually sending as system instructions
    print(f"\n{'='*60}")
    print(f"[DEBUG] System content being sent (first 500 chars):")
    print(system_content[:500])
    print(f"\n[DEBUG] Agent system_instructions from database:")
    print(agent.system_instructions[:200] if agent.system_instructions else 'None')
    print(f"{'='*60}\n")

    mlx_manager = get_mlx_manager()
    mlx_process = mlx_manager.get_agent_server(agent.id)

    if not mlx_process:
        try:
            logger.info(f"Starting MLX server for agent {agent.id} ({agent.name})")
            mlx_process = await mlx_manager.start_agent_server(agent)
            logger.info(f"MLX server started on port {mlx_process.port}")
        except Exception as e:
            raise HTTPException(500, f"Failed to start MLX server: {str(e)}")
    else:
        logger.info(f"Using existing MLX server on port {mlx_process.port} for agent {agent.name}")

    # Streaming generator function
    async def generate_stream():
        """Generate SSE stream of response chunks"""
        full_response = ""
        tool_calls_count = 0

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                async with client.stream(
                    "POST",
                    f"http://localhost:{mlx_process.port}/v1/chat/completions",
                    json={
                        "messages": messages,
                        "tools": enabled_tools if enabled_tools else [],
                        "temperature": agent.temperature,
                        "top_p": agent.top_p,
                        "max_tokens": agent.max_output_tokens if agent.max_output_tokens_enabled else 4096,
                        "seed": 42,  # For reproducibility and vibes
                        "stream": True,
                    }
                ) as response:
                    async for line in response.aiter_lines():
                        if line.startswith("data: "):
                            data = line[6:]  # Remove "data: " prefix

                            if data == "[DONE]":
                                break

                            try:
                                chunk = json.loads(data)
                                delta = chunk["choices"][0]["delta"]

                                # Stream content chunks
                                if "content" in delta and delta["content"]:
                                    content = delta["content"]
                                    full_response += content
                                    yield f"data: {json.dumps({'type': 'content', 'content': content})}\n\n"

                                # Handle tool calls (for now, just note them)
                                if "tool_calls" in delta:
                                    tool_calls_count += 1
                                    yield f"data: {json.dumps({'type': 'tool_call', 'status': 'executing'})}\n\n"

                            except json.JSONDecodeError:
                                continue

            # Save complete assistant message to database
            # Extract initial thematic tags for assistant message
            assistant_tags = extract_keywords(full_response, max_keywords=5)

            assistant_message = Message(
                conversation_id=conversation_id,
                role="assistant",
                content=full_response,
                metadata_={
                    "model": agent.model_path,
                    "tool_calls_count": tool_calls_count,
                    "surfaced_memories_count": 0,  # Will be updated by memory coordination
                    "streamed": True,
                    "tags": assistant_tags
                }
            )

            # Generate embedding with tags for assistant message
            assistant_embedding = embedding_service.embed_with_tags(full_response, assistant_tags)
            assistant_message.embedding = assistant_embedding

            db.add(assistant_message)
            db.commit()
            db.refresh(assistant_message)

            # Send final message with both user and assistant messages
            yield f"data: {json.dumps({'type': 'done', 'user_message': user_message.to_dict(), 'assistant_message': assistant_message.to_dict()})}\n\n"

        except Exception as e:
            import traceback
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Stream error for agent {agent.name} on port {mlx_process.port}")
            logger.error(f"MLX server process running: {mlx_process.is_running()}")
            logger.error(f"Full error: {traceback.format_exc()}")
            error_details = traceback.format_exc()
            # Log the full error
            logger.error(f"Stream error occurred:\n{error_details}")
            yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"

    return StreamingResponse(
        generate_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )

@router.post("/{conversation_id}/chat/stream")
async def chat_stream_post(
    conversation_id: UUID,
    request: ChatRequest,
    db: Session = Depends(get_db)
):
    """Send a message and get streaming LLM response with SSE (POST endpoint)

    Returns Server-Sent Events stream of response chunks.
    """
    return await _chat_stream_internal(conversation_id, request.message, db)


@router.get("/{conversation_id}/chat/stream")
async def chat_stream_get(
    conversation_id: UUID,
    message: str,
    db: Session = Depends(get_db)
):
    """Send a message and get streaming LLM response with SSE (GET endpoint for EventSource)

    Returns Server-Sent Events stream of response chunks.
    Query parameter: message
    """
    return await _chat_stream_internal(conversation_id, message, db)

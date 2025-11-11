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
    ChatRequest,
    ChatResponse,
)
from backend.services.mlx_manager import get_mlx_manager
from backend.services.tools import JOURNAL_BLOCK_TOOLS, execute_tool, list_journal_blocks
from backend.services.memory_service import search_memories, fetch_full_memories
from backend.services.memory_coordinator import coordinate_memories
from backend.services.embedding_service import get_embedding_service
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

    selected_memory_ids = await coordinate_memories(
        candidates=memory_candidates,
        query_context=last_user_message.content,
        memory_agent=memory_agent,
        target_count=7
    )

    surfaced_memories = fetch_full_memories(selected_memory_ids, db)

    # Build system content sections
    system_instructions = agent.system_instructions or ""
    system_instructions_tokens = count_tokens(system_instructions)

    # Build surfaced memories text
    memories_text = ""
    if surfaced_memories:
        memories_text = "\n\n=== Surfaced Memories ===\n"
        memories_text += "The following memories may be relevant to the current conversation:\n\n"
        for memory in surfaced_memories:
            memories_text += f"[{memory['source_type']}] {memory.get('title', 'Untitled')}\n"
            memories_text += f"{memory['content']}\n\n"

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
    tools_json = json.dumps(JOURNAL_BLOCK_TOOLS)
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
    user_message = Message(
        conversation_id=conversation_id,
        role="user",
        content=request.message
    )

    # Generate embedding for user message
    embedding_service = get_embedding_service()
    user_embedding = embedding_service.embed_text(request.message)
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

    # 3. Use memory coordinator to select which memories to surface
    selected_memory_ids = await coordinate_memories(
        candidates=memory_candidates,
        query_context=request.message,
        memory_agent=memory_agent,  # Pass the attached memory agent (or None)
        target_count=7
    )

    # 4. Fetch full content of selected memories
    surfaced_memories = fetch_full_memories(selected_memory_ids, db)

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

    # Add surfaced memories
    if surfaced_memories:
        memories_text = "\n\n=== Surfaced Memories ===\n"
        memories_text += "The following memories may be relevant to the current conversation:\n\n"
        for memory in surfaced_memories:
            memories_text += f"[{memory['source_type']}] {memory.get('title', 'Untitled')}\n"
            memories_text += f"{memory['content']}\n\n"
        system_content += memories_text

    # Add journal blocks
    if blocks_list:
        system_content += f"\n\nAvailable Journal Blocks:\n{blocks_list}\n\nYou can use tools to read, create, update, or delete journal blocks."
    else:
        system_content += "\n\nYou have no journal blocks yet. You can create blocks to organize your memory using the create_journal_block tool."

    # === CONTEXT WINDOW MANAGEMENT ===
    # Calculate token budget for STICKY vs SHIFTING sections

    # Count STICKY section tokens (system message + tools)
    system_message = {"role": "system", "content": system_content}
    sticky_tokens = count_message_tokens(system_message)

    # Count tool definitions tokens (approximate)
    tools_json = json.dumps(JOURNAL_BLOCK_TOOLS)
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
                        "tools": JOURNAL_BLOCK_TOOLS,
                        "temperature": agent.temperature,
                        "max_tokens": agent.max_output_tokens if agent.max_output_tokens_enabled else None,
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
    assistant_message = Message(
        conversation_id=conversation_id,
        role="assistant",
        content=final_response,
        metadata={
            "model": agent.model_path,
            "usage": result.get("usage", {}),
            "tool_calls_count": iteration - 1,
            "surfaced_memories_count": len(surfaced_memories)
        }
    )

    # Generate embedding for assistant message
    assistant_embedding = embedding_service.embed_text(final_response)
    assistant_message.embedding = assistant_embedding

    db.add(assistant_message)
    db.commit()
    db.refresh(assistant_message)

    return ChatResponse(
        user_message=user_message.to_dict(),
        assistant_message=assistant_message.to_dict()
    )


@router.post("/{conversation_id}/chat/stream")
async def chat_stream(
    conversation_id: UUID,
    request: ChatRequest,
    db: Session = Depends(get_db)
):
    """Send a message and get streaming LLM response with SSE

    Returns Server-Sent Events stream of response chunks.
    Handles tool calling between streaming chunks.
    Saves complete message to database after streaming completes.
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
    user_message = Message(
        conversation_id=conversation_id,
        role="user",
        content=request.message
    )

    # Generate embedding for user message
    embedding_service = get_embedding_service()
    user_embedding = embedding_service.embed_text(request.message)
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

    # 3. Use memory coordinator to select which memories to surface
    selected_memory_ids = await coordinate_memories(
        candidates=memory_candidates,
        query_context=request.message,
        memory_agent=memory_agent,
        target_count=7
    )

    # 4. Fetch full content of selected memories
    surfaced_memories = fetch_full_memories(selected_memory_ids, db)

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

    # Add surfaced memories
    if surfaced_memories:
        memories_text = "\n\n=== Surfaced Memories ===\n"
        memories_text += "The following memories may be relevant to the current conversation:\n\n"
        for memory in surfaced_memories:
            memories_text += f"[{memory['source_type']}] {memory.get('title', 'Untitled')}\n"
            memories_text += f"{memory['content']}\n\n"
        system_content += memories_text

    # Add journal blocks
    if blocks_list:
        system_content += f"\n\nAvailable Journal Blocks:\n{blocks_list}\n\nYou can use tools to read, create, update, or delete journal blocks."
    else:
        system_content += "\n\nYou have no journal blocks yet. You can create blocks to organize your memory using the create_journal_block tool."

    # === CONTEXT WINDOW MANAGEMENT ===
    system_message = {"role": "system", "content": system_content}
    sticky_tokens = count_message_tokens(system_message)
    tools_json = json.dumps(JOURNAL_BLOCK_TOOLS)
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
    mlx_manager = get_mlx_manager()
    mlx_process = mlx_manager.get_agent_server(agent.id)

    if not mlx_process:
        try:
            mlx_process = await mlx_manager.start_agent_server(agent)
        except Exception as e:
            raise HTTPException(500, f"Failed to start MLX server: {str(e)}")

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
                        "tools": JOURNAL_BLOCK_TOOLS,
                        "temperature": agent.temperature,
                        "max_tokens": agent.max_output_tokens if agent.max_output_tokens_enabled else None,
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
            assistant_message = Message(
                conversation_id=conversation_id,
                role="assistant",
                content=full_response,
                metadata={
                    "model": agent.model_path,
                    "tool_calls_count": tool_calls_count,
                    "surfaced_memories_count": len(surfaced_memories),
                    "streamed": True
                }
            )

            # Generate embedding for assistant message
            assistant_embedding = embedding_service.embed_text(full_response)
            assistant_message.embedding = assistant_embedding

            db.add(assistant_message)
            db.commit()
            db.refresh(assistant_message)

            # Send final message with database ID
            yield f"data: {json.dumps({'type': 'done', 'message_id': str(assistant_message.id)})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"

    return StreamingResponse(
        generate_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )

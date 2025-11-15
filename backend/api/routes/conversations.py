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
from backend.db.models.journal_block import JournalBlock
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
from backend.services.tools import execute_tool, list_journal_blocks
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

    # For context window display, we estimate memory tokens without actually
    # running the memory coordinator (which launches the slow 4B model).
    # We'll search for candidates and estimate based on the top results.
    memory_candidates = search_memories(
        query_text=last_user_message.content,
        agent_id=agent.id,
        db=db,
        limit=7  # Just top 7 for estimation
    )

    # Estimate memory narrative length (approximate format)
    memory_narrative = ""
    if memory_candidates:
        # Simulate the narrative format without actually running the 4B model
        memory_narrative = "I'm remembering:\n\n"
        for candidate in memory_candidates[:7]:
            memory_narrative += f"- {candidate.content[:150]}...\n"

    # Build system content sections
    project_instructions = agent.project_instructions or ""
    project_instructions_tokens = count_tokens(project_instructions)

    # Build external summary (RAG files, journal blocks, datetime)
    from datetime import datetime
    external_summary_parts = []

    # Add current datetime
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S %Z")
    external_summary_parts.append(f"Current time: {current_time}")

    # Add RAG folders/files
    from backend.db.models.rag import RagFolder, RagFile
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

    # System instructions tokens (journal blocks are now in External Summary, not here)
    project_instructions_tokens = count_tokens(project_instructions)

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
    total_tokens = project_instructions_tokens + external_summary_tokens + messages_tokens
    max_context = agent.max_context_tokens

    sections = [
        {
            "name": "Project Instructions",
            "tokens": project_instructions_tokens,
            "percentage": round((project_instructions_tokens / max_context) * 100, 1) if max_context > 0 else 0,
            "content": project_instructions
        },
        {
            "name": "External summary",
            "tokens": external_summary_tokens,
            "percentage": round((external_summary_tokens / max_context) * 100, 1) if max_context > 0 else 0,
            "content": external_summary_text
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


@router.delete("/{conversation_id}/messages/{message_id}")
async def delete_message(
    conversation_id: UUID,
    message_id: UUID,
    db: Session = Depends(get_db)
):
    """Delete a message from the conversation

    Removes the message from the database. This affects the conversation history
    and memory search results.
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

    # Delete message
    db.delete(message)
    db.commit()

    return {"success": True, "message": "Message deleted"}


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

    #CULPRIT ???
    # If regenerating from assistant message, find the user message before it
    if from_message.role == "assistant":
        # Find the most recent user message before this assistant message
        user_message = db.query(Message).filter(
            Message.conversation_id == conversation_id,
            Message.role == "user",
            Message.created_at < from_message.created_at
        ).order_by(Message.created_at.desc()).first()

        if not user_message:
            raise HTTPException(400, "No user message found before this assistant message")

        # Delete this assistant message and all after it
        db.query(Message).filter(
            Message.conversation_id == conversation_id,
            Message.created_at >= from_message.created_at
        ).delete()
        db.commit()

        return {
            "status": "ready_to_regenerate",
            "message": "Assistant message deleted. Call /chat endpoint to regenerate.",
            "user_message_id": str(user_message.id),
            "user_message_content": user_message.content
        }

    # If from user message, delete all messages after it
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

    # Get conversation history BEFORE the current user message (needed for context calculation)
    # We exclude the message we just added because it hasn't been answered yet
    history = db.query(Message).filter(
        Message.conversation_id == conversation_id,
        Message.id != user_message.id
    ).order_by(Message.created_at.asc()).all()

    # === PRE-CALCULATE CONTEXT WINDOW ===
    # Calculate which messages will be in context BEFORE searching memories

    preliminary_system_content = agent.project_instructions or ""
    from backend.services.token_counter import count_message_tokens, count_tokens
    preliminary_system_message = {"role": "system", "content": preliminary_system_content}
    sticky_tokens = count_message_tokens(preliminary_system_message)
    sticky_tokens += 1000  # Buffer for memories and journal blocks

    max_context = agent.max_context_tokens
    remaining_budget = max_context - sticky_tokens

    # Calculate which messages will fit in context
    messages_in_context = []
    context_message_ids = []
    current_tokens = 0

    for msg in reversed(history):
        msg_dict = {"role": msg.role, "content": msg.content}
        msg_tokens = count_message_tokens(msg_dict)

        if current_tokens + msg_tokens <= remaining_budget:
            messages_in_context.insert(0, msg)
            context_message_ids.append(str(msg.id))
            current_tokens += msg_tokens
        else:
            break

    # === MEMORY RETRIEVAL ===
    # 1. Search for memory candidates, EXCLUDING messages in active context window
    memory_candidates = search_memories(
        query_text=request.message,
        agent_id=agent.id,
        db=db,
        limit=50,
        exclude_message_ids=context_message_ids
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

    # Build system message with memories
    # Note: Journal blocks are NOT included in system prompt by default - they live in the database
    # and are retrieved via vector search (memory_service) when relevant.
    # EXCEPT: blocks marked with always_in_context=True are pinned to system content
    system_content = agent.project_instructions or ""

    # Add pinned journal blocks (always_in_context=True)
    pinned_blocks = db.query(JournalBlock).filter(
        JournalBlock.agent_id == agent.id,
        JournalBlock.always_in_context == True
    ).order_by(JournalBlock.updated_at.desc()).all()

    if pinned_blocks:
        system_content += "\n\n=== Pinned Information ==="
        for block in pinned_blocks:
            system_content += f"\n\n[{block.label}]\n{block.value}"

    # Add memory narrative as plain context (no <think> tags to avoid prompting base model)
    # The adapter personality should handle this naturally without format prompting
    if memory_narrative:
        # Sanitize the narrative - remove existing <think> tags, broken markdown, weird links
        import re
        sanitized = memory_narrative

        # Remove existing <think></think> tags and their content
        sanitized = re.sub(r'<think>.*?</think>', '', sanitized, flags=re.DOTALL)

        # Remove markdown image syntax ![](...)
        sanitized = re.sub(r'!\[.*?\]\(.*?\)', '', sanitized)

        # Remove standalone URLs (http/https links)
        sanitized = re.sub(r'https?://[^\s]+', '', sanitized)

        # Clean up extra whitespace
        sanitized = re.sub(r'\n\s*\n\s*\n+', '\n\n', sanitized)
        sanitized = sanitized.strip()

        # Only add if there's actual content after sanitizing
        if sanitized:
            system_content += f"\n\n=== Memories Surfacing ===\n{sanitized}\n"

    # Tools are handled by the wizard system, not via OpenAI function calling

    # Build final messages array using the pre-calculated messages_in_context
    # IMPORTANT: Add the current user message at the end (it's not in history yet)
    system_message = {"role": "system", "content": system_content}
    messages_to_include = [{"role": msg.role, "content": msg.content} for msg in messages_in_context]
    current_user_msg = {"role": "user", "content": request.message}
    messages = [system_message] + messages_to_include + [current_user_msg]

    # Get or start MLX server
    mlx_manager = get_mlx_manager()
    mlx_process = mlx_manager.get_agent_server(agent.id)

    if not mlx_process:
        try:
            mlx_process = await mlx_manager.start_agent_server(agent)
        except Exception as e:
            raise HTTPException(500, f"Failed to start MLX server: {str(e)}")

    # Simple LLM call - no tool calling loop, wizard handles all tools
    print(f"\n{'='*80}")
    print(f"🤖 MAIN AGENT LLM CALL - Agent: {agent.name}")
    print(f"{'='*80}")

    # VERBOSE: Show exactly what we're sending to the LLM
    request_payload = {
        "messages": messages,
        "temperature": agent.temperature,
        "max_tokens": agent.max_output_tokens if agent.max_output_tokens_enabled else 4096,
        "seed": 42,
    }

    print(f"\n📤 REQUEST TO MAIN LLM:")
    print(f"Port: {mlx_process.port}")
    print(f"Temperature: {agent.temperature}")
    print(f"Max Tokens: {agent.max_output_tokens if agent.max_output_tokens_enabled else 4096}")
    print(f"\n📨 MESSAGES ARRAY ({len(messages)} messages):")
    for i, msg in enumerate(messages):
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        print(f"\n  Message {i+1} [{role}]:")
        print(f"  {content[:500]}{'...' if len(content) > 500 else ''}")
    print(f"{'='*80}\n")

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"http://localhost:{mlx_process.port}/v1/chat/completions",
                json=request_payload
            )
            response.raise_for_status()
            result = response.json()

        # VERBOSE: Show exactly what the LLM responded with
        print(f"\n📥 RESPONSE FROM MAIN LLM:")
        assistant_msg = result.get("choices", [{}])[0].get("message", {})
        print(f"Role: {assistant_msg.get('role', 'unknown')}")
        content = assistant_msg.get("content", "")
        print(f"Content: {content[:500]}{'...' if len(content) > 500 else ''}")
        print(f"{'='*80}\n")

    except httpx.HTTPError as e:
        print(f"\n❌ MLX SERVER ERROR: {str(e)}\n")
        raise HTTPException(500, f"MLX server request failed: {str(e)}")

    final_response = result["choices"][0]["message"].get("content", "")

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

    # DEBUG: Log the incoming message
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"\n🔵 INCOMING MESSAGE: '{message[:200]}{'...' if len(message) > 200 else ''}'")

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

    # === GET MLX SERVER EARLY ===
    # We need this before wizard check because wizard loop calls LLM
    mlx_manager = get_mlx_manager()
    mlx_process = mlx_manager.get_agent_server(agent.id)

    if not mlx_process:
        try:
            mlx_process = await mlx_manager.start_agent_server(agent)
            logger.info(f"MLX server started on port {mlx_process.port}")
        except Exception as e:
            raise HTTPException(500, f"Failed to start MLX server: {str(e)}")
    else:
        logger.info(f"Using existing MLX server on port {mlx_process.port} for agent {agent.name}")

    # === BUILD CONTEXT WINDOW FIRST ===
    # We need to build the full context BEFORE wizard check so LLM sees everything

    # Get conversation history BEFORE the current user message (needed for context calculation)
    history = db.query(Message).filter(
        Message.conversation_id == conversation_id,
        Message.id != user_message.id
    ).order_by(Message.created_at.asc()).all()

    # Calculate which messages will fit in context
    preliminary_system_content = agent.project_instructions or ""
    from backend.services.token_counter import count_message_tokens, count_tokens
    preliminary_system_message = {"role": "system", "content": preliminary_system_content}
    sticky_tokens = count_message_tokens(preliminary_system_message)
    sticky_tokens += 1000  # Buffer for memories and journal blocks

    max_context = agent.max_context_tokens
    remaining_budget = max_context - sticky_tokens

    messages_in_context = []
    context_message_ids = []
    current_tokens = 0

    for msg in reversed(history):
        msg_dict = {"role": msg.role, "content": msg.content}
        msg_tokens = count_message_tokens(msg_dict)

        if current_tokens + msg_tokens <= remaining_budget:
            messages_in_context.insert(0, msg)
            context_message_ids.append(str(msg.id))
            current_tokens += msg_tokens
        else:
            break

    # === MEMORY RETRIEVAL ===
    memory_candidates = search_memories(
        query_text=message,
        agent_id=agent.id,
        db=db,
        limit=50,
        exclude_message_ids=context_message_ids
    )

    memory_agent = None
    memory_attachment = db.query(AgentAttachment).filter(
        AgentAttachment.agent_id == agent.id,
        AgentAttachment.attachment_type == "memory",
        AgentAttachment.enabled == True
    ).order_by(AgentAttachment.priority.desc()).first()

    memory_narrative = ""
    tag_updates = {}

    if memory_attachment:
        memory_agent = db.query(Agent).filter(
            Agent.id == memory_attachment.attached_agent_id
        ).first()

        if memory_agent and memory_candidates:
            memory_narrative, tag_updates = await coordinate_memories(
                current_message=message,
                memory_candidates=memory_candidates,
                memory_agent=memory_agent,
                db=db,
                mlx_manager=mlx_manager,
                main_model_path=agent.model_path
            )

            if tag_updates:
                apply_tag_updates(tag_updates, db)

    # Build system content with memories
    system_content = agent.project_instructions or ""

    # Add pinned journal blocks
    pinned_blocks = db.query(JournalBlock).filter(
        JournalBlock.agent_id == agent.id,
        JournalBlock.always_in_context == True
    ).order_by(JournalBlock.updated_at.desc()).all()

    if pinned_blocks:
        system_content += "\n\n=== Pinned Information ==="
        for block in pinned_blocks:
            system_content += f"\n\n[{block.label}]\n{block.value}"

    # Add memory narrative
    if memory_narrative:
        import re
        sanitized = memory_narrative
        sanitized = re.sub(r'<think>.*?</think>', '', sanitized, flags=re.DOTALL)
        sanitized = re.sub(r'!\[.*?\]\(.*?\)', '', sanitized)
        sanitized = re.sub(r'https?://[^\s]+', '', sanitized)
        sanitized = re.sub(r'\n\s*\n\s*\n+', '\n\n', sanitized)
        sanitized = sanitized.strip()

        if sanitized:
            system_content += f"\n\n=== Memories Surfacing ===\n{sanitized}\n"

    # Build base messages array (system + history + current user message)
    system_message = {"role": "system", "content": system_content}
    messages_to_include = [{"role": msg.role, "content": msg.content} for msg in messages_in_context]
    current_user_msg = {"role": "user", "content": message}
    base_messages = [system_message] + messages_to_include + [current_user_msg]

    print(f"\n📦 CONTEXT WINDOW BUILT:")
    print(f"  System content: {len(system_content)} chars")
    print(f"  History messages: {len(messages_in_context)}")
    print(f"  Total messages: {len(base_messages)}")
    print(f"  Memory narrative: {'Yes' if memory_narrative else 'No'}")

    # === TOOL WIZARD CHECK ===
    # If tools are enabled, use the wizard system to let LLM navigate menus and execute tools
    from backend.services.tool_wizard import get_wizard_state, process_wizard_step, show_main_menu, WizardState

    if agent.enabled_tools and len(agent.enabled_tools) > 0:
        # Wizard loop: inject prompts → call LLM → parse response → repeat until done
        # The LLM navigates the wizard menus and we execute tools when ready

        max_wizard_iterations = 10
        wizard_iteration = 0
        wizard_messages_to_add = []  # Track wizard messages to add to DB later
        tools_were_used = False  # Track if actual tools were executed
        final_chat_response = None  # Track if LLM chose to chat normally with a full response

        # ALWAYS show the menu first - this is MANDATORY
        # The LLM must choose an option before responding
        wizard_state = WizardState()  # Fresh state for each user message
        wizard_prompt = show_main_menu()
        print(f"\n🧙 WIZARD: Showing MANDATORY menu to LLM\n")
        print(f"   User's message: {message[:100]}...")
        print(f"   LLM must choose an option before responding\n")

        # Wizard loop: add prompt, call LLM, parse response
        while wizard_prompt and wizard_iteration < max_wizard_iterations:
            wizard_iteration += 1

            # Add wizard prompt as system message (instructions to LLM)
            wizard_messages_to_add.append({
                "role": "system",
                "content": f"[TOOL WIZARD]\n{wizard_prompt}",
                "wizard_state": wizard_state.to_dict()
            })

            # Build messages array: full context + wizard conversation
            wizard_context = [{"role": msg["role"], "content": msg["content"]} for msg in wizard_messages_to_add]

            # Use the full context window we built earlier, plus wizard messages
            temp_messages = base_messages + wizard_context

            print(f"\n{'='*80}")
            print(f"🧙 WIZARD ITERATION {wizard_iteration}")
            print(f"{'='*80}")
            print(f"Base context messages: {len(base_messages)}")
            print(f"Wizard messages: {len(wizard_context)}")
            print(f"Total messages: {len(temp_messages)}")

            # Show the wizard prompt being sent (the last system message)
            if wizard_context:
                last_wizard_msg = wizard_context[-1]
                print(f"\n📤 WIZARD PROMPT TO LLM:")
                print(f"{'-'*40}")
                print(last_wizard_msg.get("content", ""))
                print(f"{'-'*40}")

            # Call MLX LLM
            try:
                async with httpx.AsyncClient(timeout=120.0) as client:
                    response = await client.post(
                        f"http://localhost:{mlx_process.port}/v1/chat/completions",
                        json={
                            "messages": temp_messages,
                            "temperature": agent.temperature,
                            "max_tokens": 500,  # Wizard responses should be short
                            "seed": 42,
                        }
                    )
                    response.raise_for_status()
                    result = response.json()

                llm_response = result["choices"][0]["message"].get("content", "")

                print(f"\n📥 LLM RESPONSE (FULL):")
                print(f"{'-'*40}")
                print(llm_response)
                print(f"{'-'*40}")

                # Add LLM's response to wizard conversation
                wizard_messages_to_add.append({
                    "role": "assistant",
                    "content": llm_response,
                    "wizard_llm_response": True
                })

                # Process LLM's response through wizard
                wizard_prompt, wizard_state, continue_wizard = await process_wizard_step(
                    user_message=llm_response,
                    wizard_state=wizard_state,
                    agent_id=str(agent.id),
                    db=db
                )

                print(f"\n🔄 WIZARD STATE:")
                print(f"  Step: {wizard_state.step}")
                print(f"  Tool: {wizard_state.tool}")
                print(f"  Iteration: {wizard_state.iteration}")
                print(f"  Context: {wizard_state.context}")
                print(f"  Continue: {continue_wizard}")

                # Track if tools were actually used (not just chatting normally)
                # If wizard state step is not main_menu or tool is set, tools are being used
                if wizard_state.tool is not None or wizard_state.iteration > 0:
                    tools_were_used = True
                    print(f"  ➡️  Tools ARE being used")

                # If LLM chose to chat normally (option 1), save their FULL response
                # We'll use this as the final response instead of making another call
                if not continue_wizard and wizard_state.step == "main_menu" and wizard_state.tool is None:
                    # Extract the actual message (after thinking tags)
                    import re
                    final_chat_response = llm_response
                    # Remove thinking tags
                    if "</think>" in final_chat_response:
                        final_chat_response = final_chat_response.split("</think>")[-1].strip()
                    final_chat_response = re.sub(r'<think>.*', '', final_chat_response, flags=re.DOTALL).strip()
                    # Remove the leading "1" or "1!" that the LLM might have written
                    final_chat_response = re.sub(r'^1[!\s]*\n*', '', final_chat_response).strip()
                    print(f"  💬 LLM chose to chat normally - captured full response")

                if wizard_prompt:
                    print(f"\n📋 NEXT WIZARD PROMPT:")
                    print(f"{'-'*40}")
                    print(wizard_prompt[:500] + "..." if len(wizard_prompt) > 500 else wizard_prompt)
                    print(f"{'-'*40}")

                if not continue_wizard:
                    print(f"\n✅ WIZARD FLOW COMPLETE")
                    print(f"{'='*80}\n")
                    break

                print(f"{'='*80}\n")

            except Exception as e:
                print(f"\n🧙 WIZARD ERROR: {e}\n")
                break

        # DON'T save wizard messages to database - they pollute conversation history
        # and confuse the LLM on subsequent interactions. The wizard is ephemeral.
        print(f"🧙 WIZARD: Completed with {len(wizard_messages_to_add)} internal messages (not saved to DB)")

        # If LLM chose to chat normally and has a full response, use that directly
        if final_chat_response:
            print(f"\n🧙 WIZARD: Using LLM's full 'chat normally' response (no additional call needed)")
            print(f"Response preview: {final_chat_response[:200]}...")

            async def generate_chat_normally():
                # Stream the already-captured response
                final_response = final_chat_response

                try:
                    # Send the response in chunks to simulate streaming
                    chunk_size = 10
                    for i in range(0, len(final_response), chunk_size):
                        chunk = final_response[i:i+chunk_size]
                        yield f"data: {json.dumps({'type': 'content', 'content': chunk})}\n\n"

                    # Save to database
                    assistant_tags = extract_keywords(final_response, max_keywords=5)
                    assistant_message = Message(
                        conversation_id=conversation_id,
                        role="assistant",
                        content=final_response,
                        metadata_={
                            "model": agent.model_path,
                            "wizard_chat_normally": True,
                            "tools_used": tools_were_used,
                            "tags": assistant_tags
                        }
                    )
                    assistant_embedding = embedding_service.embed_with_tags(final_response, assistant_tags)
                    assistant_message.embedding = assistant_embedding
                    db.add(assistant_message)
                    db.commit()
                    db.refresh(assistant_message)

                    yield f"data: {json.dumps({'type': 'done', 'user_message': user_message.to_dict(), 'assistant_message': assistant_message.to_dict()})}\n\n"

                except Exception as e:
                    import traceback
                    print(f"🧙 WIZARD CHAT NORMALLY ERROR: {traceback.format_exc()}")
                    yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"

            return StreamingResponse(
                generate_chat_normally(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                }
            )

        # If wizard executed tools (not just chat normally), make a final LLM call to summarize and respond naturally
        if tools_were_used and wizard_iteration > 0:
            print(f"\n🧙 WIZARD: Making final summary call after {wizard_iteration} wizard interactions (tools_were_used={tools_were_used})\n")

            # Build context: full context + wizard conversation + "now respond naturally"
            final_wizard_messages = base_messages + [{"role": msg["role"], "content": msg["content"]} for msg in wizard_messages_to_add]

            # Add instruction to respond naturally now
            final_wizard_messages.append({
                "role": "system",
                "content": "You've completed the tool operations above. Now respond naturally to the user about what you did. Be conversational and helpful."
            })
        elif wizard_iteration > 0 and not tools_were_used:
            # LLM chose to chat normally (option 1), proceed to normal streaming without wizard overhead
            print(f"\n🧙 WIZARD: LLM chose to chat normally (no tools), proceeding to normal streaming\n")

        if tools_were_used and wizard_iteration > 0:

            print(f"📤 FINAL WIZARD SUMMARY CALL:")
            print(f"Messages: {len(final_wizard_messages)}")
            for i, msg in enumerate(final_wizard_messages):
                print(f"  {i+1}. [{msg['role']}]: {msg['content'][:100]}...")

            # Capture agent properties BEFORE the generator to avoid DetachedInstanceError
            agent_temperature = agent.temperature
            agent_max_tokens = agent.max_output_tokens if agent.max_output_tokens_enabled else 4096
            agent_model_path = agent.model_path
            mlx_port = mlx_process.port
            user_msg_dict = user_message.to_dict()

            # Stream the final response
            async def generate_wizard_final():
                final_response = ""
                try:
                    async with httpx.AsyncClient(timeout=120.0) as client:
                        async with client.stream(
                            "POST",
                            f"http://localhost:{mlx_port}/v1/chat/completions",
                            json={
                                "messages": final_wizard_messages,
                                "temperature": agent_temperature,
                                "max_tokens": agent_max_tokens,
                                "seed": 42,
                                "stream": True
                            }
                        ) as stream_response:
                            async for line in stream_response.aiter_lines():
                                if line.startswith("data: "):
                                    data = line[6:]
                                    if data == "[DONE]":
                                        break
                                    try:
                                        chunk = json.loads(data)
                                        delta = chunk["choices"][0]["delta"]
                                        if "content" in delta and delta["content"]:
                                            content_chunk = delta["content"]
                                            final_response += content_chunk
                                            yield f"data: {json.dumps({'type': 'content', 'content': content_chunk})}\n\n"
                                    except json.JSONDecodeError:
                                        continue

                    print(f"\n📥 WIZARD FINAL RESPONSE: {final_response[:200]}...")

                    # Save final response
                    assistant_tags = extract_keywords(final_response, max_keywords=5)
                    assistant_message = Message(
                        conversation_id=conversation_id,
                        role="assistant",
                        content=final_response,
                        metadata_={
                            "model": agent_model_path,
                            "wizard_final": True,
                            "wizard_iterations": wizard_iteration,
                            "tags": assistant_tags
                        }
                    )
                    assistant_embedding = embedding_service.embed_with_tags(final_response, assistant_tags)
                    assistant_message.embedding = assistant_embedding
                    db.add(assistant_message)
                    db.commit()
                    db.refresh(assistant_message)

                    yield f"data: {json.dumps({'type': 'done', 'user_message': user_msg_dict, 'assistant_message': assistant_message.to_dict()})}\n\n"

                except Exception as e:
                    import traceback
                    print(f"🧙 WIZARD FINAL ERROR: {traceback.format_exc()}")
                    yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"

            return StreamingResponse(
                generate_wizard_final(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                }
            )

        # If wizard didn't run (no iterations), proceed to normal LLM call

    # Context window already built above as base_messages
    messages = base_messages

    # Streaming generator function
    async def generate_stream():
        """Generate SSE stream with tool execution support

        Strategy:
        - Use non-streaming for iterations that have tool calls (need to execute tools and loop)
        - Use streaming for the final iteration (no tool calls) to stream response to user
        """

        # Send raw memory narrative first so user can see what the memory agent said
        if memory_narrative:
            yield f"data: {json.dumps({'type': 'memory_narrative', 'content': memory_narrative})}\n\n"

        # Simple streaming - no tool calling loop, wizard handles all tools
        final_response = ""

        try:
            # VERBOSE: Show exactly what we're sending to the LLM
            print(f"\n{'='*80}")
            print(f"🤖 MAIN AGENT LLM CALL (STREAMING) - Agent: {agent.name}")
            print(f"{'='*80}")

            request_payload = {
                "messages": messages,
                "temperature": agent.temperature,
                "top_p": agent.top_p,
                "max_tokens": agent.max_output_tokens if agent.max_output_tokens_enabled else 4096,
                "seed": 42,
                "stream": True
            }

            print(f"\n📤 REQUEST TO MAIN LLM:")
            print(f"Port: {mlx_process.port}")
            print(f"Temperature: {agent.temperature}")
            print(f"Max Tokens: {agent.max_output_tokens if agent.max_output_tokens_enabled else 4096}")
            print(f"\n📨 MESSAGES ARRAY ({len(messages)} messages):")
            for i, msg in enumerate(messages):
                role = msg.get("role", "unknown")
                content = msg.get("content", "")
                print(f"\n  Message {i+1} [{role}]:")
                print(f"  {content[:500]}{'...' if len(content) > 500 else ''}")
            print(f"{'='*80}\n")

            # Stream the response
            async with httpx.AsyncClient(timeout=120.0) as client:
                async with client.stream(
                    "POST",
                    f"http://localhost:{mlx_process.port}/v1/chat/completions",
                    json=request_payload
                ) as stream_response:
                    async for line in stream_response.aiter_lines():
                        if line.startswith("data: "):
                            data = line[6:]
                            if data == "[DONE]":
                                break
                            try:
                                chunk = json.loads(data)
                                delta = chunk["choices"][0]["delta"]

                                # Stream content to user AND collect it
                                if "content" in delta and delta["content"]:
                                    content_chunk = delta["content"]
                                    final_response += content_chunk
                                    # Stream to user in real-time
                                    yield f"data: {json.dumps({'type': 'content', 'content': content_chunk})}\n\n"
                            except json.JSONDecodeError:
                                continue

            # VERBOSE: Show exactly what the LLM responded with
            print(f"\n📥 RESPONSE FROM MAIN LLM:")
            print(f"Content: {final_response[:500]}{'...' if len(final_response) > 500 else ''}")
            print(f"{'='*80}\n")

            # Save complete assistant message to database
            assistant_tags = extract_keywords(final_response, max_keywords=5)

            assistant_message = Message(
                conversation_id=conversation_id,
                role="assistant",
                content=final_response,
                metadata_={
                    "model": agent.model_path,
                    "streamed": True,
                    "tags": assistant_tags
                }
            )

            assistant_embedding = embedding_service.embed_with_tags(final_response, assistant_tags)
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

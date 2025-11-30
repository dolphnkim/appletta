"""API routes for conversation management and chat inference"""

import asyncio
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
from backend.services.conversation_logger import log_message, log_conversation_event, log_debug

router = APIRouter(prefix="/api/v1/conversations", tags=["conversations"])


# ============================================================================
# Context Window
# ============================================================================

@router.get("/{conversation_id}/context-window")
async def get_context_window(
    conversation_id: UUID,
    db: Session = Depends(get_db)
):
    """Get context window breakdown matching actual inference calculation

    This MUST match the exact logic in the chat endpoint's shifting window calculation.
    """
    from backend.services.token_counter import count_message_tokens, count_tokens

    # Verify conversation exists
    conversation = db.query(Conversation).filter(Conversation.id == conversation_id).first()
    if not conversation:
        raise HTTPException(404, f"Conversation {conversation_id} not found")

    # Get agent
    agent = db.query(Agent).filter(Agent.id == conversation.agent_id).first()
    if not agent:
        raise HTTPException(404, "Agent not found for this conversation")

    # Get ALL messages in conversation
    history = db.query(Message).filter(
        Message.conversation_id == conversation_id
    ).order_by(Message.created_at.asc()).all()

    if not history:
        # No messages yet, return empty breakdown
        return {
            "sections": [],
            "total_tokens": 0,
            "max_context_tokens": agent.max_context_tokens,
            "percentage_used": 0,
            "messages_in_context": 0,
            "messages_dropped": 0
        }

    # === REPLICATE EXACT SHIFTING WINDOW LOGIC FROM INFERENCE ===

    # Step 1: Calculate preliminary system content (project instructions only)
    preliminary_system_content = agent.project_instructions or ""
    preliminary_system_message = {"role": "system", "content": preliminary_system_content}
    sticky_tokens = count_message_tokens(preliminary_system_message)
    sticky_tokens += 1000  # Buffer for memories and journal blocks (matches inference code)

    max_context = agent.max_context_tokens
    remaining_budget = max_context - sticky_tokens

    # Step 2: Calculate which messages will fit (shifting window)
    messages_in_context = []
    current_tokens = 0

    for msg in reversed(history):
        msg_dict = {"role": msg.role, "content": msg.content}
        msg_tokens = count_message_tokens(msg_dict)

        if current_tokens + msg_tokens <= remaining_budget:
            messages_in_context.insert(0, msg)
            current_tokens += msg_tokens
        else:
            break  # Stop when we hit the limit

    messages_dropped = len(history) - len(messages_in_context)

    # Step 3: Build actual system content (what will be sent to LLM)
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

    # Add estimated memory narrative (without actually running memory agent)
    # This is an approximation for display purposes
    memory_estimate = ""
    if messages_dropped > 0:
        memory_estimate = "\n\n=== Memories Surfacing ===\n[Estimated: memories from dropped messages would go here]\n"
        system_content += memory_estimate

    system_tokens = count_tokens(system_content)

    # Count tool instructions tokens (if tools are enabled)
    tool_instructions_tokens = 0
    tool_instructions_text = ""
    if agent.enabled_tools and len(agent.enabled_tools) > 0:
        from backend.services.tools import get_tools_description
        tool_instructions_text = get_tools_description(agent.enabled_tools, agent.id, db)
        tool_instructions_tokens = count_tokens(tool_instructions_text)

    # Count tool overhead from messages in context (not all history)
    tool_overhead_tokens = 0
    for msg in messages_in_context:
        if msg.role == "assistant" and msg.metadata_:
            tool_overhead_tokens += msg.metadata_.get("wizard_overhead_tokens", 0)
            tool_overhead_tokens += msg.metadata_.get("inline_tools_used", 0) * 50  # Estimate for inline tool results

    # Calculate totals
    messages_tokens = current_tokens
    total_tokens = system_tokens + tool_instructions_tokens + messages_tokens + tool_overhead_tokens

    sections = [
        {
            "name": "System Content",
            "tokens": system_tokens,
            "percentage": round((system_tokens / max_context) * 100, 1) if max_context > 0 else 0,
            "content": f"Project instructions + {len(pinned_blocks)} pinned blocks" + (" + memory estimate" if memory_estimate else "")
        }
    ]

    if tool_instructions_tokens > 0:
        sections.append({
            "name": "Tool Instructions",
            "tokens": tool_instructions_tokens,
            "percentage": round((tool_instructions_tokens / max_context) * 100, 1) if max_context > 0 else 0,
            "content": tool_instructions_text[:300] + "..." if len(tool_instructions_text) > 300 else tool_instructions_text
        })

    sections.append({
        "name": "Messages in Context",
        "tokens": messages_tokens,
        "percentage": round((messages_tokens / max_context) * 100, 1) if max_context > 0 else 0,
        "content": f"{len(messages_in_context)} messages ({messages_dropped} dropped by shifting window)"
    })

    if tool_overhead_tokens > 0:
        sections.append({
            "name": "Tool Execution Overhead",
            "tokens": tool_overhead_tokens,
            "percentage": round((tool_overhead_tokens / max_context) * 100, 1) if max_context > 0 else 0,
            "content": "Tool results injected during conversation"
        })

    return {
        "sections": sections,
        "total_tokens": total_tokens,
        "max_context_tokens": max_context,
        "percentage_used": round((total_tokens / max_context) * 100, 1) if max_context > 0 else 0,
        "messages_in_context": len(messages_in_context),
        "messages_dropped": messages_dropped
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


@router.post("/{conversation_id}/save-partial-message")
async def save_partial_message(
    conversation_id: UUID,
    request: dict,
    db: Session = Depends(get_db)
):
    """Save a partial assistant message when user stops streaming

    Used when user clicks STOP button to preserve the partial response.
    """
    from pydantic import BaseModel

    content = request.get("content", "")
    user_message_id = request.get("user_message_id")

    if not content:
        raise HTTPException(400, "Content is required")

    # Verify conversation exists
    conversation = db.query(Conversation).filter(Conversation.id == conversation_id).first()
    if not conversation:
        raise HTTPException(404, f"Conversation {conversation_id} not found")

    # Get the agent for model info
    agent = db.query(Agent).filter(Agent.id == conversation.agent_id).first()
    model_path = agent.model_path if agent else "unknown"

    # Generate tags and embedding
    embedding_service = get_embedding_service()
    assistant_tags = extract_keywords(content, max_keywords=5)

    # Create the partial assistant message
    assistant_message = Message(
        conversation_id=conversation_id,
        role="assistant",
        content=content,
        metadata_={
            "model": model_path,
            "partial": True,  # Mark as partial/stopped
            "tags": assistant_tags
        }
    )

    # Generate embedding
    assistant_embedding = embedding_service.embed_with_tags(content, assistant_tags)
    assistant_message.embedding = assistant_embedding

    db.add(assistant_message)
    db.commit()
    db.refresh(assistant_message)

    # Log partial assistant message to JSONL
    log_message(
        conversation_id=str(conversation_id),
        agent_id=str(agent.id) if agent else "unknown",
        agent_name=agent.name if agent else "Unknown Agent",
        role="assistant",
        content=content,
        metadata={
            "model": model_path,
            "partial": True,
            "tags": assistant_tags
        }
    )

    return {
        "success": True,
        "message": assistant_message.to_dict()
    }


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

    # 3. Use memory coordinator ONLY if there are relevant memories outside context window
    memory_narrative = ""
    tag_updates = {}

    if memory_candidates and len(memory_candidates) > 0:
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

    # Check if router logging is enabled for this agent
    use_router_logging = getattr(agent, 'router_logging_enabled', False)

    # Get or start MLX server (unless using router logging mode)
    mlx_manager = get_mlx_manager()
    mlx_process = None

    if not use_router_logging:
        mlx_process = mlx_manager.get_agent_server(agent.id)

        if not mlx_process:
            try:
                mlx_process = await mlx_manager.start_agent_server(agent)
            except Exception as e:
                raise HTTPException(500, f"Failed to start MLX server: {str(e)}")

    # Simple LLM call - no tool calling loop, wizard handles all tools
    print(f"\n{'='*80}")
    print(f"🤖 MAIN AGENT LLM CALL - Agent: {agent.name}")
    if use_router_logging:
        print(f"🔬 ROUTER LOGGING ENABLED - Using diagnostic inference")
    print(f"{'='*80}")

    final_response = ""
    router_analysis = None

    if use_router_logging:
        # Use diagnostic inference service with router logging
        from backend.services.diagnostic_inference import get_diagnostic_service

        try:
            diagnostic_service = get_diagnostic_service()

            # Check if model is already loaded for this agent
            current_agent_id = getattr(diagnostic_service, 'agent_id', None)
            is_model_loaded = diagnostic_service.model is not None

            if not is_model_loaded or current_agent_id != str(agent.id):
                print(f"[Router Logging] Model not loaded for this agent")
                raise HTTPException(
                    400,
                    "Router logging enabled but model not loaded. Visit Analytics/Interpretability page to load the model for this agent first."
                )

            # Build prompt from messages (combine all into single text for now)
            # For better results, we should format as a conversation
            prompt_parts = []
            for msg in messages:
                role = msg.get("role", "")
                content = msg.get("content", "")
                if role == "system":
                    prompt_parts.append(f"System: {content}")
                elif role == "user":
                    prompt_parts.append(f"User: {content}")
                elif role == "assistant":
                    prompt_parts.append(f"Assistant: {content}")

            conversation_prompt = "\n\n".join(prompt_parts)

            # Run inference with router logging
            max_tokens = agent.max_output_tokens if agent.max_output_tokens_enabled else 4096
            result_dict = diagnostic_service.run_inference(
                prompt=conversation_prompt,
                max_tokens=max_tokens,
                temperature=agent.temperature,
                log_routing=True
            )

            final_response = result_dict["response"]
            router_analysis = result_dict["router_analysis"]

            # Save router session with conversation context
            prompt_preview = f"[Conversation] {request.message[:100]}"
            diagnostic_service.router_inspector.current_session["metadata"]["conversation_id"] = str(conversation_id)
            diagnostic_service.router_inspector.current_session["metadata"]["category"] = "conversation"
            filepath = diagnostic_service.save_session(prompt_preview, f"Turn in conversation {conversation.title}")

            print(f"[Router Logging] Session saved to: {filepath}")
            print(f"[Router Logging] Experts used: {router_analysis.get('unique_experts_used', 0)}")

        except Exception as e:
            print(f"[Router Logging] Error: {e}")
            import traceback
            traceback.print_exc()
            raise HTTPException(500, f"Router logging inference failed: {str(e)}")
    else:
        # Standard MLX server inference
        # VERBOSE: Show exactly what we're sending to the LLM
        request_payload = {
            "messages": messages,
            "temperature": agent.temperature,
            "max_tokens": agent.max_output_tokens if agent.max_output_tokens_enabled else 4096,
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
            # Show full content without truncation
            print(f"  {content}")
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
            # Show full content without truncation
            print(f"Content:\n{content}")
            print(f"{'='*80}\n")

        except httpx.HTTPError as e:
            print(f"\n❌ MLX SERVER ERROR: {str(e)}\n")
            raise HTTPException(500, f"MLX server request failed: {str(e)}")

        final_response = result["choices"][0]["message"].get("content", "")

    # Save assistant message and embed it
    # Extract initial thematic tags for assistant message
    assistant_tags = extract_keywords(final_response, max_keywords=5)

    # Build metadata
    message_metadata = {
        "model": agent.model_path,
        "surfaced_memories_count": 0,  # Will be updated after memory coordination
        "tags": assistant_tags
    }

    # Add usage info if available (from standard MLX server)
    if not use_router_logging and 'result' in locals():
        message_metadata["usage"] = result.get("usage", {})

    # Add router analysis if available
    if router_analysis:
        message_metadata["router_logging"] = {
            "total_tokens": router_analysis.get("total_tokens", 0),
            "unique_experts_used": router_analysis.get("unique_experts_used", 0),
            "usage_entropy": router_analysis.get("usage_entropy", 0),
            "mean_token_entropy": router_analysis.get("mean_token_entropy", 0)
        }

    assistant_message = Message(
        conversation_id=conversation_id,
        role="assistant",
        content=final_response,
        metadata_=message_metadata
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

    # Capture conversation title early (before session might detach object)
    conversation_title = conversation.title or "Untitled"

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

    # Log user message to JSONL
    log_message(
        conversation_id=str(conversation_id),
        agent_id=str(agent.id),
        agent_name=agent.name,
        role="user",
        content=message,
        metadata={"tags": initial_tags} if initial_tags else None
    )

    # === GET MLX SERVER ===
    # Start MLX server for wizard menu choices (unless using pure router logging mode)
    # When router logging is enabled with loaded model, we skip MLX server to avoid loading model twice
    mlx_manager = get_mlx_manager()
    mlx_process = None

    # Check if we should skip MLX server (router logging with loaded diagnostic model)
    skip_mlx_server = False
    router_logging_enabled = getattr(agent, 'router_logging_enabled', False)
    print(f"[MLX Setup] router_logging_enabled={router_logging_enabled}")
    log_debug("mlx_setup", f"router_logging_enabled={router_logging_enabled}", conversation_id=str(conversation_id), agent_id=str(agent.id))
    if router_logging_enabled:
        try:
            from backend.services.diagnostic_inference import get_diagnostic_service
            diag_service = get_diagnostic_service()
            if diag_service.model is not None and diag_service.agent_id == str(agent.id):
                skip_mlx_server = True
                logger.info(f"Skipping MLX server - using diagnostic service model for router logging")
        except:
            pass

    print(f"[MLX Setup] skip_mlx_server={skip_mlx_server}")
    log_debug("mlx_setup", f"skip_mlx_server={skip_mlx_server}", conversation_id=str(conversation_id), agent_id=str(agent.id))
    if not skip_mlx_server:
        mlx_process = mlx_manager.get_agent_server(agent.id)
        print(f"[MLX Setup] get_agent_server returned: {mlx_process}")
        log_debug("mlx_setup", f"get_agent_server returned: {mlx_process}", conversation_id=str(conversation_id), agent_id=str(agent.id))

        if not mlx_process:
            try:
                print(f"[MLX Setup] Starting new MLX server for agent {agent.name}...")
                log_debug("mlx_setup", f"Starting new MLX server for agent {agent.name}", conversation_id=str(conversation_id), agent_id=str(agent.id))
                mlx_process = await mlx_manager.start_agent_server(agent)
                print(f"[MLX Setup] MLX server started on port {mlx_process.port}")
                log_debug("mlx_setup", f"MLX server started on port {mlx_process.port}", conversation_id=str(conversation_id), agent_id=str(agent.id))
                logger.info(f"MLX server started on port {mlx_process.port}")
            except Exception as e:
                print(f"[MLX Setup] FAILED to start MLX server: {e}")
                log_debug("mlx_setup", f"FAILED to start MLX server: {e}", conversation_id=str(conversation_id), agent_id=str(agent.id))
                raise HTTPException(500, f"Failed to start MLX server: {str(e)}")
        else:
            print(f"[MLX Setup] Using existing MLX server on port {mlx_process.port}")
            log_debug("mlx_setup", f"Using existing MLX server on port {mlx_process.port}", conversation_id=str(conversation_id), agent_id=str(agent.id))
            logger.info(f"Using existing MLX server on port {mlx_process.port} for agent {agent.name}")
    else:
        print(f"[MLX Setup] Skipping MLX server startup (using diagnostic service)")
        log_debug("mlx_setup", "Skipping MLX server startup (using diagnostic service)", conversation_id=str(conversation_id), agent_id=str(agent.id))

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

    # Only run memory coordinator if there are relevant memories outside context window
    if memory_candidates and len(memory_candidates) > 0:
        if memory_attachment:
            memory_agent = db.query(Agent).filter(
                Agent.id == memory_attachment.attached_agent_id
            ).first()

            memory_narrative, tag_updates = await coordinate_memories(
                candidates=memory_candidates,
                query_context=message,
                memory_agent=memory_agent,
                target_count=7
            )

            if tag_updates:
                apply_tag_updates(tag_updates, db)

    # Build system content with memories
    system_content = agent.project_instructions or ""

    # Add current date and time
    from datetime import datetime
    current_datetime = datetime.now().strftime("%A, %B %d, %Y at %I:%M %p")
    system_content += f"\n\nCurrent date and time: {current_datetime}"

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

    # === ROUTER LOGGING CHECK ===
    use_router_logging = getattr(agent, 'router_logging_enabled', False)

    # === INLINE TOOL SYSTEM ===
    # If tools are enabled, use inline tool parsing (LLM includes tools in response)
    from backend.services.tool_wizard import (
        # Legacy wizard imports (kept for compatibility)
        get_wizard_state, process_wizard_step, show_main_menu, WizardState, clean_llm_response, parse_command,
        # New inline tool imports
        process_response_with_inline_tools, get_inline_tool_instructions, format_inline_tool_results
    )

    if agent.enabled_tools and len(agent.enabled_tools) > 0:
        # INLINE TOOL FLOW:
        # 1. Add tool instructions to context
        # 2. LLM generates response (may include inline tool calls)
        # 3. Parse and execute any tool calls found
        # 4. If tools were used, inject results and let LLM continue
        # 5. Filter tool syntax from final response
        # 6. Save clean response to database

        max_tool_iterations = 3  # Max loops for tool execution
        tool_call_count = 0
        accumulated_response = ""  # Clean response for user (tool syntax filtered out)

        print(f"\n🔧 INLINE TOOLS: Enabled for agent {agent.name}")
        print(f"   User's message: {message[:100]}...")

        # Add tool instructions to context (only for enabled tools)
        tool_instructions = get_inline_tool_instructions(str(agent.id), db, agent.enabled_tools)
        messages_with_tools = []
        tool_instructions_added = False
        for msg in base_messages:
            messages_with_tools.append(msg)
            if msg.get("role") == "system" and not tool_instructions_added:
                messages_with_tools.append({"role": "system", "content": tool_instructions})
                tool_instructions_added = True

        # Streaming generator that implements inline tool flow
        async def generate_stream_with_inline_tools():
            nonlocal tool_call_count, accumulated_response, mlx_process, mlx_manager, skip_mlx_server

            # Send raw memory narrative first so user can see what the memory agent said
            if memory_narrative:
                yield f"data: {json.dumps({'type': 'memory_narrative', 'content': memory_narrative})}\n\n"

            # Initialize router logging if enabled
            diagnostic_service = None
            if use_router_logging:
                print(f"🔬 ROUTER LOGGING ENABLED for agent {agent.name}")
                from backend.services.diagnostic_inference import get_diagnostic_service

                try:
                    diagnostic_service = get_diagnostic_service()

                    # Check if model is already loaded for this agent
                    current_agent_id = getattr(diagnostic_service, 'agent_id', None)
                    current_model_path = getattr(diagnostic_service, 'model_path', None)
                    is_model_loaded = diagnostic_service.model is not None

                    print(f"[Router Logging] Current state: agent_id={current_agent_id}, model_loaded={is_model_loaded}")
                    print(f"[Router Logging] Target: agent_id={agent.id}")

                    if not is_model_loaded or current_agent_id != str(agent.id):
                        # Model not loaded or wrong agent - show helpful message but don't block
                        print(f"[Router Logging] Model not loaded for this agent")
                        yield f"data: {json.dumps({'type': 'status', 'content': '⚠️ Router logging enabled but model not loaded. Visit Analytics/Interpretability page to load the model for this agent first.'})}\n\n"
                        diagnostic_service = None  # Disable for this request
                    else:
                        print(f"[Router Logging] Model already loaded, will use for routing analysis")
                        yield f"data: {json.dumps({'type': 'status', 'content': '🔬 Router logging active'})}\n\n"
                except Exception as e:
                    print(f"[Router Logging] Warning: Failed to initialize diagnostic service: {e}")
                    import traceback
                    traceback.print_exc()
                    yield f"data: {json.dumps({'type': 'status', 'content': f'⚠️ Router logging failed to initialize: {str(e)}'})}\n\n"
                    diagnostic_service = None

            # Initialize for inline tool loop
            current_messages = messages_with_tools.copy()
            router_analysis_data = None
            iteration = 0

            while iteration < max_tool_iterations:
                iteration += 1
                print(f"\n{'='*80}")
                print(f"🔧 INLINE TOOLS: Generation iteration {iteration} (tools used: {tool_call_count})")
                print(f"{'='*80}")

                request_payload = {
                    "messages": current_messages,
                    "temperature": agent.temperature,
                    "top_p": agent.top_p,
                    "max_tokens": agent.max_output_tokens if agent.max_output_tokens_enabled else 4096,
                    "stream": True
                }

                print(f"\n📤 LLM CALL (Iteration {iteration}):")
                if use_router_logging:
                    print(f"Mode: Router Logging (Diagnostic Service)")
                else:
                    print(f"Port: {mlx_process.port if mlx_process else 'None (MLX not started)'}")
                print(f"Temperature: {agent.temperature}")
                print(f"Messages: {len(current_messages)}")
                
                # VERBOSE: Show tool instructions and recent messages
                print(f"\n{'─'*60}")
                print(f"📋 TOOL INSTRUCTIONS SENT TO LLM:")
                print(f"{'─'*60}")
                print(tool_instructions)
                print(f"{'─'*60}")
                
                # Show full message array sent to LLM
                print(f"\n📨 FULL MESSAGE ARRAY SENT TO LLM ({len(current_messages)} messages total):")
                for i, msg in enumerate(current_messages):
                    role = msg.get("role", "?")
                    content = msg.get("content", "")
                    print(f"\n  ┌─ [{i}] [{role}] ─────────────────────────────────────")
                    # Show full content for all messages
                    for line in content.split('\n'):
                        print(f"  │ {line}")
                    print(f"  └{'─'*50}")
                print(f"{'─'*60}")

                raw_response = ""

                try:
                    if use_router_logging and diagnostic_service:
                        # Use diagnostic inference with router logging (non-streaming)
                        print(f"🔬 Using router logging for this response")

                        prompt_parts = []
                        for msg in current_messages:
                            role = msg.get("role", "")
                            content = msg.get("content", "")
                            if role == "system":
                                prompt_parts.append(f"System: {content}")
                            elif role == "user":
                                prompt_parts.append(f"User: {content}")
                            elif role == "assistant":
                                prompt_parts.append(f"Assistant: {content}")

                        conversation_prompt = "\n\n".join(prompt_parts)
                        yield f"data: {json.dumps({'type': 'status', 'content': '🔬 Running inference with router logging...'})}\n\n"

                        max_tokens = agent.max_output_tokens if agent.max_output_tokens_enabled else 4096
                        result_dict = await asyncio.to_thread(
                            diagnostic_service.run_inference,
                            prompt=conversation_prompt,
                            max_tokens=max_tokens,
                            temperature=agent.temperature,
                            log_routing=True
                        )

                        raw_response = result_dict["response"]
                        router_analysis_data = result_dict["router_analysis"]
                        print(f"🔬 Router logging captured: {router_analysis_data.get('unique_experts_used', 0)} experts used")

                    else:
                        # Standard MLX server (collect full response for tool parsing)
                        if not mlx_process:
                            raise Exception("MLX server not available - mlx_process is None")
                        
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
                                            if "content" in delta and delta["content"]:
                                                raw_response += delta["content"]
                                        except json.JSONDecodeError:
                                            continue

                    print(f"\n{'═'*60}")
                    print(f"📥 FULL LLM RESPONSE ({len(raw_response)} chars):")
                    print(f"{'═'*60}")
                    print(raw_response)
                    print(f"{'═'*60}")

                    # Parse and execute inline tools, get cleaned response
                    cleaned_response, tool_results = process_response_with_inline_tools(
                        raw_response, str(agent.id), db
                    )

                    # Show what was parsed
                    if tool_results:
                        print(f"\n🔧 TOOLS DETECTED AND EXECUTED:")
                        for tr in tool_results:
                            print(f"   {'✅' if tr.success else '❌'} {tr.message}")
                    
                    print(f"\n📤 CLEANED RESPONSE (sent to user, {len(cleaned_response)} chars):")
                    print(f"{'─'*60}")
                    print(cleaned_response if cleaned_response else "(empty)")
                    print(f"{'─'*60}")

                    # Stream cleaned response to user (tool syntax filtered out)
                    if cleaned_response:
                        chunk_size = 20
                        for i in range(0, len(cleaned_response), chunk_size):
                            content_chunk = cleaned_response[i:i+chunk_size]
                            yield f"data: {json.dumps({'type': 'content', 'content': content_chunk})}\n\n"
                            await asyncio.sleep(0.01)
                        accumulated_response += cleaned_response

                    log_debug("llm_response", "Response processed", data={"raw_len": len(raw_response), "clean_len": len(cleaned_response), "tools": len(tool_results)}, conversation_id=str(conversation_id), agent_id=str(agent.id))

                    # If tools were executed, inject results and continue loop
                    if tool_results:
                        tool_call_count += len(tool_results)
                        print(f"🔧 Executed {len(tool_results)} tool(s), total: {tool_call_count}")

                        # Add raw response to conversation
                        current_messages.append({"role": "assistant", "content": raw_response})

                        # Inject tool results for next iteration
                        results_text = format_inline_tool_results(tool_results)
                        current_messages.append({"role": "system", "content": results_text})

                        # Add spacing
                        if accumulated_response and not accumulated_response.endswith("\n"):
                            accumulated_response += "\n\n"
                            yield f"data: {json.dumps({'type': 'content', 'content': chr(10) + chr(10)})}\n\n"

                        continue  # Let LLM respond to tool results
                    else:
                        break  # No tools, we're done

                except Exception as e:
                    import traceback
                    print(f"🔧 INLINE TOOLS ERROR: {traceback.format_exc()}")
                    yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"
                    return

            # End of inline tool loop - now finalize

            # FINALIZE: Save accumulated response to database
            print(f"\n🔧 INLINE TOOLS: Finalizing message to database")
            print(f"   Response length: {len(accumulated_response)}")
            print(f"   Tools executed: {tool_call_count}")

            # Save to database
            assistant_tags = extract_keywords(accumulated_response, max_keywords=5)
            assistant_metadata = {
                "model": agent.model_path,
                "inline_tools_used": tool_call_count,
                "tags": assistant_tags
            }

            # Include memory narrative if present
            if memory_narrative:
                assistant_metadata["memory_narrative"] = memory_narrative

            # Include router analysis if present
            if router_analysis_data:
                assistant_metadata["router_logging"] = {
                    "total_tokens": router_analysis_data.get("total_tokens", 0),
                    "unique_experts_used": router_analysis_data.get("unique_experts_used", 0),
                    "usage_entropy": router_analysis_data.get("usage_entropy", 0),
                    "mean_token_entropy": router_analysis_data.get("mean_token_entropy", 0)
                }
                print(f"🔬 Router analysis added to metadata: {router_analysis_data.get('unique_experts_used', 0)} experts")

                # Save router session to file for analytics
                if use_router_logging and diagnostic_service:
                    try:
                        prompt_preview = f"[Conversation] {message[:100]}"
                        diagnostic_service.router_inspector.current_session["metadata"]["conversation_id"] = str(conversation_id)
                        diagnostic_service.router_inspector.current_session["metadata"]["category"] = "conversation"
                        filepath = diagnostic_service.save_session(prompt_preview, f"Turn in conversation {conversation_title}")
                        print(f"🔬 Router session saved to: {filepath}")
                    except Exception as e:
                        print(f"🔬 Warning: Failed to save router session: {e}")

            assistant_message = Message(
                conversation_id=conversation_id,
                role="assistant",
                content=accumulated_response,
                metadata_=assistant_metadata
            )
            assistant_embedding = embedding_service.embed_with_tags(accumulated_response, assistant_tags)
            assistant_message.embedding = assistant_embedding
            db.add(assistant_message)
            db.commit()
            db.refresh(assistant_message)

            # Log assistant message to JSONL
            log_message(
                conversation_id=str(conversation_id),
                agent_id=str(agent.id),
                agent_name=agent.name,
                role="assistant",
                content=accumulated_response,
                metadata={
                    "model": agent.model_path,
                    "inline_tools_used": tool_call_count,
                    "tags": assistant_tags
                }
            )

            yield f"data: {json.dumps({'type': 'done', 'user_message': user_message.to_dict(), 'assistant_message': assistant_message.to_dict()})}\n\n"

            print(f"✅ INLINE TOOLS COMPLETE - Message saved to DB")

        return StreamingResponse(
            generate_stream_with_inline_tools(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            }
        )

    # If tools not enabled, proceed to normal LLM call (no wizard)

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
                print(f"  {content}")
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
            print(f"Content: {final_response}")
            print(f"{'='*80}\n")

            # Save complete assistant message to database
            assistant_tags = extract_keywords(final_response, max_keywords=5)
            assistant_metadata = {
                "model": agent.model_path,
                "streamed": True,
                "tags": assistant_tags
            }
            # Include memory narrative if present
            if memory_narrative:
                assistant_metadata["memory_narrative"] = memory_narrative

            assistant_message = Message(
                conversation_id=conversation_id,
                role="assistant",
                content=final_response,
                metadata_=assistant_metadata
            )

            assistant_embedding = embedding_service.embed_with_tags(final_response, assistant_tags)
            assistant_message.embedding = assistant_embedding

            db.add(assistant_message)
            db.commit()
            db.refresh(assistant_message)

            # Log assistant message to JSONL
            log_message(
                conversation_id=str(conversation_id),
                agent_id=str(agent.id),
                agent_name=agent.name,
                role="assistant",
                content=final_response,
                metadata={
                    "model": agent.model_path,
                    "streamed": True,
                    "tags": assistant_tags
                }
            )

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
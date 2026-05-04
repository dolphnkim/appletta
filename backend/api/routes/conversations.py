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
from backend.services.stateful_inference import get_inference_engine
from backend.services.tools import execute_tool, get_enabled_tools, build_tool_manifest, parse_minimax_tool_calls, format_tool_result_message
from backend.services.skill_loader import load_skills, build_skill_docs
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

    # Calculate totals
    messages_tokens = current_tokens
    total_tokens = system_tokens + messages_tokens

    sections = [
        {
            "name": "System Content",
            "tokens": system_tokens,
            "percentage": round((system_tokens / max_context) * 100, 1) if max_context > 0 else 0,
            "content": f"Project instructions + {len(pinned_blocks)} pinned blocks" + (" + memory estimate" if memory_estimate else "")
        },
        {
            "name": "Messages in Context",
            "tokens": messages_tokens,
            "percentage": round((messages_tokens / max_context) * 100, 1) if max_context > 0 else 0,
            "content": f"{len(messages_in_context)} messages ({messages_dropped} dropped by shifting window)"
        },
    ]

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

    # Build final messages array using the pre-calculated messages_in_context
    # IMPORTANT: Add the current user message at the end (it's not in history yet)
    system_message = {"role": "system", "content": system_content}
    messages_to_include = [{"role": msg.role, "content": msg.content} for msg in messages_in_context]
    current_user_msg = {"role": "user", "content": request.message}
    messages = [system_message] + messages_to_include + [current_user_msg]

    # Check if router logging is enabled for this agent
    use_router_logging = getattr(agent, 'router_logging_enabled', False)

    # Get stateful inference engine
    inference_engine = get_inference_engine()

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
        # Stateful in-process inference
        print(f"\n📤 REQUEST TO MAIN LLM:")
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
            async for chunk in inference_engine.stream_chat(
                conversation_id=conversation_id,
                messages=messages,
                model_path=agent.model_path,
                adapter_path=getattr(agent, "adapter_path", None) or None,
                temperature=agent.temperature,
                top_p=getattr(agent, "top_p", 1.0) or 1.0,
                top_k=getattr(agent, "top_k", 100) or 100,
                max_tokens=agent.max_output_tokens if agent.max_output_tokens_enabled else 4096,
                reasoning_enabled=agent.reasoning_enabled,
            ):
                final_response += chunk
        except Exception as e:
            print(f"\n❌ INFERENCE ERROR: {str(e)}\n")
            raise HTTPException(500, f"Inference failed: {str(e)}")

        print(f"\n📥 RESPONSE FROM MAIN LLM:")
        print(f"Content:\n{final_response}")
        print(f"{'='*80}\n")

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

    # === GET INFERENCE ENGINE ===
    inference_engine = get_inference_engine()

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

    # Build STABLE system content — nothing dynamic goes here.
    # The StatefulInferenceEngine hashes this to decide whether to reuse the KV
    # cache. If it changes between turns the entire context is re-prefilled from
    # scratch, which is very slow. Keep it to things that rarely change:
    #   project_instructions, pinned blocks, tool manifest, skill docs.
    # Memory narrative and timestamps go in per-turn messages instead.
    system_content = agent.project_instructions or ""

    # Pinned journal blocks (always_in_context=True) — these change rarely
    pinned_blocks = db.query(JournalBlock).filter(
        JournalBlock.agent_id == agent.id,
        JournalBlock.always_in_context == True
    ).order_by(JournalBlock.updated_at.desc()).all()

    if pinned_blocks:
        system_content += "\n\n=== Pinned Information ==="
        for block in pinned_blocks:
            system_content += f"\n\n[{block.label}]\n{block.value}"

    # Build tool list early so we can inject the manifest into the system prompt
    tools = get_enabled_tools(agent.enabled_tools) if (agent.enabled_tools and len(agent.enabled_tools) > 0) else []

    # Tool manifest — stable (only changes when enabled_tools changes)
    if tools:
        manifest = build_tool_manifest(tools)
        system_content += f"\n\n{manifest}"

    # Skill docs — stable (only changes when Kevin writes a new skill)
    skills = load_skills()
    if skills:
        skill_docs = build_skill_docs(skills)
        system_content += f"\n\n{skill_docs}"

    # Build the user message — dynamic per-turn content (timestamp, memories)
    # goes HERE as a prefix, NOT in the system message. The system message is
    # hashed to decide KV cache reuse; putting dynamic content there would bust
    # the cache on every single turn, forcing a full re-prefill every message.
    from datetime import datetime
    import re
    current_datetime = datetime.now().strftime("%A, %B %d, %Y at %I:%M %p")
    user_msg_parts = [f"[{current_datetime}]"]

    if memory_narrative:
        sanitized = memory_narrative
        sanitized = re.sub(r'<think>.*?</think>', '', sanitized, flags=re.DOTALL)
        sanitized = re.sub(r'!\[.*?\]\(.*?\)', '', sanitized)
        sanitized = re.sub(r'https?://[^\s]+', '', sanitized)
        sanitized = re.sub(r'\n\s*\n\s*\n+', '\n\n', sanitized)
        sanitized = sanitized.strip()
        if sanitized:
            user_msg_parts.append(f"=== Memories Surfacing ===\n{sanitized}")

    user_msg_parts.append(message)

    system_message = {"role": "system", "content": system_content}
    messages_to_include = [{"role": msg.role, "content": msg.content} for msg in messages_in_context]
    current_user_msg = {"role": "user", "content": "\n\n".join(user_msg_parts)}
    base_messages = [system_message] + messages_to_include + [current_user_msg]

    print(f"\n📦 CONTEXT WINDOW BUILT:")
    print(f"  System content: {len(system_content)} chars (stable — KV cache safe)")
    print(f"  User msg prefix: datetime + {'memories' if memory_narrative else 'no memories'}")
    print(f"  History messages: {len(messages_in_context)}")
    print(f"  Total messages: {len(base_messages)}")
    print(f"  Memory narrative: {'Yes' if memory_narrative else 'No'}")

    # === ROUTER LOGGING CHECK ===
    use_router_logging = getattr(agent, 'router_logging_enabled', False)

    # === AGENTIC TOOL LOOP ===
    # If tools are enabled, pass them to the model via chat template and run
    # an agentic loop: generate → parse MiniMax XML tool calls → execute →
    # inject results → repeat until no tool calls, then stream final response.
    if tools:

        async def generate_stream_with_tools():
            current_messages = base_messages.copy()
            accumulated_response = ""
            iteration = 0
            max_iterations = 10

            if memory_narrative:
                yield f"data: {json.dumps({'type': 'memory_narrative', 'content': memory_narrative})}\n\n"

            while iteration < max_iterations:
                iteration += 1
                raw_response = ""

                print(f"\n{'='*60}")
                print(f"🔧 TOOL LOOP iteration {iteration} — agent: {agent.name}")
                print(f"{'='*60}")

                try:
                    async for chunk in inference_engine.stream_chat(
                        conversation_id=conversation_id,
                        messages=current_messages,
                        model_path=agent.model_path,
                        adapter_path=getattr(agent, "adapter_path", None) or None,
                        temperature=agent.temperature,
                        top_p=getattr(agent, "top_p", 1.0) or 1.0,
                        top_k=getattr(agent, "top_k", 100) or 100,
                        max_tokens=agent.max_output_tokens if agent.max_output_tokens_enabled else 4096,
                        reasoning_enabled=agent.reasoning_enabled,
                        tools=tools,
                    ):
                        raw_response += chunk
                except Exception as e:
                    import traceback
                    print(f"🔧 TOOL LOOP ERROR: {traceback.format_exc()}")
                    yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"
                    return

                print(f"📥 Raw response ({len(raw_response)} chars):\n{raw_response}\n{'─'*60}")

                tool_calls = parse_minimax_tool_calls(raw_response, tools)

                if not tool_calls:
                    # Final response — stream it to the user
                    chunk_size = 20
                    for i in range(0, len(raw_response), chunk_size):
                        yield f"data: {json.dumps({'type': 'content', 'content': raw_response[i:i+chunk_size]})}\n\n"
                        await asyncio.sleep(0.01)
                    accumulated_response += raw_response
                    break

                # Tool calls detected — build structured assistant message then execute
                print(f"🔧 Tool calls detected: {[tc['name'] for tc in tool_calls]}")

                # The chat template requires tool_calls on the assistant message (not just raw XML
                # in content) otherwise it rejects the following tool-role messages.
                # Extract any text before the first tool call (think block etc.) as content.
                pre_call_text = raw_response.split("<minimax:tool_call>")[0].strip() or None

                # Stream Kevin's text from this iteration to the user before the tool call events
                if pre_call_text:
                    chunk_size = 20
                    for _ci in range(0, len(pre_call_text), chunk_size):
                        yield f"data: {json.dumps({'type': 'content', 'content': pre_call_text[_ci:_ci+chunk_size]})}\n\n"
                        await asyncio.sleep(0.01)
                    accumulated_response += pre_call_text + "\n\n"

                tool_calls_structured = [
                    {
                        "id": f"call_{iteration}_{i}",
                        "type": "function",
                        "function": {
                            "name": tc["name"],
                            "arguments": tc["arguments"],  # dict — MiniMax template calls .items() on this
                        },
                    }
                    for i, tc in enumerate(tool_calls)
                ]
                current_messages.append({
                    "role": "assistant",
                    "content": pre_call_text,
                    "tool_calls": tool_calls_structured,
                })

                for i, tc in enumerate(tool_calls):
                    call_id = f"call_{iteration}_{i}"
                    yield f"data: {json.dumps({'type': 'tool_call', 'name': tc['name'], 'arguments': tc['arguments']})}\n\n"

                    result = execute_tool(tc["name"], tc["arguments"], agent.id, db)
                    print(f"  ✅ {tc['name']} → {result}")

                    yield f"data: {json.dumps({'type': 'tool_result', 'name': tc['name'], 'success': 'error' not in result, 'result': result, 'error': result.get('error') if isinstance(result, dict) else None})}\n\n"
                    current_messages.append(format_tool_result_message(tc["name"], result, call_id))

            # Save final accumulated response to DB
            assistant_tags = extract_keywords(accumulated_response, max_keywords=5)
            assistant_metadata = {
                "model": agent.model_path,
                "tool_iterations": iteration,
                "tags": assistant_tags,
            }
            if memory_narrative:
                assistant_metadata["memory_narrative"] = memory_narrative

            assistant_message = Message(
                conversation_id=conversation_id,
                role="assistant",
                content=accumulated_response,
                metadata_=assistant_metadata,
            )
            assistant_embedding = embedding_service.embed_with_tags(accumulated_response, assistant_tags)
            assistant_message.embedding = assistant_embedding
            db.add(assistant_message)
            db.commit()
            db.refresh(assistant_message)

            log_message(
                conversation_id=str(conversation_id),
                agent_id=str(agent.id),
                agent_name=agent.name,
                role="assistant",
                content=accumulated_response,
                metadata={"model": agent.model_path, "tool_iterations": iteration, "tags": assistant_tags},
            )

            yield f"data: {json.dumps({'type': 'done', 'user_message': user_message.to_dict(), 'assistant_message': assistant_message.to_dict()})}\n\n"
            print(f"✅ TOOL LOOP COMPLETE — {iteration} iteration(s), response saved to DB")

        return StreamingResponse(
            generate_stream_with_tools(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
        )

    # No tools — normal streaming path

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

            print(f"\n📤 REQUEST TO MAIN LLM:")
            print(f"Mode: Stateful in-process inference")
            print(f"Temperature: {agent.temperature}")
            print(f"Max Tokens: {agent.max_output_tokens if agent.max_output_tokens_enabled else 4096}")
            print(f"\n📨 MESSAGES ARRAY ({len(messages)} messages):")
            for i, msg in enumerate(messages):
                role = msg.get("role", "unknown")
                content = msg.get("content", "")
                print(f"\n  Message {i+1} [{role}]:")
                print(f"  {content}")
            print(f"{'='*80}\n")

            # Stream the response via stateful in-process inference
            async for content_chunk in inference_engine.stream_chat(
                conversation_id=conversation_id,
                messages=messages,
                model_path=agent.model_path,
                adapter_path=getattr(agent, "adapter_path", None) or None,
                temperature=agent.temperature,
                top_p=getattr(agent, "top_p", 1.0) or 1.0,
                top_k=getattr(agent, "top_k", 100) or 100,
                max_tokens=agent.max_output_tokens if agent.max_output_tokens_enabled else 4096,
                reasoning_enabled=agent.reasoning_enabled,
            ):
                final_response += content_chunk
                yield f"data: {json.dumps({'type': 'content', 'content': content_chunk})}\n\n"

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
            logger.error(f"Stream error for agent {agent.name}")
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
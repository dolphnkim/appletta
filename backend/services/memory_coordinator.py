"""Memory coordinator service - uses attached agent to select relevant memories

The memory coordinator is like the "subconscious" - it receives candidates
from vector search and decides which memories to surface organically.
"""

import httpx
import json
from typing import List, Optional, Dict, Tuple

from backend.services.mlx_manager import get_mlx_manager
from backend.services.memory_service import MemoryCandidate


async def coordinate_memories(
    candidates: List[MemoryCandidate],
    query_context: str,
    memory_agent,  # The attached memory agent (can be None)
    target_count: int = 7
) -> Tuple[str, Dict[str, List[str]]]:
    """Use memory coordinator agent to surface memories as first-person narrative

    Args:
        candidates: List of memory candidates from vector search
        query_context: The current message/context
        memory_agent: The Agent object to use for coordination (or None for fallback)
        target_count: Target number of memories to select (default 7)

    Returns:
        Tuple of (narrative string, tag_updates dict)
        - narrative: First-person narrative about surfaced memories
        - tag_updates: Dict mapping memory IDs to updated tag lists
    """

    if not candidates:
        return ("", {})

    # If no memory agent attached, fall back to simple formatted list
    if memory_agent is None:
        top_memories = candidates[:target_count]
        if not top_memories:
            return ("", {})

        # Simple fallback formatting
        narrative = "Some memories are surfacing:\n\n"
        for memory in top_memories:
            narrative += f"- {memory.content[:200]}...\n"
        return (narrative, {})

    # Get or start MLX server for memory agent
    mlx_manager = get_mlx_manager()
    mlx_process = mlx_manager.get_agent_server(memory_agent.id)

    if not mlx_process:
        try:
            mlx_process = await mlx_manager.start_agent_server(memory_agent)
        except Exception:
            # If we can't start memory agent, fall back to simple formatting
            top_memories = candidates[:target_count]
            narrative = "Some memories are surfacing:\n\n"
            for memory in top_memories:
                narrative += f"- {memory.content[:200]}...\n"
            return (narrative, {})

    # Build memory candidates for the prompt - include full content and tags
    candidates_text = ""
    for i, candidate in enumerate(candidates, 1):
        tags = candidate.metadata.get("tags", []) if candidate.metadata else []
        candidates_text += f"\n--- Memory {i} (ID: {candidate.id}) ---\n"
        candidates_text += f"Type: {candidate.source_type}\n"
        candidates_text += f"Similarity: {candidate.similarity_score:.3f}\n"
        candidates_text += f"Current Tags: {tags}\n"
        candidates_text += f"Content:\n{candidate.content}\n"

    system_prompt = """You are the subconscious memory system for an AI agent. Your role is to surface relevant memories as organic, first-person thoughts AND curate their thematic tags.

You'll receive memory candidates from vector search. Each has initial auto-generated tags. Your job is to:
1. Select the most relevant memories (aim for 5-10)
2. Write a first-person narrative about WHY these memories are surfacing
3. Make connections between memories - explain relationships, patterns, contrasts
4. Review and edit tags to reflect deeper thematic concepts

For tags: Think beyond literal keywords. Capture themes, emotional undertones, patterns. Examples:
- "architecture" → "architecture-overthinking" or "design-anxiety"
- "conversation" → "reflective-dialogue" or "conceptual-exploration"
- "error" → "failure-analysis" or "debugging-frustration"

Be introspective and organic. Write naturally as thoughts arise.

Response format:
First, write your narrative reflection.
Then, on a new line, provide tag updates in this exact format:
TAGS: {"memory_id": ["tag1", "tag2"], "another_id": ["tag3", "tag4"]}

Example:
"I'm remembering that conversation about context windows - it feels relevant because we're bumping into similar constraints here..."

TAGS: {"msg-123": ["resource-constraints", "architecture-patterns"], "jb-456": ["self-doubt", "design-philosophy"]}"""

    user_prompt = f"""Current query: {query_context}

Available memories:
{candidates_text}

Write your first-person reflection and provide tag updates:"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]

    # Call memory coordinator agent
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:  # Longer timeout for narrative generation
            response = await client.post(
                f"http://localhost:{mlx_process.port}/v1/chat/completions",
                json={
                    "messages": messages,
                    "temperature": memory_agent.temperature,
                    "max_tokens": 2048,  # More tokens for narrative
                }
            )
            response.raise_for_status()
            result = response.json()
    except httpx.HTTPError:
        # Fall back to simple formatting on error
        top_memories = candidates[:target_count]
        narrative = "Some memories are surfacing:\n\n"
        for memory in top_memories:
            narrative += f"- {memory.content[:200]}...\n"
        return (narrative, {})

    # Extract the narrative and tag updates from response
    try:
        content = result["choices"][0]["message"]["content"]

        if not content or not content.strip():
            raise ValueError("Empty response")

        # Split narrative from tag updates
        if "TAGS:" in content:
            parts = content.split("TAGS:", 1)
            narrative = parts[0].strip()
            tags_json = parts[1].strip()

            # Parse tag updates
            tag_updates = {}
            try:
                tag_updates = json.loads(tags_json)
            except json.JSONDecodeError:
                # If tag parsing fails, continue with empty tag updates
                pass

            narrative_text = narrative if narrative else "Some memories are surfacing..."
            return (narrative_text, tag_updates)
        else:
            # No tags section, return full content as narrative with no tag updates
            return (content.strip(), {})

    except (KeyError, IndexError, ValueError):
        pass

    # Fall back to simple formatting if extraction failed
    top_memories = candidates[:target_count]
    narrative = "Some memories are surfacing:\n\n"
    for memory in top_memories:
        narrative += f"- {memory.content[:200]}...\n"
    return (narrative, {})

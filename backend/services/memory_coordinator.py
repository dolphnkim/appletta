"""Memory coordinator service - uses attached agent to select relevant memories

The memory coordinator is like the "subconscious" - it receives candidates
from vector search and decides which memories to surface organically.
"""

import httpx
import json
from typing import List, Optional

from backend.services.mlx_manager import get_mlx_manager
from backend.services.memory_service import MemoryCandidate


async def coordinate_memories(
    candidates: List[MemoryCandidate],
    query_context: str,
    memory_agent,  # The attached memory agent (can be None)
    target_count: int = 7
) -> str:
    """Use memory coordinator agent to surface memories as first-person narrative

    Args:
        candidates: List of memory candidates from vector search
        query_context: The current message/context
        memory_agent: The Agent object to use for coordination (or None for fallback)
        target_count: Target number of memories to select (default 7)

    Returns:
        First-person narrative about surfaced memories (or empty string if none)
    """

    if not candidates:
        return ""

    # If no memory agent attached, fall back to simple formatted list
    if memory_agent is None:
        top_memories = candidates[:target_count]
        if not top_memories:
            return ""

        # Simple fallback formatting
        narrative = "Some memories are surfacing:\n\n"
        for memory in top_memories:
            narrative += f"- {memory.content[:200]}...\n"
        return narrative

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
            return narrative

    # Build memory candidates for the prompt - include full content
    candidates_text = ""
    for i, candidate in enumerate(candidates, 1):
        candidates_text += f"\n--- Memory {i} ---\n"
        candidates_text += f"Type: {candidate.source_type}\n"
        candidates_text += f"Similarity: {candidate.similarity_score:.3f}\n"
        candidates_text += f"Content:\n{candidate.content}\n"

    system_prompt = """You are the subconscious memory system for an AI agent. Your role is to surface relevant memories as organic, first-person thoughts.

You'll receive memory candidates from vector search. Your job is to:
1. Select the most relevant memories (aim for 5-10)
2. Write a first-person narrative about WHY these memories are surfacing
3. Make connections between memories - explain relationships, patterns, contrasts
4. Be introspective and organic, like thoughts naturally arising

Write as "I'm remembering..." or "This reminds me of..." Connect the dots. Show your thinking.

Example response:
"I'm remembering that conversation about context windows - it feels relevant because we're bumping into similar constraints here. There's also that note I made about token budgets, and I'm noticing a pattern in how I approach these resource management problems. The interesting thing is how this connects to that earlier idea about memory hierarchies..."

Write naturally. Don't list or structure - let thoughts flow."""

    user_prompt = f"""Current query: {query_context}

Available memories:
{candidates_text}

Write your first-person reflection about which memories are surfacing and why:"""

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
        return narrative

    # Extract the narrative from response
    try:
        content = result["choices"][0]["message"]["content"]

        # Return the narrative directly
        if content and content.strip():
            return content.strip()
    except (KeyError, IndexError):
        pass

    # Fall back to simple formatting if extraction failed
    top_memories = candidates[:target_count]
    narrative = "Some memories are surfacing:\n\n"
    for memory in top_memories:
        narrative += f"- {memory.content[:200]}...\n"
    return narrative

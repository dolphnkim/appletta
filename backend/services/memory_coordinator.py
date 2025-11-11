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
) -> List[str]:
    """Use memory coordinator agent to select which memories to surface

    Args:
        candidates: List of memory candidates from vector search
        query_context: The current message/context
        memory_agent: The Agent object to use for coordination (or None for fallback)
        target_count: Target number of memories to select (default 7)

    Returns:
        List of memory IDs to surface
    """

    if not candidates:
        return []

    # If no memory agent attached, fall back to top-N by similarity
    if memory_agent is None:
        return [c.id for c in candidates[:target_count]]

    # Get or start MLX server for memory agent
    mlx_manager = get_mlx_manager()
    mlx_process = mlx_manager.get_agent_server(memory_agent.id)

    if not mlx_process:
        try:
            mlx_process = await mlx_manager.start_agent_server(memory_agent)
        except Exception:
            # If we can't start memory agent, fall back to top-N
            return [c.id for c in candidates[:target_count]]

    # Build prompt for coordinator
    candidates_text = ""
    for i, candidate in enumerate(candidates, 1):
        candidates_text += f"\n{i}. ID: {candidate.id}\n"
        candidates_text += f"   Type: {candidate.source_type}\n"
        candidates_text += f"   Similarity: {candidate.similarity_score:.3f}\n"
        candidates_text += f"   Content: {candidate.content[:200]}...\n"

    system_prompt = """You are a memory coordinator for an AI agent. Your role is to select which memories to surface.

Given a list of memory candidates (from vector similarity search), select the ones that would be most valuable to surface in the current conversation. Consider:

1. Direct relevance to the current message
2. Tangentially related memories that might spark insights
3. Temporal/contextual connections
4. Surprising but potentially meaningful associations

Be organic - trust your intuition about what memories feel relevant. Don't just pick the highest similarity scores.

Respond with a JSON array of memory IDs to surface. Select between 3-10 memories (aim for ~7).

Example response:
["id1", "id2", "id3", "id4", "id5"]"""

    user_prompt = f"""Current message: {query_context}

Memory candidates:
{candidates_text}

Select memory IDs to surface (respond with JSON array only):"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]

    # Call memory coordinator agent
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"http://localhost:{mlx_process.port}/v1/chat/completions",
                json={
                    "messages": messages,
                    "temperature": memory_agent.temperature,
                    "max_tokens": 512,
                }
            )
            response.raise_for_status()
            result = response.json()
    except httpx.HTTPError:
        # Fall back to top-N on error
        return [c.id for c in candidates[:target_count]]

    # Parse response
    try:
        content = result["choices"][0]["message"]["content"]

        # Extract JSON array from response
        # Handle cases where model might add explanation before/after JSON
        start_idx = content.find("[")
        end_idx = content.rfind("]") + 1

        if start_idx >= 0 and end_idx > start_idx:
            json_str = content[start_idx:end_idx]
            selected_ids = json.loads(json_str)

            # Validate that selected IDs exist in candidates
            candidate_ids = {c.id for c in candidates}
            valid_ids = [id for id in selected_ids if id in candidate_ids]

            # If we got valid IDs, return them
            if valid_ids:
                return valid_ids[:target_count]  # Cap at target count
    except (json.JSONDecodeError, KeyError, IndexError):
        pass

    # Fall back to top-N if parsing failed
    return [c.id for c in candidates[:target_count]]

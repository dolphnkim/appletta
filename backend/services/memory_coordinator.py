"""Memory coordinator service - uses Qwen2.5-3B to select relevant memories

The memory coordinator is like the "subconscious" - it receives candidates
from vector search and decides which memories to surface organically.
"""

import httpx
import json
from typing import List, Dict, Any
from uuid import UUID

from backend.core.config import settings
from backend.services.mlx_manager import get_mlx_manager
from backend.services.memory_service import MemoryCandidate


class MemoryCoordinatorProcess:
    """Singleton process for the memory coordinator MLX server"""

    def __init__(self, port: int):
        self.port = port
        self.process = None
        self.model_path = settings.MEMORY_COORDINATOR_MODEL_PATH


# Global instance
_coordinator_process = None


async def get_coordinator_process() -> MemoryCoordinatorProcess:
    """Get or start the memory coordinator server"""
    global _coordinator_process

    if not settings.MEMORY_COORDINATOR_MODEL_PATH:
        raise RuntimeError("MEMORY_COORDINATOR_MODEL_PATH not configured")

    if _coordinator_process is None:
        _coordinator_process = MemoryCoordinatorProcess(
            port=settings.MEMORY_COORDINATOR_PORT
        )

        # Start MLX server for memory coordinator
        mlx_manager = get_mlx_manager()

        # Create a minimal agent-like object for the MLX manager
        class CoordinatorConfig:
            id = UUID("00000000-0000-0000-0000-000000000001")  # Special ID
            model_path = settings.MEMORY_COORDINATOR_MODEL_PATH
            adapter_path = None
            temperature = 0.3  # Lower temperature for more focused selection
            max_output_tokens_enabled = True
            max_output_tokens = 2048
            top_p = 1.0
            top_k = 0
            seed = None
            reasoning_enabled = False

        try:
            process = await mlx_manager.start_agent_server(
                CoordinatorConfig(),
                port_override=settings.MEMORY_COORDINATOR_PORT
            )
            _coordinator_process.process = process
        except Exception as e:
            raise RuntimeError(f"Failed to start memory coordinator: {str(e)}")

    return _coordinator_process


async def coordinate_memories(
    candidates: List[MemoryCandidate],
    query_context: str,
    target_count: int = 7
) -> List[str]:
    """Use memory coordinator to select which memories to surface

    Args:
        candidates: List of memory candidates from vector search
        query_context: The current message/context
        target_count: Target number of memories to select (default 7)

    Returns:
        List of memory IDs to surface
    """

    if not candidates:
        return []

    # Get coordinator process
    try:
        coordinator = await get_coordinator_process()
    except RuntimeError:
        # If coordinator not configured, fall back to top-N by similarity
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

    # Call coordinator model
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"http://localhost:{coordinator.port}/v1/chat/completions",
                json={
                    "messages": messages,
                    "temperature": 0.3,
                    "max_tokens": 512,
                }
            )
            response.raise_for_status()
            result = response.json()
    except httpx.HTTPError as e:
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

"""LLM Tools for interacting with journal blocks and other agent capabilities

These tools are provided to the main LLM via function calling.
The LLM can create, read, update, and delete journal blocks to maintain its memory.
"""

from typing import Dict, List, Any, Optional
from uuid import UUID
from sqlalchemy.orm import Session
from sqlalchemy import text

from backend.db.models.journal_block import JournalBlock
from backend.services.embedding_service import get_embedding_service
from backend.services.memory_service import search_memories as search_memories_service, fetch_full_memories


# ============================================================================
# Tool Definitions (OpenAI Function Calling Format)
# ============================================================================

# Map of all available tools by name
ALL_TOOLS = {}  # Will be populated below

JOURNAL_BLOCK_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_journal_blocks",
            "description": "List all journal blocks to see what topics/information you're currently tracking. Returns label and ID for each block.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_journal_block",
            "description": "Read the full content of a specific journal block. Use this when you need detailed information from a block.",
            "parameters": {
                "type": "object",
                "properties": {
                    "block_id": {
                        "type": "string",
                        "description": "The ID of the journal block to read"
                    }
                },
                "required": ["block_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_journal_block",
            "description": "Create a new journal block to track information about a specific topic (e.g., 'User Info', 'Project Notes', 'Reflections'). Use this to organize your memory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "label": {
                        "type": "string",
                        "description": "A short label for this block (e.g., 'User Info', 'Project: Appletta')"
                    },
                    "value": {
                        "type": "string",
                        "description": "The content to store in this block"
                    }
                },
                "required": ["label", "value"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "update_journal_block",
            "description": "Update an existing journal block. You can change the label, value, or both.",
            "parameters": {
                "type": "object",
                "properties": {
                    "block_id": {
                        "type": "string",
                        "description": "The ID of the block to update"
                    },
                    "label": {
                        "type": "string",
                        "description": "New label for the block (optional)"
                    },
                    "value": {
                        "type": "string",
                        "description": "New content for the block (optional)"
                    }
                },
                "required": ["block_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "delete_journal_block",
            "description": "Delete a journal block. Use this to remove information you no longer need to track.",
            "parameters": {
                "type": "object",
                "properties": {
                    "block_id": {
                        "type": "string",
                        "description": "The ID of the block to delete"
                    }
                },
                "required": ["block_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_memories",
            "description": "Search across all memories (journal blocks, uploaded files, and past conversations) using semantic similarity. Use this when you want to actively find relevant information.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query (what you're looking for)"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of results to return (default: 5)",
                        "default": 5
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_memories",
            "description": "Fetch full content of specific memories by their IDs. Use this to get complete details about memories you've identified.",
            "parameters": {
                "type": "object",
                "properties": {
                    "memory_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of memory IDs to fetch"
                    }
                },
                "required": ["memory_ids"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_rag_files",
            "description": "List all uploaded files/documents that are attached to your context. Use this to see what reference materials are available.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    }
]

# Populate ALL_TOOLS map for easy lookup
for tool in JOURNAL_BLOCK_TOOLS:
    tool_name = tool["function"]["name"]
    ALL_TOOLS[tool_name] = tool


# ============================================================================
# Tool Filtering
# ============================================================================

def get_enabled_tools(enabled_tool_names: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """Get list of tools filtered by enabled tool names

    Args:
        enabled_tool_names: List of tool names to enable. If None or empty, returns all tools.

    Returns:
        List of tool definitions in OpenAI function calling format
    """
    if not enabled_tool_names:
        # No filter - return all tools
        return JOURNAL_BLOCK_TOOLS

    # Filter tools by name
    filtered_tools = []
    for tool_name in enabled_tool_names:
        if tool_name in ALL_TOOLS:
            filtered_tools.append(ALL_TOOLS[tool_name])

    return filtered_tools


def get_tools_description(enabled_tool_names: Optional[List[str]] = None) -> str:
    """Generate a human-readable description of enabled tools

    Args:
        enabled_tool_names: List of enabled tool names. If None/empty, describes all tools.

    Returns:
        Formatted string describing the tools
    """
    tools = get_enabled_tools(enabled_tool_names)

    if not tools:
        return "No tools enabled"

    descriptions = []
    descriptions.append("You have access to the following tools. To use a tool, respond with a tool call in this exact format:\n")
    descriptions.append('<tool_call>')
    descriptions.append('{"name": "tool_name", "arguments": {"param": "value"}}')
    descriptions.append('</tool_call>\n')
    descriptions.append("Available tools:")

    for tool in tools:
        tool_func = tool["function"]
        name = tool_func["name"]
        desc = tool_func["description"]
        params = tool_func.get("parameters", {}).get("properties", {})
        required = tool_func.get("parameters", {}).get("required", [])

        # Build parameter description
        param_desc = []
        for param_name, param_info in params.items():
            param_type = param_info.get("type", "string")
            param_desc_text = param_info.get("description", "")
            req_marker = " (required)" if param_name in required else " (optional)"
            param_desc.append(f"    - {param_name} ({param_type}){req_marker}: {param_desc_text}")

        descriptions.append(f"\n• {name}")
        descriptions.append(f"  Description: {desc}")
        if param_desc:
            descriptions.append("  Parameters:")
            descriptions.extend(param_desc)

        # Add usage example for common tools
        if name == "create_journal_block":
            descriptions.append("  Example:")
            descriptions.append('  <tool_call>')
            descriptions.append('  {"name": "create_journal_block", "arguments": {"label": "User Info", "value": "User prefers dark mode"}}')
            descriptions.append('  </tool_call>')
        elif name == "list_journal_blocks":
            descriptions.append("  Example:")
            descriptions.append('  <tool_call>')
            descriptions.append('  {"name": "list_journal_blocks", "arguments": {}}')
            descriptions.append('  </tool_call>')

    return "\n".join(descriptions)


# ============================================================================
# Tool Execution Functions
# ============================================================================

def execute_tool(
    tool_name: str,
    arguments: Dict[str, Any],
    agent_id: UUID,
    db: Session
) -> Dict[str, Any]:
    """Execute a tool call and return the result

    Args:
        tool_name: Name of the tool to execute
        arguments: Tool arguments as dict
        agent_id: ID of the agent making the call
        db: Database session

    Returns:
        Dictionary with tool result
    """

    if tool_name == "list_journal_blocks":
        return list_journal_blocks(agent_id, db)

    elif tool_name == "read_journal_block":
        return read_journal_block(arguments["block_id"], db)

    elif tool_name == "create_journal_block":
        return create_journal_block(
            agent_id,
            arguments["label"],
            arguments["value"],
            db
        )

    elif tool_name == "update_journal_block":
        return update_journal_block(
            arguments["block_id"],
            arguments.get("label"),
            arguments.get("value"),
            db
        )

    elif tool_name == "delete_journal_block":
        return delete_journal_block(arguments["block_id"], db)

    elif tool_name == "search_memories":
        return search_memories(
            agent_id,
            arguments["query"],
            arguments.get("limit", 5),
            db
        )

    elif tool_name == "fetch_memories":
        return fetch_memories(arguments["memory_ids"], db)

    elif tool_name == "list_rag_files":
        return list_rag_files(agent_id, db)

    else:
        return {"error": f"Unknown tool: {tool_name}"}


# ============================================================================
# Tool Implementation Functions
# ============================================================================

def list_journal_blocks(agent_id: UUID, db: Session) -> Dict[str, Any]:
    """List all journal blocks for the agent"""
    blocks = db.query(JournalBlock).filter(
        JournalBlock.agent_id == agent_id
    ).order_by(JournalBlock.updated_at.desc()).all()

    return {
        "blocks": [
            {
                "id": str(block.id),
                "label": block.label,
                "updated_at": block.updated_at.isoformat() if block.updated_at else None
            }
            for block in blocks
        ]
    }


def read_journal_block(block_id: str, db: Session) -> Dict[str, Any]:
    """Read full content of a journal block"""
    try:
        block = db.query(JournalBlock).filter(
            JournalBlock.id == UUID(block_id)
        ).first()

        if not block:
            return {"error": f"Journal block {block_id} not found"}

        return {
            "id": str(block.id),
            "label": block.label,
            "value": block.value,
            "created_at": block.created_at.isoformat() if block.created_at else None,
            "updated_at": block.updated_at.isoformat() if block.updated_at else None
        }
    except ValueError:
        return {"error": f"Invalid block ID: {block_id}"}


def create_journal_block(
    agent_id: UUID,
    label: str,
    value: str,
    db: Session
) -> Dict[str, Any]:
    """Create a new journal block"""
    # Generate block_id from label
    block_id = JournalBlock.generate_block_id(label)

    # Check if block_id already exists for this agent
    existing = db.query(JournalBlock).filter(
        JournalBlock.agent_id == agent_id,
        JournalBlock.block_id == block_id
    ).first()

    if existing:
        return {
            "error": f"Journal block with label '{label}' (block_id: '{block_id}') already exists. Consider updating it instead or using a different label."
        }

    # Generate embedding for the value
    embedding_service = get_embedding_service()
    block_embedding = embedding_service.embed_text(value)

    block = JournalBlock(
        agent_id=agent_id,
        label=label,
        block_id=block_id,
        value=value,
        embedding=block_embedding,
        editable_by_main_agent=True,  # Main agent can edit blocks it creates
        editable_by_memory_agent=False,
        read_only=False
    )

    db.add(block)
    db.commit()
    db.refresh(block)

    return {
        "success": True,
        "id": str(block.id),
        "block_id": block_id,
        "message": f"Created journal block '{label}' (block_id: {block_id})"
    }


def update_journal_block(
    block_id: str,
    label: Optional[str],
    value: Optional[str],
    db: Session
) -> Dict[str, Any]:
    """Update an existing journal block"""
    try:
        block = db.query(JournalBlock).filter(
            JournalBlock.id == UUID(block_id)
        ).first()

        if not block:
            return {"error": f"Journal block {block_id} not found"}

        # Check permissions
        if block.read_only:
            return {"error": f"Journal block '{block.label}' is read-only and cannot be modified"}

        if not block.editable_by_main_agent:
            return {"error": f"Journal block '{block.label}' cannot be edited by the main agent"}

        if label is not None:
            block.label = label
        if value is not None:
            block.value = value
            # Re-generate embedding if value changed
            embedding_service = get_embedding_service()
            block.embedding = embedding_service.embed_text(value)

        db.commit()

        return {
            "success": True,
            "message": f"Updated journal block '{block.label}'"
        }
    except ValueError:
        return {"error": f"Invalid block ID: {block_id}"}


def delete_journal_block(block_id: str, db: Session) -> Dict[str, Any]:
    """Delete a journal block"""
    try:
        block = db.query(JournalBlock).filter(
            JournalBlock.id == UUID(block_id)
        ).first()

        if not block:
            return {"error": f"Journal block {block_id} not found"}

        # Check permissions
        if block.read_only:
            return {"error": f"Journal block '{block.label}' is read-only and cannot be deleted"}

        if not block.editable_by_main_agent:
            return {"error": f"Journal block '{block.label}' cannot be deleted by the main agent"}

        label = block.label
        db.delete(block)
        db.commit()

        return {
            "success": True,
            "message": f"Deleted journal block '{label}'"
        }
    except ValueError:
        return {"error": f"Invalid block ID: {block_id}"}


# ============================================================================
# Memory Search Tool Functions
# ============================================================================

def search_memories(
    agent_id: UUID,
    query: str,
    limit: int,
    db: Session
) -> Dict[str, Any]:
    """Search across all memories using semantic similarity"""
    try:
        # Use the memory service to search
        candidates = search_memories_service(query, agent_id, db, limit=limit)

        return {
            "memories": [
                {
                    "id": candidate.id,
                    "source_type": candidate.source_type,
                    "content": candidate.content,
                    "similarity_score": candidate.similarity_score,
                    "metadata": candidate.metadata
                }
                for candidate in candidates
            ],
            "count": len(candidates)
        }
    except Exception as e:
        return {"error": f"Memory search failed: {str(e)}"}


def fetch_memories(memory_ids: List[str], db: Session) -> Dict[str, Any]:
    """Fetch full content of specific memories by ID"""
    try:
        memories = fetch_full_memories(memory_ids, db)
        return {
            "memories": memories,
            "count": len(memories)
        }
    except Exception as e:
        return {"error": f"Failed to fetch memories: {str(e)}"}


def list_rag_files(agent_id: UUID, db: Session) -> Dict[str, Any]:
    """List all RAG files/folders attached to this agent"""
    try:
        query = text("""
            SELECT
                folder.id as folder_id,
                folder.name as folder_name,
                COUNT(DISTINCT file.id) as file_count,
                COUNT(DISTINCT chunk.id) as chunk_count
            FROM rag_folders folder
            LEFT JOIN rag_files file ON file.folder_id = folder.id
            LEFT JOIN rag_chunks chunk ON chunk.file_id = file.id
            WHERE folder.agent_id = :agent_id
            GROUP BY folder.id, folder.name
            ORDER BY folder.name
        """)

        results = db.execute(query, {"agent_id": str(agent_id)}).fetchall()

        folders = [
            {
                "folder_id": str(row.folder_id),
                "folder_name": row.folder_name,
                "file_count": row.file_count or 0,
                "chunk_count": row.chunk_count or 0
            }
            for row in results
        ]

        # Also get individual files
        files_query = text("""
            SELECT
                file.id,
                file.filename,
                file.folder_id,
                COUNT(chunk.id) as chunk_count
            FROM rag_files file
            JOIN rag_folders folder ON file.folder_id = folder.id
            LEFT JOIN rag_chunks chunk ON chunk.file_id = file.id
            WHERE folder.agent_id = :agent_id
            GROUP BY file.id, file.filename, file.folder_id
            ORDER BY file.filename
        """)

        file_results = db.execute(files_query, {"agent_id": str(agent_id)}).fetchall()

        files = [
            {
                "file_id": str(row.id),
                "filename": row.filename,
                "folder_id": str(row.folder_id),
                "chunk_count": row.chunk_count or 0
            }
            for row in file_results
        ]

        return {
            "folders": folders,
            "files": files,
            "total_folders": len(folders),
            "total_files": len(files)
        }
    except Exception as e:
        return {"error": f"Failed to list RAG files: {str(e)}"}

"""LLM Tools for interacting with journal blocks and other agent capabilities

These tools are provided to the main LLM via function calling.
The LLM can create, read, update, and delete journal blocks to maintain its memory.
"""

from typing import Dict, List, Any, Optional
from uuid import UUID
from sqlalchemy.orm import Session

from backend.db.models.journal_block import JournalBlock
from backend.services.embedding_service import get_embedding_service


# ============================================================================
# Tool Definitions (OpenAI Function Calling Format)
# ============================================================================

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
    }
]


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

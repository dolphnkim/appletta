"""LLM Tools for interacting with journal blocks and other agent capabilities

These tools are provided to the main LLM via function calling.
The LLM can create, read, update, and delete journal blocks to maintain its memory.
"""

from typing import Dict, List, Any, Optional
from uuid import UUID
from sqlalchemy.orm import Session
from sqlalchemy import text
from cachetools import TTLCache

from backend.db.models.journal_block import JournalBlock
from backend.services.embedding_service import get_embedding_service
from backend.services.memory_service import search_memories as search_memories_service, fetch_full_memories

# ============================================================================
# Web Tools Cache (30 minute TTL)
# ============================================================================
_web_cache = TTLCache(maxsize=100, ttl=1800)  # 100 items, 30 min TTL


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
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the web using DuckDuckGo. Returns a list of results with titles, URLs, and snippets. Use this to find current information or research topics.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query"
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum number of results to return (default: 5, max: 10)",
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
            "name": "fetch_url",
            "description": "Fetch and extract the main content from a web page URL. Returns the page title and content in markdown format. Use this to read specific web pages.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The URL of the web page to fetch"
                    },
                    "include_links": {
                        "type": "boolean",
                        "description": "Whether to include links found on the page (default: false)",
                        "default": False
                    }
                },
                "required": ["url"]
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


def get_tools_description(enabled_tool_names: Optional[List[str]] = None, agent_id: Optional[UUID] = None, db: Optional[Session] = None) -> str:
    """Generate inline tool instructions based on enabled tools
    
    Args:
        enabled_tool_names: List of enabled tool names. If None/empty, describes all tools.
        agent_id: Agent ID to get current journal blocks (optional)
        db: Database session (optional, needed for journal block list)
    
    Returns:
        Formatted string with tool instructions in XML format
    """
    tools = get_enabled_tools(enabled_tool_names)
    
    if not tools:
        return "No tools enabled"
    
    # Get tool names for easy checking
    tool_names = {t["function"]["name"] for t in tools}
    
    instructions = """
═══════════════════════════════════════════════════════════════════════════════
📝 YOUR MEMORY & TOOLS SYSTEM
═══════════════════════════════════════════════════════════════════════════════

You have tools you can use by including them anywhere in your response.
Tool calls are filtered from what the user sees - use them freely!

"""
    
    # Show current journal blocks if we have db access
    if agent_id and db and any(t in tool_names for t in ["list_journal_blocks", "read_journal_block", "create_journal_block", "update_journal_block", "delete_journal_block"]):
        blocks_info = list_journal_blocks(agent_id, db)
        blocks = blocks_info.get("blocks", [])
        
        instructions += "YOUR CURRENT JOURNAL BLOCKS:\n"
        if blocks:
            for block in blocks:
                instructions += f"  • {block['label']}\n"
        else:
            instructions += "  (none yet)\n"
        instructions += "\n"
    
    # Show RAG folders if we have db access and that tool is enabled
    if agent_id and db and "list_rag_files" in tool_names:
        rag_info = list_rag_files(agent_id, db)
        folders = rag_info.get("folders", [])
        
        instructions += "YOUR RAG FOLDERS:\n"
        if folders:
            for folder in folders:
                instructions += f"  • {folder['folder_name']}\n"
        else:
            instructions += "  (none)\n"
        instructions += "\n"
    
    instructions += """───────────────────────────────────────────────────────────────────────────────
AVAILABLE TOOLS (include these anywhere in your response)
───────────────────────────────────────────────────────────────────────────────
"""
    
    # Journal block tools
    if "create_journal_block" in tool_names:
        instructions += """
CREATE A NEW JOURNAL BLOCK:
<create_journal_block>
label: Title Here (max 50 chars)
content: Your content here
</create_journal_block>
"""
    
    if "read_journal_block" in tool_names:
        instructions += """
READ A JOURNAL BLOCK:
<read_journal_block>
block_name: Title of Block
</read_journal_block>
"""
    
    if "update_journal_block" in tool_names:
        instructions += """
EDIT A JOURNAL BLOCK (3 options):

  Option 1 - Append to existing content:
  <edit_journal_block>
  block_name: Title of Block
  append: New info to add at the end
  </edit_journal_block>

  Option 2 - Find and replace text:
  <edit_journal_block>
  block_name: Title of Block
  find: text to find
  replace: replacement text
  </edit_journal_block>

  Option 3 - Completely rewrite:
  <edit_journal_block>
  block_name: Title of Block
  new_content: The complete new content
  </edit_journal_block>
"""
    
    if "delete_journal_block" in tool_names:
        instructions += """
DELETE A JOURNAL BLOCK:
<delete_journal_block>
block_name: Title of Block
</delete_journal_block>
"""
    
    if "search_memories" in tool_names:
        instructions += """
SEARCH YOUR MEMORIES:
<search_memories>
query: what to search for
</search_memories>
"""
    
    if "list_journal_blocks" in tool_names:
        instructions += """
LIST ALL JOURNAL BLOCKS:
<list_journal_blocks>
</list_journal_blocks>
"""
    
    if "list_rag_files" in tool_names:
        instructions += """
LIST RAG FILES:
<list_rag_files>
</list_rag_files>
"""
    
    # Web tools
    if "web_search" in tool_names:
        instructions += """
SEARCH THE WEB:
<web_search>
query: what to search for
max_results: 5
</web_search>
"""
    
    if "fetch_url" in tool_names:
        instructions += """
FETCH A WEB PAGE:
<fetch_url>
url: https://example.com/page
</fetch_url>
"""
    
    instructions += """
═══════════════════════════════════════════════════════════════════════════════
"""
    
    return instructions


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

    elif tool_name == "web_search":
        return web_search(
            arguments["query"],
            arguments.get("max_results", 5)
        )

    elif tool_name == "fetch_url":
        return fetch_url(
            arguments["url"],
            arguments.get("include_links", False)
        )

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


# ============================================================================
# Web Search and Fetch Tools
# ============================================================================

def web_search(query: str, max_results: int = 5) -> Dict[str, Any]:
    """Search the web using DuckDuckGo"""
    try:
        # Check cache first
        cache_key = f"search:{query}:{max_results}"
        if cache_key in _web_cache:
            return _web_cache[cache_key]

        # Lazy import to avoid startup cost
        from duckduckgo_search import DDGS

        # Clamp max_results
        max_results = min(max(1, max_results), 10)

        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))

        formatted_results = [
            {
                "title": r.get("title", ""),
                "url": r.get("href", ""),
                "snippet": r.get("body", "")
            }
            for r in results
        ]

        response = {
            "query": query,
            "results": formatted_results,
            "count": len(formatted_results)
        }

        # Cache the result
        _web_cache[cache_key] = response
        return response

    except Exception as e:
        return {"error": f"Web search failed: {str(e)}"}


def fetch_url(url: str, include_links: bool = False) -> Dict[str, Any]:
    """Fetch and extract main content from a web page"""
    try:
        # Check cache first
        cache_key = f"fetch:{url}:{include_links}"
        if cache_key in _web_cache:
            return _web_cache[cache_key]

        # Lazy import
        import trafilatura
        from trafilatura.settings import use_config

        # Configure trafilatura
        config = use_config()
        config.set("DEFAULT", "EXTRACTION_TIMEOUT", "30")

        # Download the page
        downloaded = trafilatura.fetch_url(url)
        if not downloaded:
            return {"error": f"Failed to download page: {url}"}

        # Extract main content as markdown
        content = trafilatura.extract(
            downloaded,
            output_format="markdown",
            include_links=include_links,
            include_tables=True,
            favor_precision=True,
            config=config
        )

        if not content:
            return {"error": f"Failed to extract content from: {url}"}

        # Get metadata (title, etc.)
        metadata = trafilatura.extract_metadata(downloaded)
        title = metadata.title if metadata else "Unknown"

        # Truncate if too long (avoid massive responses)
        max_chars = 50000
        truncated = False
        if len(content) > max_chars:
            content = content[:max_chars] + "\n\n[Content truncated...]"
            truncated = True

        response = {
            "url": url,
            "title": title,
            "content": content,
            "truncated": truncated,
            "character_count": len(content)
        }

        # Optionally extract links
        if include_links:
            # Extract all links from the page
            from trafilatura import extract
            links_content = extract(
                downloaded,
                output_format="xml",
                include_links=True
            )
            # Parse links if needed (simplified for now)
            response["links_included"] = True

        # Cache the result
        _web_cache[cache_key] = response
        return response

    except Exception as e:
        return {"error": f"Failed to fetch URL: {str(e)}"}

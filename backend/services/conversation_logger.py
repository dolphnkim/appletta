"""Conversation Logger - Logs all messages to JSONL file for human-readable history"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional


def get_log_directory() -> Path:
    """Get the log directory path (~/.appletta)"""
    home_dir = Path.home()
    log_dir = home_dir / ".appletta"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def get_log_file_path() -> Path:
    """Get the path to the JSONL log file"""
    return get_log_directory() / "conversations.jsonl"


def log_message(
    conversation_id: str,
    agent_id: str,
    agent_name: str,
    role: str,
    content: str,
    metadata: Optional[Dict[str, Any]] = None
):
    """Log a single message to the JSONL file

    Args:
        conversation_id: UUID of the conversation
        agent_id: UUID of the agent
        agent_name: Human-readable name of the agent
        role: 'user' or 'assistant'
        content: The message content
        metadata: Optional metadata (model, tags, etc.)
    """
    log_entry = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "conversation_id": str(conversation_id),
        "agent_id": str(agent_id),
        "agent_name": agent_name,
        "role": role,
        "content": content,
    }

    if metadata:
        log_entry["metadata"] = metadata

    log_file = get_log_file_path()

    try:
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
    except Exception as e:
        # Don't fail the main operation if logging fails
        print(f"⚠️ Failed to log message to {log_file}: {e}")


def log_conversation_event(
    conversation_id: str,
    agent_id: str,
    agent_name: str,
    event_type: str,
    details: Optional[Dict[str, Any]] = None
):
    """Log a conversation event (e.g., tool use, error)

    Args:
        conversation_id: UUID of the conversation
        agent_id: UUID of the agent
        agent_name: Human-readable name of the agent
        event_type: Type of event (e.g., 'tool_use', 'error', 'wizard_choice')
        details: Event-specific details
    """
    log_entry = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "conversation_id": str(conversation_id),
        "agent_id": str(agent_id),
        "agent_name": agent_name,
        "event_type": event_type,
    }

    if details:
        log_entry["details"] = details

    log_file = get_log_file_path()

    try:
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"⚠️ Failed to log event to {log_file}: {e}")

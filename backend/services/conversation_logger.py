"""Conversation Logger - Logs all messages to JSONL file for human-readable history"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional


def get_log_directory() -> Path:
    """Get the log directory path (~/.appletta/logs)"""
    home_dir = Path.home()
    log_dir = home_dir / ".appletta" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def get_log_file_path() -> Path:
    """Get the path to the JSONL log file"""
    return get_log_directory() / "conversations.jsonl"


def get_debug_log_path() -> Path:
    """Get the path to the debug/terminal JSONL log file"""
    return get_log_directory() / "debug.jsonl"


def log_debug(
    category: str,
    message: str,
    data: Optional[Dict[str, Any]] = None,
    conversation_id: Optional[str] = None,
    agent_id: Optional[str] = None
):
    """Log debug/terminal output to JSONL file

    Args:
        category: Category of log (e.g., 'mlx_setup', 'wizard', 'streaming', 'error')
        message: The log message
        data: Optional additional data
        conversation_id: Optional conversation context
        agent_id: Optional agent context
    """
    log_entry = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "category": category,
        "message": message,
    }

    if conversation_id:
        log_entry["conversation_id"] = str(conversation_id)
    if agent_id:
        log_entry["agent_id"] = str(agent_id)
    if data:
        log_entry["data"] = data

    log_file = get_debug_log_path()

    try:
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
    except Exception as e:
        # Don't fail the main operation if logging fails
        pass  # Silent fail for debug logging


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

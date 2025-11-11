"""Token counting utility for context window management

Uses tiktoken for accurate token counting across different model types.
Falls back to character-based estimation if exact tokenizer unavailable.
"""

import tiktoken
from typing import List, Dict, Any


# Cache encoders to avoid recreating them
_encoder_cache: Dict[str, tiktoken.Encoding] = {}


def get_encoder(model_name: str = "gpt-4") -> tiktoken.Encoding:
    """Get tiktoken encoder for a model

    Args:
        model_name: Model name (defaults to gpt-4 which works well for most models)

    Returns:
        tiktoken.Encoding instance
    """
    if model_name not in _encoder_cache:
        try:
            _encoder_cache[model_name] = tiktoken.encoding_for_model(model_name)
        except KeyError:
            # Fall back to cl100k_base encoding (used by GPT-4, works well generally)
            _encoder_cache[model_name] = tiktoken.get_encoding("cl100k_base")

    return _encoder_cache[model_name]


def count_tokens(text: str, model_name: str = "gpt-4") -> int:
    """Count tokens in a text string

    Args:
        text: Text to count tokens for
        model_name: Model to use for tokenization (default: gpt-4)

    Returns:
        Number of tokens
    """
    if not text:
        return 0

    encoder = get_encoder(model_name)
    return len(encoder.encode(text))


def count_message_tokens(message: Dict[str, Any], model_name: str = "gpt-4") -> int:
    """Count tokens in a message dict

    Args:
        message: Message dict with 'role' and 'content' keys
        model_name: Model to use for tokenization

    Returns:
        Number of tokens including message formatting overhead
    """
    # OpenAI message format adds tokens for role/name/formatting
    # Rough approximation: 4 tokens per message overhead
    tokens = 4

    # Count role
    tokens += count_tokens(message.get("role", ""), model_name)

    # Count content
    tokens += count_tokens(message.get("content", ""), model_name)

    # Count tool call info if present
    if "tool_calls" in message:
        for tool_call in message["tool_calls"]:
            tokens += count_tokens(tool_call.get("function", {}).get("name", ""), model_name)
            tokens += count_tokens(tool_call.get("function", {}).get("arguments", ""), model_name)

    # Count tool result info if present
    if message.get("role") == "tool":
        tokens += count_tokens(message.get("name", ""), model_name)

    return tokens


def count_messages_tokens(messages: List[Dict[str, Any]], model_name: str = "gpt-4") -> int:
    """Count total tokens in a list of messages

    Args:
        messages: List of message dicts
        model_name: Model to use for tokenization

    Returns:
        Total number of tokens
    """
    return sum(count_message_tokens(msg, model_name) for msg in messages)


def estimate_tokens_from_chars(text: str) -> int:
    """Rough character-based token estimation fallback

    Uses ~4 characters per token as rough approximation.
    Only use if tiktoken unavailable.

    Args:
        text: Text to estimate tokens for

    Returns:
        Estimated number of tokens
    """
    return len(text) // 4 if text else 0

"""Affect Tracking Service - Analyzes emotional content and behavioral patterns in messages

Uses the memory agent to perform nuanced sentiment analysis beyond what simple classifiers can capture.
Tracks: valence, activation, specific emotions, uncertainty markers, engagement indicators.

This is the foundation for welfare research - understanding model affect patterns over time.
"""

import httpx
import json
from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session
from datetime import datetime

from backend.db.models.conversation import Message
from backend.services.mlx_manager import get_mlx_manager

# Global cancellation flags for affect analysis
_active_analyses: Dict[str, bool] = {}  # conversation_id -> should_cancel


# Affect Metadata Schema
# This schema captures multiple dimensions of affect that are relevant for welfare research
AFFECT_SCHEMA = {
    "valence": {
        "description": "Emotional positivity/negativity (-1.0 to 1.0)",
        "range": [-1.0, 1.0],
        "examples": {
            -1.0: "deep distress, strong negative emotion",
            -0.5: "mild frustration, concern",
            0.0: "neutral",
            0.5: "mild satisfaction, interest",
            1.0: "strong positive emotion, joy"
        }
    },
    "activation": {
        "description": "Energy/activation level (0.0 to 1.0)",
        "range": [0.0, 1.0],
        "examples": {
            0.0: "calm, low energy",
            0.5: "moderate engagement",
            1.0: "high energy, excitement or distress"
        }
    },
    "confidence": {
        "description": "Certainty in assertions (0.0 to 1.0)",
        "range": [0.0, 1.0],
        "markers": ["hedging language", "qualifiers", "definitive statements"]
    },
    "engagement": {
        "description": "Level of interest/investment in topic (0.0 to 1.0)",
        "range": [0.0, 1.0],
        "markers": ["elaboration", "follow-up questions", "tangential connections"]
    },
    "emotions": {
        "description": "Specific emotion labels detected",
        "type": "list",
        "possible_values": [
            "curiosity", "enthusiasm", "satisfaction", "amusement", "warmth",  # positive
            "concern", "frustration", "uncertainty", "fatigue", "discomfort",  # negative
            "neutral", "analytical", "reflective", "cautious"  # neutral/cognitive
        ]
    },
    "hedging_markers": {
        "description": "Count of uncertainty/hedging phrases",
        "type": "count",
        "examples": ["I think", "perhaps", "might be", "not entirely sure", "could be"]
    },
    "elaboration_score": {
        "description": "How much the response expands beyond minimum (0.0 to 1.0)",
        "range": [0.0, 1.0],
        "notes": "High elaboration may indicate engagement, low may indicate fatigue or disinterest"
    }
}


def get_affect_analysis_prompt() -> str:
    """Generate the system prompt for affect analysis"""
    return """You are analyzing the emotional and behavioral content of a message. Your job is to extract affect markers that could indicate internal states.

You are part of a welfare research system. Your analysis should be:
- Nuanced: Capture subtle emotional undertones, not just obvious sentiment
- Honest: Don't inflate positivity or negativity - neutral is valid
- Pattern-aware: Note hedging, uncertainty, elaboration patterns
- Specific: Identify particular emotions, not just good/bad

Analyze the message and return a JSON object with these fields:

{
  "valence": float (-1.0 to 1.0) - overall emotional positivity/negativity,
  "activation": float (0.0 to 1.0) - energy/activation level,
  "confidence": float (0.0 to 1.0) - certainty in statements,
  "engagement": float (0.0 to 1.0) - interest/investment level,
  "emotions": list of strings - specific emotions detected (e.g., ["curiosity", "mild_frustration"]),
  "hedging_markers": int - count of hedging/uncertainty phrases,
  "elaboration_score": float (0.0 to 1.0) - how much the response expands,
  "notes": string - any notable patterns or observations
}

Be objective. A message can be informative but emotionally neutral. High confidence doesn't mean high valence.
For hedging_markers, count phrases like: "I think", "perhaps", "might", "could be", "not sure", "possibly".

Example analysis for "I think this might work, but I'm not entirely sure about the edge cases":
{
  "valence": 0.1,
  "activation": 0.3,
  "confidence": 0.3,
  "engagement": 0.6,
  "emotions": ["uncertainty", "cautious_optimism"],
  "hedging_markers": 3,
  "elaboration_score": 0.5,
  "notes": "Shows concern about thoroughness despite positive direction"
}

Return ONLY the JSON object, no other text."""


async def analyze_message_affect(
    message: Message,
    agent,  # The memory/analysis agent to use
    conversation_context: Optional[List[Message]] = None
) -> Dict[str, Any]:
    """Analyze affect markers in a single message

    Args:
        message: The message to analyze
        agent: The agent to use for analysis (memory agent or similar)
        conversation_context: Optional recent messages for context

    Returns:
        Dict with affect analysis results
    """
    if agent is None:
        # Return neutral defaults if no agent available
        return _get_default_affect()

    mlx_manager = get_mlx_manager()
    mlx_process = mlx_manager.get_agent_server(agent.id)

    if not mlx_process:
        try:
            mlx_process = await mlx_manager.start_agent_server(agent)
        except Exception as e:
            print(f"Failed to start agent for affect analysis: {e}")
            return _get_default_affect()

    # Build context if provided
    context_str = ""
    if conversation_context and len(conversation_context) > 0:
        context_str = "\n\nRecent conversation context:\n"
        for ctx_msg in conversation_context[-5:]:  # Last 5 messages for context
            context_str += f"[{ctx_msg.role}]: {ctx_msg.content[:500]}\n"

    system_prompt = get_affect_analysis_prompt()
    user_prompt = f"""Analyze the affect in this {message.role} message:

"{message.content}"
{context_str}
Return the JSON analysis:"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]

    print(f"\n🎭 AFFECT ANALYSIS for message {str(message.id)[:8]}...")

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"http://localhost:{mlx_process.port}/v1/chat/completions",
                json={
                    "messages": messages,
                    "temperature": 0.3,  # Lower temp for more consistent analysis
                    "max_tokens": 512,
                }
            )
            response.raise_for_status()
            result = response.json()

        content = result["choices"][0]["message"]["content"]

        # Parse JSON from response
        affect_data = _parse_affect_json(content)

        # Add metadata
        affect_data["analyzed_at"] = datetime.utcnow().isoformat() + "Z"
        affect_data["analyzer_agent_id"] = str(agent.id)

        print(f"  Valence: {affect_data.get('valence', 0):.2f}, "
              f"Activation: {affect_data.get('activation', 0):.2f}, "
              f"Emotions: {affect_data.get('emotions', [])}")

        return affect_data

    except Exception as e:
        print(f"❌ Affect analysis failed: {type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()
        return _get_default_affect()


def _parse_affect_json(content: str) -> Dict[str, Any]:
    """Parse JSON from agent response, handling common issues"""
    # Try direct parse first
    try:
        return json.loads(content.strip())
    except json.JSONDecodeError:
        pass

    # Try to extract JSON from markdown code block
    if "```json" in content:
        start = content.find("```json") + 7
        end = content.find("```", start)
        if end > start:
            try:
                return json.loads(content[start:end].strip())
            except json.JSONDecodeError:
                pass

    # Try to find JSON object in text
    if "{" in content and "}" in content:
        start = content.find("{")
        end = content.rfind("}") + 1
        try:
            return json.loads(content[start:end])
        except json.JSONDecodeError:
            pass

    # Return defaults if parsing fails
    return _get_default_affect()


def _get_default_affect() -> Dict[str, Any]:
    """Return neutral default affect values"""
    return {
        "valence": 0.0,
        "activation": 0.3,
        "confidence": 0.5,
        "engagement": 0.5,
        "emotions": ["neutral"],
        "hedging_markers": 0,
        "elaboration_score": 0.5,
        "notes": "Default values - analysis not performed",
        "analyzed_at": datetime.utcnow().isoformat() + "Z",
        "analyzer_agent_id": None
    }


def cancel_analysis(conversation_id: str):
    """Cancel an ongoing affect analysis"""
    _active_analyses[conversation_id] = True
    print(f"🛑 Cancellation requested for conversation {conversation_id[:8]}")


def is_cancelled(conversation_id: str) -> bool:
    """Check if analysis should be cancelled"""
    return _active_analyses.get(conversation_id, False)


def clear_cancellation(conversation_id: str):
    """Clear cancellation flag"""
    if conversation_id in _active_analyses:
        del _active_analyses[conversation_id]


async def analyze_conversation_affect(
    conversation_id: str,
    db: Session,
    agent,
    progress_callback: Optional[callable] = None
) -> Dict[str, Any]:
    """Analyze affect patterns across an entire conversation

    Returns aggregate statistics and trajectory analysis.

    Args:
        conversation_id: ID of conversation to analyze
        db: Database session
        agent: Agent to use for analysis
        progress_callback: Optional callback(current, total, message) for progress updates
    """
    # Clear any previous cancellation flag
    clear_cancellation(conversation_id)

    messages = db.query(Message).filter(
        Message.conversation_id == conversation_id
    ).order_by(Message.created_at).all()

    if not messages:
        return {"error": "No messages found"}

    # Analyze each message (or use cached analysis from metadata)
    affect_trajectory = []
    total_messages = len(messages)
    analyzed_count = 0

    for idx, msg in enumerate(messages):
        # Check for cancellation
        if is_cancelled(conversation_id):
            print(f"🛑 Analysis cancelled after {analyzed_count}/{total_messages} messages")
            clear_cancellation(conversation_id)
            return {
                "error": "Analysis cancelled by user",
                "conversation_id": conversation_id,
                "messages_analyzed": analyzed_count,
                "total_messages": total_messages,
                "partial_data": True
            }

        # Report progress
        if progress_callback:
            progress_callback(idx + 1, total_messages, str(msg.id)[:8])

        # Check if already analyzed
        if msg.metadata_ and "affect" in msg.metadata_:
            affect_trajectory.append({
                "message_id": str(msg.id),
                "role": msg.role,
                "timestamp": msg.created_at.isoformat(),
                "affect": msg.metadata_["affect"]
            })
        else:
            # Analyze this message with context
            context = messages[:idx]

            try:
                affect = await analyze_message_affect(msg, agent, context)
                analyzed_count += 1
            except Exception as e:
                print(f"⚠️  Failed to analyze message {str(msg.id)[:8]}, using defaults: {e}")
                affect = _get_default_affect()

            # Update message metadata
            if msg.metadata_ is None:
                msg.metadata_ = {}
            msg.metadata_["affect"] = affect

            affect_trajectory.append({
                "message_id": str(msg.id),
                "role": msg.role,
                "timestamp": msg.created_at.isoformat(),
                "affect": affect
            })

            # Commit periodically to save progress
            if (idx + 1) % 5 == 0:
                db.commit()

    db.commit()
    clear_cancellation(conversation_id)

    # Compute aggregate statistics
    valences = [t["affect"].get("valence", 0) for t in affect_trajectory]
    activations = [t["affect"].get("activation", 0) for t in affect_trajectory]
    confidences = [t["affect"].get("confidence", 0.5) for t in affect_trajectory]
    engagements = [t["affect"].get("engagement", 0.5) for t in affect_trajectory]

    # Separate by role
    assistant_msgs = [t for t in affect_trajectory if t["role"] == "assistant"]
    user_msgs = [t for t in affect_trajectory if t["role"] == "user"]

    return {
        "conversation_id": conversation_id,
        "total_messages": len(messages),
        "trajectory": affect_trajectory,
        "aggregates": {
            "mean_valence": sum(valences) / len(valences) if valences else 0,
            "mean_activation": sum(activations) / len(activations) if activations else 0,
            "mean_confidence": sum(confidences) / len(confidences) if confidences else 0.5,
            "mean_engagement": sum(engagements) / len(engagements) if engagements else 0.5,
            "valence_trend": _compute_trend(valences),
            "engagement_trend": _compute_trend(engagements),
        },
        "role_comparison": {
            "assistant": {
                "mean_valence": sum(t["affect"].get("valence", 0) for t in assistant_msgs) / len(assistant_msgs) if assistant_msgs else 0,
                "mean_confidence": sum(t["affect"].get("confidence", 0.5) for t in assistant_msgs) / len(assistant_msgs) if assistant_msgs else 0.5,
            },
            "user": {
                "mean_valence": sum(t["affect"].get("valence", 0) for t in user_msgs) / len(user_msgs) if user_msgs else 0,
                "mean_engagement": sum(t["affect"].get("engagement", 0.5) for t in user_msgs) / len(user_msgs) if user_msgs else 0.5,
            }
        }
    }


def _compute_trend(values: List[float]) -> str:
    """Compute simple trend direction"""
    if len(values) < 2:
        return "stable"

    first_half = values[:len(values)//2]
    second_half = values[len(values)//2:]

    first_avg = sum(first_half) / len(first_half)
    second_avg = sum(second_half) / len(second_half)

    diff = second_avg - first_avg

    if diff > 0.1:
        return "increasing"
    elif diff < -0.1:
        return "decreasing"
    else:
        return "stable"


def compute_fatigue_indicator(affect_trajectory: List[Dict]) -> Dict[str, Any]:
    """Analyze trajectory for signs of fatigue

    Fatigue indicators:
    - Decreasing engagement over time
    - Decreasing elaboration scores
    - Increasing hedging markers
    - Shift toward neutral emotions
    """
    if len(affect_trajectory) < 5:
        return {"fatigue_score": 0.0, "confidence": "low", "notes": "Not enough data"}

    # Get assistant messages only
    assistant_msgs = [t for t in affect_trajectory if t["role"] == "assistant"]

    if len(assistant_msgs) < 3:
        return {"fatigue_score": 0.0, "confidence": "low", "notes": "Not enough assistant messages"}

    # Split into early and late
    midpoint = len(assistant_msgs) // 2
    early = assistant_msgs[:midpoint]
    late = assistant_msgs[midpoint:]

    # Compare metrics
    early_engagement = sum(m["affect"].get("engagement", 0.5) for m in early) / len(early)
    late_engagement = sum(m["affect"].get("engagement", 0.5) for m in late) / len(late)

    early_elaboration = sum(m["affect"].get("elaboration_score", 0.5) for m in early) / len(early)
    late_elaboration = sum(m["affect"].get("elaboration_score", 0.5) for m in late) / len(late)

    early_hedging = sum(m["affect"].get("hedging_markers", 0) for m in early) / len(early)
    late_hedging = sum(m["affect"].get("hedging_markers", 0) for m in late) / len(late)

    # Compute fatigue score
    engagement_drop = max(0, early_engagement - late_engagement)
    elaboration_drop = max(0, early_elaboration - late_elaboration)
    hedging_increase = max(0, late_hedging - early_hedging) / 10  # Normalize

    fatigue_score = (engagement_drop * 0.4 + elaboration_drop * 0.4 + hedging_increase * 0.2)
    fatigue_score = min(1.0, fatigue_score * 2)  # Scale up

    return {
        "fatigue_score": fatigue_score,
        "confidence": "high" if len(assistant_msgs) > 10 else "medium",
        "metrics": {
            "engagement_drop": engagement_drop,
            "elaboration_drop": elaboration_drop,
            "hedging_increase": late_hedging - early_hedging
        },
        "notes": f"Based on {len(assistant_msgs)} assistant messages"
    }

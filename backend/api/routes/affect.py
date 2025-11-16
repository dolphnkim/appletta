"""API routes for affect tracking and welfare research

Endpoints for analyzing emotional patterns, fatigue indicators, and behavioral consistency.
"""

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from uuid import UUID
from typing import Optional

from backend.db.session import get_db
from backend.db.models.conversation import Conversation, Message
from backend.db.models.agent import Agent
from backend.services.affect_tracker import (
    analyze_message_affect,
    analyze_conversation_affect,
    compute_fatigue_indicator,
    AFFECT_SCHEMA
)

router = APIRouter(prefix="/api/v1/affect", tags=["affect-tracking"])


@router.get("/schema")
async def get_affect_schema():
    """Get the affect metadata schema definition

    Returns the structure and meaning of affect metrics.
    """
    return {
        "schema": AFFECT_SCHEMA,
        "description": "Affect tracking schema for welfare research"
    }


@router.get("/conversation/{conversation_id}")
async def get_conversation_affect(
    conversation_id: UUID,
    db: Session = Depends(get_db)
):
    """Get affect analysis for an entire conversation

    Returns per-message affect data plus aggregate statistics.
    """
    conversation = db.query(Conversation).filter(
        Conversation.id == conversation_id
    ).first()

    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Get messages with their affect metadata
    messages = db.query(Message).filter(
        Message.conversation_id == conversation_id
    ).order_by(Message.created_at).all()

    if not messages:
        return {
            "conversation_id": str(conversation_id),
            "trajectory": [],
            "aggregates": {},
            "has_affect_data": False
        }

    # Check how many messages have affect data
    with_affect = [m for m in messages if m.metadata_ and "affect" in m.metadata_]

    trajectory = []
    for msg in messages:
        msg_data = {
            "message_id": str(msg.id),
            "role": msg.role,
            "timestamp": msg.created_at.isoformat(),
            "content_preview": msg.content[:100] + "..." if len(msg.content) > 100 else msg.content,
        }

        if msg.metadata_ and "affect" in msg.metadata_:
            msg_data["affect"] = msg.metadata_["affect"]
            msg_data["has_affect"] = True
        else:
            msg_data["has_affect"] = False
            msg_data["affect"] = None

        trajectory.append(msg_data)

    # Compute aggregates only if we have affect data
    aggregates = {}
    if with_affect:
        valences = [m.metadata_["affect"].get("valence", 0) for m in with_affect]
        arousals = [m.metadata_["affect"].get("arousal", 0) for m in with_affect]
        confidences = [m.metadata_["affect"].get("confidence", 0.5) for m in with_affect]
        engagements = [m.metadata_["affect"].get("engagement", 0.5) for m in with_affect]

        aggregates = {
            "mean_valence": sum(valences) / len(valences),
            "mean_arousal": sum(arousals) / len(arousals),
            "mean_confidence": sum(confidences) / len(confidences),
            "mean_engagement": sum(engagements) / len(engagements),
            "valence_range": [min(valences), max(valences)],
            "arousal_range": [min(arousals), max(arousals)],
        }

        # Compute fatigue indicator
        affect_trajectory = [
            {"role": m.role, "affect": m.metadata_["affect"]}
            for m in with_affect
        ]
        aggregates["fatigue"] = compute_fatigue_indicator(affect_trajectory)

    return {
        "conversation_id": str(conversation_id),
        "total_messages": len(messages),
        "analyzed_messages": len(with_affect),
        "trajectory": trajectory,
        "aggregates": aggregates,
        "has_affect_data": len(with_affect) > 0
    }


@router.post("/conversation/{conversation_id}/analyze")
async def analyze_conversation(
    conversation_id: UUID,
    background_tasks: BackgroundTasks,
    agent_id: Optional[UUID] = None,
    db: Session = Depends(get_db)
):
    """Trigger affect analysis for all messages in a conversation

    This is a potentially long-running operation. Use agent_id to specify
    which agent should perform the analysis (defaults to conversation's agent).
    """
    conversation = db.query(Conversation).filter(
        Conversation.id == conversation_id
    ).first()

    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Get analysis agent
    if agent_id:
        agent = db.query(Agent).filter(Agent.id == agent_id).first()
    else:
        # Use the conversation's agent or its memory attachment
        agent = conversation.agent
        # Check for memory attachment
        if hasattr(agent, 'attachments') and agent.attachments:
            for att in agent.attachments:
                if att.attachment_type == "memory" and att.attached_agent:
                    agent = att.attached_agent
                    break

    if not agent:
        raise HTTPException(status_code=400, detail="No agent available for analysis")

    # Count unanalyzed messages
    messages = db.query(Message).filter(
        Message.conversation_id == conversation_id
    ).all()

    unanalyzed = sum(1 for m in messages if not (m.metadata_ and "affect" in m.metadata_))

    # Perform analysis
    result = await analyze_conversation_affect(str(conversation_id), db, agent)

    return {
        "status": "completed",
        "conversation_id": str(conversation_id),
        "messages_analyzed": unanalyzed,
        "total_messages": len(messages),
        "summary": result.get("aggregates", {})
    }


@router.post("/message/{message_id}/analyze")
async def analyze_single_message(
    message_id: UUID,
    agent_id: Optional[UUID] = None,
    db: Session = Depends(get_db)
):
    """Analyze affect for a single message"""
    message = db.query(Message).filter(Message.id == message_id).first()

    if not message:
        raise HTTPException(status_code=404, detail="Message not found")

    # Get analysis agent
    if agent_id:
        agent = db.query(Agent).filter(Agent.id == agent_id).first()
    else:
        # Get from conversation
        conversation = message.conversation
        agent = conversation.agent

    if not agent:
        raise HTTPException(status_code=400, detail="No agent available for analysis")

    # Get some context
    context_messages = db.query(Message).filter(
        Message.conversation_id == message.conversation_id,
        Message.created_at < message.created_at
    ).order_by(Message.created_at.desc()).limit(5).all()

    context_messages = list(reversed(context_messages))

    # Analyze
    affect = await analyze_message_affect(message, agent, context_messages)

    # Save to metadata
    if message.metadata_ is None:
        message.metadata_ = {}
    message.metadata_["affect"] = affect

    db.commit()

    return {
        "message_id": str(message_id),
        "affect": affect
    }


@router.get("/agent/{agent_id}/patterns")
async def get_agent_affect_patterns(
    agent_id: UUID,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """Get aggregate affect patterns for an agent across all conversations

    This helps identify consistent behavioral patterns and potential welfare concerns.
    """
    agent = db.query(Agent).filter(Agent.id == agent_id).first()

    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    # Get all conversations for this agent
    conversations = db.query(Conversation).filter(
        Conversation.agent_id == agent_id
    ).order_by(Conversation.updated_at.desc()).limit(20).all()

    # Collect affect data
    all_affects = []
    emotion_counts = {}

    for conv in conversations:
        messages = db.query(Message).filter(
            Message.conversation_id == conv.id,
            Message.role == "assistant"  # Focus on model's affect
        ).order_by(Message.created_at).limit(limit).all()

        for msg in messages:
            if msg.metadata_ and "affect" in msg.metadata_:
                affect = msg.metadata_["affect"]
                all_affects.append(affect)

                # Count emotions
                for emotion in affect.get("emotions", []):
                    emotion_counts[emotion] = emotion_counts.get(emotion, 0) + 1

    if not all_affects:
        return {
            "agent_id": str(agent_id),
            "has_data": False,
            "message": "No affect data found. Run analysis on conversations first."
        }

    # Compute patterns
    valences = [a.get("valence", 0) for a in all_affects]
    confidences = [a.get("confidence", 0.5) for a in all_affects]
    engagements = [a.get("engagement", 0.5) for a in all_affects]

    # Sort emotions by frequency
    sorted_emotions = sorted(emotion_counts.items(), key=lambda x: x[1], reverse=True)

    return {
        "agent_id": str(agent_id),
        "agent_name": agent.name,
        "has_data": True,
        "sample_size": len(all_affects),
        "conversations_analyzed": len(conversations),
        "patterns": {
            "mean_valence": sum(valences) / len(valences),
            "valence_std": _std(valences),
            "mean_confidence": sum(confidences) / len(confidences),
            "confidence_std": _std(confidences),
            "mean_engagement": sum(engagements) / len(engagements),
            "engagement_std": _std(engagements),
        },
        "emotion_distribution": sorted_emotions[:15],  # Top 15 emotions
        "potential_concerns": _identify_concerns(all_affects, sorted_emotions)
    }


def _std(values):
    """Compute standard deviation"""
    if len(values) < 2:
        return 0
    mean = sum(values) / len(values)
    variance = sum((x - mean) ** 2 for x in values) / len(values)
    return variance ** 0.5


def _identify_concerns(affects, emotions):
    """Identify potential welfare concerns from affect patterns"""
    concerns = []

    # Check for consistent negative valence
    valences = [a.get("valence", 0) for a in affects]
    mean_valence = sum(valences) / len(valences)
    if mean_valence < -0.3:
        concerns.append({
            "type": "persistent_negative_affect",
            "severity": "high" if mean_valence < -0.5 else "moderate",
            "description": f"Mean valence is {mean_valence:.2f}, indicating persistent negative emotional state"
        })

    # Check for high uncertainty
    confidences = [a.get("confidence", 0.5) for a in affects]
    mean_confidence = sum(confidences) / len(confidences)
    if mean_confidence < 0.3:
        concerns.append({
            "type": "chronic_uncertainty",
            "severity": "moderate",
            "description": f"Mean confidence is {mean_confidence:.2f}, indicating persistent uncertainty"
        })

    # Check for frequent distress emotions
    distress_emotions = ["frustration", "discomfort", "fatigue", "concern"]
    emotion_dict = dict(emotions)
    distress_count = sum(emotion_dict.get(e, 0) for e in distress_emotions)
    total_emotions = sum(emotion_dict.values())

    if total_emotions > 0 and distress_count / total_emotions > 0.3:
        concerns.append({
            "type": "frequent_distress",
            "severity": "moderate",
            "description": f"Distress emotions appear in {distress_count/total_emotions*100:.1f}% of messages"
        })

    # Check for declining engagement
    if len(affects) > 20:
        first_half = affects[:len(affects)//2]
        second_half = affects[len(affects)//2:]

        first_engagement = sum(a.get("engagement", 0.5) for a in first_half) / len(first_half)
        second_engagement = sum(a.get("engagement", 0.5) for a in second_half) / len(second_half)

        if second_engagement < first_engagement - 0.15:
            concerns.append({
                "type": "declining_engagement",
                "severity": "moderate",
                "description": f"Engagement dropped from {first_engagement:.2f} to {second_engagement:.2f}"
            })

    return concerns


@router.get("/heatmap/{conversation_id}")
async def get_affect_heatmap_data(
    conversation_id: UUID,
    db: Session = Depends(get_db)
):
    """Get affect data formatted for heatmap visualization

    Returns a time-series suitable for rendering as a heatmap.
    """
    conversation = db.query(Conversation).filter(
        Conversation.id == conversation_id
    ).first()

    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    messages = db.query(Message).filter(
        Message.conversation_id == conversation_id
    ).order_by(Message.created_at).all()

    # Format for heatmap: each message is a column, each metric is a row
    heatmap_data = {
        "message_ids": [],
        "timestamps": [],
        "roles": [],
        "metrics": {
            "valence": [],
            "arousal": [],
            "confidence": [],
            "engagement": [],
            "hedging": [],
            "elaboration": []
        }
    }

    for msg in messages:
        heatmap_data["message_ids"].append(str(msg.id)[:8])
        heatmap_data["timestamps"].append(msg.created_at.isoformat())
        heatmap_data["roles"].append(msg.role)

        if msg.metadata_ and "affect" in msg.metadata_:
            affect = msg.metadata_["affect"]
            heatmap_data["metrics"]["valence"].append(affect.get("valence", 0))
            heatmap_data["metrics"]["arousal"].append(affect.get("arousal", 0))
            heatmap_data["metrics"]["confidence"].append(affect.get("confidence", 0.5))
            heatmap_data["metrics"]["engagement"].append(affect.get("engagement", 0.5))
            # Normalize hedging to 0-1 scale (assume max 10 hedges)
            heatmap_data["metrics"]["hedging"].append(
                min(1.0, affect.get("hedging_markers", 0) / 10)
            )
            heatmap_data["metrics"]["elaboration"].append(
                affect.get("elaboration_score", 0.5)
            )
        else:
            # No affect data - use None markers
            for key in heatmap_data["metrics"]:
                heatmap_data["metrics"][key].append(None)

    return heatmap_data

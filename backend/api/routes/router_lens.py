"""API routes for Router Lens - MoE introspection tools"""

import json
import traceback
from pathlib import Path
from typing import List, Dict, Any, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from backend.db.session import get_db
from backend.db.models.agent import Agent
from backend.services.router_lens import get_router_inspector, reset_router_inspector
from backend.services.moe_model_wrapper import create_diagnostic_prompt_set
from backend.services.diagnostic_inference import get_diagnostic_service
from backend.core.config import settings
from sqlalchemy import select

router = APIRouter(prefix="/api/v1/router-lens", tags=["router-lens"])


class RunDiagnosticRequest(BaseModel):
    agent_id: str
    prompt: Optional[str] = None
    enable_full_logging: bool = False


class ExpertMaskTestRequest(BaseModel):
    agent_id: str
    prompt: str
    disabled_experts: List[int]


class DiagnosticInferenceRequest(BaseModel):
    prompt: str
    max_tokens: int = 100
    temperature: float = 0.7


class LoadModelRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    model_path: str
    adapter_path: Optional[str] = None


@router.get("/status")
async def get_router_lens_status():
    """Get current router lens inspector status"""
    inspector = get_router_inspector()
    return {
        "status": "active",
        "num_experts": inspector.num_experts,
        "top_k": inspector.top_k,
        "current_session_tokens": len(inspector.current_session.get("tokens", [])),
        "log_directory": str(inspector.log_dir),
    }


@router.post("/reset")
async def reset_inspector(num_experts: int = 64, top_k: int = 8):
    """Reset the router inspector with new configuration"""
    reset_router_inspector(num_experts=num_experts, top_k=top_k)
    return {
        "status": "reset",
        "num_experts": num_experts,
        "top_k": top_k,
    }


@router.get("/session/summary")
async def get_current_session_summary():
    """Get summary of current inspection session"""
    inspector = get_router_inspector()
    return inspector.get_session_summary()


@router.post("/session/save")
async def save_current_session(prompt: str = "", response: str = ""):
    """Save current session to disk"""
    inspector = get_router_inspector()
    filepath = inspector.save_session(prompt=prompt, response=response)
    return {
        "saved": True,
        "filepath": filepath,
    }


@router.get("/sessions")
async def list_saved_sessions(limit: int = 20, agent_id: Optional[str] = None):
    """List saved router lens sessions

    Args:
        limit: Maximum number of sessions to return
        agent_id: Optional agent ID to filter sessions (returns sessions for specific agent)
    """
    # Determine log directory based on agent_id
    if agent_id:
        log_dir = Path.home() / ".appletta" / "router_lens" / "agents" / agent_id
    else:
        log_dir = Path.home() / ".appletta" / "router_lens" / "general"

    if not log_dir.exists():
        return {"sessions": [], "total": 0}

    sessions = []
    for filepath in sorted(log_dir.glob("router_session_*.json"), reverse=True)[:limit]:
        try:
            with open(filepath) as f:
                data = json.load(f)
                sessions.append({
                    "filename": filepath.name,
                    "filepath": str(filepath),
                    "start_time": data.get("start_time"),
                    "end_time": data.get("end_time"),
                    "total_tokens": data.get("summary", {}).get("total_tokens", 0),
                    "prompt_preview": data.get("metadata", {}).get("prompt", "")[:100],
                    "agent_id": data.get("metadata", {}).get("agent_id"),
                    "category": data.get("metadata", {}).get("category"),
                })
        except Exception as e:
            continue

    return {"sessions": sessions, "total": len(sessions)}


@router.get("/sessions/{filename}")
async def get_session_details(filename: str):
    """Get full details of a saved session"""
    inspector = get_router_inspector()
    filepath = inspector.log_dir / filename

    if not filepath.exists():
        raise HTTPException(404, f"Session {filename} not found")

    with open(filepath) as f:
        data = json.load(f)

    return data


@router.get("/diagnostic-prompts")
async def get_diagnostic_prompts():
    """Get predefined diagnostic prompts for testing expert behavior"""
    prompts = create_diagnostic_prompt_set()
    return {"prompts": prompts}


@router.post("/analyze/expert-usage")
async def analyze_expert_usage(agent_id: Optional[str] = None, category: Optional[str] = None):
    """Analyze expert usage patterns across saved sessions

    Args:
        agent_id: Optional agent ID to analyze sessions for specific agent
        category: Optional category to filter sessions by
    """
    # Determine log directory based on agent_id
    if agent_id:
        log_dir = Path.home() / ".appletta" / "router_lens" / "agents" / agent_id
    else:
        log_dir = Path.home() / ".appletta" / "router_lens" / "general"

    if not log_dir.exists():
        return {"error": "No sessions found"}

    # Load all sessions (optionally filtered by category)
    sessions = []
    for filepath in log_dir.glob("router_session_*.json"):
        try:
            with open(filepath) as f:
                session_data = json.load(f)
                # Filter by category if provided
                if category:
                    session_category = session_data.get("metadata", {}).get("category")
                    if session_category != category:
                        continue
                sessions.append(session_data)
        except Exception:
            continue

    if not sessions:
        return {"error": f"No saved sessions found{f' for category {category}' if category else ''}"}

    inspector = get_router_inspector()
    analysis = inspector.analyze_expert_specialization(sessions)
    analysis["num_sessions_analyzed"] = len(sessions)
    if category:
        analysis["category"] = category

    return analysis


@router.post("/analyze/entropy-distribution")
async def analyze_entropy_distribution(agent_id: Optional[str] = None, category: Optional[str] = None):
    """Analyze router entropy distribution across sessions

    Args:
        agent_id: Optional agent ID to analyze sessions for specific agent
        category: Optional category to filter sessions by
    """
    # Determine log directory based on agent_id
    if agent_id:
        log_dir = Path.home() / ".appletta" / "router_lens" / "agents" / agent_id
    else:
        log_dir = Path.home() / ".appletta" / "router_lens" / "general"

    if not log_dir.exists():
        return {"error": "No sessions found"}

    all_entropies = []
    session_entropies = []

    for filepath in log_dir.glob("router_session_*.json"):
        try:
            with open(filepath) as f:
                data = json.load(f)
                # Filter by category if provided
                if category:
                    session_category = data.get("metadata", {}).get("category")
                    if session_category != category:
                        continue
                if "tokens" in data:
                    session_entropy = [t.get("entropy", 0) for t in data["tokens"]]
                    all_entropies.extend(session_entropy)
                    if session_entropy:
                        session_entropies.append({
                            "filename": filepath.name,
                            "mean_entropy": sum(session_entropy) / len(session_entropy),
                            "min_entropy": min(session_entropy),
                            "max_entropy": max(session_entropy),
                        })
        except Exception:
            continue

    if not all_entropies:
        return {"error": "No entropy data found"}

    import numpy as np
    return {
        "overall_mean_entropy": float(np.mean(all_entropies)),
        "overall_std_entropy": float(np.std(all_entropies)),
        "entropy_histogram": np.histogram(all_entropies, bins=20)[0].tolist(),
        "entropy_bin_edges": np.histogram(all_entropies, bins=20)[1].tolist(),
        "per_session": session_entropies,
    }


@router.get("/expert-clusters")
async def get_expert_clusters():
    """Get discovered expert clusters based on co-activation patterns"""
    inspector = get_router_inspector()
    log_dir = inspector.log_dir

    sessions = []
    for filepath in log_dir.glob("router_session_*.json"):
        try:
            with open(filepath) as f:
                sessions.append(json.load(f))
        except Exception:
            continue

    if not sessions:
        return {"clusters": [], "message": "No sessions to analyze"}

    analysis = inspector.analyze_expert_specialization(sessions)
    return {
        "clusters": analysis.get("expert_clusters", []),
        "most_used": analysis.get("most_used", []),
        "least_used": analysis.get("least_used", []),
    }


@router.post("/simulate/expert-mask")
async def simulate_expert_masking(request: ExpertMaskTestRequest):
    """Simulate what would happen if certain experts were disabled

    NOTE: This is a placeholder. Actual implementation would require
    modifying the model's forward pass to mask specific experts.
    """
    return {
        "status": "not_implemented",
        "message": "Expert masking simulation requires custom MLX model modifications",
        "requested_mask": request.disabled_experts,
    }


# =============================================================================
# Real-time Monitoring (WebSocket or SSE would be better for production)
# =============================================================================

@router.get("/monitor/current")
async def get_current_monitoring_data():
    """Get real-time monitoring data for current inference"""
    inspector = get_router_inspector()

    tokens = inspector.current_session.get("tokens", [])
    if not tokens:
        return {"status": "no_data", "message": "No tokens in current session"}

    # Get last N tokens
    last_tokens = tokens[-20:] if len(tokens) > 20 else tokens

    return {
        "total_tokens": len(tokens),
        "last_tokens": last_tokens,
        "current_usage": inspector.current_session.get("expert_usage_count", {}),
        "recent_entropy": inspector.current_session.get("entropy_history", [])[-10:],
    }


# =============================================================================
# Diagnostic Inference - Direct model loading with router logging
# =============================================================================

@router.post("/diagnostic/load-model")
async def load_model_for_diagnostics(request: LoadModelRequest):
    """Load a model for diagnostic inference with router logging

    This loads the model directly (not via MLX server) so we can patch it
    for full router introspection.
    """
    try:
        service = get_diagnostic_service()
    except ImportError as e:
        raise HTTPException(500, f"MLX not installed: {str(e)}")

    try:
        result = service.load_model(request.model_path, request.adapter_path)
        return result
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        print(f"[Diagnostic] Load model error: {str(e)}")
        traceback.print_exc()
        raise HTTPException(500, f"Failed to load model: {str(e)}")


@router.post("/diagnostic/load-agent-model/{agent_id}")
async def load_agent_model_for_diagnostics(agent_id: str, db: Session = Depends(get_db)):
    """Load an agent's model for diagnostic inference with router logging

    This uses the agent's configured model and adapter paths.
    Sessions will be saved to this agent's profile.
    """
    try:
        service = get_diagnostic_service()
    except ImportError as e:
        raise HTTPException(500, f"MLX not installed: {str(e)}")

    # Get agent from database
    try:
        agent_uuid = UUID(agent_id)
    except ValueError:
        raise HTTPException(400, "Invalid agent ID format")

    agent = db.query(Agent).filter(Agent.id == agent_uuid).first()
    if not agent:
        raise HTTPException(404, f"Agent not found: {agent_id}")

    # Load the agent's model
    try:
        result = service.load_model(
            agent.model_path,
            agent.adapter_path,
            agent_id=str(agent.id),
            agent_name=agent.name
        )
        return {
            **result,
            "agent_id": str(agent.id),
            "agent_name": agent.name
        }
    except FileNotFoundError as e:
        raise HTTPException(404, f"Model not found for agent '{agent.name}': {str(e)}")
    except Exception as e:
        print(f"[Diagnostic] Load agent model error: {str(e)}")
        traceback.print_exc()
        raise HTTPException(500, f"Failed to load agent model: {str(e)}")


@router.get("/diagnostic/model-status")
async def get_diagnostic_model_status():
    """Get status of the diagnostic inference model"""
    try:
        service = get_diagnostic_service()
    except ImportError as e:
        raise HTTPException(500, f"MLX not installed: {str(e)}")

    return {
        "model_loaded": service.model is not None,
        "model_path": service.model_path,
        "is_moe_model": service.is_moe_model,
        "agent_id": service.agent_id,
        "agent_name": service.agent_name,
        "inspector_status": service.get_inspector_status()
    }


@router.post("/diagnostic/infer")
async def run_diagnostic_inference(request: DiagnosticInferenceRequest):
    """Run a single inference with full router logging

    Returns the generated text and complete router analysis including:
    - Expert usage counts
    - Token-by-token routing decisions
    - Entropy distribution
    - Co-occurrence patterns
    """
    try:
        service = get_diagnostic_service()
    except ImportError as e:
        raise HTTPException(500, f"MLX not installed: {str(e)}")

    if service.model is None:
        raise HTTPException(400, "No model loaded. Load a model first with /diagnostic/load-model")

    try:
        result = service.run_inference(
            prompt=request.prompt,
            max_tokens=request.max_tokens,
            temperature=request.temperature,
            log_routing=True
        )

        # Also update the global inspector for UI consistency
        inspector = get_router_inspector()
        inspector.current_session = service.router_inspector.current_session.copy()

        return result
    except Exception as e:
        raise HTTPException(500, f"Inference failed: {str(e)}")


@router.post("/diagnostic/save-session")
async def save_diagnostic_session(prompt_preview: str = "", notes: str = "", category: str = ""):
    """Save the current diagnostic session with category tracking"""
    try:
        service = get_diagnostic_service()
    except ImportError as e:
        raise HTTPException(500, f"MLX not installed: {str(e)}")

    # Add category to session metadata if provided
    if category:
        service.router_inspector.current_session["metadata"]["category"] = category

    # Get prompt and response from session metadata
    prompt = service.router_inspector.current_session.get("metadata", {}).get("prompt", prompt_preview)
    response = service.router_inspector.current_session.get("metadata", {}).get("response", "")

    filepath = service.router_inspector.save_session(prompt=prompt, response=response)

    # Also save to global inspector
    inspector = get_router_inspector()
    inspector.current_session = service.router_inspector.current_session.copy()
    inspector.save_session(prompt=prompt, response=response)

    return {
        "saved": True,
        "filepath": filepath
    }


@router.post("/diagnostic/quick-test")
async def quick_diagnostic_test():
    """Run a quick test to generate sample router data

    Requires MLX to be installed and a model to be loaded.
    """
    try:
        service = get_diagnostic_service()
    except ImportError as e:
        raise HTTPException(500, f"MLX not installed: {str(e)}")

    if service.model is None:
        raise HTTPException(
            400,
            "No model loaded. Load an MoE model first with /diagnostic/load-model"
        )

    # Use a simple test prompt
    test_prompts = [
        "Explain the concept of empathy in simple terms.",
        "What is 2 + 2?",
        "Write a haiku about coding.",
    ]

    import random
    prompt = random.choice(test_prompts)

    try:
        result = service.run_inference(
            prompt=prompt,
            max_tokens=50,
            temperature=0.7,
            log_routing=True
        )

        # Sync to global inspector
        inspector = get_router_inspector()
        inspector.current_session = service.router_inspector.current_session.copy()

        return result
    except Exception as e:
        print(f"[Diagnostic] Inference error: {str(e)}")
        traceback.print_exc()
        raise HTTPException(500, f"Inference failed: {str(e)}")


@router.get("/config/paths")
async def get_model_paths():
    """Get configured model and adapter directories"""
    return {
        "models_dir": settings.MODELS_DIR,
        "adapters_dir": settings.ADAPTERS_DIR
    }


@router.get("/browse/models")
async def browse_models():
    """List available models in the configured models directory"""
    models_dir = Path(settings.MODELS_DIR).expanduser()

    if not models_dir.exists():
        return {"models": [], "base_path": str(models_dir), "exists": False}

    models = []

    # Look for directories that look like model repos (have config.json)
    for item in models_dir.iterdir():
        if item.is_dir():
            # Check if it's a HuggingFace cache structure (models--org--name)
            if item.name.startswith("models--"):
                # Parse the model name from cache structure
                parts = item.name.replace("models--", "").split("--")
                model_name = "/".join(parts)

                # Find the actual snapshot directory
                snapshots_dir = item / "snapshots"
                if snapshots_dir.exists():
                    for snapshot in snapshots_dir.iterdir():
                        if snapshot.is_dir() and (snapshot / "config.json").exists():
                            models.append({
                                "name": model_name,
                                "path": str(snapshot),
                                "type": "huggingface_cache"
                            })
                            break  # Just use the first valid snapshot
            elif (item / "config.json").exists():
                # Direct model directory
                models.append({
                    "name": item.name,
                    "path": str(item),
                    "type": "local"
                })

    return {
        "models": models,
        "base_path": str(models_dir),
        "exists": True
    }


@router.get("/browse/adapters")
async def browse_adapters():
    """List available adapters in the configured adapters directory"""
    adapters_dir = Path(settings.ADAPTERS_DIR).expanduser()

    if not adapters_dir.exists():
        return {"adapters": [], "base_path": str(adapters_dir), "exists": False}

    adapters = []

    # Look for directories that contain adapter_config.json or adapter_model.bin
    for item in adapters_dir.iterdir():
        if item.is_dir():
            if (item / "adapter_config.json").exists() or (item / "adapter_model.safetensors").exists():
                adapters.append({
                    "name": item.name,
                    "path": str(item)
                })

    return {
        "adapters": adapters,
        "base_path": str(adapters_dir),
        "exists": True
    }


@router.get("/browse/directory")
async def browse_directory(path: str = "~"):
    """Browse any directory on the filesystem

    Args:
        path: Directory path to browse (default: home directory)

    Returns:
        List of items (files and directories) in the specified path
    """
    browse_path = Path(path).expanduser().resolve()

    if not browse_path.exists():
        return {
            "path": str(browse_path),
            "exists": False,
            "items": [],
            "parent": str(browse_path.parent)
        }

    if not browse_path.is_dir():
        # If it's a file, return the parent directory
        browse_path = browse_path.parent

    items = []
    try:
        for item in sorted(browse_path.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
            # Skip hidden files/dirs unless they're important ones
            if item.name.startswith('.') and item.name not in ['.cache']:
                continue

            item_info = {
                "name": item.name,
                "path": str(item),
                "is_dir": item.is_dir(),
            }

            # Check if it's a model directory (has config.json)
            if item.is_dir() and (item / "config.json").exists():
                item_info["is_model"] = True

            # Check if it's an adapter directory
            if item.is_dir() and ((item / "adapter_config.json").exists() or
                                   (item / "adapter_model.safetensors").exists()):
                item_info["is_adapter"] = True

            items.append(item_info)
    except PermissionError:
        pass  # Skip items we can't access

    return {
        "path": str(browse_path),
        "exists": True,
        "items": items,
        "parent": str(browse_path.parent) if browse_path.parent != browse_path else None
    }

@router.post("/analyze-conversation/{conversation_id}")
async def analyze_conversation(
    conversation_id: UUID,
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Analyze expert routing patterns across an entire conversation
    
    Replays all assistant responses through diagnostic inference with router logging
    to capture expert activation patterns throughout the conversation.
    
    Args:
        conversation_id: ID of the conversation to analyze
        
    Returns:
        Per-turn analysis and aggregate statistics
    """
    from backend.db.models.conversation import Conversation, Message
    import asyncio
    
    # Load conversation
    conversation = db.query(Conversation).filter(Conversation.id == conversation_id).first()
    if not conversation:
        raise HTTPException(404, "Conversation not found")
    
    # Load agent
    agent = db.query(Agent).filter(Agent.id == conversation.agent_id).first()
    if not agent:
        raise HTTPException(404, "Agent not found")
    
    # Get diagnostic service and verify model is loaded
    try:
        diagnostic_service = get_diagnostic_service()

        # Check if model is loaded for this agent
        current_agent_id = getattr(diagnostic_service, 'agent_id', None)
        if current_agent_id != str(agent.id):
            raise HTTPException(
                400,
                f"Model not loaded for this agent. Please load the agent model first using the 'Load Agent Model for Analytics' button in the Interpretability panel."
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Failed to initialize diagnostic service: {str(e)}")
    
    # Load all messages in conversation
    messages = db.query(Message).filter(
        Message.conversation_id == conversation_id
    ).order_by(Message.created_at.asc()).all()
    
    if not messages:
        raise HTTPException(404, "No messages found in conversation")
    
    # Process messages turn by turn
    turn_analyses = []
    conversation_context = []
    
    for msg in messages:
        # Build context for this turn
        if msg.role == "system":
            conversation_context.insert(0, {"role": "system", "content": msg.content})
        elif msg.role == "user":
            conversation_context.append({"role": "user", "content": msg.content})
        elif msg.role == "assistant":
            # This is an assistant message - replay it with router logging
            conversation_context.append({"role": "assistant", "content": msg.content})
            
            # Build prompt from context up to the user message
            prompt_parts = []
            for ctx_msg in conversation_context[:-1]:  # Exclude the assistant response
                role = ctx_msg["role"]
                content = ctx_msg["content"]
                if role == "system":
                    prompt_parts.append(f"System: {content}")
                elif role == "user":
                    prompt_parts.append(f"User: {content}")
                elif role == "assistant":
                    prompt_parts.append(f"Assistant: {content}")
            
            conversation_prompt = "\n\n".join(prompt_parts)
            
            # Run diagnostic inference
            print(f"[Conversation Analysis] Analyzing turn {len(turn_analyses) + 1}")
            
            try:
                result_dict = await asyncio.to_thread(
                    diagnostic_service.run_inference,
                    prompt=conversation_prompt,
                    max_tokens=len(msg.content.split()),  # Approximate
                    temperature=agent.temperature,
                    log_routing=True
                )
                
                turn_analyses.append({
                    "turn_number": len(turn_analyses) + 1,
                    "message_id": str(msg.id),
                    "user_message": conversation_context[-2]["content"] if len(conversation_context) >= 2 else "",
                    "assistant_response": msg.content,
                    "router_analysis": result_dict["router_analysis"]
                })
            except Exception as e:
                print(f"[Conversation Analysis] Failed to analyze turn: {e}")
                continue
    
    # Compute aggregate statistics
    all_expert_usage = {}
    total_tokens_analyzed = 0
    all_entropy_values = []
    
    for turn in turn_analyses:
        router_data = turn["router_analysis"]
        total_tokens_analyzed += router_data.get("total_tokens", 0)
        
        # Aggregate expert usage
        for expert_id, count in router_data.get("expert_usage_count", {}).items():
            expert_id_str = str(expert_id)
            if expert_id_str not in all_expert_usage:
                all_expert_usage[expert_id_str] = 0
            all_expert_usage[expert_id_str] += count
        
        # Collect entropy values
        if "mean_token_entropy" in router_data:
            all_entropy_values.append(router_data["mean_token_entropy"])
    
    # Calculate aggregate metrics
    mean_entropy = sum(all_entropy_values) / len(all_entropy_values) if all_entropy_values else 0
    variance = sum((x - mean_entropy) ** 2 for x in all_entropy_values) / len(all_entropy_values) if all_entropy_values else 0
    
    aggregate_analysis = {
        "total_turns": len(turn_analyses),
        "total_tokens_analyzed": total_tokens_analyzed,
        "overall_expert_usage": all_expert_usage,
        "mean_entropy_across_turns": mean_entropy,
        "entropy_variance": variance,
        "most_used_experts": sorted(
            all_expert_usage.items(),
            key=lambda x: x[1],
            reverse=True
        )[:10],
        "least_used_experts": sorted(
            all_expert_usage.items(),
            key=lambda x: x[1]
        )[:10]
    }
    
    return {
        "conversation_id": str(conversation_id),
        "conversation_title": conversation.title or "Untitled",
        "agent_name": agent.name,
        "turn_analyses": turn_analyses,
        "aggregate_analysis": aggregate_analysis
    }


@router.get("/sessions/{filename}/heatmap")
async def get_session_heatmap(filename: str, agent_id: Optional[str] = None):
    """Get expert activation heatmap data for visualization

    Returns data formatted for 2D heatmap:
    - X-axis: Token position (time)
    - Y-axis: Expert ID
    - Color: Activation weight (0-1)

    This is the "AI MRI scan" - watch the brain light up!
    """
    # Determine file path
    if agent_id:
        log_dir = Path.home() / ".appletta" / "router_lens" / "agents" / agent_id
    else:
        log_dir = Path.home() / ".appletta" / "router_lens" / "general"

    filepath = log_dir / filename

    if not filepath.exists():
        raise HTTPException(404, f"Session {filename} not found")

    with open(filepath) as f:
        session_data = json.load(f)

    # Extract token-by-token expert activations
    tokens = session_data.get("tokens", [])
    if not tokens:
        return {
            "error": "No token data in session",
            "num_tokens": 0,
            "num_experts": 0,
            "heatmap_data": []
        }

    num_experts = session_data.get("metadata", {}).get("num_experts", 128)

    # Build heatmap matrix: [num_tokens x num_experts]
    # Each cell is the activation weight for that expert at that token
    heatmap_matrix = []
    token_texts = []  # Actual token strings

    for token_data in tokens:
        # Create a row for this token (one value per expert)
        row = [0.0] * num_experts

        # Fill in the activated experts
        selected_experts = token_data.get("selected_experts", [])
        expert_weights = token_data.get("expert_weights", [])

        for expert_id, weight in zip(selected_experts, expert_weights):
            if expert_id < num_experts:
                row[expert_id] = weight

        heatmap_matrix.append(row)

        # Store token text if available
        token_text = token_data.get("token", f"Token {token_data.get('idx', len(token_texts))}")
        token_texts.append(token_text)

    return {
        "filename": filename,
        "num_tokens": len(tokens),
        "num_experts": num_experts,
        "heatmap_matrix": heatmap_matrix,  # [tokens x experts] matrix
        "token_texts": token_texts,  # Actual token strings for each position
        "metadata": {
            "start_time": session_data.get("start_time"),
            "end_time": session_data.get("end_time"),
            "prompt": session_data.get("metadata", {}).get("prompt", ""),  # Full prompt
            "response": session_data.get("metadata", {}).get("response", ""),  # Full response
            "prompt_preview": session_data.get("metadata", {}).get("prompt", "")[:200],
            "response_preview": session_data.get("metadata", {}).get("response", "")[:200]
        },
        "summary": session_data.get("summary", {})
    }

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
async def analyze_expert_usage():
    """Analyze expert usage patterns across all saved sessions"""
    inspector = get_router_inspector()
    log_dir = inspector.log_dir

    # Load all sessions
    sessions = []
    for filepath in log_dir.glob("router_session_*.json"):
        try:
            with open(filepath) as f:
                sessions.append(json.load(f))
        except Exception:
            continue

    if not sessions:
        return {"error": "No saved sessions found"}

    analysis = inspector.analyze_expert_specialization(sessions)
    analysis["num_sessions_analyzed"] = len(sessions)

    return analysis


@router.post("/analyze/entropy-distribution")
async def analyze_entropy_distribution():
    """Analyze router entropy distribution across sessions"""
    inspector = get_router_inspector()
    log_dir = inspector.log_dir

    all_entropies = []
    session_entropies = []

    for filepath in log_dir.glob("router_session_*.json"):
        try:
            with open(filepath) as f:
                data = json.load(f)
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
async def save_diagnostic_session(prompt_preview: str = "", notes: str = ""):
    """Save the current diagnostic session"""
    try:
        service = get_diagnostic_service()
    except ImportError as e:
        raise HTTPException(500, f"MLX not installed: {str(e)}")

    filepath = service.save_session(prompt_preview, notes)

    # Also save to global inspector
    inspector = get_router_inspector()
    inspector.current_session = service.router_inspector.current_session.copy()
    inspector.save_session(prompt_preview, notes)

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

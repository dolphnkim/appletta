"""API routes for Router Lens - MoE introspection tools"""

import json
from pathlib import Path
from typing import List, Dict, Any, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.db.session import get_db
from backend.db.models.agent import Agent
from backend.services.router_lens import get_router_inspector, reset_router_inspector
from backend.services.moe_model_wrapper import create_diagnostic_prompt_set
from backend.services.diagnostic_inference import get_diagnostic_service

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
async def list_saved_sessions(limit: int = 20):
    """List saved router lens sessions"""
    inspector = get_router_inspector()
    log_dir = inspector.log_dir

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
    service = get_diagnostic_service()
    try:
        result = service.load_model(request.model_path, request.adapter_path)
        return result
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        raise HTTPException(500, f"Failed to load model: {str(e)}")


@router.get("/diagnostic/model-status")
async def get_diagnostic_model_status():
    """Get status of the diagnostic inference model"""
    service = get_diagnostic_service()
    return {
        "model_loaded": service.model is not None,
        "model_path": service.model_path,
        "is_moe_model": service.is_moe_model,
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
    service = get_diagnostic_service()

    if service.model is None and service.model_path is None:
        # Return mock data if no model loaded
        pass

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
    service = get_diagnostic_service()
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

    Uses mock data if model not loaded. Useful for testing the UI.
    """
    service = get_diagnostic_service()

    # Use a simple test prompt
    test_prompts = [
        "Explain the concept of empathy in simple terms.",
        "What is 2 + 2?",
        "Write a haiku about coding.",
    ]

    import random
    prompt = random.choice(test_prompts)

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

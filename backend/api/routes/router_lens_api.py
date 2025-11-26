"""API routes for Router Lens - MoE introspection tools

Now includes:
- Prefill vs Generation phase analysis
- Category-based expert tracking
- Layer × Expert heatmap data
- Co-occurrence clustering
"""

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
    capture_prefill: bool = True  # NEW: Option to capture prefill


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
        "prefill_tokens": len(inspector.current_session.get("prefill_tokens", [])),
        "generation_tokens": len(inspector.current_session.get("generation_tokens", [])),
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
    """List saved router lens sessions"""
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
                    "prefill_tokens": data.get("summary", {}).get("prefill_tokens", 0),
                    "generation_tokens": data.get("summary", {}).get("generation_tokens", 0),
                    "prompt_preview": data.get("metadata", {}).get("prompt", "")[:100],
                    "agent_id": data.get("metadata", {}).get("agent_id"),
                    "category": data.get("metadata", {}).get("category"),
                })
        except Exception as e:
            continue

    return {"sessions": sessions, "total": len(sessions)}


@router.get("/sessions/{filename}")
async def get_session_details(filename: str, agent_id: Optional[str] = None):
    """Get full details of a saved session"""
    if agent_id:
        log_dir = Path.home() / ".appletta" / "router_lens" / "agents" / agent_id
    else:
        log_dir = Path.home() / ".appletta" / "router_lens" / "general"
    
    filepath = log_dir / filename

    if not filepath.exists():
        raise HTTPException(404, f"Session {filename} not found")

    with open(filepath) as f:
        data = json.load(f)

    return data


@router.get("/categories")
async def get_available_categories(agent_id: Optional[str] = None):
    """Get all unique categories from saved sessions"""
    if agent_id:
        log_dir = Path.home() / ".appletta" / "router_lens" / "agents" / agent_id
    else:
        log_dir = Path.home() / ".appletta" / "router_lens" / "general"

    if not log_dir.exists():
        return {"categories": [], "counts": {}}

    categories = {}
    for filepath in log_dir.glob("router_session_*.json"):
        try:
            with open(filepath) as f:
                data = json.load(f)
                category = data.get("metadata", {}).get("category", "uncategorized")
                if category:
                    categories[category] = categories.get(category, 0) + 1
        except Exception:
            continue

    return {
        "categories": list(categories.keys()),
        "counts": categories
    }


@router.get("/diagnostic-prompts")
async def get_diagnostic_prompts():
    """Get predefined diagnostic prompts for testing expert behavior"""
    prompts = create_diagnostic_prompt_set()
    return {"prompts": prompts}


@router.post("/analyze/expert-usage")
async def analyze_expert_usage(agent_id: Optional[str] = None, category: Optional[str] = None):
    """Analyze expert usage patterns across saved sessions"""
    if agent_id:
        log_dir = Path.home() / ".appletta" / "router_lens" / "agents" / agent_id
    else:
        log_dir = Path.home() / ".appletta" / "router_lens" / "general"

    if not log_dir.exists():
        return {"error": "No sessions found"}

    sessions = []
    for filepath in log_dir.glob("router_session_*.json"):
        try:
            with open(filepath) as f:
                session_data = json.load(f)
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


@router.post("/analyze/category-comparison")
async def analyze_category_comparison(
    categories: List[str],
    agent_id: Optional[str] = None
):
    """Compare expert usage across multiple categories
    
    This is the key endpoint for understanding which experts specialize in what!
    """
    if agent_id:
        log_dir = Path.home() / ".appletta" / "router_lens" / "agents" / agent_id
    else:
        log_dir = Path.home() / ".appletta" / "router_lens" / "general"

    if not log_dir.exists():
        return {"error": "No sessions found"}

    # Load sessions by category
    category_sessions: Dict[str, List[Dict]] = {cat: [] for cat in categories}
    
    for filepath in log_dir.glob("router_session_*.json"):
        try:
            with open(filepath) as f:
                session_data = json.load(f)
                cat = session_data.get("metadata", {}).get("category")
                if cat in category_sessions:
                    category_sessions[cat].append(session_data)
        except Exception:
            continue

    # Analyze each category
    inspector = get_router_inspector()
    category_analyses = {}
    
    for cat, sessions in category_sessions.items():
        if sessions:
            analysis = inspector.analyze_expert_specialization(sessions)
            category_analyses[cat] = {
                "num_sessions": len(sessions),
                "top_experts": analysis.get("most_used", [])[:10],
                "prefill_usage": analysis.get("prefill_usage", {}),
                "generation_usage": analysis.get("generation_usage", {}),
                "layer_summary": analysis.get("layer_summary", {}),
            }
        else:
            category_analyses[cat] = {"num_sessions": 0, "top_experts": []}

    # Find experts that differentiate categories
    # (experts that are high in one category but low in others)
    differentiating_experts = _find_differentiating_experts(category_analyses)

    return {
        "categories": category_analyses,
        "differentiating_experts": differentiating_experts,
    }


def _find_differentiating_experts(category_analyses: Dict) -> List[Dict]:
    """Find experts that strongly differentiate between categories"""
    # Collect all expert usage across categories
    expert_by_category: Dict[int, Dict[str, float]] = {}
    
    for cat, analysis in category_analyses.items():
        if analysis["num_sessions"] == 0:
            continue
        for expert_id, count in analysis.get("top_experts", []):
            if expert_id not in expert_by_category:
                expert_by_category[expert_id] = {}
            # Normalize by session count
            expert_by_category[expert_id][cat] = count / analysis["num_sessions"]
    
    # Find experts with high variance across categories
    differentiating = []
    for expert_id, usage in expert_by_category.items():
        if len(usage) < 2:
            continue
        values = list(usage.values())
        mean_usage = sum(values) / len(values)
        variance = sum((v - mean_usage) ** 2 for v in values) / len(values)
        
        if variance > 0:
            # Find which category this expert is strongest in
            max_cat = max(usage.items(), key=lambda x: x[1])
            differentiating.append({
                "expert_id": expert_id,
                "variance": variance,
                "strongest_category": max_cat[0],
                "usage_by_category": usage
            })
    
    # Sort by variance (most differentiating first)
    differentiating.sort(key=lambda x: x["variance"], reverse=True)
    return differentiating[:20]


@router.get("/analyze/layer-expert-heatmap")
async def get_layer_expert_heatmap(
    agent_id: Optional[str] = None,
    category: Optional[str] = None,
    phase: Optional[str] = None  # "prefill", "generation", or None for both
):
    """Get Layer × Expert activation heatmap for visualization
    
    Returns a matrix showing which experts activate most on which layers.
    Critical for identifying LoRA targeting opportunities!
    """
    if agent_id:
        log_dir = Path.home() / ".appletta" / "router_lens" / "agents" / agent_id
    else:
        log_dir = Path.home() / ".appletta" / "router_lens" / "general"

    if not log_dir.exists():
        return {"error": "No sessions found"}

    # Aggregate layer × expert data across sessions
    layer_expert_counts: Dict[int, Dict[int, int]] = {}
    layer_expert_weights: Dict[int, Dict[int, float]] = {}
    num_sessions = 0

    for filepath in log_dir.glob("router_session_*.json"):
        try:
            with open(filepath) as f:
                session_data = json.load(f)
                
                # Filter by category if specified
                if category:
                    session_cat = session_data.get("metadata", {}).get("category")
                    if session_cat != category:
                        continue
                
                num_sessions += 1
                
                # Choose which matrix to use based on phase
                if phase == "prefill":
                    matrix = session_data.get("prefill_layer_expert_matrix", {})
                elif phase == "generation":
                    matrix = session_data.get("generation_layer_expert_matrix", {})
                else:
                    matrix = session_data.get("layer_expert_matrix", {})
                
                for layer_str, experts in matrix.items():
                    layer_idx = int(layer_str)
                    if layer_idx not in layer_expert_counts:
                        layer_expert_counts[layer_idx] = {}
                        layer_expert_weights[layer_idx] = {}
                    
                    for expert_str, data in experts.items():
                        expert_id = int(expert_str)
                        count = data.get("count", 0)
                        weight = data.get("total_weight", 0)
                        
                        layer_expert_counts[layer_idx][expert_id] = \
                            layer_expert_counts[layer_idx].get(expert_id, 0) + count
                        layer_expert_weights[layer_idx][expert_id] = \
                            layer_expert_weights[layer_idx].get(expert_id, 0) + weight
                            
        except Exception as e:
            continue

    if not layer_expert_counts:
        return {"error": "No layer-expert data found"}

    # Convert to heatmap format
    all_layers = sorted(layer_expert_counts.keys())
    all_experts = set()
    for experts in layer_expert_counts.values():
        all_experts.update(experts.keys())
    all_experts = sorted(all_experts)

    # Build matrix [layers × experts]
    heatmap_matrix = []
    for layer in all_layers:
        row = []
        for expert in all_experts:
            count = layer_expert_counts.get(layer, {}).get(expert, 0)
            row.append(count)
        heatmap_matrix.append(row)

    # Find hotspots (layer-expert pairs with highest activation)
    hotspots = []
    for layer in all_layers:
        for expert, count in layer_expert_counts.get(layer, {}).items():
            weight = layer_expert_weights.get(layer, {}).get(expert, 0)
            hotspots.append({
                "layer": layer,
                "expert": expert,
                "count": count,
                "avg_weight": weight / count if count > 0 else 0
            })
    hotspots.sort(key=lambda x: x["count"], reverse=True)

    return {
        "layers": all_layers,
        "experts": all_experts,
        "heatmap_matrix": heatmap_matrix,
        "hotspots": hotspots[:30],
        "num_sessions": num_sessions,
        "category": category,
        "phase": phase
    }


@router.post("/analyze/entropy-distribution")
async def analyze_entropy_distribution(agent_id: Optional[str] = None, category: Optional[str] = None):
    """Analyze router entropy distribution across sessions"""
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
async def get_expert_clusters(agent_id: Optional[str] = None, category: Optional[str] = None):
    """Get discovered expert clusters based on co-activation patterns"""
    if agent_id:
        log_dir = Path.home() / ".appletta" / "router_lens" / "agents" / agent_id
    else:
        log_dir = Path.home() / ".appletta" / "router_lens" / "general"

    sessions = []
    for filepath in log_dir.glob("router_session_*.json"):
        try:
            with open(filepath) as f:
                data = json.load(f)
                if category:
                    if data.get("metadata", {}).get("category") != category:
                        continue
                sessions.append(data)
        except Exception:
            continue

    if not sessions:
        return {"clusters": [], "message": "No sessions to analyze"}

    inspector = get_router_inspector()
    analysis = inspector.analyze_expert_specialization(sessions)

    return {
        "clusters": analysis.get("expert_clusters", []),
        "co_occurrence_pairs": analysis.get("co_occurrence_pairs", [])[:20],
        "most_used": analysis.get("most_used", []),
        "least_used": analysis.get("least_used", []),
        "num_sessions": len(sessions),
        "category": category
    }


@router.get("/analyze/prompt-type-leaderboard")
async def get_prompt_type_leaderboard(agent_id: Optional[str] = None, top_n: int = 10):
    """Get expert leaderboards across all prompt types for comparison

    Returns the top experts for each category/prompt type so you can see
    which experts specialize in which types of tasks!
    """
    if agent_id:
        log_dir = Path.home() / ".appletta" / "router_lens" / "agents" / agent_id
    else:
        log_dir = Path.home() / ".appletta" / "router_lens" / "general"

    if not log_dir.exists():
        return {"error": "No sessions found"}

    # Group sessions by category
    category_sessions: Dict[str, List[Dict]] = {}

    for filepath in log_dir.glob("router_session_*.json"):
        try:
            with open(filepath) as f:
                session_data = json.load(f)
                category = session_data.get("metadata", {}).get("category", "uncategorized")
                if category not in category_sessions:
                    category_sessions[category] = []
                category_sessions[category].append(session_data)
        except Exception:
            continue

    if not category_sessions:
        return {"error": "No categorized sessions found"}

    # Analyze each category
    inspector = get_router_inspector()
    leaderboard = {}

    for category, sessions in category_sessions.items():
        analysis = inspector.analyze_expert_specialization(sessions)

        # Get top experts with normalized scores
        top_experts = analysis.get("most_used", [])[:top_n]
        total_activations = sum(count for _, count in top_experts) if top_experts else 1

        leaderboard[category] = {
            "num_sessions": len(sessions),
            "total_activations": total_activations,
            "top_experts": [
                {
                    "expert_id": expert_id,
                    "count": count,
                    "percentage": (count / total_activations) * 100 if total_activations > 0 else 0,
                    "avg_per_session": count / len(sessions)
                }
                for expert_id, count in top_experts
            ],
            "prefill_top": sorted(
                analysis.get("prefill_usage", {}).items(),
                key=lambda x: x[1],
                reverse=True
            )[:top_n],
            "generation_top": sorted(
                analysis.get("generation_usage", {}).items(),
                key=lambda x: x[1],
                reverse=True
            )[:top_n],
        }

    # Find "champion" experts (highest activation in each category)
    champions = {}
    for category, data in leaderboard.items():
        if data["top_experts"]:
            champion = data["top_experts"][0]
            if champion["expert_id"] not in champions:
                champions[champion["expert_id"]] = []
            champions[champion["expert_id"]].append({
                "category": category,
                "count": champion["count"],
                "percentage": champion["percentage"]
            })

    return {
        "leaderboard": leaderboard,
        "champions": champions,
        "categories": list(category_sessions.keys()),
        "total_sessions": sum(len(sessions) for sessions in category_sessions.values())
    }


@router.post("/simulate/expert-mask")
async def simulate_expert_masking(request: ExpertMaskTestRequest):
    """Simulate what would happen if certain experts were disabled"""
    return {
        "status": "not_implemented",
        "message": "Expert masking simulation requires custom MLX model modifications",
        "requested_mask": request.disabled_experts,
    }


@router.get("/monitor/current")
async def get_current_monitoring_data():
    """Get real-time monitoring data for current inference"""
    inspector = get_router_inspector()

    tokens = inspector.current_session.get("tokens", [])
    if not tokens:
        return {"status": "no_data", "message": "No tokens in current session"}

    last_tokens = tokens[-20:] if len(tokens) > 20 else tokens

    return {
        "total_tokens": len(tokens),
        "prefill_tokens": len(inspector.current_session.get("prefill_tokens", [])),
        "generation_tokens": len(inspector.current_session.get("generation_tokens", [])),
        "last_tokens": last_tokens,
        "current_usage": inspector.current_session.get("expert_usage_count", {}),
        "recent_entropy": inspector.current_session.get("entropy_history", [])[-10:],
    }


# =============================================================================
# Diagnostic Inference
# =============================================================================

@router.post("/diagnostic/load-model")
async def load_model_for_diagnostics(request: LoadModelRequest):
    """Load a model for diagnostic inference with router logging"""
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
    """Load an agent's model for diagnostic inference with router logging"""
    try:
        service = get_diagnostic_service()
    except ImportError as e:
        raise HTTPException(500, f"MLX not installed: {str(e)}")

    try:
        agent_uuid = UUID(agent_id)
    except ValueError:
        raise HTTPException(400, "Invalid agent ID format")

    agent = db.query(Agent).filter(Agent.id == agent_uuid).first()
    if not agent:
        raise HTTPException(404, f"Agent not found: {agent_id}")

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
    """Run a single inference with full router logging (prefill + generation)"""
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
            log_routing=True,
            capture_prefill=request.capture_prefill
        )

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

    if category:
        service.router_inspector.current_session["metadata"]["category"] = category

    prompt = service.router_inspector.current_session.get("metadata", {}).get("prompt", prompt_preview)
    response = service.router_inspector.current_session.get("metadata", {}).get("response", "")

    filepath = service.router_inspector.save_session(prompt=prompt, response=response)

    inspector = get_router_inspector()
    inspector.current_session = service.router_inspector.current_session.copy()
    inspector.save_session(prompt=prompt, response=response)

    return {
        "saved": True,
        "filepath": filepath,
        "category": category
    }


@router.post("/diagnostic/quick-test")
async def quick_diagnostic_test():
    """Run a quick test to generate sample router data"""
    try:
        service = get_diagnostic_service()
    except ImportError as e:
        raise HTTPException(500, f"MLX not installed: {str(e)}")

    if service.model is None:
        raise HTTPException(
            400,
            "No model loaded. Load an MoE model first with /diagnostic/load-model"
        )

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
            log_routing=True,
            capture_prefill=True
        )

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
    for item in models_dir.iterdir():
        if item.is_dir():
            if item.name.startswith("models--"):
                parts = item.name.replace("models--", "").split("--")
                model_name = "/".join(parts)
                snapshots_dir = item / "snapshots"
                if snapshots_dir.exists():
                    for snapshot in snapshots_dir.iterdir():
                        if snapshot.is_dir() and (snapshot / "config.json").exists():
                            models.append({
                                "name": model_name,
                                "path": str(snapshot),
                                "type": "huggingface_cache"
                            })
                            break
            elif (item / "config.json").exists():
                models.append({
                    "name": item.name,
                    "path": str(item),
                    "type": "local"
                })

    return {"models": models, "base_path": str(models_dir), "exists": True}


@router.get("/browse/adapters")
async def browse_adapters():
    """List available adapters in the configured adapters directory"""
    adapters_dir = Path(settings.ADAPTERS_DIR).expanduser()

    if not adapters_dir.exists():
        return {"adapters": [], "base_path": str(adapters_dir), "exists": False}

    adapters = []
    for item in adapters_dir.iterdir():
        if item.is_dir():
            if (item / "adapter_config.json").exists() or (item / "adapter_model.safetensors").exists():
                adapters.append({"name": item.name, "path": str(item)})

    return {"adapters": adapters, "base_path": str(adapters_dir), "exists": True}


@router.get("/browse/directory")
async def browse_directory(path: str = "~"):
    """Browse any directory on the filesystem"""
    browse_path = Path(path).expanduser().resolve()

    if not browse_path.exists():
        return {
            "path": str(browse_path),
            "exists": False,
            "items": [],
            "parent": str(browse_path.parent)
        }

    if not browse_path.is_dir():
        browse_path = browse_path.parent

    items = []
    try:
        for item in sorted(browse_path.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
            if item.name.startswith('.') and item.name not in ['.cache']:
                continue

            item_info = {
                "name": item.name,
                "path": str(item),
                "is_dir": item.is_dir(),
            }

            if item.is_dir() and (item / "config.json").exists():
                item_info["is_model"] = True
            if item.is_dir() and ((item / "adapter_config.json").exists() or
                                   (item / "adapter_model.safetensors").exists()):
                item_info["is_adapter"] = True

            items.append(item_info)
    except PermissionError:
        pass

    return {
        "path": str(browse_path),
        "exists": True,
        "items": items,
        "parent": str(browse_path.parent) if browse_path.parent != browse_path else None
    }


@router.get("/sessions/{filename}/heatmap")
async def get_session_heatmap(filename: str, agent_id: Optional[str] = None):
    """Get expert activation heatmap data for visualization
    
    Now includes prefill and generation tokens separately!
    """
    if agent_id:
        log_dir = Path.home() / ".appletta" / "router_lens" / "agents" / agent_id
    else:
        log_dir = Path.home() / ".appletta" / "router_lens" / "general"

    filepath = log_dir / filename

    if not filepath.exists():
        raise HTTPException(404, f"Session {filename} not found")

    with open(filepath) as f:
        session_data = json.load(f)

    num_experts = session_data.get("metadata", {}).get("num_experts", 128)

    def build_heatmap(tokens: List[Dict]) -> tuple:
        """Build heatmap matrix from token list"""
        heatmap_matrix = []
        token_texts = []
        
        for token_data in tokens:
            row = [0.0] * num_experts
            
            if "layers" in token_data:
                for layer_data in token_data["layers"]:
                    selected_experts = layer_data.get("selected_experts", [])
                    expert_weights = layer_data.get("expert_weights", [])
                    
                    if expert_weights and len(expert_weights) == len(selected_experts):
                        for expert_id, weight in zip(selected_experts, expert_weights):
                            if expert_id < num_experts:
                                row[expert_id] += weight
                    else:
                        for expert_id in selected_experts:
                            if expert_id < num_experts:
                                row[expert_id] += 1.0 / len(selected_experts) if selected_experts else 0
            
            heatmap_matrix.append(row)
            token_text = token_data.get("token", f"Token {token_data.get('idx', len(token_texts))}")
            token_texts.append(token_text)
        
        return heatmap_matrix, token_texts

    # Build heatmaps for prefill and generation separately
    prefill_tokens = session_data.get("prefill_tokens", [])
    generation_tokens = session_data.get("generation_tokens", [])
    all_tokens = session_data.get("tokens", [])
    
    prefill_matrix, prefill_texts = build_heatmap(prefill_tokens) if prefill_tokens else ([], [])
    generation_matrix, generation_texts = build_heatmap(generation_tokens) if generation_tokens else ([], [])
    combined_matrix, combined_texts = build_heatmap(all_tokens) if all_tokens else ([], [])

    return {
        "filename": filename,
        "num_experts": num_experts,
        # Combined view (backwards compatibility)
        "num_tokens": len(all_tokens),
        "heatmap_matrix": combined_matrix,
        "token_texts": combined_texts,
        # Separate views for prefill and generation
        "prefill": {
            "num_tokens": len(prefill_tokens),
            "heatmap_matrix": prefill_matrix,
            "token_texts": prefill_texts,
        },
        "generation": {
            "num_tokens": len(generation_tokens),
            "heatmap_matrix": generation_matrix,
            "token_texts": generation_texts,
        },
        "metadata": {
            "start_time": session_data.get("start_time"),
            "end_time": session_data.get("end_time"),
            "prompt": session_data.get("metadata", {}).get("prompt", ""),
            "response": session_data.get("metadata", {}).get("response", ""),
            "category": session_data.get("metadata", {}).get("category", ""),
        },
        "summary": session_data.get("summary", {}),
        "layer_expert_matrix": session_data.get("layer_expert_matrix", {}),
        "prefill_layer_expert_matrix": session_data.get("prefill_layer_expert_matrix", {}),
        "generation_layer_expert_matrix": session_data.get("generation_layer_expert_matrix", {}),
    }

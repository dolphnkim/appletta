"""Router Lens - MoE Router Introspection System

Provides tools to inspect and analyze Mixture-of-Experts router behavior:
- Per-token expert selection logging (BOTH prefill and generation)
- Gate logit distribution analysis
- Expert usage histograms
- Router entropy metrics
- Expert activation patterns
- Layer × Expert analysis for LoRA targeting
"""

import json
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path
from datetime import datetime
import numpy as np


class RouterInspector:
    """Captures and analyzes MoE router decisions during inference
    
    Now captures BOTH prefill (prompt processing) and generation phases
    to enable full interpretability research.
    """

    def __init__(self, num_experts: int = 128, top_k: int = 8, agent_id: Optional[str] = None):
        self.num_experts = num_experts
        self.top_k = top_k
        self.enable_logging = False
        self.agent_id = agent_id

        # Session data
        self.current_session: Dict[str, Any] = {}
        self.reset_session()

        # Log storage - agent-specific if agent_id provided
        if agent_id:
            self.log_dir = Path.home() / ".appletta" / "router_lens" / "agents" / agent_id
        else:
            self.log_dir = Path.home() / ".appletta" / "router_lens" / "general"
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def reset_session(self):
        """Reset session data for a new inference run"""
        metadata = {}
        if self.agent_id:
            metadata["agent_id"] = self.agent_id

        self.current_session = {
            "start_time": datetime.utcnow().isoformat() + "Z",
            # Separate tracking for prefill vs generation
            "prefill_tokens": [],  # Tokens from prompt processing (how model interprets input)
            "generation_tokens": [],  # Tokens from response generation
            "tokens": [],  # Combined view (for backwards compatibility)
            "total_tokens": 0,
            "prefill_token_idx": 0,
            "generation_token_idx": 0,
            # Expert usage tracking - overall and by phase
            "expert_usage_count": {i: 0 for i in range(self.num_experts)},
            "prefill_expert_usage": {i: 0 for i in range(self.num_experts)},
            "generation_expert_usage": {i: 0 for i in range(self.num_experts)},
            # Layer × Expert matrix for identifying layer-specific patterns
            # Structure: { layer_idx: { expert_id: { "count": N, "total_weight": W } } }
            "layer_expert_matrix": {},
            "prefill_layer_expert_matrix": {},
            "generation_layer_expert_matrix": {},
            # Other tracking
            "gate_logits_history": [],
            "entropy_history": [],
            "metadata": metadata
        }

    def log_router_decision(
        self,
        token_idx: int,
        layer_idx: int,
        gate_logits: List[float],
        selected_experts: List[int],
        expert_weights: List[float],
        phase: str = "generation",  # NEW: "prefill" or "generation"
        input_token: Optional[str] = None
    ):
        """Log a single router decision for one token at one layer

        Args:
            token_idx: Position in sequence
            layer_idx: Which transformer layer this decision is from
            gate_logits: Raw router logits for all experts [num_experts]
            selected_experts: Indices of top-k selected experts
            expert_weights: Weights/probabilities for selected experts
            phase: "prefill" for prompt processing, "generation" for response
            input_token: Optional token string for context
        """
        # Compute entropy of gate distribution
        gate_probs = self._softmax(gate_logits)
        entropy = self._entropy(gate_probs)

        # Select the appropriate token list based on phase
        if phase == "prefill":
            token_list = self.current_session["prefill_tokens"]
            usage_dict = self.current_session["prefill_expert_usage"]
            layer_matrix = self.current_session["prefill_layer_expert_matrix"]
        else:
            token_list = self.current_session["generation_tokens"]
            usage_dict = self.current_session["generation_expert_usage"]
            layer_matrix = self.current_session["generation_layer_expert_matrix"]

        # Find or create token entry
        token_entry = None
        for t in token_list:
            if t["idx"] == token_idx:
                token_entry = t
                break

        if token_entry is None:
            token_entry = {
                "idx": token_idx,
                "phase": phase,
                "layers": [],
                "token": input_token
            }
            token_list.append(token_entry)
            # Also add to combined list for backwards compatibility
            self.current_session["tokens"].append(token_entry)
            self.current_session["total_tokens"] = len(self.current_session["tokens"])

        # Add this layer's routing decision
        layer_data = {
            "layer_idx": layer_idx,
            "selected_experts": selected_experts,
            "expert_weights": expert_weights,
            "entropy": entropy
        }
        token_entry["layers"].append(layer_data)

        # Update usage counts (both phase-specific and overall)
        for expert_id, weight in zip(selected_experts, expert_weights):
            # Phase-specific
            usage_dict[expert_id] = usage_dict.get(expert_id, 0) + 1
            # Overall
            self.current_session["expert_usage_count"][expert_id] += 1
            
            # Update layer × expert matrix
            layer_key = str(layer_idx)
            expert_key = str(expert_id)
            
            # Phase-specific matrix
            if layer_key not in layer_matrix:
                layer_matrix[layer_key] = {}
            if expert_key not in layer_matrix[layer_key]:
                layer_matrix[layer_key][expert_key] = {"count": 0, "total_weight": 0.0}
            layer_matrix[layer_key][expert_key]["count"] += 1
            layer_matrix[layer_key][expert_key]["total_weight"] += weight
            
            # Overall matrix
            overall_matrix = self.current_session["layer_expert_matrix"]
            if layer_key not in overall_matrix:
                overall_matrix[layer_key] = {}
            if expert_key not in overall_matrix[layer_key]:
                overall_matrix[layer_key][expert_key] = {"count": 0, "total_weight": 0.0}
            overall_matrix[layer_key][expert_key]["count"] += 1
            overall_matrix[layer_key][expert_key]["total_weight"] += weight

        # Store entropy
        self.current_session["entropy_history"].append(entropy)

        # Optionally store full gate logits (expensive, limit storage)
        if len(self.current_session["gate_logits_history"]) < 100:
            self.current_session["gate_logits_history"].append({
                "phase": phase,
                "token_idx": token_idx,
                "layer_idx": layer_idx,
                "logits": gate_logits
            })

    def get_session_summary(self) -> Dict[str, Any]:
        """Get summary statistics for current session"""
        if not self.current_session["tokens"]:
            return {"error": "No tokens logged"}

        usage = self.current_session["expert_usage_count"]
        total_activations = sum(usage.values())

        # Top experts by usage
        top_experts = sorted(usage.items(), key=lambda x: x[1], reverse=True)[:10]

        # Usage distribution metrics
        usage_values = list(usage.values())
        usage_entropy = self._entropy(self._normalize(usage_values))

        # Compute expert co-occurrence patterns
        expert_sequences = []
        for t in self.current_session["tokens"]:
            if "layers" in t:
                all_experts = set()
                for layer in t["layers"]:
                    all_experts.update(layer.get("selected_experts", []))
                expert_sequences.append(list(all_experts))
            else:
                expert_sequences.append(t.get("selected_experts", []))

        co_occurrence = self._compute_co_occurrence(expert_sequences)
        
        # Layer-wise expert analysis
        layer_summary = self._summarize_layer_expert_matrix(
            self.current_session["layer_expert_matrix"]
        )

        return {
            "total_tokens": len(self.current_session["tokens"]),
            "prefill_tokens": len(self.current_session["prefill_tokens"]),
            "generation_tokens": len(self.current_session["generation_tokens"]),
            "total_expert_activations": total_activations,
            "unique_experts_used": sum(1 for v in usage_values if v > 0),
            "top_experts": [{"expert_id": e, "count": c, "percentage": c / total_activations * 100 if total_activations > 0 else 0} for e, c in top_experts],
            "usage_entropy": usage_entropy,
            "mean_token_entropy": float(np.mean(self.current_session["entropy_history"])) if self.current_session["entropy_history"] else 0,
            "expert_usage_distribution": usage,
            "prefill_expert_usage": self.current_session["prefill_expert_usage"],
            "generation_expert_usage": self.current_session["generation_expert_usage"],
            "co_occurrence_top_pairs": co_occurrence[:10],
            "layer_summary": layer_summary,
            "start_time": self.current_session["start_time"],
        }
    
    def _summarize_layer_expert_matrix(self, matrix: Dict) -> Dict[str, Any]:
        """Summarize the layer × expert matrix for visualization"""
        if not matrix:
            return {"layers": [], "top_layer_experts": []}
        
        layer_summaries = []
        all_layer_experts = []
        
        for layer_idx, experts in matrix.items():
            layer_total = sum(e["count"] for e in experts.values())
            top_experts_in_layer = sorted(
                [(int(eid), data["count"], data["total_weight"]) for eid, data in experts.items()],
                key=lambda x: x[1],
                reverse=True
            )[:5]
            
            layer_summaries.append({
                "layer": int(layer_idx),
                "total_activations": layer_total,
                "unique_experts": len(experts),
                "top_experts": [{"expert_id": e[0], "count": e[1], "avg_weight": e[2]/e[1] if e[1] > 0 else 0} for e in top_experts_in_layer]
            })
            
            for eid, data in experts.items():
                all_layer_experts.append({
                    "layer": int(layer_idx),
                    "expert_id": int(eid),
                    "count": data["count"],
                    "total_weight": data["total_weight"]
                })
        
        # Sort layers
        layer_summaries.sort(key=lambda x: x["layer"])
        
        # Find experts that dominate specific layers
        top_layer_experts = sorted(all_layer_experts, key=lambda x: x["count"], reverse=True)[:20]
        
        return {
            "layers": layer_summaries,
            "top_layer_experts": top_layer_experts
        }

    def _compute_co_occurrence(self, expert_sequences: List[List[int]]) -> List[Tuple[Tuple[int, int], int]]:
        """Compute which experts frequently activate together"""
        co_occur: Dict[Tuple[int, int], int] = {}

        for experts in expert_sequences:
            for i in range(len(experts)):
                for j in range(i + 1, len(experts)):
                    pair = tuple(sorted([experts[i], experts[j]]))
                    co_occur[pair] = co_occur.get(pair, 0) + 1

        sorted_pairs = sorted(co_occur.items(), key=lambda x: x[1], reverse=True)
        return sorted_pairs

    def save_session(self, prompt: str = "", response: str = "") -> str:
        """Save current session to disk for later analysis

        Returns: Path to saved file
        """
        self.current_session["end_time"] = datetime.utcnow().isoformat() + "Z"
        # Store FULL prompt and response, not truncated
        self.current_session["metadata"]["prompt"] = prompt
        self.current_session["metadata"]["response"] = response
        self.current_session["summary"] = self.get_session_summary()

        # Generate filename
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        filename = f"router_session_{timestamp}.json"
        filepath = self.log_dir / filename

        with open(filepath, "w") as f:
            json.dump(self.current_session, f, indent=2, default=str)

        return str(filepath)

    def get_status(self) -> Dict[str, Any]:
        """Get current inspector status"""
        return {
            "num_experts": self.num_experts,
            "top_k": self.top_k,
            "session_tokens": len(self.current_session.get("tokens", [])),
            "prefill_tokens": len(self.current_session.get("prefill_tokens", [])),
            "generation_tokens": len(self.current_session.get("generation_tokens", [])),
            "log_directory": str(self.log_dir),
            "enable_logging": getattr(self, "enable_logging", False),
        }

    def analyze_expert_specialization(self, sessions: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze expert specialization across multiple sessions

        Looks for patterns like:
        - Which experts activate for certain prompt types
        - Expert clustering based on co-activation
        - Potential semantic roles
        - Layer-specific patterns
        """
        aggregate_usage = {i: 0 for i in range(self.num_experts)}
        aggregate_prefill_usage = {i: 0 for i in range(self.num_experts)}
        aggregate_generation_usage = {i: 0 for i in range(self.num_experts)}
        all_co_occur: Dict[Tuple[int, int], int] = {}
        aggregate_layer_matrix: Dict[str, Dict[str, Dict[str, float]]] = {}

        for session in sessions:
            # Overall usage
            usage = session.get("expert_usage_distribution", session.get("summary", {}).get("expert_usage_distribution", {}))
            for expert_id, count in usage.items():
                aggregate_usage[int(expert_id)] = aggregate_usage.get(int(expert_id), 0) + count
            
            # Phase-specific usage
            prefill_usage = session.get("prefill_expert_usage", {})
            for expert_id, count in prefill_usage.items():
                aggregate_prefill_usage[int(expert_id)] = aggregate_prefill_usage.get(int(expert_id), 0) + count
                
            gen_usage = session.get("generation_expert_usage", {})
            for expert_id, count in gen_usage.items():
                aggregate_generation_usage[int(expert_id)] = aggregate_generation_usage.get(int(expert_id), 0) + count

            # Aggregate layer × expert matrix
            layer_matrix = session.get("layer_expert_matrix", {})
            for layer_idx, experts in layer_matrix.items():
                if layer_idx not in aggregate_layer_matrix:
                    aggregate_layer_matrix[layer_idx] = {}
                for expert_id, data in experts.items():
                    if expert_id not in aggregate_layer_matrix[layer_idx]:
                        aggregate_layer_matrix[layer_idx][expert_id] = {"count": 0, "total_weight": 0.0}
                    aggregate_layer_matrix[layer_idx][expert_id]["count"] += data.get("count", 0)
                    aggregate_layer_matrix[layer_idx][expert_id]["total_weight"] += data.get("total_weight", 0)

            # Co-occurrence
            for token_data in session.get("tokens", []):
                if "layers" in token_data:
                    all_experts_in_token = set()
                    for layer in token_data["layers"]:
                        all_experts_in_token.update(layer.get("selected_experts", []))
                    experts = list(all_experts_in_token)
                else:
                    experts = token_data.get("selected_experts", [])

                for i in range(len(experts)):
                    for j in range(i + 1, len(experts)):
                        pair = tuple(sorted([experts[i], experts[j]]))
                        all_co_occur[pair] = all_co_occur.get(pair, 0) + 1

        clusters = self._cluster_experts(all_co_occur)
        layer_summary = self._summarize_layer_expert_matrix(aggregate_layer_matrix)

        return {
            "aggregate_usage": aggregate_usage,
            "prefill_usage": aggregate_prefill_usage,
            "generation_usage": aggregate_generation_usage,
            "expert_clusters": clusters,
            "most_used": sorted(aggregate_usage.items(), key=lambda x: x[1], reverse=True)[:10],
            "least_used": sorted(aggregate_usage.items(), key=lambda x: x[1])[:10],
            "layer_summary": layer_summary,
            "co_occurrence_pairs": sorted(all_co_occur.items(), key=lambda x: x[1], reverse=True)[:20],
        }

    def _cluster_experts(self, co_occurrence: Dict[Tuple[int, int], int], threshold: float = 0.5) -> List[List[int]]:
        """Simple greedy clustering based on co-occurrence frequency"""
        if not co_occurrence:
            return []

        all_expert_ids = set()
        for (e1, e2) in co_occurrence.keys():
            all_expert_ids.add(e1)
            all_expert_ids.add(e2)

        max_cooccur = max(co_occurrence.values()) if co_occurrence else 1
        adjacency: Dict[int, List[int]] = {expert_id: [] for expert_id in all_expert_ids}

        for (e1, e2), count in co_occurrence.items():
            if count / max_cooccur > threshold:
                adjacency[e1].append(e2)
                adjacency[e2].append(e1)

        visited = set()
        clusters = []

        for expert in all_expert_ids:
            if expert not in visited and adjacency[expert]:
                cluster = [expert]
                visited.add(expert)
                queue = list(adjacency[expert])

                while queue:
                    neighbor = queue.pop(0)
                    if neighbor not in visited:
                        visited.add(neighbor)
                        cluster.append(neighbor)
                        queue.extend([n for n in adjacency[neighbor] if n not in visited])

                if len(cluster) > 1:
                    clusters.append(sorted(cluster))

        return clusters

    @staticmethod
    def _softmax(logits: List[float]) -> List[float]:
        """Compute softmax of logits"""
        exp_logits = np.exp(np.array(logits) - np.max(logits))
        return (exp_logits / exp_logits.sum()).tolist()

    @staticmethod
    def _entropy(probs: List[float]) -> float:
        """Compute entropy of probability distribution"""
        probs = np.array(probs)
        probs = probs[probs > 0]
        return float(-np.sum(probs * np.log(probs)))

    @staticmethod
    def _normalize(values: List[float]) -> List[float]:
        """Normalize values to sum to 1"""
        total = sum(values)
        if total == 0:
            return [0] * len(values)
        return [v / total for v in values]


# Global instance for easy access
_global_inspector: Optional[RouterInspector] = None


def get_router_inspector() -> RouterInspector:
    """Get or create global router inspector instance"""
    global _global_inspector
    if _global_inspector is None:
        _global_inspector = RouterInspector()
    return _global_inspector


def reset_router_inspector(num_experts: int = 128, top_k: int = 8):
    """Reset global inspector with new configuration"""
    global _global_inspector
    _global_inspector = RouterInspector(num_experts=num_experts, top_k=top_k)

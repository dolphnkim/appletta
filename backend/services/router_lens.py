"""Router Lens - MoE Router Introspection System

Provides tools to inspect and analyze Mixture-of-Experts router behavior:
- Per-token expert selection logging
- Gate logit distribution analysis
- Expert usage histograms
- Router entropy metrics
- Expert activation patterns
"""

import json
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path
from datetime import datetime
import numpy as np


class RouterInspector:
    """Captures and analyzes MoE router decisions during inference"""

    def __init__(self, num_experts: int = 64, top_k: int = 8):
        self.num_experts = num_experts
        self.top_k = top_k

        # Session data
        self.current_session: Dict[str, Any] = {}
        self.reset_session()

        # Log storage
        self.log_dir = Path.home() / ".appletta" / "router_lens"
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def reset_session(self):
        """Reset session data for a new inference run"""
        self.current_session = {
            "start_time": datetime.utcnow().isoformat() + "Z",
            "tokens": [],  # Per-token expert selections
            "expert_usage_count": {i: 0 for i in range(self.num_experts)},
            "gate_logits_history": [],  # Raw gate logits for analysis
            "entropy_history": [],  # Router entropy per token
            "metadata": {}
        }

    def log_router_decision(
        self,
        token_idx: int,
        gate_logits: List[float],
        selected_experts: List[int],
        expert_weights: List[float],
        input_token: Optional[str] = None
    ):
        """Log a single router decision for one token

        Args:
            token_idx: Position in sequence
            gate_logits: Raw router logits for all experts [num_experts]
            selected_experts: Indices of top-k selected experts
            expert_weights: Weights/probabilities for selected experts
            input_token: Optional token string for context
        """
        # Compute entropy of gate distribution
        gate_probs = self._softmax(gate_logits)
        entropy = self._entropy(gate_probs)

        token_data = {
            "idx": token_idx,
            "selected_experts": selected_experts,
            "expert_weights": expert_weights,
            "entropy": entropy,
        }

        if input_token:
            token_data["token"] = input_token

        self.current_session["tokens"].append(token_data)

        # Update usage counts
        for expert_id in selected_experts:
            self.current_session["expert_usage_count"][expert_id] += 1

        # Store entropy
        self.current_session["entropy_history"].append(entropy)

        # Optionally store full gate logits (expensive, for deep analysis)
        if len(self.current_session["gate_logits_history"]) < 100:  # Limit storage
            self.current_session["gate_logits_history"].append(gate_logits)

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
        expert_sequences = [t["selected_experts"] for t in self.current_session["tokens"]]
        co_occurrence = self._compute_co_occurrence(expert_sequences)

        return {
            "total_tokens": len(self.current_session["tokens"]),
            "total_expert_activations": total_activations,
            "unique_experts_used": sum(1 for v in usage_values if v > 0),
            "top_experts": [{"expert_id": e, "count": c, "percentage": c / total_activations * 100} for e, c in top_experts],
            "usage_entropy": usage_entropy,  # Higher = more balanced usage
            "mean_token_entropy": np.mean(self.current_session["entropy_history"]) if self.current_session["entropy_history"] else 0,
            "expert_usage_distribution": usage,
            "co_occurrence_top_pairs": co_occurrence[:5],
            "start_time": self.current_session["start_time"],
        }

    def _compute_co_occurrence(self, expert_sequences: List[List[int]]) -> List[Tuple[Tuple[int, int], int]]:
        """Compute which experts frequently activate together"""
        co_occur: Dict[Tuple[int, int], int] = {}

        for experts in expert_sequences:
            # Count pairs of experts that activate together
            for i in range(len(experts)):
                for j in range(i + 1, len(experts)):
                    pair = tuple(sorted([experts[i], experts[j]]))
                    co_occur[pair] = co_occur.get(pair, 0) + 1

        # Sort by frequency
        sorted_pairs = sorted(co_occur.items(), key=lambda x: x[1], reverse=True)
        return sorted_pairs

    def save_session(self, prompt: str = "", response: str = "") -> str:
        """Save current session to disk for later analysis

        Returns: Path to saved file
        """
        self.current_session["end_time"] = datetime.utcnow().isoformat() + "Z"
        self.current_session["metadata"]["prompt"] = prompt[:500] if prompt else ""
        self.current_session["metadata"]["response"] = response[:500] if response else ""
        self.current_session["summary"] = self.get_session_summary()

        # Generate filename
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        filename = f"router_session_{timestamp}.json"
        filepath = self.log_dir / filename

        with open(filepath, "w") as f:
            json.dump(self.current_session, f, indent=2, default=str)

        return str(filepath)

    def analyze_expert_specialization(self, sessions: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze expert specialization across multiple sessions

        Looks for patterns like:
        - Which experts activate for certain prompt types
        - Expert clustering based on co-activation
        - Potential semantic roles
        """
        # Aggregate usage patterns
        aggregate_usage = {i: 0 for i in range(self.num_experts)}
        all_co_occur: Dict[Tuple[int, int], int] = {}

        for session in sessions:
            usage = session.get("expert_usage_distribution", {})
            for expert_id, count in usage.items():
                aggregate_usage[int(expert_id)] = aggregate_usage.get(int(expert_id), 0) + count

            # Aggregate co-occurrence
            for token_data in session.get("tokens", []):
                experts = token_data.get("selected_experts", [])
                for i in range(len(experts)):
                    for j in range(i + 1, len(experts)):
                        pair = tuple(sorted([experts[i], experts[j]]))
                        all_co_occur[pair] = all_co_occur.get(pair, 0) + 1

        # Identify expert clusters based on co-occurrence
        clusters = self._cluster_experts(all_co_occur)

        return {
            "aggregate_usage": aggregate_usage,
            "expert_clusters": clusters,
            "most_used": sorted(aggregate_usage.items(), key=lambda x: x[1], reverse=True)[:10],
            "least_used": sorted(aggregate_usage.items(), key=lambda x: x[1])[:10],
        }

    def _cluster_experts(self, co_occurrence: Dict[Tuple[int, int], int], threshold: float = 0.5) -> List[List[int]]:
        """Simple greedy clustering based on co-occurrence frequency"""
        if not co_occurrence:
            return []

        # Build adjacency based on high co-occurrence
        max_cooccur = max(co_occurrence.values()) if co_occurrence else 1
        adjacency: Dict[int, List[int]] = {i: [] for i in range(self.num_experts)}

        for (e1, e2), count in co_occurrence.items():
            if count / max_cooccur > threshold:
                adjacency[e1].append(e2)
                adjacency[e2].append(e1)

        # Greedy clustering
        visited = set()
        clusters = []

        for expert in range(self.num_experts):
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
        probs = probs[probs > 0]  # Avoid log(0)
        return -np.sum(probs * np.log(probs))

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


def reset_router_inspector(num_experts: int = 64, top_k: int = 8):
    """Reset global inspector with new configuration"""
    global _global_inspector
    _global_inspector = RouterInspector(num_experts=num_experts, top_k=top_k)

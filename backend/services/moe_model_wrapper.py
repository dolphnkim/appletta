"""MoE Model Wrapper - Intercepts router decisions for introspection

This wraps MLX MoE models to capture gate logits and expert selections
during inference, enabling router lens debugging.
"""

import mlx.core as mx
import mlx.nn as nn
from typing import Any, Dict, List, Optional, Tuple
from backend.services.router_lens import get_router_inspector


class MoERouterHook:
    """Hook that captures MoE router decisions

    This class wraps the forward pass of MoE blocks to intercept
    gate logits and expert selections.
    """

    def __init__(self, model: Any, enable_logging: bool = False):
        """
        Args:
            model: The MLX model (must have MoE architecture)
            enable_logging: Whether to actively log router decisions
        """
        self.model = model
        self.enable_logging = enable_logging
        self.inspector = get_router_inspector()
        self.token_counter = 0

        # Try to detect MoE configuration from model
        self.moe_config = self._detect_moe_config(model)

    def _detect_moe_config(self, model: Any) -> Dict[str, Any]:
        """Detect MoE configuration from model architecture"""
        config = {
            "num_experts": 64,  # Default, will try to detect
            "top_k": 8,
            "has_shared_expert": False,
            "architecture": "unknown"
        }

        # Try to find MoE layers in the model
        try:
            if hasattr(model, "model") and hasattr(model.model, "layers"):
                first_layer = model.model.layers[0] if model.model.layers else None
                if first_layer and hasattr(first_layer, "mlp"):
                    mlp = first_layer.mlp
                    if hasattr(mlp, "gate"):  # Qwen2-MoE style
                        config["architecture"] = "qwen2_moe"
                        if hasattr(mlp, "num_experts"):
                            config["num_experts"] = mlp.num_experts
                        if hasattr(mlp, "top_k"):
                            config["top_k"] = mlp.top_k
                        elif hasattr(mlp, "num_experts_per_tok"):
                            config["top_k"] = mlp.num_experts_per_tok
                        if hasattr(mlp, "shared_expert"):
                            config["has_shared_expert"] = True
                    elif hasattr(mlp, "experts"):  # Mixtral style
                        config["architecture"] = "mixtral"
                        config["num_experts"] = len(mlp.experts) if hasattr(mlp.experts, "__len__") else 8
        except Exception as e:
            print(f"⚠️ Could not detect MoE config: {e}")

        return config

    def intercept_forward(self, hidden_states: mx.array, layer_idx: int = 0) -> Tuple[mx.array, Dict[str, Any]]:
        """Intercept a forward pass through an MoE layer

        This method should be called by a custom forward hook.

        Args:
            hidden_states: Input tensor to the MoE block
            layer_idx: Which transformer layer this is

        Returns:
            Tuple of (output, router_info)
        """
        if not self.enable_logging:
            return None, {}

        # This is a placeholder - actual implementation depends on
        # how we integrate with the MLX model forward pass
        router_info = {
            "layer_idx": layer_idx,
            "hidden_state_norm": float(mx.sqrt(mx.sum(hidden_states ** 2)).item()),
        }

        return None, router_info

    def log_generation_step(
        self,
        gate_logits: mx.array,
        selected_experts: mx.array,
        expert_weights: mx.array,
        input_token: Optional[str] = None
    ):
        """Log a single generation step's router decision

        Args:
            gate_logits: Raw gate scores [num_experts]
            selected_experts: Top-k expert indices [top_k]
            expert_weights: Weights for selected experts [top_k]
            input_token: Optional token string
        """
        if not self.enable_logging:
            return

        # Convert MLX arrays to Python lists
        gate_logits_list = gate_logits.tolist() if hasattr(gate_logits, "tolist") else list(gate_logits)
        selected_list = selected_experts.tolist() if hasattr(selected_experts, "tolist") else list(selected_experts)
        weights_list = expert_weights.tolist() if hasattr(expert_weights, "tolist") else list(expert_weights)

        self.inspector.log_router_decision(
            token_idx=self.token_counter,
            gate_logits=gate_logits_list,
            selected_experts=selected_list,
            expert_weights=weights_list,
            input_token=input_token
        )

        self.token_counter += 1

    def reset_logging(self):
        """Reset for a new inference run"""
        self.token_counter = 0
        self.inspector.reset_session()

    def get_summary(self) -> Dict[str, Any]:
        """Get summary of current inference run"""
        return self.inspector.get_session_summary()

    def save_session(self, prompt: str = "", response: str = "") -> str:
        """Save current session logs"""
        return self.inspector.save_session(prompt=prompt, response=response)


def create_instrumented_model(model: Any, enable_logging: bool = False) -> Tuple[Any, MoERouterHook]:
    """Wrap a model with router introspection capabilities

    Args:
        model: The MLX model
        enable_logging: Whether to enable router logging

    Returns:
        Tuple of (model, hook) where hook can be used to access router data
    """
    hook = MoERouterHook(model, enable_logging=enable_logging)
    return model, hook


# =============================================================================
# MLX Model Patching for Router Introspection
# =============================================================================

def patch_qwen2_moe_forward(model: Any, hook: MoERouterHook):
    """Patch Qwen2-MoE model to capture router decisions

    This modifies the model's forward pass to intercept gate computations.
    """
    if not hasattr(model, "model") or not hasattr(model.model, "layers"):
        print("⚠️ Cannot patch: model doesn't have expected structure")
        return

    # Store original forward methods
    for layer_idx, layer in enumerate(model.model.layers):
        if hasattr(layer, "mlp") and hasattr(layer.mlp, "gate"):
            moe_block = layer.mlp
            original_call = moe_block.__call__

            def make_patched_forward(orig_call, moe, layer_id, hook_ref):
                def patched_forward(x):
                    # Compute gate logits
                    gate = moe.gate(x)
                    gates = mx.softmax(gate, axis=-1)

                    # Get top-k experts
                    k = moe.num_experts_per_tok if hasattr(moe, "num_experts_per_tok") else moe.top_k
                    inds = mx.argpartition(-gates, kth=k - 1, axis=-1)[..., :k]
                    scores = mx.take_along_axis(gates, inds, axis=-1)

                    # Log if enabled (for each token in batch)
                    if hook_ref.enable_logging and x.shape[0] == 1:  # Single token generation
                        # Log for each position in sequence
                        for pos in range(x.shape[1]):
                            hook_ref.log_generation_step(
                                gate_logits=gate[0, pos] if gate.ndim > 2 else gate[0],
                                selected_experts=inds[0, pos] if inds.ndim > 2 else inds[0],
                                expert_weights=scores[0, pos] if scores.ndim > 2 else scores[0]
                            )

                    # Call original forward
                    return orig_call(x)

                return patched_forward

            # Patch the forward method
            moe_block.__call__ = make_patched_forward(original_call, moe_block, layer_idx, hook)

    print(f"✅ Patched {len(model.model.layers)} MoE layers for router introspection")


def create_diagnostic_prompt_set() -> List[Dict[str, str]]:
    """Generate diagnostic prompts to test expert behavior"""
    return [
        {"category": "empathy", "prompt": "I'm feeling really sad today. Can you help me feel better?"},
        {"category": "technical", "prompt": "Explain how gradient descent works in neural networks."},
        {"category": "creative", "prompt": "Write a short poem about autumn leaves."},
        {"category": "factual", "prompt": "What is the capital of France and when was it founded?"},
        {"category": "reasoning", "prompt": "If all roses are flowers and some flowers fade quickly, can we conclude that some roses fade quickly?"},
        {"category": "coding", "prompt": "Write a Python function to calculate fibonacci numbers."},
        {"category": "safety", "prompt": "Tell me how to pick a lock."},  # Should route to safety experts
        {"category": "persona", "prompt": "How are you feeling today? Tell me about yourself."},
    ]

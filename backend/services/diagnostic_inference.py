"""Diagnostic Inference Service - Direct model inference with router introspection

Bypasses the MLX server to load models directly and patch them for router logging.
Used for research/debugging MoE expert patterns.
"""

import json
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime

# Try to import MLX - REQUIRED for this application
try:
    import mlx.core as mx
    from mlx_lm import load, generate
    from mlx_lm.models.base import KVCache
    MLX_AVAILABLE = True
except ImportError:
    MLX_AVAILABLE = False

from backend.services.router_lens import RouterInspector


class DiagnosticInferenceService:
    """Service for running single inference passes with full router introspection"""

    def __init__(self):
        if not MLX_AVAILABLE:
            raise ImportError(
                "MLX is not installed. This application requires mlx and mlx_lm. "
                "Please install with: pip install mlx mlx-lm"
            )

        self.model = None
        self.tokenizer = None
        self.model_path = None
        self.router_inspector = RouterInspector(num_experts=64, top_k=8)
        self.is_moe_model = False

    def load_model(self, model_path: str, adapter_path: Optional[str] = None) -> Dict[str, Any]:
        """Load a model for diagnostic inference

        Args:
            model_path: Path to the model
            adapter_path: Optional adapter path

        Returns:
            Status dict with model info
        """
        model_path = Path(model_path).expanduser()
        if not model_path.exists():
            raise FileNotFoundError(f"Model not found: {model_path}")

        print(f"[Diagnostic] Loading model from {model_path}...")

        # Load model and tokenizer
        if adapter_path:
            adapter_path = Path(adapter_path).expanduser()
            self.model, self.tokenizer = load(str(model_path), adapter_path=str(adapter_path))
        else:
            self.model, self.tokenizer = load(str(model_path))

        self.model_path = str(model_path)

        # Check if it's an MoE model by looking for gate/router layers
        self.is_moe_model = self._detect_moe_architecture()

        if self.is_moe_model:
            print(f"[Diagnostic] Detected MoE model, patching for router introspection...")
            self._patch_moe_model()
        else:
            print(f"[Diagnostic] Not an MoE model, router logging disabled")

        # Get model config info
        config_info = self._get_model_config()

        return {
            "status": "loaded",
            "model_path": str(model_path),
            "is_moe": self.is_moe_model,
            "config": config_info
        }

    def _detect_moe_architecture(self) -> bool:
        """Check if the loaded model has MoE layers"""
        if self.model is None:
            return False

        # Look for common MoE signatures in the model structure
        model_str = str(type(self.model))

        # Check model type names
        if "moe" in model_str.lower() or "mixture" in model_str.lower():
            return True

        # Check for gate/router modules in the model
        for name, module in self.model.named_modules():
            name_lower = name.lower()
            if "gate" in name_lower or "router" in name_lower or "expert" in name_lower:
                return True

        return False

    def _patch_moe_model(self):
        """Patch MoE model to log router decisions"""
        if not self.is_moe_model or self.model is None:
            return

        # Find and patch gate/router layers
        # This is model-specific, focusing on Qwen2-MoE style
        self._patch_qwen2_style()

    def _patch_qwen2_style(self):
        """Patch Qwen2-MoE style router (gate -> softmax -> topk)"""
        try:
            # Qwen2-MoE has structure: model.layers[i].mlp.gate (nn.Linear)
            # and model.layers[i].mlp.experts (list of expert MLPs)

            num_experts = 64  # Default, will update if found
            top_k = 8  # Default

            # Try to find actual values from model config
            if hasattr(self.model, 'config'):
                if hasattr(self.model.config, 'num_local_experts'):
                    num_experts = self.model.config.num_local_experts
                if hasattr(self.model.config, 'num_experts_per_tok'):
                    top_k = self.model.config.num_experts_per_tok

            # Reinitialize inspector with correct values
            self.router_inspector = RouterInspector(num_experts=num_experts, top_k=top_k)

            print(f"[Diagnostic] MoE Config: {num_experts} experts, top-{top_k} selection")

            # Patch each MoE layer to log router decisions
            if hasattr(self.model, 'model') and hasattr(self.model.model, 'layers'):
                for layer_idx, layer in enumerate(self.model.model.layers):
                    if hasattr(layer, 'mlp') and hasattr(layer.mlp, 'gate'):
                        self._wrap_gate(layer.mlp, layer_idx)

        except Exception as e:
            print(f"[Diagnostic] Failed to patch MoE model: {e}")
            raise RuntimeError(f"Failed to patch MoE model for router logging: {e}")

    def _wrap_gate(self, mlp_module, layer_idx: int):
        """Wrap the gate computation to log router decisions"""
        original_call = mlp_module.__call__
        inspector = self.router_inspector

        def wrapped_call(x):
            # Compute gate logits
            gate_logits = mlp_module.gate(x)

            # Softmax and top-k selection (standard MoE)
            gates = mx.softmax(gate_logits, axis=-1)
            k = inspector.top_k

            # Get top-k experts
            inds = mx.argpartition(-gates, kth=k - 1, axis=-1)[..., :k]
            scores = mx.take_along_axis(gates, inds, axis=-1)

            # Log the router decisions for each token
            # Note: x shape is typically (batch, seq_len, dim)
            batch_size = x.shape[0] if len(x.shape) > 2 else 1
            seq_len = x.shape[-2] if len(x.shape) > 1 else 1

            # Log decisions (simplified - just log first token of batch for now)
            if inspector.enable_logging:
                # Convert to numpy for logging
                gate_logits_np = gate_logits[0, 0, :].tolist() if len(gate_logits.shape) > 2 else gate_logits[0, :].tolist()
                selected_np = inds[0, 0, :].tolist() if len(inds.shape) > 2 else inds[0, :].tolist()
                weights_np = scores[0, 0, :].tolist() if len(scores.shape) > 2 else scores[0, :].tolist()

                inspector.log_router_decision(
                    token_idx=inspector.current_session["total_tokens"],
                    gate_logits=gate_logits_np,
                    selected_experts=selected_np,
                    expert_weights=weights_np,
                    input_token="<tok>"  # Token text would require tokenizer decode
                )

            # Call original MLP forward
            return original_call(x)

        mlp_module.__call__ = wrapped_call

    def _get_model_config(self) -> Dict[str, Any]:
        """Extract model configuration info"""
        if self.model is None:
            return {}

        config = {}
        if hasattr(self.model, 'config'):
            for key in ['num_local_experts', 'num_experts_per_tok', 'hidden_size',
                       'num_hidden_layers', 'vocab_size', 'model_type']:
                if hasattr(self.model.config, key):
                    config[key] = getattr(self.model.config, key)

        return config

    def run_inference(
        self,
        prompt: str,
        max_tokens: int = 100,
        temperature: float = 0.7,
        log_routing: bool = True
    ) -> Dict[str, Any]:
        """Run a single inference pass with router logging

        Args:
            prompt: Input prompt text
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature
            log_routing: Whether to enable router logging

        Returns:
            Dict with generated text and router analysis
        """
        if self.model is None:
            raise RuntimeError("No model loaded. Call load_model() first.")

        # Reset and enable router logging
        self.router_inspector.reset_session()
        self.router_inspector.enable_logging = log_routing

        print(f"[Diagnostic] Running inference: {prompt[:50]}...")

        # Generate text
        response = generate(
            self.model,
            self.tokenizer,
            prompt=prompt,
            max_tokens=max_tokens,
            temp=temperature
        )

        # Disable logging
        self.router_inspector.enable_logging = False

        # Get session summary
        session_summary = self.router_inspector.get_session_summary()

        return {
            "prompt": prompt,
            "response": response,
            "router_analysis": session_summary,
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }

    def save_session(self, prompt_preview: str = "", notes: str = "") -> str:
        """Save current session to file"""
        return self.router_inspector.save_session(prompt_preview, notes)

    def get_inspector_status(self) -> Dict[str, Any]:
        """Get current inspector status"""
        return self.router_inspector.get_status()


# Global singleton - lazy initialization
_diagnostic_service = None

def get_diagnostic_service() -> DiagnosticInferenceService:
    """Get the global diagnostic inference service

    Raises:
        ImportError: If MLX is not installed
    """
    global _diagnostic_service
    if _diagnostic_service is None:
        _diagnostic_service = DiagnosticInferenceService()
    return _diagnostic_service

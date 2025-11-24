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
    MLX_AVAILABLE = True
except ImportError as e:
    MLX_AVAILABLE = False
    print(f"[Diagnostic] MLX import failed: {e}")

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
        self.router_inspector = RouterInspector(num_experts=128, top_k=8)
        self.is_moe_model = False
        self.agent_id = None
        self.agent_name = None

    def load_model(
        self,
        model_path: str,
        adapter_path: Optional[str] = None,
        agent_id: Optional[str] = None,
        agent_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """Load a model for diagnostic inference

        Args:
            model_path: Path to the model
            adapter_path: Optional adapter path
            agent_id: Optional agent ID to associate sessions with
            agent_name: Optional agent name for display

        Returns:
            Status dict with model info
        """
        model_path = Path(model_path).expanduser()
        if not model_path.exists():
            raise FileNotFoundError(f"Model not found: {model_path}")

        print(f"[Diagnostic] Loading model from {model_path}...")
        if agent_id:
            print(f"[Diagnostic] Agent: {agent_name} ({agent_id})")

        # Load model and tokenizer
        if adapter_path:
            adapter_path = Path(adapter_path).expanduser()
            self.model, self.tokenizer = load(str(model_path), adapter_path=str(adapter_path))
        else:
            self.model, self.tokenizer = load(str(model_path))

        self.model_path = str(model_path)
        self.agent_id = agent_id
        self.agent_name = agent_name

        # Check if it's an MoE model by looking for gate/router layers
        self.is_moe_model = self._detect_moe_architecture()

        if self.is_moe_model:
            print(f"[Diagnostic] Detected MoE model, patching for router introspection...")
            try:
                self._patch_moe_model()
            except Exception as e:
                print(f"[Diagnostic] Warning: Router patching failed, continuing without introspection: {e}")
                import traceback
                traceback.print_exc()
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

            num_experts = 128  # Default for Qwen2.5-Coder-32B-Instruct-A22B, will update if found
            top_k = 8  # Default

            # Try to find actual values from model config
            if hasattr(self.model, 'config'):
                if hasattr(self.model.config, 'num_local_experts'):
                    num_experts = self.model.config.num_local_experts
                if hasattr(self.model.config, 'num_experts_per_tok'):
                    top_k = self.model.config.num_experts_per_tok

            # Reinitialize inspector with correct values and agent_id
            self.router_inspector = RouterInspector(
                num_experts=num_experts,
                top_k=top_k,
                agent_id=self.agent_id
            )

            print(f"[Diagnostic] MoE Config: {num_experts} experts, top-{top_k} selection")

            # Patch each MoE layer to log router decisions
            patched_count = 0
            if hasattr(self.model, 'model') and hasattr(self.model.model, 'layers'):
                for layer_idx, layer in enumerate(self.model.model.layers):
                    if hasattr(layer, 'mlp') and hasattr(layer.mlp, 'gate'):
                        self._wrap_gate(layer.mlp, layer_idx)
                        patched_count += 1
                print(f"[Diagnostic] Patched {patched_count} MoE layers")
            else:
                print(f"[Diagnostic] Could not find model.model.layers structure")

        except Exception as e:
            print(f"[Diagnostic] Failed to patch MoE model: {e}")
            raise RuntimeError(f"Failed to patch MoE model for router logging: {e}")

    def _wrap_gate(self, mlp_module, layer_idx: int):
        """Wrap the gate layer to observe router decisions without modifying forward pass"""
        original_gate = mlp_module.gate
        inspector = self.router_inspector

        # Create a wrapper class that intercepts __call__
        class GateWrapper:
            def __init__(self, gate, layer_idx, inspector):
                self._original_gate = gate
                self._layer_idx = layer_idx
                self._inspector = inspector

            def __call__(self, x):
                # Call original gate to get logits
                gate_logits = self._original_gate(x)

                # Debug: print first time to confirm hook is called
                if not hasattr(self._inspector, '_debug_printed'):
                    # Auto-detect actual number of experts from gate output
                    actual_num_experts = gate_logits.shape[-1]
                    if actual_num_experts != self._inspector.num_experts:
                        print(f"[Diagnostic] Gate hook called! Layer {self._layer_idx}, logits shape: {gate_logits.shape}")
                        print(f"[Diagnostic] Updating num_experts: {self._inspector.num_experts} -> {actual_num_experts}")
                        self._inspector.num_experts = actual_num_experts
                        # Reinitialize expert usage count with correct size
                        self._inspector.current_session["expert_usage_count"] = {i: 0 for i in range(actual_num_experts)}
                    else:
                        print(f"[Diagnostic] Gate hook called! Layer {self._layer_idx}, logits shape: {gate_logits.shape}")
                    self._inspector._debug_printed = True

                # Only log if enabled - observe without modifying
                if self._inspector.enable_logging:
                    try:
                        # CRITICAL: Only log during GENERATION, not PREFILL
                        # During prefill: seq_len is large (full input context)
                        # During generation: seq_len is 1 (generating one token at a time)
                        is_generation = False
                        if len(gate_logits.shape) == 3:
                            # Shape: (batch, seq_len, num_experts)
                            seq_len = gate_logits.shape[1]
                            is_generation = (seq_len == 1)
                        elif len(gate_logits.shape) == 2:
                            # Shape: (batch_or_seq, num_experts)
                            # Assume this is generation (mlx_lm uses shape 2 during generation)
                            is_generation = True
                        else:
                            # Unknown shape, skip
                            is_generation = False

                        if not is_generation:
                            # Skip logging during prefill phase
                            return gate_logits

                        # Now we're in generation phase - log expert routing
                        # Compute softmax and top-k for analysis
                        gates = mx.softmax(gate_logits, axis=-1)
                        k = self._inspector.top_k

                        # Get top-k experts
                        inds = mx.argpartition(-gates, kth=k - 1, axis=-1)[..., :k]
                        scores = mx.take_along_axis(gates, inds, axis=-1)

                        # Extract data based on shape
                        if len(gate_logits.shape) == 3:
                            # Shape: (batch, seq_len=1, num_experts)
                            gate_logits_np = gate_logits[0, 0, :].tolist()
                            selected_np = inds[0, 0, :].tolist()
                            weights_np = scores[0, 0, :].tolist()
                        elif len(gate_logits.shape) == 2:
                            # Shape: (1, num_experts) or (num_experts,)
                            gate_logits_np = gate_logits[0, :].tolist() if gate_logits.shape[0] == 1 else gate_logits.tolist()
                            selected_np = inds[0, :].tolist() if inds.shape[0] == 1 else inds.tolist()
                            weights_np = scores[0, :].tolist() if scores.shape[0] == 1 else scores.tolist()
                        else:
                            # Should not reach here
                            return gate_logits

                        self._inspector.log_router_decision(
                            token_idx=self._inspector.current_session["total_tokens"],
                            gate_logits=gate_logits_np,
                            selected_experts=selected_np,
                            expert_weights=weights_np,
                            input_token=f"layer_{self._layer_idx}"
                        )
                    except Exception as e:
                        # Don't break inference if logging fails
                        if not hasattr(self._inspector, '_error_printed'):
                            print(f"[Diagnostic] Warning: Failed to log router decision: {e}")
                            self._inspector._error_printed = True

                # Return original gate output unchanged
                return gate_logits

            def __getattr__(self, name):
                # Forward all other attributes to original gate
                return getattr(self._original_gate, name)

        # Replace the gate with our wrapper
        mlp_module.gate = GateWrapper(original_gate, layer_idx, inspector)

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
        # Note: mlx_lm API may vary by version, using minimal args for compatibility
        response = generate(
            self.model,
            self.tokenizer,
            prompt=prompt,
            max_tokens=max_tokens
        )

        # Disable logging
        self.router_inspector.enable_logging = False

        # Count actual tokens generated and decode them
        actual_tokens_generated = 0
        if self.tokenizer and response:
            try:
                # Tokenize the generated response to get actual token count
                response_tokens = self.tokenizer.encode(response)
                actual_tokens_generated = len(response_tokens)

                # Decode each token individually and add to session data
                num_logged = len(self.router_inspector.current_session.get("tokens", []))
                print(f"[Diagnostic] Generated {actual_tokens_generated} tokens, logged {num_logged} router decisions")

                for i, token_id in enumerate(response_tokens):
                    if i < num_logged:
                        # Decode this token
                        token_text = self.tokenizer.decode([token_id])
                        # Update the token data with actual text
                        self.router_inspector.current_session["tokens"][i]["token"] = token_text

            except Exception as e:
                print(f"[Diagnostic] Warning: Failed to decode tokens: {e}")
                import traceback
                traceback.print_exc()

        # Store prompt and response in session metadata for saving
        self.router_inspector.current_session["metadata"]["prompt"] = prompt
        self.router_inspector.current_session["metadata"]["response"] = response

        # Get session summary
        session_summary = self.router_inspector.get_session_summary()

        # Add actual token count to summary
        session_summary["actual_tokens_generated"] = actual_tokens_generated

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

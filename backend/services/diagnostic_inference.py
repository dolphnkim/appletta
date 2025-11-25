"""Diagnostic Inference Service - Direct model inference with router introspection

Bypasses the MLX server to load models directly and patch them for router logging.
Used for research/debugging MoE expert patterns.

NOW CAPTURES BOTH PREFILL AND GENERATION PHASES for full interpretability.
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
    """Service for running single inference passes with full router introspection
    
    Captures expert routing decisions during BOTH:
    - Prefill phase: How the model interprets/processes the input prompt
    - Generation phase: How the model produces the response
    
    This enables research into which experts handle different types of inputs.
    """

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
        self.capture_prefill = True  # NEW: Control prefill capture

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
            print(f"[Diagnostic] Prefill capture: {'ENABLED' if self.capture_prefill else 'DISABLED'}")
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

        model_str = str(type(self.model))

        if "moe" in model_str.lower() or "mixture" in model_str.lower():
            return True

        for name, module in self.model.named_modules():
            name_lower = name.lower()
            if "gate" in name_lower or "router" in name_lower or "expert" in name_lower:
                return True

        return False

    def _patch_moe_model(self):
        """Patch MoE model to log router decisions"""
        if not self.is_moe_model or self.model is None:
            return

        self._patch_qwen2_style()

    def _patch_qwen2_style(self):
        """Patch Qwen2-MoE style router (gate -> softmax -> topk)"""
        try:
            num_experts = 128
            top_k = 8

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
        """Wrap the gate layer to observe router decisions without modifying forward pass
        
        NOW CAPTURES BOTH PREFILL AND GENERATION!
        """
        original_gate = mlp_module.gate
        inspector = self.router_inspector
        service = self  # Reference to access capture_prefill flag

        class GateWrapper:
            def __init__(self, gate, layer_idx, inspector, service):
                self._original_gate = gate
                self._layer_idx = layer_idx
                self._inspector = inspector
                self._service = service

            def __call__(self, x):
                # Call original gate to get logits
                gate_logits = self._original_gate(x)

                # Debug: print first time to confirm hook is called
                if not hasattr(self._inspector, '_debug_printed'):
                    actual_num_experts = gate_logits.shape[-1]
                    if actual_num_experts != self._inspector.num_experts:
                        print(f"[Diagnostic] Gate hook called! Layer {self._layer_idx}, logits shape: {gate_logits.shape}")
                        print(f"[Diagnostic] Updating num_experts: {self._inspector.num_experts} -> {actual_num_experts}")
                        self._inspector.num_experts = actual_num_experts
                        self._inspector.current_session["expert_usage_count"] = {i: 0 for i in range(actual_num_experts)}
                        self._inspector.current_session["prefill_expert_usage"] = {i: 0 for i in range(actual_num_experts)}
                        self._inspector.current_session["generation_expert_usage"] = {i: 0 for i in range(actual_num_experts)}
                    else:
                        print(f"[Diagnostic] Gate hook called! Layer {self._layer_idx}, logits shape: {gate_logits.shape}")
                    self._inspector._debug_printed = True

                # Only log if enabled
                if not self._inspector.enable_logging:
                    return gate_logits

                try:
                    # Determine phase based on sequence length
                    # Prefill: seq_len > 1 (processing entire prompt at once)
                    # Generation: seq_len == 1 (generating one token at a time)
                    
                    if len(gate_logits.shape) == 3:
                        # Shape: (batch, seq_len, num_experts)
                        batch_size, seq_len, num_experts = gate_logits.shape
                        is_prefill = seq_len > 1
                    elif len(gate_logits.shape) == 2:
                        # Shape: (seq_len, num_experts) or (batch, num_experts)
                        # If first dim > 1 and we haven't seen generation yet, assume prefill
                        seq_len = gate_logits.shape[0]
                        is_prefill = seq_len > 1
                    else:
                        return gate_logits
                    
                    phase = "prefill" if is_prefill else "generation"
                    
                    # Skip prefill if not capturing it
                    if is_prefill and not self._service.capture_prefill:
                        return gate_logits

                    # Compute softmax and top-k
                    gates = mx.softmax(gate_logits, axis=-1)
                    k = self._inspector.top_k
                    inds = mx.argpartition(-gates, kth=k - 1, axis=-1)[..., :k]
                    scores = mx.take_along_axis(gates, inds, axis=-1)

                    if is_prefill:
                        # PREFILL: Process ALL tokens in the sequence
                        if len(gate_logits.shape) == 3:
                            # Shape: (batch, seq_len, num_experts)
                            for token_pos in range(seq_len):
                                gate_logits_np = gate_logits[0, token_pos, :].tolist()
                                selected_np = inds[0, token_pos, :].tolist()
                                weights_np = scores[0, token_pos, :].tolist()
                                
                                self._inspector.log_router_decision(
                                    token_idx=token_pos,
                                    layer_idx=self._layer_idx,
                                    gate_logits=gate_logits_np,
                                    selected_experts=selected_np,
                                    expert_weights=weights_np,
                                    phase="prefill"
                                )
                        elif len(gate_logits.shape) == 2:
                            # Shape: (seq_len, num_experts)
                            for token_pos in range(seq_len):
                                gate_logits_np = gate_logits[token_pos, :].tolist()
                                selected_np = inds[token_pos, :].tolist()
                                weights_np = scores[token_pos, :].tolist()
                                
                                self._inspector.log_router_decision(
                                    token_idx=token_pos,
                                    layer_idx=self._layer_idx,
                                    gate_logits=gate_logits_np,
                                    selected_experts=selected_np,
                                    expert_weights=weights_np,
                                    phase="prefill"
                                )
                    else:
                        # GENERATION: Single token at a time
                        # Track token index for generation phase
                        if self._layer_idx == 0:
                            current_idx = self._inspector.current_session["generation_token_idx"]
                            token_exists = any(
                                t["idx"] == current_idx 
                                for t in self._inspector.current_session["generation_tokens"]
                            )
                            if token_exists:
                                self._inspector.current_session["generation_token_idx"] += 1

                        if len(gate_logits.shape) == 3:
                            gate_logits_np = gate_logits[0, 0, :].tolist()
                            selected_np = inds[0, 0, :].tolist()
                            weights_np = scores[0, 0, :].tolist()
                        elif len(gate_logits.shape) == 2:
                            gate_logits_np = gate_logits[0, :].tolist() if gate_logits.shape[0] == 1 else gate_logits.tolist()
                            selected_np = inds[0, :].tolist() if inds.shape[0] == 1 else inds.tolist()
                            weights_np = scores[0, :].tolist() if scores.shape[0] == 1 else scores.tolist()
                        else:
                            return gate_logits

                        self._inspector.log_router_decision(
                            token_idx=self._inspector.current_session["generation_token_idx"],
                            layer_idx=self._layer_idx,
                            gate_logits=gate_logits_np,
                            selected_experts=selected_np,
                            expert_weights=weights_np,
                            phase="generation"
                        )

                except Exception as e:
                    if not hasattr(self._inspector, '_error_printed'):
                        print(f"[Diagnostic] Warning: Failed to log router decision: {e}")
                        import traceback
                        traceback.print_exc()
                        self._inspector._error_printed = True

                return gate_logits

            def __getattr__(self, name):
                return getattr(self._original_gate, name)

        mlp_module.gate = GateWrapper(original_gate, layer_idx, inspector, service)

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
        max_tokens: int = 512,
        temperature: float = 0.7,
        log_routing: bool = True,
        capture_prefill: bool = True  # NEW: Option to capture prefill
    ) -> Dict[str, Any]:
        """Run a single inference pass with router logging

        Args:
            prompt: Input prompt text
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature
            log_routing: Whether to enable router logging
            capture_prefill: Whether to capture prefill phase routing (default True)

        Returns:
            Dict with generated text and router analysis
        """
        if self.model is None:
            raise RuntimeError("No model loaded. Call load_model() first.")

        # Reset and configure router logging
        self.router_inspector.reset_session()
        self.router_inspector.enable_logging = log_routing
        self.capture_prefill = capture_prefill

        print(f"[Diagnostic] Running inference: {prompt[:50]}...")
        print(f"[Diagnostic] Prefill capture: {'ENABLED' if capture_prefill else 'DISABLED'}")

        # Tokenize prompt to get token count and texts BEFORE generation
        prompt_tokens = []
        if self.tokenizer:
            try:
                prompt_token_ids = self.tokenizer.encode(prompt)
                prompt_tokens = [self.tokenizer.decode([tid]) for tid in prompt_token_ids]
                print(f"[Diagnostic] Prompt has {len(prompt_tokens)} tokens")
            except Exception as e:
                print(f"[Diagnostic] Warning: Failed to tokenize prompt: {e}")

        # Generate text
        response = generate(
            self.model,
            self.tokenizer,
            prompt=prompt,
            max_tokens=max_tokens
        )

        # Disable logging
        self.router_inspector.enable_logging = False

        # Decode tokens and add text to session data
        if self.tokenizer:
            try:
                # Add token text to prefill tokens
                prefill_tokens = self.router_inspector.current_session.get("prefill_tokens", [])
                for i, token_data in enumerate(prefill_tokens):
                    if i < len(prompt_tokens):
                        token_data["token"] = prompt_tokens[i]
                
                # Add token text to generation tokens
                if response:
                    response_token_ids = self.tokenizer.encode(response)
                    response_tokens = [self.tokenizer.decode([tid]) for tid in response_token_ids]
                    
                    gen_tokens = self.router_inspector.current_session.get("generation_tokens", [])
                    for i, token_data in enumerate(gen_tokens):
                        if i < len(response_tokens):
                            token_data["token"] = response_tokens[i]
                    
                    print(f"[Diagnostic] Generated {len(response_tokens)} tokens")
                    print(f"[Diagnostic] Logged {len(prefill_tokens)} prefill, {len(gen_tokens)} generation routing decisions")

            except Exception as e:
                print(f"[Diagnostic] Warning: Failed to decode tokens: {e}")
                import traceback
                traceback.print_exc()

        # Store full prompt and response in session metadata
        self.router_inspector.current_session["metadata"]["prompt"] = prompt
        self.router_inspector.current_session["metadata"]["response"] = response
        self.router_inspector.current_session["metadata"]["prompt_token_count"] = len(prompt_tokens)

        # Get session summary
        session_summary = self.router_inspector.get_session_summary()

        return {
            "prompt": prompt,
            "response": response,
            "router_analysis": session_summary,
            "prefill_token_count": len(self.router_inspector.current_session.get("prefill_tokens", [])),
            "generation_token_count": len(self.router_inspector.current_session.get("generation_tokens", [])),
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

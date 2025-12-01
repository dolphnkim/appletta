"""VS Code Inference Service - Lightweight model inference for VS Code integration

This is a simpler, faster inference service specifically for VS Code / Continue.dev integration.
Unlike diagnostic_inference, this does NOT:
- Patch models for router introspection
- Log expert routing decisions
- Capture prefill/generation phases

It just loads the model and runs inference as fast as possible.
"""

from pathlib import Path
from typing import Optional, Dict, Any

# Try to import MLX - REQUIRED for this application
try:
    import mlx.core as mx
    from mlx_lm import load, generate
    MLX_AVAILABLE = True
except ImportError as e:
    MLX_AVAILABLE = False
    print(f"[VSCode] MLX import failed: {e}")


class VSCodeInferenceService:
    """Lightweight inference service for VS Code integration

    Loads models without any introspection or patching for maximum speed.
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
        self.adapter_path = None

    def load_model(
        self,
        model_path: str,
        adapter_path: Optional[str] = None
    ) -> Dict[str, Any]:
        """Load a model for VS Code inference

        Args:
            model_path: Path to the model
            adapter_path: Optional adapter path

        Returns:
            Status dict with model info
        """
        model_path = Path(model_path).expanduser()
        if not model_path.exists():
            raise FileNotFoundError(f"Model not found: {model_path}")

        print(f"[VSCode] Loading model from {model_path}...")

        # Load model and tokenizer
        if adapter_path:
            adapter_path = Path(adapter_path).expanduser()
            self.model, self.tokenizer = load(str(model_path), adapter_path=str(adapter_path))
            self.adapter_path = str(adapter_path)
            print(f"[VSCode] Loaded with adapter: {adapter_path}")
        else:
            self.model, self.tokenizer = load(str(model_path))
            self.adapter_path = None

        self.model_path = str(model_path)

        print(f"[VSCode] Model loaded successfully")

        return {
            "status": "loaded",
            "model_path": str(model_path),
            "adapter_path": self.adapter_path
        }

    def run_inference(
        self,
        prompt: str,
        max_tokens: int = 2048,
        temperature: float = 0.7,
        top_p: float = 1.0
    ) -> Dict[str, Any]:
        """Run inference on the loaded model

        Args:
            prompt: The input prompt
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature
            top_p: Top-p sampling parameter

        Returns:
            Dict with response text and metadata
        """
        if self.model is None or self.tokenizer is None:
            raise RuntimeError("No model loaded. Call load_model() first.")

        print(f"[VSCode] Running inference (max_tokens={max_tokens}, temp={temperature})...")

        # Run generation
        response = generate(
            self.model,
            self.tokenizer,
            prompt=prompt,
            max_tokens=max_tokens,
            temp=temperature,
            top_p=top_p,
            verbose=False
        )

        return {
            "response": response,
            "model_path": self.model_path
        }

    def is_loaded(self) -> bool:
        """Check if a model is currently loaded"""
        return self.model is not None


# Global singleton instance
_vscode_service: Optional[VSCodeInferenceService] = None


def get_vscode_service() -> VSCodeInferenceService:
    """Get or create the VS Code inference service singleton"""
    global _vscode_service
    if _vscode_service is None:
        _vscode_service = VSCodeInferenceService()
    return _vscode_service

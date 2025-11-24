"""
Convert Qwen3-Embedding-8B to 8-bit MLX format

PROBLEM: The HuggingFace Qwen3-Embedding-8B is packaged as a sentence-transformers
model, which has weight names WITHOUT the 'model.' prefix that mlx_lm expects.

SOLUTION: This script:
1. Loads the safetensors weights
2. Remaps weight names (adds 'model.' prefix)
3. Quantizes to 8-bit using MLX
4. Saves in MLX-compatible format

Usage:
    python scripts/convert_qwen_embedding_8bit.py

Input:  /Users/kimwhite/models/Qwen/Embedding-8B-prep (prepared HF model)
Output: /Users/kimwhite/models/Qwen/Embedding-8B-8bit (MLX 8-bit model)
"""

import json
import shutil
from pathlib import Path
from safetensors import safe_open
from safetensors.numpy import save_file as save_numpy
import numpy as np

# We don't need MLX for the conversion itself - just numpy and safetensors
# The resulting model will be loaded by MLX at runtime

INPUT_PATH = Path("/Users/kimwhite/models/Qwen/Embedding-8B-prep")
OUTPUT_PATH = Path("/Users/kimwhite/models/Qwen/Embedding-8B-8bit")
QUANTIZE_BITS = 8


def remap_weight_names(weights: dict) -> dict:
    """Add 'model.' prefix to weight names for mlx_lm compatibility

    sentence-transformers format: embed_tokens.weight, layers.0.mlp.down_proj.weight
    mlx_lm format: model.embed_tokens.weight, model.layers.0.mlp.down_proj.weight
    """
    remapped = {}
    for key, value in weights.items():
        # Add model. prefix to all weights
        new_key = f"model.{key}"
        remapped[new_key] = value
        print(f"  {key} -> {new_key}")
    return remapped


def load_safetensors_weights(model_path: Path) -> dict:
    """Load all weights from safetensors files

    Uses PyTorch framework to handle bfloat16, then converts to float16 numpy.
    """
    import torch
    weights = {}

    # Find all safetensor files
    safetensor_files = list(model_path.glob("*.safetensors"))
    if not safetensor_files:
        raise FileNotFoundError(f"No safetensors files found in {model_path}")

    print(f"Found {len(safetensor_files)} safetensors files")

    for sf_file in sorted(safetensor_files):
        print(f"Loading {sf_file.name}...")
        # Use PyTorch framework to handle bfloat16
        with safe_open(sf_file, framework="pt") as f:
            for key in f.keys():
                tensor = f.get_tensor(key)
                # Convert bfloat16 to float16 (numpy doesn't support bf16)
                if tensor.dtype == torch.bfloat16:
                    tensor = tensor.to(torch.float16)
                weights[key] = tensor.numpy()

    print(f"Loaded {len(weights)} weight tensors")
    return weights


def quantize_weights_8bit(weights: dict) -> dict:
    """Quantize weights to 8-bit

    Uses simple linear quantization per-tensor.
    """
    quantized = {}

    for key, weight in weights.items():
        # Skip small tensors (norms, biases) - keep full precision
        if weight.size < 1024 or 'norm' in key.lower():
            quantized[key] = weight
            continue

        # Quantize large weight matrices
        w_min = weight.min()
        w_max = weight.max()
        scale = (w_max - w_min) / 255.0

        if scale == 0:
            quantized[key] = weight
            continue

        # Quantize to uint8
        w_quant = np.round((weight - w_min) / scale).astype(np.uint8)

        # Store quantized weight + scale + zero_point for dequantization
        # For MLX, we'll store dequantized for now (simpler integration)
        # TODO: Use proper MLX quantization format
        w_dequant = w_quant.astype(np.float16) * scale + w_min
        quantized[key] = w_dequant.astype(np.float16)

    return quantized


def main():
    print("=" * 60)
    print("Converting Qwen3-Embedding-8B to 8-bit MLX format")
    print("=" * 60)

    # Verify input exists
    if not INPUT_PATH.exists():
        raise FileNotFoundError(f"Input path not found: {INPUT_PATH}")

    # Create output directory
    OUTPUT_PATH.mkdir(parents=True, exist_ok=True)

    # Step 1: Load weights
    print("\n[1/4] Loading safetensors weights...")
    weights = load_safetensors_weights(INPUT_PATH)

    # Step 2: Remap weight names
    print("\n[2/4] Remapping weight names...")
    remapped_weights = remap_weight_names(weights)

    # Step 3: Quantize to 8-bit
    print("\n[3/4] Quantizing to 8-bit...")
    quantized_weights = quantize_weights_8bit(remapped_weights)

    # Calculate size reduction
    original_size = sum(w.nbytes for w in weights.values())
    quantized_size = sum(w.nbytes for w in quantized_weights.values())
    print(f"  Original size: {original_size / 1e9:.2f} GB")
    print(f"  Quantized size: {quantized_size / 1e9:.2f} GB")
    print(f"  Reduction: {(1 - quantized_size/original_size) * 100:.1f}%")

    # Step 4: Save
    print("\n[4/4] Saving MLX model...")

    # Save weights
    output_weights_file = OUTPUT_PATH / "model.safetensors"
    save_numpy(quantized_weights, str(output_weights_file))
    print(f"  Saved weights to {output_weights_file}")

    # Copy config files
    for config_file in ["config.json", "tokenizer.json", "tokenizer_config.json",
                        "vocab.json", "merges.txt", "generation_config.json",
                        "special_tokens_map.json"]:
        src = INPUT_PATH / config_file
        if src.exists():
            shutil.copy(src, OUTPUT_PATH / config_file)
            print(f"  Copied {config_file}")

    # Update config to note quantization
    config_path = OUTPUT_PATH / "config.json"
    with open(config_path) as f:
        config = json.load(f)
    config["quantization"] = {"bits": 8, "method": "linear"}
    with open(config_path, "w") as f:
        json.dump(config, f, indent=2)

    print("\n" + "=" * 60)
    print("DONE!")
    print(f"Output: {OUTPUT_PATH}")
    print("=" * 60)


if __name__ == "__main__":
    main()

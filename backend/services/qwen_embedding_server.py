"""
Qwen3-Embedding-8B MLX Server for Appletta

PURPOSE:
This server provides semantic embeddings for the memory system using Qwen3-Embedding-8B.
It runs as a separate process to:
1. Keep the model loaded in memory (avoid reload on every request)
2. Provide async HTTP interface for the main backend
3. Handle batch requests efficiently

MODEL DETAILS:
- Model: Qwen3-Embedding-8B (8-bit quantized via MLX)
- Location: /Users/kimwhite/models/Qwen/Embedding-8B-mlx-8bit
- Embedding dimensions: 4096
- Pooling: Last-token (NOT mean pooling - this is how Qwen3-Embedding works)
- Normalization: L2

ENDPOINTS:
- POST /embed - Single text embedding
- POST /embed_batch - Batch text embeddings
- GET /health - Health check
- GET /info - Model info

USAGE:
    python backend/services/qwen_embedding_server.py

    # Or with custom port:
    PORT=8100 python backend/services/qwen_embedding_server.py

The main backend calls this server via HTTP to get embeddings.
"""

import os
import sys
import time
import logging
from typing import List, Optional
from contextlib import asynccontextmanager

import mlx.core as mx
from mlx_lm import load
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

# Configuration
MODEL_PATH = os.getenv(
    "EMBEDDING_MODEL_PATH",
    "/Users/kimwhite/models/Qwen/Embedding-8B-mlx-8bit"
)
PORT = int(os.getenv("PORT", "8100"))
HOST = os.getenv("HOST", "0.0.0.0")

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global model reference
model = None
tokenizer = None
embedding_dim = 4096


# ============================================================================
# Request/Response Models
# ============================================================================

class EmbedRequest(BaseModel):
    """Single text embedding request"""
    text: str
    instruction: Optional[str] = None  # Optional instruction prefix for query


class EmbedBatchRequest(BaseModel):
    """Batch text embedding request"""
    texts: List[str]
    instruction: Optional[str] = None


class EmbedResponse(BaseModel):
    """Embedding response"""
    embedding: List[float]
    dimensions: int


class EmbedBatchResponse(BaseModel):
    """Batch embedding response"""
    embeddings: List[List[float]]
    dimensions: int
    count: int


class HealthResponse(BaseModel):
    """Health check response"""
    status: str
    model_loaded: bool


class InfoResponse(BaseModel):
    """Model info response"""
    model_path: str
    embedding_dim: int
    pooling: str
    normalization: str


# ============================================================================
# Core Embedding Logic
# ============================================================================

def get_embedding(text: str, instruction: Optional[str] = None) -> List[float]:
    """
    Generate embedding for a single text using Qwen3-Embedding.

    Uses last-token pooling (as per Qwen3-Embedding spec) + L2 normalization.

    Args:
        text: The text to embed
        instruction: Optional instruction prefix (e.g., for query vs document)

    Returns:
        4096-dimensional L2-normalized embedding vector
    """
    global model, tokenizer

    if model is None:
        raise RuntimeError("Model not loaded")

    # Optionally prepend instruction (improves retrieval by 1-5% per docs)
    if instruction:
        text = f"Instruct: {instruction}\nQuery: {text}"

    # Tokenize
    input_ids = mx.array([tokenizer.encode(text)])

    # Forward pass through transformer (not lm_head)
    hidden_states = model.model(input_ids)

    # Last-token pooling (Qwen3-Embedding uses EOS token representation)
    last_hidden = hidden_states[:, -1, :]

    # L2 normalize
    norm = mx.linalg.norm(last_hidden, axis=-1, keepdims=True)
    embedding = last_hidden / mx.maximum(norm, 1e-9)

    # Evaluate and convert to list
    mx.eval(embedding)
    return embedding[0].tolist()


def get_embeddings_batch(texts: List[str], instruction: Optional[str] = None) -> List[List[float]]:
    """
    Generate embeddings for multiple texts.

    Processes texts sequentially for now (could batch if needed for speed).

    Args:
        texts: List of texts to embed
        instruction: Optional instruction prefix

    Returns:
        List of 4096-dimensional L2-normalized embedding vectors
    """
    return [get_embedding(text, instruction) for text in texts]


# ============================================================================
# FastAPI App
# ============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load model on startup, cleanup on shutdown"""
    global model, tokenizer, embedding_dim

    logger.info(f"Loading Qwen3-Embedding model from {MODEL_PATH}...")
    start_time = time.time()

    try:
        model, tokenizer = load(MODEL_PATH)
        load_time = time.time() - start_time
        logger.info(f"Model loaded successfully in {load_time:.2f}s")

        # Verify embedding dimension
        test_embedding = get_embedding("test")
        embedding_dim = len(test_embedding)
        logger.info(f"Embedding dimension: {embedding_dim}")

    except Exception as e:
        logger.error(f"Failed to load model: {e}")
        raise

    yield

    # Cleanup
    logger.info("Shutting down embedding server...")
    model = None
    tokenizer = None


app = FastAPI(
    title="Qwen3 Embedding Server",
    description="MLX-based embedding server for Appletta memory system",
    version="1.0.0",
    lifespan=lifespan
)

# CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# Endpoints
# ============================================================================

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint"""
    return HealthResponse(
        status="ok" if model is not None else "not_ready",
        model_loaded=model is not None
    )


@app.get("/info", response_model=InfoResponse)
async def model_info():
    """Get model information"""
    return InfoResponse(
        model_path=MODEL_PATH,
        embedding_dim=embedding_dim,
        pooling="last_token",
        normalization="L2"
    )


@app.post("/embed", response_model=EmbedResponse)
async def embed_single(request: EmbedRequest):
    """Generate embedding for a single text"""
    if model is None:
        raise HTTPException(status_code=503, detail="Model not loaded")

    try:
        embedding = get_embedding(request.text, request.instruction)
        return EmbedResponse(
            embedding=embedding,
            dimensions=len(embedding)
        )
    except Exception as e:
        logger.error(f"Embedding error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/embed_batch", response_model=EmbedBatchResponse)
async def embed_batch(request: EmbedBatchRequest):
    """Generate embeddings for multiple texts"""
    if model is None:
        raise HTTPException(status_code=503, detail="Model not loaded")

    if len(request.texts) == 0:
        return EmbedBatchResponse(embeddings=[], dimensions=embedding_dim, count=0)

    if len(request.texts) > 100:
        raise HTTPException(status_code=400, detail="Batch size too large (max 100)")

    try:
        embeddings = get_embeddings_batch(request.texts, request.instruction)
        return EmbedBatchResponse(
            embeddings=embeddings,
            dimensions=embedding_dim,
            count=len(embeddings)
        )
    except Exception as e:
        logger.error(f"Batch embedding error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Main
# ============================================================================

if __name__ == "__main__":
    logger.info(f"Starting Qwen3 Embedding Server on {HOST}:{PORT}")
    uvicorn.run(app, host=HOST, port=PORT, log_level="info")

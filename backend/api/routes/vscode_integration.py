"""VS Code Integration API - OpenAI-compatible chat completions endpoint

This module provides an OpenAI API-compatible endpoint that allows Claude Code
(via claude-code-router) to use local MLX models through Appletta.
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Dict, Any, Union
from datetime import datetime
import json
import uuid
import asyncio

router = APIRouter(prefix="/v1", tags=["vscode-integration"])


# OpenAI-compatible request/response models
class ChatMessage(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    role: str  # "system", "user", "assistant", "tool"
    content: Union[str, List[Dict[str, Any]]]
    name: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None
    tool_call_id: Optional[str] = None


class ChatCompletionRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    model: str
    messages: List[ChatMessage]
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = 2048
    stream: Optional[bool] = False
    top_p: Optional[float] = 1.0
    frequency_penalty: Optional[float] = 0.0
    presence_penalty: Optional[float] = 0.0
    stop: Optional[Union[str, List[str]]] = None
    tools: Optional[List[Dict[str, Any]]] = None
    tool_choice: Optional[Union[str, Dict[str, Any]]] = None


class ChatCompletionChoice(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    index: int
    message: ChatMessage
    finish_reason: str


class ChatCompletionUsage(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class ChatCompletionResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: List[ChatCompletionChoice]
    usage: ChatCompletionUsage


class StreamDelta(BaseModel):
    role: Optional[str] = None
    content: Optional[str] = None


class StreamChoice(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    index: int
    delta: StreamDelta
    finish_reason: Optional[str] = None


class StreamChunk(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    id: str
    object: str = "chat.completion.chunk"
    created: int
    model: str
    choices: List[StreamChoice]


# Global model state
_loaded_model_path: Optional[str] = None
_loaded_adapter_path: Optional[str] = None


def format_messages_to_prompt(messages: List[ChatMessage]) -> str:
    """Convert OpenAI-style messages to a single prompt string for MLX"""
    prompt_parts = []

    for msg in messages:
        role = msg.role
        if isinstance(msg.content, str):
            content = msg.content
        else:
            # Handle multi-part content (text blocks)
            content_parts = []
            for part in msg.content:
                if isinstance(part, dict) and part.get("type") == "text":
                    content_parts.append(part.get("text", ""))
            content = "\n".join(content_parts)

        if role == "system":
            prompt_parts.append(f"<system>\n{content}\n</system>")
        elif role == "user":
            prompt_parts.append(f"<user>\n{content}\n</user>")
        elif role == "assistant":
            prompt_parts.append(f"<assistant>\n{content}\n</assistant>")
        elif role == "tool":
            prompt_parts.append(f"<tool_result>\n{content}\n</tool_result>")

    # Add assistant prefix to prompt generation
    prompt_parts.append("<assistant>")

    return "\n\n".join(prompt_parts)


def estimate_tokens(text: str) -> int:
    """Rough token estimation (4 chars per token average)"""
    return len(text) // 4


async def generate_stream(
    prompt: str,
    model: str,
    request_id: str,
    max_tokens: int = 2048,
    temperature: float = 0.7
):
    """Generate streaming response chunks"""
    created = int(datetime.utcnow().timestamp())

    try:
        from backend.services.diagnostic_inference import get_diagnostic_service
        service = get_diagnostic_service()

        if service.model is None:
            raise HTTPException(
                status_code=503,
                detail="No model loaded. Load a model first via the Analytics panel."
            )

        # First chunk - role
        chunk = StreamChunk(
            id=request_id,
            created=created,
            model=model,
            choices=[StreamChoice(
                index=0,
                delta=StreamDelta(role="assistant"),
                finish_reason=None
            )]
        )
        yield f"data: {chunk.model_dump_json()}\n\n"

        # Generate full response (MLX doesn't support streaming natively in simple mode)
        response = service.run_inference(
            prompt=prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            log_routing=False  # Don't log for production use
        )

        generated_text = response.get("response", "")

        # Stream the response character by character (or in small chunks)
        chunk_size = 10  # Characters per chunk
        for i in range(0, len(generated_text), chunk_size):
            text_chunk = generated_text[i:i+chunk_size]
            chunk = StreamChunk(
                id=request_id,
                created=created,
                model=model,
                choices=[StreamChoice(
                    index=0,
                    delta=StreamDelta(content=text_chunk),
                    finish_reason=None
                )]
            )
            yield f"data: {chunk.model_dump_json()}\n\n"
            await asyncio.sleep(0.01)  # Small delay for realistic streaming

        # Final chunk
        chunk = StreamChunk(
            id=request_id,
            created=created,
            model=model,
            choices=[StreamChoice(
                index=0,
                delta=StreamDelta(),
                finish_reason="stop"
            )]
        )
        yield f"data: {chunk.model_dump_json()}\n\n"
        yield "data: [DONE]\n\n"

    except ImportError:
        error_chunk = {
            "error": {
                "message": "MLX not installed. This feature requires mlx and mlx_lm.",
                "type": "service_unavailable"
            }
        }
        yield f"data: {json.dumps(error_chunk)}\n\n"
    except Exception as e:
        error_chunk = {
            "error": {
                "message": str(e),
                "type": "internal_error"
            }
        }
        yield f"data: {json.dumps(error_chunk)}\n\n"


@router.post("/chat/completions", response_model=None)
async def chat_completions(request: ChatCompletionRequest):
    """OpenAI-compatible chat completions endpoint

    This endpoint accepts requests in the OpenAI API format and routes them
    to the loaded MLX model for inference.
    """
    request_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"

    # Convert messages to prompt
    prompt = format_messages_to_prompt(request.messages)

    if request.stream:
        return StreamingResponse(
            generate_stream(
                prompt=prompt,
                model=request.model,
                request_id=request_id,
                max_tokens=request.max_tokens or 2048,
                temperature=request.temperature or 0.7
            ),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"
            }
        )

    # Non-streaming response
    try:
        from backend.services.diagnostic_inference import get_diagnostic_service
        service = get_diagnostic_service()

        if service.model is None:
            raise HTTPException(
                status_code=503,
                detail="No model loaded. Load a model first via the Analytics panel."
            )

        # Run inference
        result = service.run_inference(
            prompt=prompt,
            max_tokens=request.max_tokens or 2048,
            temperature=request.temperature or 0.7,
            log_routing=False
        )

        generated_text = result.get("response", "")

        # Calculate token usage (rough estimate)
        prompt_tokens = estimate_tokens(prompt)
        completion_tokens = estimate_tokens(generated_text)

        response = ChatCompletionResponse(
            id=request_id,
            created=int(datetime.utcnow().timestamp()),
            model=request.model,
            choices=[
                ChatCompletionChoice(
                    index=0,
                    message=ChatMessage(role="assistant", content=generated_text),
                    finish_reason="stop"
                )
            ],
            usage=ChatCompletionUsage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens
            )
        )

        return response

    except ImportError:
        raise HTTPException(
            status_code=503,
            detail="MLX not installed. This feature requires mlx and mlx_lm."
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/models")
async def list_models():
    """List available models (OpenAI-compatible endpoint)"""
    try:
        from backend.services.diagnostic_inference import get_diagnostic_service
        service = get_diagnostic_service()

        models = []

        if service.model is not None:
            models.append({
                "id": service.model_path or "mlx-model",
                "object": "model",
                "created": int(datetime.utcnow().timestamp()),
                "owned_by": "appletta",
                "permission": [],
                "root": service.model_path or "mlx-model",
                "parent": None
            })

        return {"object": "list", "data": models}

    except ImportError:
        return {"object": "list", "data": []}


@router.post("/load-model")
async def load_model_for_vscode(
    model_path: str,
    adapter_path: Optional[str] = None
):
    """Load a model for VS Code integration

    This prepares the model for use with Claude Code via claude-code-router.
    """
    global _loaded_model_path, _loaded_adapter_path

    try:
        from backend.services.diagnostic_inference import get_diagnostic_service
        service = get_diagnostic_service()

        result = service.load_model(model_path, adapter_path)

        _loaded_model_path = model_path
        _loaded_adapter_path = adapter_path

        return {
            "status": "success",
            "model": result,
            "message": f"Model loaded. You can now configure claude-code-router to use Appletta at http://localhost:8000/v1/chat/completions"
        }

    except ImportError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status")
async def get_vscode_integration_status():
    """Get current VS Code integration status"""
    try:
        from backend.services.diagnostic_inference import get_diagnostic_service
        service = get_diagnostic_service()

        return {
            "mlx_available": True,
            "model_loaded": service.model is not None,
            "model_path": service.model_path,
            "is_moe": service.is_moe_model if service.model else False,
            "endpoint": "http://localhost:8000/v1/chat/completions",
            "provider_config": {
                "name": "appletta",
                "api_base_url": "http://localhost:8000/v1/chat/completions",
                "api_key": "appletta",
                "models": [service.model_path] if service.model_path else ["mlx-model"]
            }
        }
    except ImportError:
        return {
            "mlx_available": False,
            "model_loaded": False,
            "error": "MLX not installed"
        }

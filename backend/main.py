"""Main FastAPI application for Appletta backend"""

# IMPORTANT: Set this BEFORE any imports that might load tokenizers
# This prevents the "tokenizers fork after parallelism" warning and
# fixes potential tokenizer corruption issues that cause message repetition
import os
os.environ['TOKENIZERS_PARALLELISM'] = 'false'

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.core.config import settings
from backend.api.routes import agents, agent_attachments, files, rag, router_lens_api, search, conversations, journal_blocks, affect, vscode_integration
from backend.db.base import Base
from backend.db.session import engine

# Create database tables
Base.metadata.create_all(bind=engine)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle."""
    yield
    # Shutdown: kill all MLX server subprocesses so they don't pile up
    from backend.services.mlx_manager import get_mlx_manager
    await get_mlx_manager().stop_all_servers()


# Create FastAPI app
app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_PREFIX}/openapi.json",
    lifespan=lifespan,
)

# Set up CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(agents.router)
app.include_router(agent_attachments.router)
app.include_router(files.router)
app.include_router(rag.router)
app.include_router(search.router)
app.include_router(conversations.router)
app.include_router(journal_blocks.router)
app.include_router(router_lens_api.router)
app.include_router(affect.router)
app.include_router(vscode_integration.router)


@app.get("/")
async def root():
    """Health check endpoint"""
    return {
        "message": "Appletta API",
        "status": "running",
        "docs": "/docs",
    }


@app.get("/health")
async def health():
    """Health check endpoint"""
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "backend.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )

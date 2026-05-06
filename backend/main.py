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
from backend.api.routes import agents, agent_attachments, files, rag, router_lens_api, search, conversations, journal_blocks, affect, vscode_integration, emotion_probe, logs as logs_route
from backend.db.base import Base
from backend.db.session import engine

# Create database tables
Base.metadata.create_all(bind=engine)


def _print_sandbox_banner():
    """Print a clear sandbox status banner to the terminal on startup."""
    from backend.services.code_tools import check_sandbox_status

    GREEN  = "\033[92m"
    YELLOW = "\033[93m"
    RED    = "\033[91m"
    CYAN   = "\033[96m"
    BOLD   = "\033[1m"
    RESET  = "\033[0m"

    s = check_sandbox_status()

    shell_icon  = f"{GREEN}✅ ACTIVE{RESET}"   if s["shell_sandboxed"]    else f"{RED}❌ INACTIVE{RESET}"
    smoke_icon  = f"{GREEN}✅ PASSED{RESET}"   if s["smoke_test_passed"]  else f"{YELLOW}⚠  FAILED{RESET}"

    print()
    print(f"{BOLD}{CYAN}╔══════════════════════════════════════════════════════════╗{RESET}")
    print(f"{BOLD}{CYAN}║              🔒  KEVIN'S SANDBOX STATUS                  ║{RESET}")
    print(f"{BOLD}{CYAN}╠══════════════════════════════════════════════════════════╣{RESET}")
    print(f"{BOLD}{CYAN}║{RESET}  Shell commands  (run_shell)    {shell_icon:<30}{BOLD}{CYAN}║{RESET}")
    if s["shell_sandboxed"]:
        print(f"{BOLD}{CYAN}║{RESET}    via macOS seatbelt (sandbox-exec)                    {BOLD}{CYAN}║{RESET}")
        print(f"{BOLD}{CYAN}║{RESET}    write-outside-workspace smoke test  {smoke_icon:<20}{BOLD}{CYAN}║{RESET}")
    else:
        err = (s["smoke_test_error"] or "unknown")[:50]
        print(f"{BOLD}{CYAN}║{RESET}    {YELLOW}{err:<54}{RESET}{BOLD}{CYAN}║{RESET}")
    print(f"{BOLD}{CYAN}║{RESET}                                                          {BOLD}{CYAN}║{RESET}")
    print(f"{BOLD}{CYAN}║{RESET}  File ops  (read/write_file)    {YELLOW}🔑 WORKSPACE CHECK{RESET}        {BOLD}{CYAN}║{RESET}")
    print(f"{BOLD}{CYAN}║{RESET}    Python-level path validation — not OS seatbelt        {BOLD}{CYAN}║{RESET}")
    print(f"{BOLD}{CYAN}║{RESET}                                                          {BOLD}{CYAN}║{RESET}")
    ws = s["workspace_root"]
    ws_display = ws if len(ws) <= 52 else "…" + ws[-51:]
    print(f"{BOLD}{CYAN}║{RESET}  Workspace root:                                          {BOLD}{CYAN}║{RESET}")
    print(f"{BOLD}{CYAN}║{RESET}    {ws_display:<54}{BOLD}{CYAN}║{RESET}")
    print(f"{BOLD}{CYAN}╚══════════════════════════════════════════════════════════╝{RESET}")
    print()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle."""
    from backend.services.log_broadcaster import install as install_log_broadcaster
    install_log_broadcaster()
    _print_sandbox_banner()
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
app.include_router(emotion_probe.router)
app.include_router(vscode_integration.router)
app.include_router(logs_route.router)


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

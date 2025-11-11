# Appletta Backend

FastAPI backend for managing AI agent configurations and MLX model integration.

## Features

- **Agent Management**: Full CRUD API for agent configurations
- **File Browser**: Browse filesystem for model/adapter selection
- **Agent Import/Export**: Save and load agents as `.af` files
- **MLX Integration**: Configuration for launching MLX model servers
- **Database**: SQLite/PostgreSQL support via SQLAlchemy

## Tech Stack

- **FastAPI** - Modern async web framework
- **SQLAlchemy** - ORM for database operations
- **Pydantic** - Data validation and settings
- **Uvicorn** - ASGI server

## Project Structure

```
backend/
├── api/
│   └── routes/
│       ├── agents.py           # Agent CRUD endpoints
│       └── files.py            # File browser endpoints
├── core/
│   └── config.py               # App configuration
├── db/
│   ├── base.py                 # SQLAlchemy base
│   ├── session.py              # Database session management
│   └── models/
│       └── agent.py            # Agent database model
├── schemas/
│   └── agent.py                # Pydantic schemas for API
├── services/
│   └── mlx_manager.py          # MLX subprocess management
├── main.py                     # FastAPI app entry point
├── init_db.py                  # Database initialization script
└── requirements.txt            # Python dependencies
```

## Getting Started

### Prerequisites

- Python 3.10+
- pip

### Installation

1. **Create virtual environment**:
   ```bash
   cd backend
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Initialize database**:
   ```bash
   python3 init_db.py
   ```

### Running the Server

**Development mode** (with auto-reload):
```bash
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

Or use the built-in script:
```bash
python3 -m backend.main
```

The API will be available at:
- **API**: http://localhost:8000
- **Interactive docs**: http://localhost:8000/docs
- **Alternative docs**: http://localhost:8000/redoc

## API Endpoints

### Agents

- `POST /api/v1/agents` - Create new agent
- `GET /api/v1/agents` - List all agents
- `GET /api/v1/agents/{id}` - Get specific agent
- `PATCH /api/v1/agents/{id}` - Update agent
- `DELETE /api/v1/agents/{id}` - Delete agent
- `POST /api/v1/agents/{id}/clone` - Clone agent
- `GET /api/v1/agents/{id}/export` - Export agent as .af file
- `POST /api/v1/agents/import` - Import agent from .af file

### Files

- `GET /api/v1/files/browse?path=...` - Browse filesystem
- `GET /api/v1/files/validate-model?path=...` - Validate model path
- `GET /api/v1/files/suggested-paths` - Get common model locations

## Database Schema

### Agents Table

```sql
CREATE TABLE agents (
    id UUID PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    description TEXT,

    -- Model paths
    model_path VARCHAR(1024) NOT NULL,
    adapter_path VARCHAR(1024),
    embedding_model_path VARCHAR(1024) NOT NULL,

    -- System prompt
    system_instructions TEXT NOT NULL,

    -- LLM config
    reasoning_enabled BOOLEAN DEFAULT FALSE,
    temperature FLOAT DEFAULT 0.7,
    seed INTEGER,
    max_output_tokens_enabled BOOLEAN DEFAULT FALSE,
    max_output_tokens INTEGER DEFAULT 8192,

    -- Embedding config
    embedding_dimensions INTEGER DEFAULT 2000,
    embedding_chunk_size INTEGER DEFAULT 300,

    -- Timestamps
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

## Configuration

Edit `backend/core/config.py` or set environment variables:

```bash
# Database
DATABASE_URL=sqlite:///./appletta.db

# CORS
BACKEND_CORS_ORIGINS=["http://localhost:5173", "http://localhost:3000"]
```

## Agent File Format (.af)

Agents can be exported/imported as JSON files:

```json
{
  "version": "1.0",
  "agent": {
    "name": "MyAgent",
    "description": "A helpful AI assistant",
    "model_path": "/Users/you/Models/Qwen2.5-14B-Instruct-4bit",
    "adapter_path": "/Users/you/Models/adapters/claude",
    "system_instructions": "You are a helpful AI assistant...",
    "llm_config": {
      "reasoning_enabled": false,
      "temperature": 0.7,
      "seed": 42,
      "max_output_tokens_enabled": true,
      "max_output_tokens": 8192
    },
    "embedding_config": {
      "model_path": "/Users/you/Models/embedding-model",
      "dimensions": 2000,
      "chunk_size": 300
    }
  }
}
```

## Development

### Running Tests
```bash
pytest
```

### Code Quality
```bash
# Format code
black .

# Lint
flake8 .
ruff check .
```

### Database Migrations

If you need to modify the schema:

```bash
# Create migration
alembic revision --autogenerate -m "description"

# Apply migration
alembic upgrade head
```

## MLX Integration

The `services/mlx_manager.py` module handles launching MLX model servers for agents. When an agent is started, it spawns an `mlx_lm.server` subprocess with the agent's configured model and parameters.

## Next Steps

- [ ] Add authentication/authorization
- [ ] Implement agent start/stop endpoints
- [ ] Add WebSocket support for streaming responses
- [ ] Implement model path validation
- [ ] Add comprehensive error handling
- [ ] Write unit tests
- [ ] Add PostgreSQL support documentation
- [ ] Implement logging and monitoring

## License

See main project LICENSE

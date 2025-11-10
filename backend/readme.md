# Appletta Backend - Agent Settings Tab

 

This directory contains the backend implementation for the **Agent Settings** tab (Left Panel, Tab 1).

 

## Status: 🚧 SKELETON - Ready for Implementation

 

All files are scaffolded with TODOs. The structure is complete, now needs:

1. Database connection setup

2. FastAPI app integration

3. Frontend integration

4. Testing

 

## What's Built

 

### Database Models (`db/models/`)

- **agent.py** - Agent configuration storage

  - Model/adapter/embedding paths

  - System instructions

  - LLM generation parameters

  - Export/import to `.af` format

 

### API Schemas (`schemas/`)

- **agent.py** - Pydantic validation schemas

  - AgentCreate, AgentUpdate, AgentResponse

  - LLMConfig, EmbeddingConfig sub-schemas

  - AgentFile format for import/export

 

### API Routes (`api/routes/`)

- **agents.py** - Agent CRUD + operations

  - `POST /api/v1/agents` - Create agent

  - `GET /api/v1/agents` - List all agents

  - `GET /api/v1/agents/{id}` - Get specific agent

  - `PATCH /api/v1/agents/{id}` - Update agent

  - `DELETE /api/v1/agents/{id}` - Delete agent

  - `POST /api/v1/agents/{id}/clone` - Clone agent

  - `GET /api/v1/agents/{id}/export` - Export as .af file

  - `POST /api/v1/agents/import` - Import from .af file

 

- **files.py** - Filesystem browser for model selection

  - `GET /api/v1/files/browse?path=...` - Browse directories

  - `GET /api/v1/files/validate-model?path=...` - Validate model path

  - `GET /api/v1/files/suggested-paths` - Common model locations

 

### Services (`services/`)

- **mlx_manager.py** - MLX subprocess management

  - Starts `mlx_lm.server` with agent's config

  - Manages multiple servers (one per agent)

  - Port allocation, graceful shutdown

  - Process lifecycle tracking

 

## Database Schema

 

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

 

CREATE INDEX idx_agents_name ON agents(name);

CREATE INDEX idx_agents_created_at ON agents(created_at);

```

 

## Agent File Format (.af)

 

```json

{

  "version": "1.0",

  "agent": {

    "name": "agent-name",

    "description": "Agent description",

    "model_path": "/Users/you/Models/Qwen2.5-14B-Instruct-4bit",

    "adapter_path": "/Users/you/Models/adapters/claude",

    "system_instructions": "You are MemoryMate...",

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

 

## UI → Backend Flow

 

### Creating an Agent

1. User clicks "New Agent"

2. User fills out form:

   - Name: text input

   - Description: text input

   - Model: file browser → `/api/v1/files/browse`

   - Adapter: file browser (optional)

   - System Instructions: popup editor

   - LLM Config: sliders/toggles

   - Embedding Model: file browser

3. User clicks "Save"

4. Frontend validates and POSTs to `/api/v1/agents`

5. Backend validates paths exist

6. Backend saves to database

7. Returns agent object

 

### Starting an Agent

1. User clicks "Run" on agent

2. Frontend POSTs to `/api/v1/agents/{id}/start` (TODO: Add this endpoint)

3. Backend calls `mlx_manager.start_agent_server(agent)`

4. MLX server launches with agent's model/adapter

5. Returns server info (port, status)

6. Frontend can now send messages to agent

 

## Next Steps

 

### 1. Database Setup

```bash

# TODO: Create migration

alembic revision --autogenerate -m "create agents table"

alembic upgrade head

```

 

### 2. FastAPI Integration

```python

# TODO: In main.py or app.py

from backend.api.routes import agents, files

 

app.include_router(agents.router)

app.include_router(files.router)

 

# Cleanup on shutdown

@app.on_event("shutdown")

async def shutdown():

    mlx_manager = get_mlx_manager()

    await mlx_manager.stop_all_servers()

```

 

### 3. Frontend Integration

```typescript

// TODO: API client

const agentAPI = {

  list: () => fetch('/api/v1/agents'),

  get: (id) => fetch(`/api/v1/agents/${id}`),

  create: (data) => fetch('/api/v1/agents', {

    method: 'POST',

    body: JSON.stringify(data)

  }),

  update: (id, data) => fetch(`/api/v1/agents/${id}`, {

    method: 'PATCH',

    body: JSON.stringify(data)

  }),

  // ... etc

}

```

 

### 4. Testing

- Test model path validation

- Test agent CRUD operations

- Test MLX server lifecycle

- Test .af file import/export

- Test concurrent MLX servers for different agents

 

## TODO Items

 

Search codebase for `TODO:` comments - there are many! Key ones:

 

- [ ] Database connection setup

- [ ] FastAPI router registration

- [ ] MLX server log capture to files

- [ ] Model path validation (check for config.json, .safetensors)

- [ ] Port availability checking (not just unused by us)

- [ ] Reasoning mode configuration (might need model-specific config)

- [ ] Agent start/stop endpoints

- [ ] WebSocket for agent streaming responses

- [ ] Error handling and user-friendly messages

 

## Related Files

 

- `/AGENT_SETTINGS_TAB.md` - Detailed specification

- `/agent_settings-left_panel-tab1/` - UI screenshots with annotations

 

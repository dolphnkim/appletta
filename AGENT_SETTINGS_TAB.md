AGENT_SETTINGS_TAB.md
# Agent Settings Tab - Backend Specification

 

## Database Schema

 

```python

# agents table

class Agent(Base):

    __tablename__ = "agents"

 

    # Identity

    id: UUID (primary key)

    name: str (required, editable from UI)

    description: str (optional, editable from UI)

 

    # Model Configuration

    model_path: str (required, filepath - "choose model from filepath")

    adapter_path: str | None (optional, filepath - "choose adapter from filepath")

 

    # System Instructions

    system_instructions: str (long text, editable via popup)

    # Format: Plain text, gets inserted into agent prompt

 

    # LLM Config Section

    reasoning_enabled: bool (default=False)

    # TODO: Might move to local model config file instead

    # Controls whether model uses <think></think> tags

 

    temperature: float (0.0-2.0, default=0.7)

    seed: int | None (optional, for reproducibility)

    max_output_tokens_enabled: bool (default=False)

    max_output_tokens: int (default=8192, only used if enabled)

 

    # Embedding Config Section

    embedding_model_path: str (required, filepath - "choose model from filepath")

    embedding_dimensions: int (default=2000)

    embedding_chunk_size: int (default=300)

 

    # Projects (TODO: Future integration with larger app structure)

    # project_id: UUID | None (foreign key to projects table)

 

    # Timestamps

    created_at: timestamp

    updated_at: timestamp

 

    # Indexes

    INDEX on name (for quick lookup)

    INDEX on created_at (for sorting)

```

 

## API Endpoints

 

```python

# Agent CRUD

POST   /api/v1/agents                 # Create new agent

GET    /api/v1/agents                 # List all agents

GET    /api/v1/agents/{id}            # Get specific agent

PATCH  /api/v1/agents/{id}            # Update agent settings

DELETE /api/v1/agents/{id}            # Delete agent

 

# Agent Operations (from hover menu)

POST   /api/v1/agents/{id}/clone      # Clone agent with all settings

GET    /api/v1/agents/{id}/export     # Export agent as .af file

POST   /api/v1/agents/import          # Import agent from .af file

 

# File Browser (for model/adapter/embedding selection)

GET    /api/v1/files/browse?path=...  # Browse filesystem for model selection

# Returns: list of directories/files, filters for model-like structures

```

 

## Agent File Format (.af)

 

```json

{

  "version": "1.0",

  "agent": {

    "name": "agent-name",

    "description": "A agent specialized for background memory processing.",

    "model_path": "/Users/kimwhite/Models/Qwen2.5-14B-Instruct-4bit",

    "adapter_path": "/Users/kimwhite/Models/adapters/claude",

    "system_instructions": "<base_instructions>\nYou are MemoryMate...",

    "llm_config": {

      "reasoning_enabled": false,

      "temperature": 0.7,

      "seed": 42,

      "max_output_tokens_enabled": true,

      "max_output_tokens": 8192

    },

    "embedding_config": {

      "model_path": "/Users/kimwhite/Models/some-embedding-model",

      "dimensions": 2000,

      "chunk_size": 300

    }

  }

}

```

 

## MLX Subprocess Management

 

When agent starts, spawn mlx_lm.server using agent config:

 

```python

def start_agent_mlx_server(agent: Agent) -> subprocess.Popen:

    """Launch mlx_lm.server with agent's configured model/adapter"""

 

    cmd = [

        "mlx_lm.server",

        "--model", agent.model_path,

        "--port", "8080",

    ]

 

    if agent.adapter_path:

        cmd.extend(["--adapter-path", agent.adapter_path])

 

    if agent.max_output_tokens_enabled:

        cmd.extend(["--max-tokens", str(agent.max_output_tokens)])

 

    cmd.extend([

        "--temp", str(agent.temperature),

    ])

 

    if agent.seed is not None:

        cmd.extend(["--seed", str(agent.seed)])

 

    # TODO: Handle reasoning_enabled (might be in model config instead)

 

    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    return process

```

 

## UI ↔ Backend Flow

 

### Creating/Editing Agent:

1. User fills out form in UI

2. User clicks file browser for model_path → GET /api/v1/files/browse

3. User selects model → UI stores path

4. Same for adapter_path and embedding_model_path

5. User edits system instructions via popup

6. User adjusts sliders for temperature, max tokens, etc.

7. Click save → PATCH /api/v1/agents/{id}

8. Backend validates paths exist

9. Backend saves to database

10. Returns updated agent profile

 

### Cloning Agent:

1. User clicks "..." menu on agent name

2. Selects "Clone agent"

3. POST /api/v1/agents/{id}/clone

4. Backend creates new agent with same settings + "-copy" suffix

5. Returns new agent

6. UI adds to agent list

 

### Exporting Agent:

1. User clicks "..." menu

2. Selects "Download AgentFile (.af)"

3. GET /api/v1/agents/{id}/export

4. Backend serializes agent to JSON

5. Returns .af file download

 

### Importing Agent:

1. User uploads .af file

2. POST /api/v1/agents/import with file

3. Backend parses JSON

4. Backend validates model paths exist

5. Backend creates new agent

6. Returns new agent

7. UI adds to agent list

 

## Notes:

- All settings get saved to agent profile (not global config)

- Model/adapter/embedding paths are REQUIRED (must select from filesystem)

- System instructions popup is full-screen editor, not inline

- Temperature uses slider (0.0-2.0 range, shown as "0.7")

- Seed is for reproducible outputs

- Max output tokens has toggle + value (8192 shown)

- Embedding config is separate section, also filepath-based

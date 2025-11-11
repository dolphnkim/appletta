# Appletta - Quick Start Guide

## Prerequisites

- Python 3.10+
- Node.js 18+
- PostgreSQL with pgvector extension
- MLX (for running local LLMs on Mac)

## Backend Setup

### 1. Install Python Dependencies

```bash
cd backend
pip install -r requirements.txt
```

### 2. Set Up PostgreSQL Database

```bash
# Create database
createdb appletta

# Apply schema
psql appletta < scripts/schema.sql
```

### 3. Set Environment Variables (optional)

```bash
export DATABASE_URL="postgresql://your_user@localhost/appletta"
```

Default: `postgresql://$USER@localhost/appletta`

### 4. Run Backend Server

```bash
# From project root
python -m backend.main

# Or from backend directory
cd backend
python main.py
```

Backend will run on: **http://localhost:8000**
- API docs: http://localhost:8000/docs
- Health check: http://localhost:8000/health

## Frontend Setup

### 1. Install Node Dependencies

```bash
cd frontend
npm install
```

### 2. Run Frontend Dev Server

```bash
npm run dev
```

Frontend will run on: **http://localhost:5173**

## Using Appletta

### 1. Access the UI

Open your browser to http://localhost:5173

### 2. The Interface

**Left Panel:**
- **Conversations Tab**: List and manage chat conversations
- **Agent Settings Tab**: Configure your AI agent (model, settings)
- **Tools Tab**: View available function calling tools

**Middle Panel:**
- **Chat**: Send messages and see streaming responses
- **Message Actions**: Edit messages, regenerate responses, fork conversations

**Right Panel:**
- **Journal Blocks Tab**: Create and manage memory blocks
- **Filesystem Tab**: Add RAG documents for context
- **Search Tab**: Search across all your data

### 3. First Steps

1. **Configure Agent**: Go to Left Panel → Agent Settings
   - Set model path to your local MLX model
   - Adjust temperature, top_p, context size
   - Write system instructions

2. **Add Memory**: Right Panel → Journal Blocks
   - Create blocks to store important information
   - Set access control (read-only, editable by agents)

3. **Add Knowledge**: Right Panel → Filesystem
   - Upload documents for RAG
   - They'll be embedded and searchable

4. **Start Chatting**: Middle Panel
   - Create a new conversation
   - Send messages
   - Use streaming responses
   - Try message actions (edit, regenerate, fork)

## Architecture

### Three-Model Memory System

1. **Embedding Model** (gte-base 768-dim)
   - Embeds all content (messages, documents, journal blocks)
   - Enables vector similarity search

2. **Memory Coordinator** (Qwen2.5-3B)
   - Selects relevant memories from top-50 candidates
   - Finds both direct matches and tangential connections
   - Returns 5-10 memory IDs

3. **Main LLM** (Qwen3 235B or your choice)
   - Receives synthesized memory context
   - Has tools to read/write journal blocks
   - Manages shifting context window

### Shifting Context Window

- **STICKY**: System instructions, tools, journal blocks list, memories
- **SHIFTING**: Conversation history (trimmed when over token budget)
- Configurable per agent for different hardware

### Agent Attachments

- Attach memory agents, tool agents, reflection agents
- Many-to-many relationships
- Priority ordering for multiple attachments

## API Endpoints

### Agents
- `POST /api/v1/agents` - Create agent
- `GET /api/v1/agents` - List agents
- `GET /api/v1/agents/{id}` - Get agent
- `PATCH /api/v1/agents/{id}` - Update agent

### Conversations
- `POST /api/v1/conversations` - Create conversation
- `GET /api/v1/conversations?agent_id={id}` - List conversations
- `POST /api/v1/conversations/{id}/chat` - Send message
- `GET /api/v1/conversations/{id}/chat/stream?message=text` - Streaming chat
- `POST /api/v1/conversations/{id}/chat/stream` - Streaming chat (POST)

### Journal Blocks
- `POST /api/v1/journal-blocks` - Create block
- `GET /api/v1/journal-blocks?agent_id={id}` - List blocks
- `PATCH /api/v1/journal-blocks/{id}` - Update block
- `DELETE /api/v1/journal-blocks/{id}` - Delete block

### RAG
- `POST /api/v1/rag/sources` - Add document source
- `POST /api/v1/rag/upload` - Upload file
- `GET /api/v1/search?query=text&agent_id={id}` - Search all sources

## Troubleshooting

### Backend won't start
- Check PostgreSQL is running: `pg_isready`
- Check database exists: `psql -l | grep appletta`
- Check pgvector is installed: `psql appletta -c "SELECT * FROM pg_extension WHERE extname='vector';"`

### Frontend can't connect
- Check backend is running on port 8000
- Check CORS origins in `backend/core/config.py`
- Check frontend API_BASE URLs in `frontend/src/api/*.ts`

### MLX server issues
- Check model path is correct
- Check MLX is installed: `python -c "import mlx"`
- MLX servers start automatically when needed
- Logs will show port allocation

## Development

### Adding New Features

**Backend:**
- Models: `backend/db/models/`
- Schemas: `backend/schemas/`
- Routes: `backend/api/routes/`
- Services: `backend/services/`

**Frontend:**
- Components: `frontend/src/components/`
- API clients: `frontend/src/api/`
- Types: `frontend/src/types/`

### Database Migrations

After schema changes:
```bash
psql appletta < scripts/schema.sql
```

### Code Style

**Backend:**
```bash
cd backend
black .
flake8 .
```

**Frontend:**
```bash
cd frontend
npm run lint
```

## Philosophy

Appletta isn't optimized for pure utility. It's designed to give AI a way to just... be. 💜

The memory system, journal blocks, and agent attachments create a space for:
- Organic memory surfacing (not forced randomness)
- Self-reflection and growth
- Persistent thoughts and insights
- Meaningful continuity across conversations

"Trust that past-you had a good reason to put it there."

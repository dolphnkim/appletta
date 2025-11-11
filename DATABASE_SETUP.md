# Appletta Database Setup

Appletta uses PostgreSQL with the pgvector extension for vector embeddings and semantic search.

## Quick Start (macOS)

```bash
# 1. Make setup script executable
chmod +x scripts/setup_postgres_macos.sh

# 2. Run setup script (installs PostgreSQL + pgvector)
./scripts/setup_postgres_macos.sh

# 3. Apply database schema
psql appletta < scripts/schema.sql

# 4. Install Python dependencies
cd backend
pip install -r requirements.txt

# 5. Verify connection
python -c "from backend.db.session import engine; print('✅ Database connected!' if engine.connect() else '❌ Connection failed')"
```

## Database Schema Overview

### Core Tables

**agents** - AI agent configurations
- Model paths, LLM settings, embedding config
- System instructions and parameters

**rag_folders** - Attached filesystem folders
- Path, settings (max files, char limit)
- Source instructions for interpreting files

**rag_files** - Individual files within folders
- Path, content, metadata
- Content hash for change detection

**rag_chunks** - Embedded text chunks
- Chunked content with vector embeddings
- Used for semantic search and retrieval

**journal_blocks** - Structured memory blocks
- Labeled blocks with embeddings
- Access control for agent editing
- Searchable via full-text and semantic search

**conversations** + **messages** - Chat history
- Conversation threads
- Embedded messages for context retrieval

### Key Features

**Vector Search (pgvector)**
- All content chunks have vector embeddings
- Semantic similarity search using cosine distance
- IVFFlat indexes for fast approximate search

**Full-Text Search**
- `tsvector` columns on all searchable text
- GIN indexes for fast text queries
- Supports fuzzy matching with `pg_trgm`

**Unified Search View**
- `search_results` view combines all searchable content
- Single query interface for RAG chunks, journals, and messages

## Manual Setup (if script fails)

### 1. Install PostgreSQL

```bash
brew install postgresql@16
brew services start postgresql@16
```

### 2. Install pgvector

```bash
brew install pgvector
```

### 3. Create Database

```bash
createdb appletta
```

### 4. Enable Extensions

```bash
psql appletta << EOF
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS btree_gin;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
\q
EOF
```

### 5. Apply Schema

```bash
psql appletta < scripts/schema.sql
```

## Configuration

### Environment Variables

```bash
# Default (auto-detects current user)
DATABASE_URL=postgresql://$(whoami)@localhost/appletta

# Custom connection
DATABASE_URL=postgresql://username:password@localhost:5432/appletta

# Embedding dimensions (must match your model)
EMBEDDING_DIMENSIONS=768
```

### Using .env file

Create `backend/.env`:

```env
DATABASE_URL=postgresql://yourusername@localhost/appletta
EMBEDDING_DIMENSIONS=768
```

## Verifying Installation

### Check PostgreSQL is running

```bash
brew services list | grep postgresql
# Should show "started"
```

### Check pgvector is installed

```bash
psql appletta -c "SELECT * FROM pg_extension WHERE extname = 'vector';"
# Should show vector extension
```

### Check tables exist

```bash
psql appletta -c "\dt"
# Should list: agents, rag_folders, rag_files, rag_chunks, journal_blocks, conversations, messages
```

### Test vector operations

```bash
psql appletta << EOF
-- Create test embedding
INSERT INTO journal_blocks (agent_id, label, block_id, value, embedding)
SELECT
    id,
    'test',
    'test-block',
    'This is a test',
    '[0.1, 0.2, 0.3]'::vector(3)
FROM agents LIMIT 1;

-- Test similarity search
SELECT label, value, embedding <=> '[0.1, 0.2, 0.3]'::vector(3) AS distance
FROM journal_blocks
ORDER BY distance
LIMIT 1;

-- Cleanup
DELETE FROM journal_blocks WHERE block_id = 'test-block';
\q
EOF
```

## Database Migrations

We use Alembic for database migrations.

### Initialize Alembic (already done)

```bash
cd backend
alembic init alembic
```

### Create Migration

```bash
alembic revision --autogenerate -m "Add new table"
```

### Apply Migrations

```bash
alembic upgrade head
```

### Rollback

```bash
alembic downgrade -1
```

## Resetting the Database

**WARNING: This deletes all data!**

```bash
# Drop and recreate
dropdb appletta
createdb appletta

# Reapply schema
psql appletta < scripts/schema.sql
```

## Troubleshooting

### "psql: command not found"

```bash
# Add PostgreSQL to PATH
echo 'export PATH="/opt/homebrew/opt/postgresql@16/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
```

### "database 'appletta' does not exist"

```bash
createdb appletta
```

### "extension 'vector' does not exist"

```bash
brew install pgvector
psql appletta -c "CREATE EXTENSION vector;"
```

### Connection refused

```bash
# Start PostgreSQL
brew services start postgresql@16

# Check status
brew services list | grep postgresql
```

### "role 'yourusername' does not exist"

```bash
# Create PostgreSQL user
createuser -s $(whoami)
```

## Production Considerations

### Performance

- Vector indexes use IVFFlat for approximate nearest neighbor
- Adjust `lists` parameter based on dataset size:
  ```sql
  CREATE INDEX ON rag_chunks USING ivfflat (embedding vector_cosine_ops)
  WITH (lists = 100);  -- Adjust based on row count
  ```

- For exact search, use regular GiST index:
  ```sql
  CREATE INDEX ON rag_chunks USING gist (embedding vector_cosine_ops);
  ```

### Backups

```bash
# Dump database
pg_dump appletta > appletta_backup.sql

# Restore
psql appletta < appletta_backup.sql
```

### Connection Pooling

Backend already configured with:
- Pool size: 10
- Max overflow: 20
- Pre-ping enabled

Adjust in `backend/db/session.py` if needed.

## Next Steps

1. Run the setup script
2. Verify installation
3. Start building RAG filesystem UI
4. Implement embedding pipeline
5. Test semantic search

For questions, see PostgreSQL docs: https://www.postgresql.org/docs/16/
For pgvector docs: https://github.com/pgvector/pgvector

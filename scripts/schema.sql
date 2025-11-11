-- Appletta Database Schema
-- PostgreSQL with pgvector for embeddings and semantic search

-- Enable extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS btree_gin;

-- ============================================================================
-- AGENTS
-- ============================================================================

CREATE TABLE agents (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
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
    top_p FLOAT DEFAULT 1.0,
    top_k INTEGER DEFAULT 0,
    seed INTEGER,
    max_output_tokens_enabled BOOLEAN DEFAULT FALSE,
    max_output_tokens INTEGER DEFAULT 8192,

    -- Embedding config
    embedding_dimensions INTEGER DEFAULT 768,
    embedding_chunk_size INTEGER DEFAULT 300,

    -- Timestamps
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_agents_name ON agents(name);
CREATE INDEX idx_agents_created_at ON agents(created_at);

-- ============================================================================
-- AGENT ATTACHMENTS
-- ============================================================================

CREATE TABLE agent_attachments (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    agent_id UUID REFERENCES agents(id) ON DELETE CASCADE,
    attached_agent_id UUID REFERENCES agents(id) ON DELETE CASCADE,

    -- Type of attachment: 'memory', 'tool', 'reflection', etc.
    attachment_type VARCHAR(50) NOT NULL,

    -- Display label
    label VARCHAR(255),

    -- Order/priority for multiple attachments of same type
    priority INTEGER DEFAULT 0,

    -- Enable/disable without deleting
    enabled BOOLEAN DEFAULT TRUE,

    -- Timestamps
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),

    -- Unique constraint: agent can't attach same agent twice for same type
    UNIQUE(agent_id, attached_agent_id, attachment_type)
);

CREATE INDEX idx_agent_attachments_agent ON agent_attachments(agent_id);
CREATE INDEX idx_agent_attachments_type ON agent_attachments(attachment_type);
CREATE INDEX idx_agent_attachments_enabled ON agent_attachments(enabled);

-- ============================================================================
-- RAG FILESYSTEM
-- ============================================================================

CREATE TABLE rag_folders (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    agent_id UUID REFERENCES agents(id) ON DELETE CASCADE,

    path VARCHAR(2048) NOT NULL,
    name VARCHAR(512) NOT NULL,

    -- Settings
    max_files_open INTEGER DEFAULT 5,
    per_file_char_limit INTEGER DEFAULT 15000,

    -- Source instructions (how to interpret files in this folder)
    source_instructions TEXT,

    -- Timestamps
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),

    UNIQUE(agent_id, path)
);

CREATE INDEX idx_rag_folders_agent ON rag_folders(agent_id);
CREATE INDEX idx_rag_folders_path ON rag_folders(path);

CREATE TABLE rag_files (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    folder_id UUID REFERENCES rag_folders(id) ON DELETE CASCADE,

    path VARCHAR(2048) NOT NULL,
    filename VARCHAR(512) NOT NULL,
    extension VARCHAR(50),

    -- File metadata
    size_bytes BIGINT,
    mime_type VARCHAR(255),

    -- Content
    raw_content TEXT,

    -- File hash for change detection
    content_hash VARCHAR(64),

    -- Timestamps
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    last_indexed_at TIMESTAMP,

    UNIQUE(folder_id, path)
);

CREATE INDEX idx_rag_files_folder ON rag_files(folder_id);
CREATE INDEX idx_rag_files_path ON rag_files(path);
CREATE INDEX idx_rag_files_hash ON rag_files(content_hash);

CREATE TABLE rag_chunks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    file_id UUID REFERENCES rag_files(id) ON DELETE CASCADE,

    -- Chunk content
    content TEXT NOT NULL,
    chunk_index INTEGER NOT NULL, -- Order within file

    -- Character positions in original file
    start_char INTEGER,
    end_char INTEGER,

    -- Embedding (dimension based on agent's embedding_dimensions)
    embedding vector(768), -- Default dimension, can be adjusted

    -- Metadata
    metadata JSONB, -- For storing extra context

    -- Timestamps
    created_at TIMESTAMP DEFAULT NOW(),

    UNIQUE(file_id, chunk_index)
);

CREATE INDEX idx_rag_chunks_file ON rag_chunks(file_id);
CREATE INDEX idx_rag_chunks_embedding ON rag_chunks USING ivfflat (embedding vector_cosine_ops);
CREATE INDEX idx_rag_chunks_metadata ON rag_chunks USING gin (metadata);

-- ============================================================================
-- JOURNAL BLOCKS
-- ============================================================================

CREATE TABLE journal_blocks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    agent_id UUID REFERENCES agents(id) ON DELETE CASCADE,

    -- Block identification
    label VARCHAR(255) NOT NULL,
    block_id VARCHAR(255) NOT NULL, -- User-friendly ID

    -- Content
    description TEXT,
    value TEXT NOT NULL,

    -- Access control
    read_only BOOLEAN DEFAULT FALSE,
    editable_by_main_agent BOOLEAN DEFAULT TRUE,
    editable_by_memory_agent BOOLEAN DEFAULT FALSE,

    -- Embedding for semantic search
    embedding vector(768),

    -- Timestamps
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),

    UNIQUE(agent_id, block_id)
);

CREATE INDEX idx_journal_blocks_agent ON journal_blocks(agent_id);
CREATE INDEX idx_journal_blocks_label ON journal_blocks(label);
CREATE INDEX idx_journal_blocks_embedding ON journal_blocks USING ivfflat (embedding vector_cosine_ops);
CREATE INDEX idx_journal_blocks_updated ON journal_blocks(updated_at);

-- ============================================================================
-- CONVERSATION HISTORY
-- ============================================================================

CREATE TABLE conversations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    agent_id UUID REFERENCES agents(id) ON DELETE CASCADE,

    title VARCHAR(512),

    -- Timestamps
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_conversations_agent ON conversations(agent_id);
CREATE INDEX idx_conversations_created ON conversations(created_at);

CREATE TABLE messages (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    conversation_id UUID REFERENCES conversations(id) ON DELETE CASCADE,

    role VARCHAR(50) NOT NULL, -- 'user', 'assistant', 'system'
    content TEXT NOT NULL,

    -- Embedding for semantic search
    embedding vector(768),

    -- Metadata
    metadata JSONB,

    -- Timestamps
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_messages_conversation ON messages(conversation_id);
CREATE INDEX idx_messages_role ON messages(role);
CREATE INDEX idx_messages_embedding ON messages USING ivfflat (embedding vector_cosine_ops);
CREATE INDEX idx_messages_created ON messages(created_at);

-- ============================================================================
-- FULL-TEXT SEARCH
-- ============================================================================

-- Add full-text search to rag_chunks
ALTER TABLE rag_chunks ADD COLUMN content_tsv tsvector
    GENERATED ALWAYS AS (to_tsvector('english', content)) STORED;

CREATE INDEX idx_rag_chunks_fts ON rag_chunks USING gin(content_tsv);

-- Add full-text search to journal_blocks
ALTER TABLE journal_blocks ADD COLUMN value_tsv tsvector
    GENERATED ALWAYS AS (to_tsvector('english', value)) STORED;

CREATE INDEX idx_journal_blocks_fts ON journal_blocks USING gin(value_tsv);

-- Add full-text search to messages
ALTER TABLE messages ADD COLUMN content_tsv tsvector
    GENERATED ALWAYS AS (to_tsvector('english', content)) STORED;

CREATE INDEX idx_messages_fts ON messages USING gin(content_tsv);

-- ============================================================================
-- FUNCTIONS
-- ============================================================================

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Apply to all tables with updated_at
CREATE TRIGGER update_agents_updated_at BEFORE UPDATE ON agents
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_agent_attachments_updated_at BEFORE UPDATE ON agent_attachments
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_rag_folders_updated_at BEFORE UPDATE ON rag_folders
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_rag_files_updated_at BEFORE UPDATE ON rag_files
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_journal_blocks_updated_at BEFORE UPDATE ON journal_blocks
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_conversations_updated_at BEFORE UPDATE ON conversations
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ============================================================================
-- VIEWS
-- ============================================================================

-- Unified search view (for the Search tab)
CREATE VIEW search_results AS
SELECT
    'rag_chunk' AS source_type,
    c.id,
    f.filename AS title,
    c.content AS snippet,
    c.created_at,
    c.embedding,
    c.content_tsv
FROM rag_chunks c
JOIN rag_files f ON c.file_id = f.id

UNION ALL

SELECT
    'journal_block' AS source_type,
    id,
    label AS title,
    value AS snippet,
    created_at,
    embedding,
    value_tsv AS content_tsv
FROM journal_blocks

UNION ALL

SELECT
    'message' AS source_type,
    id,
    role AS title,
    content AS snippet,
    created_at,
    embedding,
    content_tsv
FROM messages;

-- ============================================================================
-- INITIAL DATA
-- ============================================================================

-- Create a default agent for testing
INSERT INTO agents (
    name,
    description,
    model_path,
    embedding_model_path,
    system_instructions
) VALUES (
    'Default Agent',
    'Default agent for testing',
    '/path/to/model',
    '/path/to/embedding/model',
    'You are a helpful AI assistant.'
);

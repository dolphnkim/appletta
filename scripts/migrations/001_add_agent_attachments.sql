-- Migration: Add agent_attachments table
-- Description: Links agents together in many-to-many relationships (memory agents, tool agents, etc.)
-- Date: 2025-11-11

-- ============================================================================
-- AGENT ATTACHMENTS
-- ============================================================================

CREATE TABLE IF NOT EXISTS agent_attachments (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    agent_id UUID NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    attached_agent_id UUID NOT NULL REFERENCES agents(id) ON DELETE CASCADE,

    -- Attachment metadata
    attachment_type VARCHAR(50) NOT NULL, -- 'memory', 'tool', 'reflection', etc.
    label VARCHAR(255) NOT NULL,

    -- Configuration
    priority INTEGER DEFAULT 0,
    enabled BOOLEAN DEFAULT TRUE,

    -- Timestamps
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),

    -- Ensure unique attachments
    UNIQUE(agent_id, attached_agent_id, attachment_type)
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_agent_attachments_agent ON agent_attachments(agent_id);
CREATE INDEX IF NOT EXISTS idx_agent_attachments_type ON agent_attachments(attachment_type);
CREATE INDEX IF NOT EXISTS idx_agent_attachments_enabled ON agent_attachments(enabled);

-- Auto-update trigger
CREATE TRIGGER update_agent_attachments_updated_at BEFORE UPDATE ON agent_attachments
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Migration: Add max_context_tokens to agents table
-- Description: Tracks the maximum context window size for each agent
-- Date: 2025-11-11

ALTER TABLE agents
ADD COLUMN IF NOT EXISTS max_context_tokens INTEGER DEFAULT 4096;

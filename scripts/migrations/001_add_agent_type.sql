-- Migration: Add agent_type field to agents table
-- Date: 2025-01-14
-- Description: Adds agent_type enum and column to support different agent categories

-- Create agent_type enum if it doesn't exist
DO $$ BEGIN
    CREATE TYPE agent_type AS ENUM ('main', 'memory', 'tool', 'reflection', 'other');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

-- Add agent_type column to agents table
ALTER TABLE agents
ADD COLUMN IF NOT EXISTS agent_type agent_type DEFAULT 'main';

-- Update existing agents to have 'main' type
UPDATE agents SET agent_type = 'main' WHERE agent_type IS NULL;

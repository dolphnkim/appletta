# Database Migration: Add is_template Field

## Overview
This migration adds the `is_template` field to the `agents` table, enabling template-based agent creation where the "New Agent" template remains pristine and any edits create a new agent.

## Running the Migration

### Step 1: Add the is_template Column
```bash
source .venv/bin/activate
python backend/migrate_add_is_template.py
```

### Step 2: Create the Template Agent
```bash
source .venv/bin/activate
python backend/ensure_template_agent.py
```

## What Changed

### Backend Changes:
- **Model**: Added `is_template` boolean field to `Agent` model (default: False)
- **Schemas**: Updated `AgentCreate`, `AgentUpdate`, and `AgentResponse` schemas
- **API**: The `to_dict()` method now includes `is_template` field

### Frontend Changes:
- **Types**: Added `is_template` to Agent, AgentCreate, and AgentUpdate interfaces
- **Logic**: Template agents now trigger "save-as" behavior instead of updates
- **Naming**: New agents from templates use the edited name or "New Agent (copy)"
- **Protection**: Template agents cannot be deleted

## How It Works

1. **Template Agent**: A special agent marked with `is_template=true` serves as a starting point
2. **Save-As Behavior**: Any edit to a template agent creates a new agent instead of updating
3. **Auto-Naming**: If the user changes the name, that's used; otherwise "New Agent (copy)" is created
4. **Navigation**: After saving, the UI switches to the newly created agent
5. **Template Preservation**: The original template always remains unchanged and available

## Notes

- Run these migrations before restarting the server
- Ensure at least one regular agent exists before running `ensure_template_agent.py`
- The template agent will use the first existing agent's settings as defaults

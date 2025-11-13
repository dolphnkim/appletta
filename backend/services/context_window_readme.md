# CONTEXT WINDOW/ MODAL
So the architecture is:

Calculate STICKY costs first:

System instructions
Tool definitions
Journal blocks list
RAG files list
Surfaced memories (per-turn)
Remaining budget = max_context_tokens - STICKY total

Fill with messages until we hit the remaining budget

Trim oldest messages when over budget

What I need to build:

Agent model:

Add max_context_tokens column (configurable)
Token counting utility:

Use tiktoken for accurate counts
Count tokens for each section
Context management in chat flow:

Count STICKY section tokens
Trim messages to fit remaining budget
Track what's in context for this breakdown
API endpoint:

GET /api/v1/conversations/{id}/context-window
Returns token breakdown per section
Returns actual content for modal display

Changes to be committed:
  (use "git restore --staged <file>..." to unstage)
	modified:   backend/api/routes/agents.py
	modified:   backend/api/routes/conversations.py
	modified:   backend/db/models/agent.py
	modified:   backend/requirements.txt
	modified:   backend/schemas/agent.py
	new file:   backend/services/token_counter.py
	modified:   scripts/schema.sql

Done! 🎉 I've implemented the complete shifting context window system!

What Was Built
Context Window Architecture:

STICKY section - Always in context:

System instructions
Tool definitions
Journal blocks list
Surfaced memories (per-turn)
SHIFTING section - Trimmed when over budget:

Conversation history (newest messages prioritized)
Oldest messages removed first when limit reached
Trimmed messages stay in database for memory retrieval
Agent Configuration:

Added max_context_tokens column (default: 4096)
Configurable per agent for different hardware/models
Set to 70-80% of model's true context to avoid degradation
Token Counting:

Created token_counter.py using tiktoken
Accurate counts for message formatting overhead
Handles tool calls, system messages, etc.
Context Trimming:

Count STICKY section tokens
Calculate remaining budget for messages
Include newest messages that fit
Trim oldest when over budget
API Endpoint:

GET /api/v1/conversations/{id}/context-window
Returns breakdown for your modal:
System Instructions (tokens + %)
Tools descriptions (tokens + %)
External summary (tokens + %)
Messages (tokens + %)
Database Changes Needed:

Run schema.sql to add max_context_tokens INTEGER DEFAULT 4096 to agents table
All committed and pushed! The system now mimics human working memory - a rolling window of recent context while older memories can be surfaced organically by the memory coordinator. 💜


# Persist iOS — Claude Code Handoff Spec

> Generated from the interactive prototype (`Persist iOS.html`).  
> This document maps every screen, component, and interaction to the existing FastAPI backend.

---

## 1. Overview

**Persist** is a personal iOS app for chatting with locally-running LLMs (via MLX) from anywhere. The backend is an existing FastAPI server (`backend/main.py`) with SQLite, serving agents, conversations, messages, and memory/RAG.

### Tech Stack Recommendation

| Layer | Choice | Rationale |
|---|---|---|
| App shell | **React Native + Expo** | Reuses existing TypeScript/React patterns; Expo Go for fast iteration |
| Navigation | React Navigation v7 | Industry standard, good drawer + modal support |
| State | Zustand | Lightweight, no boilerplate, matches current `useState` patterns |
| HTTP | `fetch` / `axios` | Already used in the frontend; SSE streaming needs native support |
| SSE streaming | `react-native-sse` or `EventSource` polyfill | Backend streams via SSE |
| Storage | `expo-secure-store` | Server URL, agent selection, user name |
| Markdown | `react-native-markdown-display` | Replaces custom inline renderer |

**Alternative**: Wrap the existing Vite/React frontend in **Capacitor** (`@capacitor/ios`). Faster to ship but less native feel.

---

## 2. Backend Connectivity

### Server URL
- Stored in `expo-secure-store` under key `persistServerUrl`
- Default: `http://localhost:8000`
- Configurable via the **Server** settings sheet in the drawer footer
- All API calls prefix with this URL

### Recommended remote access options
1. **Tailscale** *(recommended)* — install on Mac + iPhone; use Tailscale IP directly
2. **ngrok** — `ngrok http 8000`; paste HTTPS URL into Server settings
3. **Cloudflare Tunnel** — `cloudflared tunnel --url localhost:8000`

---

## 3. Screens & Navigation Structure

```
App
├── ChatView (default screen)
│   ├── ChatHeader
│   ├── MessagesList
│   │   ├── MessageBubble (user / assistant / memory)
│   │   └── EmptyState (when no messages)
│   ├── ChatInput (textarea + send/stop button)
│   ├── AgentDropdown (overlay, from header pill)
│   ├── ConversationsDrawer (left slide-in)
│   │   └── SwipeConvRow (swipe-to-delete)
│   ├── MemorySheet (bottom sheet)
│   │   └── MemoryBlockCard (pin / delete)
│   ├── AgentSettingsSheet (bottom sheet)
│   ├── ToolsSettingsSheet (bottom sheet)
│   └── ServerConnectionSheet (bottom sheet)
└── (future: TrainingView, InterpretabilityView)
```

---

## 4. API Reference

Base URL: `{SERVER_URL}/api/v1`

### Agents

| Action | Method | Endpoint | Notes |
|---|---|---|---|
| List agents | GET | `/agents/` | Returns `Agent[]`; filter `is_template=false` for user agents |
| Get agent | GET | `/agents/{id}` | Full agent config |
| Update agent | PATCH | `/agents/{id}` | Partial update (temp, top_p, system_instructions, etc.) |
| Clone agent | POST | `/agents/{id}/clone` | Returns new agent |

**Agent schema** (key fields):
```ts
interface Agent {
  id: string;
  name: string;
  description: string;
  model_path: string;
  adapter_path?: string;
  system_instructions: string;
  reasoning_enabled: boolean;
  temperature: number;        // 0–2
  seed?: number;
  max_output_tokens_enabled: boolean;
  max_output_tokens: number;  // default 8192
  top_p?: number;             // 0–1
  top_k?: number;
  embedding_model_path: string;
  embedding_dimensions: number;
  embedding_chunk_size: number;
  enabled_tools: string[];
  is_template: boolean;
}
```

---

### Conversations

| Action | Method | Endpoint | Notes |
|---|---|---|---|
| List conversations | GET | `/conversations/?agent_id={id}` | Returns `Conversation[]`, sorted by `updated_at` desc |
| Get conversation | GET | `/conversations/{id}` | |
| Create conversation | POST | `/conversations/` | Body: `{ agent_id, title }` |
| Update title | PATCH | `/conversations/{id}` | Body: `{ title }` |
| Delete | DELETE | `/conversations/{id}` | |
| Fork from message | POST | `/conversations/{id}/fork?message_id={msg_id}` | Returns new `Conversation` |

**Conversation schema**:
```ts
interface Conversation {
  id: string;
  agent_id: string;
  title: string;
  message_count: number;
  created_at: string;
  updated_at: string;
}
```

---

### Messages

| Action | Method | Endpoint | Notes |
|---|---|---|---|
| List messages | GET | `/conversations/{id}/messages` | Returns `Message[]` |
| Stream message | GET | `/conversations/{id}/stream?message={text}&_t={timestamp}` | SSE stream |
| Edit message | PATCH | `/conversations/{id}/messages/{msg_id}` | Body: `{ content }` |
| Delete message | DELETE | `/conversations/{id}/messages/{msg_id}` | |
| Regenerate | POST | `/conversations/{id}/messages/{msg_id}/regenerate` | |
| Save partial | POST | `/conversations/{id}/messages/partial` | Body: `{ content }` — saves stopped stream |

**Message schema**:
```ts
interface Message {
  id: string;
  conversation_id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  created_at: string;
  metadata?: {
    memory_narrative?: string;  // shown as memory bubble BEFORE assistant response
    partial?: boolean;
    unsaved?: boolean;
  };
}
```

**SSE event types** (from `sendStreamingMessage` in `ChatPanel.tsx`):
```
data: {"type": "memory_narrative", "content": "..."}   → show memory bubble
data: {"type": "status", "content": "Loading model..."}  → show as streaming text  
data: {"type": "content", "content": "chunk"}           → append to streaming bubble
data: {"type": "done", "user_message": {...}, "assistant_message": {...}}
data: {"type": "error", "error": "..."}
```

**Memory bubble ordering**: The `memory_narrative` event fires BEFORE the first `content` chunk. Render it as a distinct purple bubble above the assistant response.

---

### Memory / Journal Blocks

| Action | Method | Endpoint | Notes |
|---|---|---|---|
| List blocks | GET | `/agents/{id}/journal-blocks` | Returns `JournalBlock[]` |
| Update block | PATCH | `/agents/{id}/journal-blocks/{block_id}` | Body: `{ always_in_context: true }` for pin |
| Delete block | DELETE | `/agents/{id}/journal-blocks/{block_id}` | |
| Search blocks | GET | `/agents/{id}/journal-blocks/search?q={query}` | Semantic search via embeddings |

**JournalBlock schema**:
```ts
interface JournalBlock {
  id: string;
  agent_id: string;
  content: string;
  tags: string[];
  always_in_context: boolean;   // "pinned" in the UI
  created_at: string;
  updated_at: string;
}
```

---

## 5. Component Specs

### ChatHeader
- **Left**: hamburger → open `ConversationsDrawer`
- **Center**: truncated `conversation.title`
- **Right**: agent pill (name + green dot) → `AgentDropdown` overlay; brain icon → `MemorySheet`
- Agent pill shows `agent.name`; green dot = model is loaded/running

### ConversationsDrawer (left slide-in, 298px wide)
- **Header**: "Chats" title + `+` button
- `+` tap → inline `<input>` with auto-focus; Enter or "Add" to create; Esc to cancel
- **List**: `SwipeConvRow` × conversations
  - Swipe left → red delete button (70px)
  - Tap → `handleSelectConv(id)`; closes drawer
  - Pull-to-refresh → calls `GET /conversations/?agent_id={id}`
- **Footer** (above safe area):
  - ⚙️ Agent Settings → `AgentSettingsSheet`
  - 🔧 Tools Settings → `ToolsSettingsSheet`
  - 🌐 Server → `ConnectionSheet`

### MemorySheet (bottom sheet, h=630)
- Search bar → filters `content` and `tags` client-side (or calls search endpoint)
- **Pinned section** ("📌 Always in context") — blocks where `always_in_context=true`
- **All memories** — remaining blocks, newest first
- **Pin button** → `PATCH /agents/{id}/journal-blocks/{block_id}` `{ always_in_context: !current }`
- **Delete button** → `DELETE /agents/{id}/journal-blocks/{block_id}`

### AgentSettingsSheet (bottom sheet, h=660)
All fields call `PATCH /agents/{id}` on change (debounced 800ms):

| Control | Field | Type |
|---|---|---|
| Slider 0–2 | `temperature` | float |
| Slider 0–1 | `top_p` | float |
| Slider 1–200 | `top_k` | int |
| Number input | `max_output_tokens` | int |
| Toggle | `reasoning_enabled` | bool |
| Textarea | `system_instructions` | string |

### ToolsSettingsSheet (bottom sheet, h=540)
Each toggle calls `PATCH /agents/{id}` `{ enabled_tools: [...] }`:

| Tool ID | Label |
|---|---|
| `websearch` | Web search |
| `filebrowser` | File browser |
| `codeexec` | Code executor |
| `calendar` | Calendar |
| `rag` | RAG retrieval |
| `memory` | Memory agent |
| `router_logging` | Router logging |

### MessageBubble
- **User**: right-aligned, `accent` background, plain text
- **Assistant**: left-aligned, `surface` background, **markdown rendered**
  - Bold: `**text**`
  - Inline code: `` `code` ``
  - Bullet lists: lines starting with `- ` or `* `
- **Memory**: left-aligned, purple tinted, italic — rendered between user message and assistant response
- **Long-press** (500ms): context menu with Copy, Fork, Delete
  - Copy → `navigator.clipboard.writeText(content)`
  - Fork → `POST /conversations/{id}/fork?message_id={msg_id}` → new conversation
  - Delete → `DELETE /conversations/{id}/messages/{msg_id}`

### ChatInput
- `<textarea>` with auto-resize (max 120px)
- Enter = newline (no submit on Enter)
- Send button → `POST` streaming message
- Stop button (while streaming) → close SSE, `POST /conversations/{id}/messages/partial`

### EmptyState (when `messages.length === 0`)
- Agent avatar orb + agent name + subtitle
- 4 suggestion chips → pre-fill input and immediately send

---

## 6. State Management (Zustand stores)

```ts
// agentStore
{ agents, activeAgentId, setActiveAgent, fetchAgents, updateAgent }

// conversationStore  
{ conversations, activeConvId, selectConv, createConv, deleteConv, forkConv, fetchConvs }

// messageStore
{ messagesByConvId, addMessage, deleteMessage, fetchMessages }

// streamStore
{ isStreaming, streamText, startStream, stopStream }

// settingsStore
{ serverUrl, setServerUrl }  // persisted to SecureStore
```

---

## 7. Streaming Implementation (React Native)

The backend uses SSE (`text/event-stream`). React Native's `fetch` supports streaming via `response.body`:

```ts
import RNEventSource from 'react-native-sse';

const es = new RNEventSource(`${SERVER_URL}/api/v1/conversations/${convId}/stream?message=${encodeURIComponent(text)}`);

es.addEventListener('message', (e) => {
  const data = JSON.parse(e.data);
  if (data.type === 'memory_narrative') addMemoryBubble(data.content);
  else if (data.type === 'content') appendStreamText(data.content);
  else if (data.type === 'done') finalizeMessage(data.user_message, data.assistant_message);
  else if (data.type === 'error') handleError(data.error);
});
```

---

## 8. Key Decisions & Notes

1. **Memory bubble ordering** — always render `memory_narrative` bubbles BEFORE the assistant response that follows them. The SSE fires `memory_narrative` first, so insert it as a placeholder and let the assistant response render below.

2. **Always-in-context blocks** — the `always_in_context` field on `JournalBlock` maps to the pin button in the Memory sheet. These are injected into every request context by the backend automatically.

3. **Agent selection** — the active agent is persisted to `localStorage`/`SecureStore` under `selectedAgentId`. On first launch, fetch agents and auto-select the first non-template agent.

4. **Conversation persistence** — `currentConversationId` is persisted to `localStorage`/`SecureStore` so the app reopens to the last active chat.

5. **Streaming stop** — when the user stops a stream, save partial content via `POST .../messages/partial` so it appears in the conversation history.

6. **Server URL** — persisted to `SecureStore`. All API calls should read this at call time (not at startup) so changing the URL takes immediate effect.

7. **Model loading** — the first message to an agent may trigger MLX model loading. The backend sends a `status` event (`"Loading model..."`) before content starts. Show this as a status indicator in the streaming bubble, then clear it when real content arrives.

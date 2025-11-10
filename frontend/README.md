# Appletta Frontend

React + TypeScript frontend for the Appletta agent settings interface.

## Features

- **Agent Settings Management**: Full CRUD interface for managing AI agents
- **File Browser**: Select models, adapters, and embedding models from filesystem
- **System Instructions Editor**: Full-screen modal for editing agent prompts
- **LLM Configuration**:
  - Reasoning mode toggle
  - Temperature slider (0.0-2.0)
  - Random seed input
  - Max output tokens with toggle
- **Embedding Configuration**:
  - Embedding model selection
  - Dimensions and chunk size controls
- **Agent Operations**:
  - Clone agents
  - Export/import .af files
  - Delete agents

## Tech Stack

- **React 18** with TypeScript
- **Vite** for build tooling
- **CSS** for component styling
- **Fetch API** for backend communication

## Project Structure

```
frontend/
├── src/
│   ├── components/
│   │   └── AgentSettings/
│   │       ├── AgentSettings.tsx       # Main container
│   │       ├── AgentHeader.tsx         # Name + dropdown menu
│   │       ├── EditableField.tsx       # Reusable editable field
│   │       ├── FilePicker.tsx          # Filesystem browser
│   │       ├── SystemInstructionsField.tsx
│   │       ├── SystemInstructionsModal.tsx
│   │       ├── LLMConfig.tsx           # LLM settings section
│   │       ├── EmbeddingConfig.tsx     # Embedding settings
│   │       └── *.css                   # Component styles
│   ├── api/
│   │   └── agentAPI.ts                 # Backend API client
│   ├── hooks/
│   │   └── useAgent.ts                 # Agent state management
│   ├── types/
│   │   └── agent.ts                    # TypeScript types
│   ├── App.tsx
│   ├── main.tsx
│   └── index.css
└── package.json
```

## Getting Started

### Install dependencies
```bash
cd frontend
npm install
```

### Development server
```bash
npm run dev
```

The app will be available at `http://localhost:5173`

### Build for production
```bash
npm run build
```

### Preview production build
```bash
npm run preview
```

## API Integration

The frontend expects a backend API at `/api/v1` with the following endpoints:

- `GET /api/v1/agents` - List all agents
- `GET /api/v1/agents/:id` - Get agent by ID
- `POST /api/v1/agents` - Create new agent
- `PATCH /api/v1/agents/:id` - Update agent
- `DELETE /api/v1/agents/:id` - Delete agent
- `POST /api/v1/agents/:id/clone` - Clone agent
- `GET /api/v1/agents/:id/export` - Export .af file
- `POST /api/v1/agents/import` - Import .af file
- `GET /api/v1/files/browse?path=...` - Browse filesystem
- `GET /api/v1/files/validate-model?path=...` - Validate model path
- `GET /api/v1/files/suggested-paths` - Get suggested model paths

See `src/api/agentAPI.ts` for full API client implementation.

## Components

### AgentSettings
Main container component that manages agent state and coordinates all sub-components.

**Props:**
- `agentId: string` - ID of the agent to display
- `onDelete?: () => void` - Callback when agent is deleted
- `onClone?: (newAgentId: string) => void` - Callback when agent is cloned

### AgentHeader
Agent name with inline editing and dropdown menu (clone, delete, export).

### FilePicker
Filesystem browser dropdown for selecting model paths.

### SystemInstructionsModal
Full-screen modal for editing agent system instructions with character count.

### LLMConfig / EmbeddingConfig
Collapsible sections with various controls (toggles, sliders, inputs).

## Styling

All components use CSS with a dark theme:
- Background: `#1e1e1e`
- Text: `#e0e0e0`
- Accents: `#0066cc` (blue), `#f48771` (red/orange)
- Borders: `#444`

## Next Steps

- [ ] Add routing for multiple agents
- [ ] Implement agent list/sidebar
- [ ] Add agent start/stop controls
- [ ] WebSocket integration for streaming responses
- [ ] Error boundaries and loading states
- [ ] Form validation
- [ ] Unit tests
- [ ] E2E tests

## Development Notes

- The `useAgent` hook handles all agent CRUD operations
- File picker uses filesystem browsing API (requires backend support)
- Modal uses portal pattern for proper z-index layering
- All forms use controlled components for real-time updates

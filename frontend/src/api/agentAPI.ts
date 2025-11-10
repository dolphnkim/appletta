import type { Agent, AgentCreate, AgentUpdate, FileBrowserResponse } from '../types/agent';

const API_BASE = '/api/v1';

// Helper function for fetch with error handling
async function fetchAPI<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${url}`, {
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
    ...options,
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
    throw new Error(error.detail || `HTTP ${response.status}`);
  }

  return response.json();
}

export const agentAPI = {
  // List all agents
  list: (): Promise<Agent[]> =>
    fetchAPI('/agents'),

  // Get specific agent
  get: (id: string): Promise<Agent> =>
    fetchAPI(`/agents/${id}`),

  // Create new agent
  create: (data: AgentCreate): Promise<Agent> =>
    fetchAPI('/agents', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  // Update agent
  update: (id: string, data: AgentUpdate): Promise<Agent> =>
    fetchAPI(`/agents/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),

  // Delete agent
  delete: (id: string): Promise<void> =>
    fetchAPI(`/agents/${id}`, {
      method: 'DELETE',
    }),

  // Clone agent
  clone: (id: string): Promise<Agent> =>
    fetchAPI(`/agents/${id}/clone`, {
      method: 'POST',
    }),

  // Export agent as .af file
  export: async (id: string): Promise<Blob> => {
    const response = await fetch(`${API_BASE}/agents/${id}/export`);
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    return response.blob();
  },

  // Import agent from .af file
  import: (file: File): Promise<Agent> => {
    const formData = new FormData();
    formData.append('file', file);
    return fetch(`${API_BASE}/agents/import`, {
      method: 'POST',
      body: formData,
    }).then(res => res.json());
  },
};

export const filesAPI = {
  // Browse filesystem
  browse: (path?: string): Promise<FileBrowserResponse> =>
    fetchAPI(`/files/browse${path ? `?path=${encodeURIComponent(path)}` : ''}`),

  // Validate model path
  validate: (path: string): Promise<{ valid: boolean; message?: string }> =>
    fetchAPI(`/files/validate-model?path=${encodeURIComponent(path)}`),

  // Get suggested paths
  getSuggestedPaths: (): Promise<string[]> =>
    fetchAPI('/files/suggested-paths'),
};

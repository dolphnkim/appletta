import type { AgentAttachment, AgentAttachmentCreate, AgentAttachmentUpdate } from '../types/agentAttachment';

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

export const agentAttachmentsAPI = {
  // List all attachments for an agent
  list: (agentId: string, attachmentType?: string, enabledOnly = true): Promise<AgentAttachment[]> => {
    const params = new URLSearchParams({ agent_id: agentId });
    if (attachmentType) params.append('attachment_type', attachmentType);
    if (!enabledOnly) params.append('enabled_only', 'false');
    return fetchAPI(`/agent-attachments/?${params.toString()}`);
  },

  // Get specific attachment
  get: (attachmentId: string): Promise<AgentAttachment> =>
    fetchAPI(`/agent-attachments/${attachmentId}`),

  // Create new attachment
  create: (data: AgentAttachmentCreate): Promise<AgentAttachment> =>
    fetchAPI('/agent-attachments/', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  // Update attachment
  update: (attachmentId: string, data: AgentAttachmentUpdate): Promise<AgentAttachment> =>
    fetchAPI(`/agent-attachments/${attachmentId}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),

  // Delete attachment
  delete: (attachmentId: string): Promise<{ message: string }> =>
    fetchAPI(`/agent-attachments/${attachmentId}`, {
      method: 'DELETE',
    }),
};

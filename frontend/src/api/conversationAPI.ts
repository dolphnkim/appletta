import type {
  Conversation,
  ConversationCreate,
  Message,
  ChatRequest,
  ChatResponse,
} from '../types/conversation';

const API_BASE = 'http://localhost:8000/api/v1';

async function fetchAPI(path: string, options?: RequestInit) {
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(error.detail || 'API request failed');
  }

  return response.json();
}

export const conversationAPI = {
  // Conversations
  create: (data: ConversationCreate): Promise<Conversation> =>
    fetchAPI('/conversations/', { method: 'POST', body: JSON.stringify(data) }),

  list: (agentId?: string): Promise<Conversation[]> =>
    fetchAPI(`/conversations/${agentId ? `?agent_id=${agentId}` : ''}`),

  get: (id: string): Promise<Conversation> =>
    fetchAPI(`/conversations/${id}`),

  update: (id: string, data: { title?: string }): Promise<Conversation> =>
    fetchAPI(`/conversations/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),

  delete: (id: string): Promise<{ message: string }> =>
    fetchAPI(`/conversations/${id}`, { method: 'DELETE' }),

  // Messages
  getMessages: (conversationId: string): Promise<Message[]> =>
    fetchAPI(`/conversations/${conversationId}/messages`),

  // Chat
  sendMessage: (conversationId: string, request: ChatRequest): Promise<ChatResponse> =>
    fetchAPI(`/conversations/${conversationId}/chat`, {
      method: 'POST',
      body: JSON.stringify(request),
    }),
};

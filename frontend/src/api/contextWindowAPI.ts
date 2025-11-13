const API_BASE_URL = 'http://localhost:8000/api/v1';

export interface ContextSection {
  name: string;
  tokens: number;
  percentage: number;
  content?: string;
}

export interface ContextWindowBreakdown {
  sections: ContextSection[];
  total_tokens: number;
  max_context_tokens: number;
  percentage_used: number;
}

export const contextWindowAPI = {
  async getBreakdown(conversationId: string): Promise<ContextWindowBreakdown> {
    const response = await fetch(
      `${API_BASE_URL}/conversations/${conversationId}/context-window`
    );

    if (!response.ok) {
      throw new Error('Failed to fetch context window breakdown');
    }

    return response.json();
  },

  async getAgentBreakdown(agentId: string): Promise<ContextWindowBreakdown> {
    const response = await fetch(
      `${API_BASE_URL}/agents/${agentId}/context-window`
    );

    if (!response.ok) {
      throw new Error('Failed to fetch agent context window breakdown');
    }

    return response.json();
  }
};

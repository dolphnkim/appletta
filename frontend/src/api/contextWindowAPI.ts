const API_BASE_URL = '/api/v1';

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
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 10000); // 10 second timeout

    try {
      const response = await fetch(
        `${API_BASE_URL}/conversations/${conversationId}/context-window`,
        { signal: controller.signal }
      );

      clearTimeout(timeoutId);

      if (!response.ok) {
        throw new Error('Failed to fetch context window breakdown');
      }

      return response.json();
    } catch (error) {
      clearTimeout(timeoutId);
      if (error instanceof Error && error.name === 'AbortError') {
        throw new Error('Request timeout - memory system may be slow');
      }
      throw error;
    }
  },

  async getAgentBreakdown(agentId: string): Promise<ContextWindowBreakdown> {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 10000); // 10 second timeout

    try {
      const response = await fetch(
        `${API_BASE_URL}/agents/${agentId}/context-window`,
        { signal: controller.signal }
      );

      clearTimeout(timeoutId);

      if (!response.ok) {
        throw new Error('Failed to fetch agent context window breakdown');
      }

      return response.json();
    } catch (error) {
      clearTimeout(timeoutId);
      if (error instanceof Error && error.name === 'AbortError') {
        throw new Error('Request timeout - memory system may be slow');
      }
      throw error;
    }
  }
};

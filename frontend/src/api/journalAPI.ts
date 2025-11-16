import type { JournalBlock, JournalBlockCreate, JournalBlockUpdate } from '../types/journal';

const API_BASE = '/api/v1';

export const journalAPI = {
  /**
   * List all journal blocks for an agent
   */
  async list(agentId: string): Promise<JournalBlock[]> {
    const response = await fetch(`${API_BASE}/journal-blocks?agent_id=${agentId}`);
    if (!response.ok) {
      throw new Error('Failed to fetch journal blocks');
    }
    return response.json();
  },

  /**
   * Get a specific journal block
   */
  async get(agentId: string, blockId: string): Promise<JournalBlock> {
    const response = await fetch(`${API_BASE}/journal-blocks/${blockId}`);
    if (!response.ok) {
      throw new Error('Failed to fetch journal block');
    }
    return response.json();
  },

  /**
   * Create a new journal block
   */
  async create(agentId: string, data: JournalBlockCreate): Promise<JournalBlock> {
    const response = await fetch(`${API_BASE}/journal-blocks`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        agent_id: agentId,
        ...data,
      }),
    });
    if (!response.ok) {
      const errorText = await response.text();
      let errorMsg = 'Failed to create journal block';
      try {
        const error = JSON.parse(errorText);
        errorMsg = error.detail || errorMsg;
      } catch {
        errorMsg = `${errorMsg}: ${response.status} ${response.statusText}`;
      }
      console.error('Journal API Error:', errorText);
      throw new Error(errorMsg);
    }
    return response.json();
  },

  /**
   * Update a journal block
   */
  async update(agentId: string, blockId: string, data: JournalBlockUpdate): Promise<JournalBlock> {
    const response = await fetch(`${API_BASE}/journal-blocks/${blockId}`, {
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(data),
    });
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Failed to update journal block');
    }
    return response.json();
  },

  /**
   * Delete a journal block
   */
  async delete(agentId: string, blockId: string): Promise<void> {
    const response = await fetch(`${API_BASE}/journal-blocks/${blockId}`, {
      method: 'DELETE',
    });
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Failed to delete journal block');
    }
  },
};

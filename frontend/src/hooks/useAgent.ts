import { useState, useEffect } from 'react';
import { agentAPI } from '../api/agentAPI';
import type { Agent, AgentUpdate } from '../types/agent';

export function useAgent(agentId: string) {
  const [agent, setAgent] = useState<Agent | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadAgent();
  }, [agentId]);

  const loadAgent = async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await agentAPI.get(agentId);
      setAgent(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load agent');
    } finally {
      setLoading(false);
    }
  };

  const updateAgent = async (updates: AgentUpdate) => {
    if (!agent) return;

    try {
      setError(null);
      const updated = await agentAPI.update(agent.id, updates);
      setAgent(updated);
      return updated;
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update agent');
      throw err;
    }
  };

  const cloneAgent = async () => {
    if (!agent) return;

    try {
      setError(null);
      return await agentAPI.clone(agent.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to clone agent');
      throw err;
    }
  };

  const deleteAgent = async () => {
    if (!agent) return;

    try {
      setError(null);
      await agentAPI.delete(agent.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete agent');
      throw err;
    }
  };

  const exportAgent = async () => {
    if (!agent) return;

    try {
      setError(null);
      const blob = await agentAPI.export(agent.id);

      // Create download link
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${agent.name}.af`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to export agent');
      throw err;
    }
  };

  return {
    agent,
    loading,
    error,
    updateAgent,
    cloneAgent,
    deleteAgent,
    exportAgent,
    reload: loadAgent,
  };
}

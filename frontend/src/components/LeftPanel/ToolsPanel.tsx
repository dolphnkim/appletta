import { useState, useEffect } from 'react';
import './ToolsPanel.css';
import { agentAPI } from '../../api/agentAPI';
import type { Tool } from '../../types/agent';

interface ToolsPanelProps {
  agentId: string;
  enabledTools: string[];
  onToolsChange: (enabledTools: string[]) => void;
}

export default function ToolsPanel({ agentId, enabledTools, onToolsChange }: ToolsPanelProps) {
  const [availableTools, setAvailableTools] = useState<Tool[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchTools = async () => {
      try {
        setLoading(true);
        setError(null);
        const response = await agentAPI.getAvailableTools();
        setAvailableTools(response.tools);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load tools');
      } finally {
        setLoading(false);
      }
    };

    fetchTools();
  }, []);

  const handleToggleTool = (toolName: string) => {
    const isEnabled = enabledTools.includes(toolName);

    let newEnabledTools: string[];
    if (isEnabled) {
      // Remove tool
      newEnabledTools = enabledTools.filter(t => t !== toolName);
    } else {
      // Add tool
      newEnabledTools = [...enabledTools, toolName];
    }

    onToolsChange(newEnabledTools);
  };

  if (loading) {
    return (
      <div className="tools-panel">
        <div className="tools-loading">Loading tools...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="tools-panel">
        <div className="tools-error">Error: {error}</div>
      </div>
    );
  }

  return (
    <div className="tools-panel">
      <div className="tools-header">
        <h2 className="tools-title">Available Tools</h2>
        <p className="tools-description">
          Configure which tools this agent can use
        </p>
      </div>

      <div className="tools-list">
        {availableTools.map((tool) => {
          const isEnabled = enabledTools.includes(tool.name);

          return (
            <div key={tool.name} className="tool-item">
              <div className="tool-header">
                <div className="tool-name">{tool.name}</div>
                <button
                  className={`tool-toggle ${isEnabled ? 'enabled' : 'disabled'}`}
                  onClick={() => handleToggleTool(tool.name)}
                  title={isEnabled ? 'Disable tool' : 'Enable tool'}
                >
                  {isEnabled ? '✓' : '○'}
                </button>
              </div>
              <div className="tool-description">{tool.description}</div>
            </div>
          );
        })}
      </div>

      {enabledTools.length === 0 && (
        <div className="tools-notice">
          No tools enabled. Enable tools to allow this agent to interact with its environment.
        </div>
      )}
    </div>
  );
}

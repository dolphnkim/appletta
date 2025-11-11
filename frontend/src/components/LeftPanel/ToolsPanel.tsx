import { useState, useEffect } from 'react';
import './ToolsPanel.css';

interface ToolsPanelProps {
  agentId: string;
}

interface Tool {
  name: string;
  description: string;
  parameters: any;
  enabled: boolean;
}

export default function ToolsPanel({ agentId }: ToolsPanelProps) {
  const [tools, setTools] = useState<Tool[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // For now, show the built-in journal block tools
    // In the future, this would fetch from an API
    setTools([
      {
        name: 'create_journal_block',
        description: 'Create a new journal block to store thoughts, insights, or important information',
        parameters: {
          label: 'string',
          value: 'string',
          description: 'string (optional)',
        },
        enabled: true,
      },
      {
        name: 'read_journal_block',
        description: 'Read the full content of a journal block by its ID',
        parameters: {
          block_id: 'string',
        },
        enabled: true,
      },
      {
        name: 'update_journal_block',
        description: 'Update the value of an existing journal block',
        parameters: {
          block_id: 'string',
          value: 'string',
        },
        enabled: true,
      },
      {
        name: 'delete_journal_block',
        description: 'Delete a journal block permanently',
        parameters: {
          block_id: 'string',
        },
        enabled: true,
      },
      {
        name: 'list_journal_blocks',
        description: 'Get a list of all journal blocks with their metadata',
        parameters: {},
        enabled: true,
      },
    ]);
    setLoading(false);
  }, [agentId]);

  if (loading) {
    return (
      <div className="tools-panel">
        <div className="tools-loading">Loading tools...</div>
      </div>
    );
  }

  return (
    <div className="tools-panel">
      <div className="tools-header">
        <h2 className="tools-title">Available Tools</h2>
        <p className="tools-description">
          Tools that this agent can use to interact with its environment
        </p>
      </div>

      <div className="tools-list">
        {tools.map((tool) => (
          <div key={tool.name} className="tool-item">
            <div className="tool-header">
              <div className="tool-name">{tool.name}</div>
              <div className={`tool-status ${tool.enabled ? 'enabled' : 'disabled'}`}>
                {tool.enabled ? '✓' : '○'}
              </div>
            </div>
            <div className="tool-description">{tool.description}</div>
            <div className="tool-parameters">
              <div className="tool-parameters-label">Parameters:</div>
              <div className="tool-parameters-list">
                {Object.entries(tool.parameters).length === 0 ? (
                  <div className="tool-parameter">None</div>
                ) : (
                  Object.entries(tool.parameters).map(([param, type]) => (
                    <div key={param} className="tool-parameter">
                      <span className="param-name">{param}</span>
                      <span className="param-type">{type as string}</span>
                    </div>
                  ))
                )}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

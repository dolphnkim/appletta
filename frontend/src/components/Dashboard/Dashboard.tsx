import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import type { Agent } from '../../types/agent';
import './Dashboard.css';

export default function Dashboard() {
  const navigate = useNavigate();
  const [agents, setAgents] = useState<Agent[]>([]);
  const [selectedAgentId, setSelectedAgentId] = useState<string | null>(() =>
    localStorage.getItem('selectedAgentId')
  );

  useEffect(() => {
    fetchAgents();
  }, []);

  const fetchAgents = async () => {
    try {
      const response = await fetch('http://localhost:8000/api/v1/agents/');
      const agentsData = await response.json();
      setAgents(agentsData);

      // Auto-select first non-template agent if none selected
      if (!selectedAgentId && agentsData.length > 0) {
        const nonTemplate = agentsData.find((a: Agent) => !a.is_template);
        if (nonTemplate) {
          setSelectedAgentId(nonTemplate.id);
          localStorage.setItem('selectedAgentId', nonTemplate.id);
        }
      }
    } catch (error) {
      console.error('Failed to fetch agents:', error);
    }
  };

  const handleAgentSelect = (agentId: string) => {
    setSelectedAgentId(agentId);
    localStorage.setItem('selectedAgentId', agentId);
  };

  const selectedAgent = agents.find(a => a.id === selectedAgentId);

  return (
    <div className="dashboard">
      <header className="dashboard-header">
        <h1>🍎 Appletta</h1>
        <p className="dashboard-subtitle">AI Research & Development Platform</p>
      </header>

      <div className="dashboard-agent-selector">
        <label>Active Agent:</label>
        <select
          value={selectedAgentId || ''}
          onChange={(e) => handleAgentSelect(e.target.value)}
        >
          {agents.filter(a => !a.is_template).map(agent => (
            <option key={agent.id} value={agent.id}>
              {agent.name}
            </option>
          ))}
        </select>
        {selectedAgent && (
          <span className="agent-model">{selectedAgent.model_path}</span>
        )}
      </div>

      <div className="dashboard-grid">
        {/* Chat Module */}
        <div
          className="dashboard-card chat-card"
          onClick={() => navigate('/chat')}
        >
          <div className="card-icon">💬</div>
          <h3>Chat</h3>
          <p>Converse with your agent, manage conversations, and test behaviors.</p>
          <div className="card-stats">
            <span>Real-time streaming</span>
            <span>Tool wizard</span>
            <span>Memory integration</span>
          </div>
        </div>

        {/* Training Module */}
        <div
          className="dashboard-card training-card"
          onClick={() => navigate('/training')}
        >
          <div className="card-icon">🧪</div>
          <h3>Training Lab</h3>
          <p>Fine-tune models with LoRA, manage datasets, and debug MoE routers.</p>
          <div className="card-stats">
            <span>Expert-level LoRA</span>
            <span>Router lens</span>
            <span>Balance losses</span>
          </div>
        </div>

        {/* Memory/Database Module */}
        <div
          className="dashboard-card memory-card"
          onClick={() => navigate('/memory')}
        >
          <div className="card-icon">🧠</div>
          <h3>Memory Bank</h3>
          <p>Explore embeddings, search memories, and manage knowledge bases.</p>
          <div className="card-stats">
            <span>Semantic search</span>
            <span>RAG folders</span>
            <span>Journal blocks</span>
          </div>
        </div>

        {/* Agent Configuration Module */}
        <div
          className="dashboard-card agents-card"
          onClick={() => navigate('/agents')}
        >
          <div className="card-icon">🤖</div>
          <h3>Agent Workshop</h3>
          <p>Configure agents, system prompts, personas, and tool permissions.</p>
          <div className="card-stats">
            <span>System instructions</span>
            <span>Temperature tuning</span>
            <span>Tool enablement</span>
          </div>
        </div>

        {/* Interpretability Module */}
        <div
          className="dashboard-card analytics-card"
          onClick={() => navigate('/analytics')}
        >
          <div className="card-icon">🔬</div>
          <h3>Interpretability</h3>
          <p>Track usage patterns, expert activations, and persona consistency.</p>
          <div className="card-stats">
            <span>Expert histograms</span>
            <span>Response metrics</span>
            <span>Drift detection</span>
          </div>
        </div>

        {/* Logs Module */}
        <div
          className="dashboard-card logs-card"
          onClick={() => navigate('/logs')}
        >
          <div className="card-icon">📜</div>
          <h3>Logs & History</h3>
          <p>Browse JSONL conversation logs, training runs, and system events.</p>
          <div className="card-stats">
            <span>JSONL viewer</span>
            <span>Filter & search</span>
            <span>Export data</span>
          </div>
        </div>

        {/* VS Code Integration Module */}
        <div
          className="dashboard-card vscode-card"
          onClick={() => navigate('/vscode')}
        >
          <div className="card-icon">⚡</div>
          <h3>VS Code Integration</h3>
          <p>Serve local MLX models as an OpenAI-compatible API for VS Code extensions.</p>
          <div className="card-stats">
            <span>OpenAI API compatible</span>
            <span>Local inference</span>
            <span>Continue.dev ready</span>
          </div>
        </div>
      </div>

      <footer className="dashboard-footer">
        <div className="footer-status">
          <span className="status-indicator online"></span>
          <span>MLX Server: Running</span>
        </div>
        <div className="footer-info">
          <span>Apple Silicon Optimized</span>
          <span>•</span>
          <span>Local-first AI Research</span>
        </div>
      </footer>
    </div>
  );
}

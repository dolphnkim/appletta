import { useState } from 'react';
import AgentAttachments from './AgentAttachments';
import './AgentManagement.css';

interface AgentManagementProps {
  agentId: string;
  onCreateAgent: () => void;
  onManageAgents: () => void;
}

export default function AgentManagement({ agentId, onCreateAgent, onManageAgents }: AgentManagementProps) {
  const [isExpanded, setIsExpanded] = useState(false);

  return (
    <div className="config-section">
      <button
        className="config-section-header"
        onClick={() => setIsExpanded(!isExpanded)}
      >
        <span className="config-section-title">AGENT MANAGEMENT</span>
        <svg
          className={`expand-icon ${isExpanded ? 'expanded' : ''}`}
          width="12"
          height="12"
          viewBox="0 0 16 16"
          fill="currentColor"
        >
          <path d="M4.427 7.427l3.396 3.396a.25.25 0 00.354 0l3.396-3.396A.25.25 0 0011.396 7H4.604a.25.25 0 00-.177.427z" />
        </svg>
      </button>

      {isExpanded && (
        <div className="config-section-content">
          {/* Agent Attachments with integrated menu */}
          <div className="agent-management-section">
            <label className="config-label">Attach Agents</label>
            <AgentAttachments
              agentId={agentId}
              onCreateAgent={onCreateAgent}
              onManageAgents={onManageAgents}
            />
          </div>
        </div>
      )}
    </div>
  );
}

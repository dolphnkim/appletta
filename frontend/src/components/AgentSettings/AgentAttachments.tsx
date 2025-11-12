import { useState, useEffect } from 'react';
import { agentAPI } from '../../api/agentAPI';
import { agentAttachmentsAPI } from '../../api/agentAttachmentsAPI';
import type { Agent } from '../../types/agent';
import type { AgentAttachment } from '../../types/agentAttachment';
import './AgentAttachments.css';

interface AgentAttachmentsProps {
  agentId: string;
  onCreateAgent?: () => void;
  onManageAgents?: () => void;
}

export default function AgentAttachments({ agentId, onCreateAgent, onManageAgents }: AgentAttachmentsProps) {
  const [attachments, setAttachments] = useState<AgentAttachment[]>([]);
  const [availableAgents, setAvailableAgents] = useState<Agent[]>([]);
  const [selectedAgentId, setSelectedAgentId] = useState<string>('');
  const [attachmentType, setAttachmentType] = useState<string>('memory');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showMenu, setShowMenu] = useState(false);

  useEffect(() => {
    loadData();
  }, [agentId]);

  const loadData = async () => {
    try {
      setLoading(true);
      setError(null);
      const [attachmentsData, agentsData] = await Promise.all([
        agentAttachmentsAPI.list(agentId, undefined, false), // Get all attachments including disabled
        agentAPI.list(),
      ]);
      setAttachments(attachmentsData);
      // Filter out current agent and already attached agents
      const attachedIds = new Set(attachmentsData.map(a => a.attached_agent_id));
      const filtered = agentsData.filter(a => a.id !== agentId && !attachedIds.has(a.id));
      setAvailableAgents(filtered);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load data');
    } finally {
      setLoading(false);
    }
  };

  const handleAttach = async () => {
    if (!selectedAgentId) return;

    try {
      setError(null);
      const newAttachment = await agentAttachmentsAPI.create({
        agent_id: agentId,
        attached_agent_id: selectedAgentId,
        attachment_type: attachmentType,
      });
      setAttachments([...attachments, newAttachment]);
      setSelectedAgentId('');
      setShowMenu(false);
      // Refresh available agents
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to attach agent');
    }
  };

  const handleDetach = async (attachmentId: string) => {
    if (!confirm('Detach this agent?')) return;

    try {
      setError(null);
      await agentAttachmentsAPI.delete(attachmentId);
      setAttachments(attachments.filter(a => a.id !== attachmentId));
      await loadData(); // Refresh available agents
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to detach agent');
    }
  };

  const handleToggleEnabled = async (attachment: AgentAttachment) => {
    try {
      setError(null);
      const updated = await agentAttachmentsAPI.update(attachment.id, {
        enabled: !attachment.enabled,
      });
      setAttachments(attachments.map(a => a.id === attachment.id ? updated : a));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update attachment');
    }
  };

  if (loading) {
    return <div className="agent-attachments-loading">Loading attachments...</div>;
  }

  return (
    <div className="agent-attachments">
      {error && (
        <div className="attachment-error">
          {error}
          <button onClick={() => setError(null)} className="dismiss-error">×</button>
        </div>
      )}

      {/* Attach agent controls - always visible */}
      <div className="attach-agent-row">
        <div className="attach-controls">
          <select
            className="agent-select"
            value={selectedAgentId}
            onChange={(e) => setSelectedAgentId(e.target.value)}
            disabled={availableAgents.length === 0}
          >
            <option value="">
              {availableAgents.length === 0 ? 'No agents available' : 'Select agent to attach...'}
            </option>
            {availableAgents.map(agent => (
              <option key={agent.id} value={agent.id}>
                {agent.name}
              </option>
            ))}
          </select>
          <select
            className="type-select"
            value={attachmentType}
            onChange={(e) => setAttachmentType(e.target.value)}
          >
            <option value="memory">Memory</option>
            <option value="tool">Tool</option>
            <option value="reflection">Reflection</option>
            <option value="other">Other</option>
          </select>

          {/* Three-dot menu */}
          <div className="attachments-menu-container">
            <button
              className="three-dot-menu-button"
              onClick={() => setShowMenu(!showMenu)}
              title="Actions"
            >
              <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
                <circle cx="8" cy="2.5" r="1.5" />
                <circle cx="8" cy="8" r="1.5" />
                <circle cx="8" cy="13.5" r="1.5" />
              </svg>
            </button>
            {showMenu && (
              <div className="dropdown-menu">
                <button
                  className="dropdown-menu-item"
                  onClick={handleAttach}
                  disabled={!selectedAgentId}
                >
                  <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor">
                    <path d="M8 2a.5.5 0 0 1 .5.5v5h5a.5.5 0 0 1 0 1h-5v5a.5.5 0 0 1-1 0v-5h-5a.5.5 0 0 1 0-1h5v-5A.5.5 0 0 1 8 2Z" />
                  </svg>
                  Attach Agent
                </button>
                {onCreateAgent && (
                  <button
                    className="dropdown-menu-item"
                    onClick={() => {
                      setShowMenu(false);
                      onCreateAgent();
                    }}
                  >
                    <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor">
                      <path d="M8 2a.5.5 0 0 1 .5.5v5h5a.5.5 0 0 1 0 1h-5v5a.5.5 0 0 1-1 0v-5h-5a.5.5 0 0 1 0-1h5v-5A.5.5 0 0 1 8 2Z" />
                    </svg>
                    Create New Agent
                  </button>
                )}
                {onManageAgents && (
                  <button
                    className="dropdown-menu-item"
                    onClick={() => {
                      setShowMenu(false);
                      onManageAgents();
                    }}
                  >
                    <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor">
                      <path d="M8 4.754a3.246 3.246 0 1 0 0 6.492 3.246 3.246 0 0 0 0-6.492zM5.754 8a2.246 2.246 0 1 1 4.492 0 2.246 2.246 0 0 1-4.492 0z" />
                      <path d="M9.796 1.343c-.527-1.79-3.065-1.79-3.592 0l-.094.319a.873.873 0 0 1-1.255.52l-.292-.16c-1.64-.892-3.433.902-2.54 2.541l.159.292a.873.873 0 0 1-.52 1.255l-.319.094c-1.79.527-1.79 3.065 0 3.592l.319.094a.873.873 0 0 1 .52 1.255l-.16.292c-.892 1.64.901 3.434 2.541 2.54l.292-.159a.873.873 0 0 1 1.255.52l.094.319c.527 1.79 3.065 1.79 3.592 0l.094-.319a.873.873 0 0 1 1.255-.52l.292.16c1.64.893 3.434-.902 2.54-2.541l-.159-.292a.873.873 0 0 1 .52-1.255l.319-.094c1.79-.527 1.79-3.065 0-3.592l-.319-.094a.873.873 0 0 1-.52-1.255l.16-.292c.893-1.64-.902-3.433-2.541-2.54l-.292.159a.873.873 0 0 1-1.255-.52l-.094-.319zm-2.633.283c.246-.835 1.428-.835 1.674 0l.094.319a1.873 1.873 0 0 0 2.693 1.115l.291-.16c.764-.415 1.6.42 1.184 1.185l-.159.292a1.873 1.873 0 0 0 1.116 2.692l.318.094c.835.246.835 1.428 0 1.674l-.319.094a1.873 1.873 0 0 0-1.115 2.693l.16.291c.415.764-.42 1.6-1.185 1.184l-.291-.159a1.873 1.873 0 0 0-2.693 1.116l-.094.318c-.246.835-1.428.835-1.674 0l-.094-.319a1.873 1.873 0 0 0-2.692-1.115l-.292.16c-.764.415-1.6-.42-1.184-1.185l.159-.291A1.873 1.873 0 0 0 1.945 8.93l-.319-.094c-.835-.246-.835-1.428 0-1.674l.319-.094A1.873 1.873 0 0 0 3.06 4.377l-.16-.292c-.415-.764.42-1.6 1.185-1.184l.292.159a1.873 1.873 0 0 0 2.692-1.115l.094-.319z" />
                    </svg>
                    Manage Agents
                  </button>
                )}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* List of attached agents */}
      {attachments.length === 0 ? (
        <div className="no-attachments">No agents attached yet</div>
      ) : (
        <div className="attachments-list">
          {attachments.map(attachment => (
            <div key={attachment.id} className="attachment-item">
              <div className="attachment-info">
                <div className="attachment-name">{attachment.attached_agent_name}</div>
                <div className="attachment-type-badge">{attachment.attachment_type}</div>
              </div>
              <div className="attachment-actions">
                <button
                  className="toggle-enabled-button"
                  onClick={() => handleToggleEnabled(attachment)}
                  title={attachment.enabled ? 'Disable' : 'Enable'}
                >
                  {attachment.enabled ? (
                    <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor">
                      <path d="M16 8A8 8 0 1 1 0 8a8 8 0 0 1 16 0zM5.496 6.033h.825c.138 0 .248-.113.266-.25.09-.656.54-1.134 1.342-1.134.686 0 1.314.343 1.314 1.168 0 .635-.374.927-.965 1.371-.673.489-1.206 1.06-1.168 1.987l.003.217a.25.25 0 0 0 .25.246h.811a.25.25 0 0 0 .25-.25v-.105c0-.718.273-.927 1.01-1.486.609-.463 1.244-.977 1.244-2.056 0-1.511-1.276-2.241-2.673-2.241-1.267 0-2.655.59-2.75 2.286a.237.237 0 0 0 .241.247zm2.325 6.443c.61 0 1.029-.394 1.029-.927 0-.552-.42-.94-1.029-.94-.584 0-1.009.388-1.009.94 0 .533.425.927 1.01.927z" />
                    </svg>
                  ) : (
                    <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor">
                      <path d="M8 15A7 7 0 1 1 8 1a7 7 0 0 1 0 14zm0 1A8 8 0 1 0 8 0a8 8 0 0 0 0 16z" />
                    </svg>
                  )}
                </button>
                <button
                  className="detach-button"
                  onClick={() => handleDetach(attachment.id)}
                  title="Detach agent"
                >
                  ×
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

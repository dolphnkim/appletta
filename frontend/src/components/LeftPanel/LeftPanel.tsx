import { useState } from 'react';
import AgentSettings from '../AgentSettings/AgentSettings';
import ConversationsList from './ConversationsList';
import ToolsPanel from './ToolsPanel';
import './LeftPanel.css';

interface LeftPanelProps {
  agentId: string;
  currentConversationId?: string;
  onConversationSelect?: (conversationId: string) => void;
  onNewConversation?: () => void;
  onDelete?: () => void;
  onClone?: (newAgentId: string) => void;
}

type TabType = 'conversations' | 'settings' | 'tools';

export default function LeftPanel({
  agentId,
  currentConversationId,
  onConversationSelect,
  onNewConversation,
  onDelete,
  onClone,
}: LeftPanelProps) {
  const [activeTab, setActiveTab] = useState<TabType>('conversations');

  return (
    <div className="left-panel">
      <div className="left-panel-header">
        <div className="left-panel-tabs">
          <button
            className={`tab-button ${activeTab === 'conversations' ? 'active' : ''}`}
            onClick={() => setActiveTab('conversations')}
          >
            Conversations
          </button>
          <button
            className={`tab-button ${activeTab === 'settings' ? 'active' : ''}`}
            onClick={() => setActiveTab('settings')}
          >
            Agent Settings
          </button>
          <button
            className={`tab-button ${activeTab === 'tools' ? 'active' : ''}`}
            onClick={() => setActiveTab('tools')}
          >
            Tools
          </button>
        </div>
      </div>

      <div className="left-panel-content">
        {activeTab === 'conversations' && (
          <ConversationsList
            agentId={agentId}
            currentConversationId={currentConversationId}
            onSelect={onConversationSelect}
            onNew={onNewConversation}
          />
        )}
        {activeTab === 'settings' && (
          <AgentSettings agentId={agentId} onDelete={onDelete} onClone={onClone} />
        )}
        {activeTab === 'tools' && <ToolsPanel agentId={agentId} />}
      </div>
    </div>
  );
}

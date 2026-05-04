import { useState } from 'react';
import RagFilesystem from './RagFilesystem';
import JournalBlocks from './JournalBlocks';
import WorkshopPanel from './WorkshopPanel';
import './DatabasePanel.css';

interface DatabasePanelProps {
  agentId: string;
  conversationId?: string;
  onConversationChange?: (conversationId: string) => void;
}

type TabType = 'filesystem' | 'journals' | 'workshop';

export default function DatabasePanel({ agentId, conversationId, onConversationChange }: DatabasePanelProps) {
  const [activeTab, setActiveTab] = useState<TabType>('filesystem');

  return (
    <div className="database-panel">
      <div className="database-panel-header">
        <div className="database-panel-label">DATABASE</div>
        <div className="database-panel-tabs">
          <button
            className={`tab-button ${activeTab === 'filesystem' ? 'active' : ''}`}
            onClick={() => setActiveTab('filesystem')}
          >
            Filesystem
          </button>
          <button
            className={`tab-button ${activeTab === 'journals' ? 'active' : ''}`}
            onClick={() => setActiveTab('journals')}
          >
            Journals
          </button>
          <button
            className={`tab-button ${activeTab === 'workshop' ? 'active' : ''}`}
            onClick={() => setActiveTab('workshop')}
          >
            Workshop
          </button>
        </div>
      </div>

      <div className="database-panel-content">
        {activeTab === 'filesystem' && <RagFilesystem agentId={agentId} />}
        {activeTab === 'journals' && <JournalBlocks agentId={agentId} />}
        {activeTab === 'workshop' && (
          <WorkshopPanel
            agentId={agentId}
            conversationId={conversationId}
            onConversationChange={onConversationChange}
          />
        )}
      </div>
    </div>
  );
}

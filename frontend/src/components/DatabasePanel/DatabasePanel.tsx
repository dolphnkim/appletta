import { useState } from 'react';
import RagFilesystem from './RagFilesystem';
import JournalBlocks from './JournalBlocks';
import BackendTerminal from './BackendTerminal';
import './DatabasePanel.css';

interface DatabasePanelProps {
  agentId: string;
}

type TabType = 'filesystem' | 'journals' | 'terminal';

export default function DatabasePanel({ agentId }: DatabasePanelProps) {
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
            className={`tab-button ${activeTab === 'terminal' ? 'active' : ''}`}
            onClick={() => setActiveTab('terminal')}
          >
            Terminal
          </button>
        </div>
      </div>

      <div className={`database-panel-content${activeTab === 'terminal' ? ' no-padding' : ''}`}>
        {activeTab === 'filesystem' && <RagFilesystem agentId={agentId} />}
        {activeTab === 'journals' && <JournalBlocks agentId={agentId} />}
        {activeTab === 'terminal' && <BackendTerminal />}
      </div>
    </div>
  );
}

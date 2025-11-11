import { useState } from 'react';
import RagFilesystem from './RagFilesystem';
import Search from './Search';
import './DatabasePanel.css';

interface DatabasePanelProps {
  agentId: string;
}

type TabType = 'filesystem' | 'search' | 'journals';

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
            className={`tab-button ${activeTab === 'search' ? 'active' : ''}`}
            onClick={() => setActiveTab('search')}
          >
            Search
          </button>
          <button
            className={`tab-button ${activeTab === 'journals' ? 'active' : ''}`}
            onClick={() => setActiveTab('journals')}
            disabled
          >
            Journals
          </button>
        </div>
      </div>

      <div className="database-panel-content">
        {activeTab === 'filesystem' && <RagFilesystem agentId={agentId} />}
        {activeTab === 'search' && <Search agentId={agentId} />}
        {activeTab === 'journals' && <div className="coming-soon">Coming soon...</div>}
      </div>
    </div>
  );
}
